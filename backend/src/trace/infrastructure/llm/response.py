"""LLM response structures and discriminated union states."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TokenUsage:
    """Token consumption statistics for an LLM response."""

    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Success:
    """Represents a successful LLM invocation with output content."""

    content: str
    model: str
    usage: TokenUsage
    kind: Literal["success"] = "success"


@dataclass(frozen=True)
class ConfigurationError:
    """Represents a configuration error such as missing credentials or disabled calls."""

    message: str
    kind: Literal["configuration_error"] = "configuration_error"


@dataclass(frozen=True)
class ProviderError:
    """Represents an error returned by the upstream LLM provider API."""

    status_code: int
    message: str
    kind: Literal["provider_error"] = "provider_error"


@dataclass(frozen=True)
class TimeoutError:
    """Represents a request timeout when contacting the LLM provider."""

    timeout_seconds: float
    kind: Literal["timeout_error"] = "timeout_error"


type LLMResponse = Success | ConfigurationError | ProviderError | TimeoutError
