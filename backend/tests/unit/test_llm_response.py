"""Unit tests for LLM response discriminated union and LLMProvider Protocol."""

from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.provider import LLMProvider
from trace.infrastructure.llm.response import (
    ConfigurationError,
    LLMResponse,
    ProviderError,
    Success,
    TimeoutError,
    TokenUsage,
)


class ConformingLLMStub:
    """Stub implementation conforming structurally to LLMProvider Protocol."""

    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        return Success(
            content="stub completion",
            model="test-model",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=10),
        )

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        return Success(
            content="[0.1, 0.2, 0.3]",
            model="test-model",
            usage=TokenUsage(prompt_tokens=3, completion_tokens=0),
        )


class NonConformingStub:
    """Class missing required methods of LLMProvider Protocol."""

    def other_method(self) -> None:
        pass


def test_llm_response_kind_literals() -> None:
    """Verify each LLMResponse dataclass has the correct kind discriminator."""
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
    success = Success(content="hello", model="test", usage=usage)
    assert success.kind == "success"
    assert success.content == "hello"
    assert success.model == "test"
    assert success.usage.prompt_tokens == 10
    assert success.usage.completion_tokens == 20

    cfg_err = ConfigurationError(message="bad config")
    assert cfg_err.kind == "configuration_error"
    assert cfg_err.message == "bad config"

    prov_err = ProviderError(status_code=502, message="bad gateway")
    assert prov_err.kind == "provider_error"
    assert prov_err.status_code == 502
    assert prov_err.message == "bad gateway"

    time_err = TimeoutError(timeout_seconds=30.0)
    assert time_err.kind == "timeout_error"
    assert time_err.timeout_seconds == 30.0


def test_llm_response_exhaustive_pattern_matching() -> None:
    """Verify pattern matching exhaustively narrows all 4 union types."""

    def handle_response(response: LLMResponse) -> str:
        match response:
            case Success(content=content):
                return f"success: {content}"
            case ConfigurationError(message=msg):
                return f"config_error: {msg}"
            case ProviderError(status_code=code):
                return f"provider_error: {code}"
            case TimeoutError(timeout_seconds=sec):
                return f"timeout: {sec}"

    usage = TokenUsage(prompt_tokens=1, completion_tokens=1)
    assert handle_response(Success(content="ok", model="m", usage=usage)) == "success: ok"
    assert handle_response(ConfigurationError(message="err")) == "config_error: err"
    assert handle_response(ProviderError(status_code=500, message="e")) == "provider_error: 500"
    assert handle_response(TimeoutError(timeout_seconds=15.0)) == "timeout: 15.0"


def test_llm_provider_runtime_checkable() -> None:
    """Verify runtime_checkable protocol recognizes conforming and non-conforming classes."""
    stub = ConformingLLMStub()
    assert isinstance(stub, LLMProvider)

    non_conforming = NonConformingStub()
    assert not isinstance(non_conforming, LLMProvider)
