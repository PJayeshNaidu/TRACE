"""Unit tests for LLM configuration dataclasses and model resolution."""

from trace.infrastructure.llm.config import (
    DEFAULT_FREE_MODEL,
    LLMConfig,
    ModelConfig,
    get_default_model,
)

import pytest


def test_model_config_default_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LLM_DEFAULT_MODEL is unset, default must be the safe free model."""
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    assert get_default_model() == DEFAULT_FREE_MODEL
    cfg = ModelConfig()
    assert cfg.default == DEFAULT_FREE_MODEL
    assert "free" in cfg.default


def test_model_config_empty_string_uses_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LLM_DEFAULT_MODEL is an empty string, fallback default is used."""
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "   ")
    assert get_default_model() == DEFAULT_FREE_MODEL
    cfg = ModelConfig()
    assert cfg.default == DEFAULT_FREE_MODEL


def test_model_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting LLM_DEFAULT_MODEL overrides ModelConfig.default dynamically."""
    override_model = "meta-llama/llama-3-8b-instruct:free"
    monkeypatch.setenv("LLM_DEFAULT_MODEL", override_model)
    assert get_default_model() == override_model
    cfg = ModelConfig()
    assert cfg.default == override_model


def test_model_config_explicit_parameter_override() -> None:
    """Explicitly passing default parameter overrides both env and fallback."""
    cfg = ModelConfig(default="custom/model-id")
    assert cfg.default == "custom/model-id"


def test_no_paid_models_in_defaults() -> None:
    """Verify default configurations never reference paid models."""
    cfg = ModelConfig()
    assert cfg.default == DEFAULT_FREE_MODEL
    assert ":free" in cfg.default
    assert cfg.reasoning is None
    assert cfg.fast is None
    assert cfg.fallback == []


def test_llm_config_defaults() -> None:
    """Verify LLMConfig default values and structure."""
    cfg = LLMConfig()
    assert cfg.base_url == ""
    assert cfg.api_key_env_name == "OPENROUTER_API_KEY"
    assert cfg.timeout_seconds == 30.0
    assert cfg.max_retries == 3
