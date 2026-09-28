"""Unit tests for LLMProvider protocol and stub implementations."""

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

import pytest


class StubLLMProvider:
    """Configurable stub implementing LLMProvider Protocol without inheriting from it."""

    def __init__(self, target_response: LLMResponse | None = None) -> None:
        self.target_response: LLMResponse = target_response or Success(
            content="stub output",
            model="test-stub",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        )

    def set_response(self, response: LLMResponse) -> None:
        """Configure the response that complete and embed will return."""
        self.target_response = response

    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Return configured response without making network calls."""
        return self.target_response

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Return configured response without making network calls."""
        return self.target_response


@pytest.fixture
def stub_llm_provider() -> StubLLMProvider:
    """Fixture providing a configurable StubLLMProvider."""
    return StubLLMProvider()


def test_stub_llm_provider_protocol_conformance(stub_llm_provider: StubLLMProvider) -> None:
    """Verify StubLLMProvider conforms to LLMProvider protocol via runtime_checkable."""
    assert isinstance(stub_llm_provider, LLMProvider)


@pytest.mark.asyncio
async def test_stub_returns_all_four_states(stub_llm_provider: StubLLMProvider) -> None:
    """Verify caller receives all 4 LLMResponse states without raising exceptions."""
    model = ModelConfig()
    config = LLMConfig()

    # 1. Success
    success_resp = Success(
        content="generated code",
        model="test-free",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=25),
    )
    stub_llm_provider.set_response(success_resp)
    res = await stub_llm_provider.complete("prompt", model, config)
    assert res.kind == "success"
    assert isinstance(res, Success)
    assert res.content == "generated code"

    # 2. ConfigurationError
    cfg_resp = ConfigurationError(message="External transmission disabled")
    stub_llm_provider.set_response(cfg_resp)
    res = await stub_llm_provider.complete("prompt", model, config)
    assert res.kind == "configuration_error"
    assert isinstance(res, ConfigurationError)
    assert res.message == "External transmission disabled"

    # 3. ProviderError
    prov_resp = ProviderError(status_code=503, message="Service Unavailable")
    stub_llm_provider.set_response(prov_resp)
    res = await stub_llm_provider.complete("prompt", model, config)
    assert res.kind == "provider_error"
    assert isinstance(res, ProviderError)
    assert res.status_code == 503

    # 4. TimeoutError
    timeout_resp = TimeoutError(timeout_seconds=30.0)
    stub_llm_provider.set_response(timeout_resp)
    res = await stub_llm_provider.complete("prompt", model, config)
    assert res.kind == "timeout_error"
    assert isinstance(res, TimeoutError)
    assert res.timeout_seconds == 30.0
