"""Unit tests verifying source code transmission gate on LLM adapters."""

from trace.core.config import ApplicationConfig
from trace.core.logging import configure_logging
from trace.infrastructure.llm.adapters.openrouter import OpenRouterAdapter
from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.response import ConfigurationError
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.mark.asyncio
async def test_transmission_gate_blocks_source_code_and_logs_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When LLM_ENABLE_EXTERNAL_TRANSMISSION is False, prompt with code is blocked."""
    configure_logging(app_env="test", log_level="INFO")

    stub_config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        openrouter_api_key="test-key",
        llm_enable_external_calls=True,
        llm_enable_external_transmission=False,
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    adapter = OpenRouterAdapter(config=stub_config, http_client=mock_client)

    prompt_code = "def main(): pass"
    model_config = ModelConfig()
    llm_config = LLMConfig()

    result = await adapter.complete(prompt=prompt_code, model=model_config, config=llm_config)

    # 1. Assert return value is ConfigurationError
    assert isinstance(result, ConfigurationError)
    assert result.kind == "configuration_error"

    # 2. Assert mock httpx client was never called
    assert mock_client.post.call_count == 0
    assert mock_client.send.call_count == 0

    # 3. Assert WARNING log event contains "provider" and "content_bytes", but NOT prompt content
    captured = capsys.readouterr()
    log_output = captured.out

    assert '"provider": "openrouter"' in log_output
    assert '"content_bytes": ' in log_output
    assert prompt_code not in log_output
