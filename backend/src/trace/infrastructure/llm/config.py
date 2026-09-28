"""LLM connection and model configuration dataclasses."""

import os
from dataclasses import dataclass, field

DEFAULT_FREE_MODEL = "mistralai/mistral-7b-instruct:free"


def get_default_model() -> str:
    """Resolve the default model from environment variable LLM_DEFAULT_MODEL with fallback."""
    env_val = os.getenv("LLM_DEFAULT_MODEL")
    if env_val is not None and env_val.strip():
        return env_val.strip()
    return DEFAULT_FREE_MODEL


@dataclass(frozen=True)
class LLMConfig:
    """Connection configuration for an LLM provider."""

    base_url: str = ""
    api_key_env_name: str = "OPENROUTER_API_KEY"
    timeout_seconds: float = 30.0
    max_retries: int = 3


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for model selection, roles, and fallback chains."""

    default: str = field(default_factory=get_default_model)
    reasoning: str | None = None
    fast: str | None = None
    fallback: list[str] = field(default_factory=list)
