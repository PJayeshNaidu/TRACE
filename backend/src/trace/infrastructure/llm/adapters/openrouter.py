"""OpenRouter LLM provider adapter using httpx and tenacity."""

from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.response import (
    ConfigurationError,
    LLMResponse,
    ProviderError,
    Success,
    TimeoutError,
    TokenUsage,
)
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

if TYPE_CHECKING:
    from trace.core.config import ApplicationConfig

logger = structlog.get_logger(__name__)

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

_CODE_PATTERNS = (
    "def ",
    "class ",
    "import ",
    "from ",
    "return ",
    "function ",
    "const ",
    "let ",
    "var ",
    "public ",
    "private ",
    "protected ",
    "void ",
    "#include",
    "package ",
    "fn ",
    "impl ",
    "```",
)


def _contains_source_code(text: str) -> bool:
    """Check whether text appears to contain source code or code snippets."""
    return any(p in text for p in _CODE_PATTERNS)


class _TransientProviderError(Exception):
    """Internal exception raised to trigger tenacity retries on 429 and 5xx."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OpenRouterAdapter:
    """LLMProvider implementation connecting to OpenRouter via httpx."""

    def __init__(self, config: "ApplicationConfig", http_client: httpx.AsyncClient) -> None:
        """Initialize adapter with application configuration and HTTP client.

        Args:
            config: Application configuration injected at startup.
            http_client: Reusable async HTTP client instance.
        """
        self._config = config
        self._client = http_client

    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a completion prompt to OpenRouter and return structured response.

        Args:
            prompt: Text prompt to complete.
            model: Model selection and fallback configuration.
            config: Connection and retry settings.

        Returns:
            LLMResponse indicating Success or an error state.
        """
        try:
            if not self._config.llm_enable_external_transmission and _contains_source_code(prompt):
                logger.warning(
                    "External transmission disabled: blocked request containing source code",
                    provider="openrouter",
                    content_bytes=len(prompt.encode("utf-8")),
                )
                return ConfigurationError(message="External source code transmission is disabled")

            if not self._config.llm_enable_external_calls:
                return ConfigurationError(
                    message="External LLM calls are disabled (LLM_ENABLE_EXTERNAL_CALLS=false)"
                )

            api_key = (
                self._config.openrouter_api_key.get_secret_value()
                if self._config.openrouter_api_key
                else ""
            )
            if not api_key:
                return ConfigurationError(message="OpenRouter API key is not configured")

            base_url = (
                str(self._config.openrouter_base_url)
                if self._config.openrouter_base_url
                else (config.base_url or OPENROUTER_DEFAULT_BASE_URL)
            ).rstrip("/")

            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model.default,
                "messages": [{"role": "user", "content": prompt}],
            }

            max_retries = max(1, config.max_retries)

            async def _execute_request() -> httpx.Response:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max_retries),
                    wait=wait_exponential_jitter(initial=0.5, max=5.0),
                    retry=retry_if_exception_type(_TransientProviderError),
                    reraise=True,
                ):
                    with attempt:
                        resp = await self._client.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=config.timeout_seconds,
                        )
                        if resp.status_code in (429, 500, 502, 503, 504):
                            raise _TransientProviderError(
                                status_code=resp.status_code,
                                message=resp.text,
                            )
                        return resp
                raise _TransientProviderError(500, "Retry loop exhausted")

            response = await _execute_request()

            if response.status_code in (401, 403):
                return ConfigurationError(
                    message=f"OpenRouter authentication failed: HTTP {response.status_code}"
                )

            if response.status_code != 200:
                return ProviderError(
                    status_code=response.status_code,
                    message=response.text,
                )

            data: dict[str, Any] = response.json()
            choices = data.get("choices", [])
            content = choices[0]["message"]["content"] if choices else ""
            model_used = str(data.get("model", model.default))
            usage_data = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                completion_tokens=int(usage_data.get("completion_tokens", 0)),
            )
            return Success(content=content, model=model_used, usage=usage)

        except _TransientProviderError as exc:
            return ProviderError(status_code=exc.status_code, message=exc.message)
        except httpx.TimeoutException:
            return TimeoutError(timeout_seconds=config.timeout_seconds)
        except Exception as exc:
            return ProviderError(status_code=500, message=str(exc))

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Generate embeddings via OpenRouter embeddings API.

        Args:
            text: Text to generate vector embeddings for.
            model: Model selection configuration.
            config: Connection and retry settings.

        Returns:
            LLMResponse indicating Success or an error state.
        """
        try:
            if not self._config.llm_enable_external_transmission and _contains_source_code(text):
                logger.warning(
                    "External transmission disabled: blocked request containing source code",
                    provider="openrouter",
                    content_bytes=len(text.encode("utf-8")),
                )
                return ConfigurationError(message="External source code transmission is disabled")

            if not self._config.llm_enable_external_calls:
                return ConfigurationError(
                    message="External LLM calls are disabled (LLM_ENABLE_EXTERNAL_CALLS=false)"
                )

            api_key = (
                self._config.openrouter_api_key.get_secret_value()
                if self._config.openrouter_api_key
                else ""
            )
            if not api_key:
                return ConfigurationError(message="OpenRouter API key is not configured")

            base_url = (
                str(self._config.openrouter_base_url)
                if self._config.openrouter_base_url
                else (config.base_url or OPENROUTER_DEFAULT_BASE_URL)
            ).rstrip("/")

            url = f"{base_url}/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model.default,
                "input": text,
            }

            max_retries = max(1, config.max_retries)

            async def _execute_request() -> httpx.Response:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max_retries),
                    wait=wait_exponential_jitter(initial=0.5, max=5.0),
                    retry=retry_if_exception_type(_TransientProviderError),
                    reraise=True,
                ):
                    with attempt:
                        resp = await self._client.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=config.timeout_seconds,
                        )
                        if resp.status_code in (429, 500, 502, 503, 504):
                            raise _TransientProviderError(
                                status_code=resp.status_code,
                                message=resp.text,
                            )
                        return resp
                raise _TransientProviderError(500, "Retry loop exhausted")

            response = await _execute_request()

            if response.status_code in (401, 403):
                return ConfigurationError(
                    message=f"OpenRouter authentication failed: HTTP {response.status_code}"
                )

            if response.status_code != 200:
                return ProviderError(
                    status_code=response.status_code,
                    message=response.text,
                )

            import json

            data = response.json()
            embedding_data = json.dumps(data.get("data", []))
            model_used = str(data.get("model", model.default))
            usage_data = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                completion_tokens=int(usage_data.get("completion_tokens", 0)),
            )
            return Success(content=embedding_data, model=model_used, usage=usage)

        except _TransientProviderError as exc:
            return ProviderError(status_code=exc.status_code, message=exc.message)
        except httpx.TimeoutException:
            return TimeoutError(timeout_seconds=config.timeout_seconds)
        except Exception as exc:
            return ProviderError(status_code=500, message=str(exc))
