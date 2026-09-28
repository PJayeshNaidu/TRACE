"""Unit tests for OpenRouterAdapter complete and embed operations."""

from trace.core.config import ApplicationConfig
from trace.core.logging import configure_logging
from trace.infrastructure.llm.adapters.openrouter import OpenRouterAdapter
from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.response import (
    ConfigurationError,
    ProviderError,
    Success,
    TimeoutError,
)
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.fixture(autouse=True)
def setup_logging() -> None:
    configure_logging(app_env="test", log_level="INFO")


def _make_config(
    enable_calls: bool = True,
    enable_transmission: bool = True,
    api_key: str | None = "test-api-key",
) -> ApplicationConfig:
    return ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        openrouter_api_key=api_key,
        llm_enable_external_calls=enable_calls,
        llm_enable_external_transmission=enable_transmission,
    )


@pytest.mark.asyncio
async def test_complete_calls_disabled_returns_configuration_error() -> None:
    """When llm_enable_external_calls=False, complete returns ConfigurationError."""
    cfg = _make_config(enable_calls=False)
    client = AsyncMock(spec=httpx.AsyncClient)
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)
    assert "disabled" in res.message


@pytest.mark.asyncio
async def test_complete_missing_api_key_returns_configuration_error() -> None:
    """When API key is absent, complete returns ConfigurationError."""
    cfg = _make_config(enable_calls=True, api_key="dummy")
    cfg.openrouter_api_key = None
    client = AsyncMock(spec=httpx.AsyncClient)
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)
    assert "not configured" in res.message


@pytest.mark.asyncio
async def test_complete_http_200_returns_success() -> None:
    """When provider returns HTTP 200, complete parses response and returns Success."""
    cfg = _make_config()
    client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(
        status_code=200,
        json={
            "id": "gen-1",
            "model": "mistralai/mistral-7b-instruct:free",
            "choices": [{"message": {"content": "Hello world!"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 12},
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    client.post.return_value = mock_resp
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig())
    assert isinstance(res, Success)
    assert res.content == "Hello world!"
    assert res.usage.prompt_tokens == 5
    assert res.usage.completion_tokens == 12


@pytest.mark.asyncio
async def test_complete_http_401_returns_configuration_error() -> None:
    """When provider returns HTTP 401, complete returns ConfigurationError."""
    cfg = _make_config()
    client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(
        status_code=401,
        text="Invalid API Key",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    client.post.return_value = mock_resp
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)
    assert "401" in res.message


@pytest.mark.asyncio
async def test_complete_http_500_retries_and_returns_provider_error() -> None:
    """When provider returns HTTP 500, tenacity retries and returns ProviderError."""
    cfg = _make_config()
    client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    client.post.return_value = mock_resp
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig(max_retries=1))
    assert isinstance(res, ProviderError)
    assert res.status_code == 500


@pytest.mark.asyncio
async def test_complete_timeout_returns_timeout_error() -> None:
    """When request times out, complete returns TimeoutError."""
    cfg = _make_config()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.TimeoutException("Timeout")
    adapter = OpenRouterAdapter(config=cfg, http_client=client)

    res = await adapter.complete("hello", ModelConfig(), LLMConfig())
    assert isinstance(res, TimeoutError)


@pytest.mark.asyncio
async def test_embed_operations_and_error_handling() -> None:
    """Test embed success, validation, and error branches."""
    # 1. Transmission gate blocked
    cfg_no_trans = _make_config(enable_transmission=False)
    client = AsyncMock(spec=httpx.AsyncClient)
    adapter = OpenRouterAdapter(config=cfg_no_trans, http_client=client)
    res = await adapter.embed("def foo(): pass", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)

    # 2. Calls disabled
    cfg_no_calls = _make_config(enable_calls=False)
    adapter = OpenRouterAdapter(config=cfg_no_calls, http_client=client)
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)

    # 3. Missing API key
    cfg_no_key = _make_config(enable_calls=True, api_key="dummy")
    cfg_no_key.openrouter_api_key = None
    adapter = OpenRouterAdapter(config=cfg_no_key, http_client=client)
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)

    # 4. Success HTTP 200
    cfg_ok = _make_config()
    mock_resp = httpx.Response(
        status_code=200,
        json={
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "model": "text-embedding",
            "usage": {"prompt_tokens": 3, "completion_tokens": 0},
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings"),
    )
    client.post.return_value = mock_resp
    adapter = OpenRouterAdapter(config=cfg_ok, http_client=client)
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig())
    assert isinstance(res, Success)
    assert "[0.1, 0.2, 0.3]" in res.content

    # 5. HTTP 403
    mock_403 = httpx.Response(
        status_code=403,
        text="Forbidden",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings"),
    )
    client.post.return_value = mock_403
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig())
    assert isinstance(res, ConfigurationError)

    # 6. HTTP 500
    mock_500 = httpx.Response(
        status_code=500,
        text="Upstream Error",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings"),
    )
    client.post.return_value = mock_500
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig(max_retries=1))
    assert isinstance(res, ProviderError)

    # 7. Timeout
    client.post.side_effect = httpx.TimeoutException("Timeout")
    res = await adapter.embed("plain text", ModelConfig(), LLMConfig())
    assert isinstance(res, TimeoutError)
