# Contract: LLMProvider Interface — Phase 0

**Version**: 0.1.0 | **Phase**: 0 | **Date**: 2026-09-25

This document defines the `LLMProvider` interface contract that all LLM provider
implementations MUST satisfy. Business logic and agent code interact only with this
interface — never with any concrete adapter (Constitution §V, §VIII).

---

## Interface Definition

**Module**: `trace/infrastructure/llm/provider.py`

**Mechanism**: Python `Protocol` (structural subtyping, PEP 544)

```python
from typing import Protocol, runtime_checkable
from trace.infrastructure.llm.response import LLMResponse
from trace.infrastructure.llm.config import LLMConfig, ModelConfig

@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse: ...

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse: ...
```

---

## Operation Contracts

### `complete(prompt, model, config) → LLMResponse`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `prompt` | `str` | Yes | The text prompt to send to the LLM |
| `model` | `ModelConfig` | Yes | Model role and fallback configuration |
| `config` | `LLMConfig` | Yes | Provider connection configuration |

**Guarantees**:
1. MUST return an `LLMResponse` — it MUST NOT raise any exception to the caller.
2. MUST NOT make any network call if `ApplicationConfig.llm_enable_external_calls` is `False`.
3. MUST NOT include source-code content in any outbound request if `ApplicationConfig.llm_enable_external_transmission` is `False`.
4. MUST NOT select a paid model unless it is explicitly configured in `ModelConfig.default` or fallback list.
5. If all models fail, MUST return `ProviderError`, not fall back to any unconfigured model.

---

### `embed(text, model, config) → LLMResponse`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `text` | `str` | Yes | The text to embed |
| `model` | `ModelConfig` | Yes | Model role configuration |
| `config` | `LLMConfig` | Yes | Provider connection configuration |

**Guarantees**: Same as `complete()` above. Returns `LLMResponse.Success` with `content`
containing the embedding vector serialised as JSON, or an error state.

---

## `LLMResponse` Union

**Module**: `trace/infrastructure/llm/response.py`

All four states are frozen dataclasses with a `kind` discriminant field:

| `kind` | Type | When returned |
|---|---|---|
| `"success"` | `Success` | Provider returned a valid response |
| `"configuration_error"` | `ConfigurationError` | Provider not configured, key missing, or transmission blocked |
| `"provider_error"` | `ProviderError` | Provider returned HTTP 4xx/5xx |
| `"timeout_error"` | `TimeoutError` | Request exceeded configured timeout |

**Callers MUST pattern-match on `kind`**:
```python
match response.kind:
    case "success":
        # use response.content
    case "configuration_error":
        # log and surface to user
    case "provider_error":
        # log with response.status_code
    case "timeout_error":
        # log with response.timeout_seconds
```

---

## `LLMConfig`

**Module**: `trace/infrastructure/llm/config.py`

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | `"https://openrouter.ai/api/v1"` | Provider API base URL |
| `api_key_env_name` | `str` | `"OPENROUTER_API_KEY"` | Name of the env var containing the key |
| `timeout_seconds` | `float` | `30.0` | Per-request timeout |
| `max_retries` | `int` | `3` | Max retries on transient ProviderError |

**Note**: `api_key_env_name` stores the environment variable **name**, not the key value.
The adapter reads the value from `os.environ` at call time. This ensures the key is never
stored in a Python object that could be serialised or logged.

---

## `ModelConfig`

| Field | Type | Default | Description |
|---|---|---|---|
| `default` | `str` | `"mistralai/mistral-7b-instruct:free"` | Default model (MUST be free-tier; overridable by `LLM_DEFAULT_MODEL`) |
| `reasoning` | `str` | (from `LLM_REASONING_MODEL`) | Heavy reasoning tasks |
| `fast` | `str` | (from `LLM_FAST_MODEL`) | Low-latency tasks |
| `fallback` | `list[str]` | `[]` | Ordered fallback models |

**Model Override Rule**: `ModelConfig.default` has a safe application default of `"mistralai/mistral-7b-instruct:free"`. Setting `LLM_DEFAULT_MODEL` in the environment overrides this value without source-code modification, while preserving the application default when the variable is unset.

---

## Known Implementations & Instantiation Boundary

| Implementation | Module | Purpose |
|---|---|---|
| `OpenRouterAdapter` | `trace/infrastructure/llm/adapters/openrouter.py` | Production |
| `StubLLMProvider` | `tests/conftest.py` | Unit test double |

### Adapter Instantiation Boundary (Constitution §V, §VIII, §XIV)

`OpenRouterAdapter` has the constructor signature:
```python
def __init__(self, config: ApplicationConfig, http_client: httpx.AsyncClient) -> None: ...
```

- **Composition Root Only**: `OpenRouterAdapter` MUST be instantiated **only** in the application composition/startup wiring layer (`trace/main.py` lifespan).
- **Dependency Injection**: It receives `ApplicationConfig` directly through its `__init__` constructor and MUST NOT import global application configuration directly.
- **Consumer Isolation**: API, domain, service, and orchestration code MUST depend strictly on the `LLMProvider` abstraction (Protocol) and MUST NOT import `OpenRouterAdapter`, `openrouter.py`, or any vendor SDK.

---

## Prohibited Patterns

- ❌ Business logic, domain, API, or orchestration code importing `openrouter.py` or `OpenRouterAdapter` directly
- ❌ Any module outside `trace/infrastructure/llm/adapters/` containing the string `openrouter.ai`
- ❌ `OpenRouterAdapter` importing global application configuration directly instead of receiving `ApplicationConfig` via `__init__`
- ❌ Instantiating `OpenRouterAdapter` outside the `main.py` lifespan composition layer
- ❌ `LLMProvider.complete()` or `embed()` raising an exception instead of returning `LLMResponse`
- ❌ Automatic model upgrade to a paid model when default fails
- ❌ API key values appearing in any log message or error string

---

## Versioning Policy

- **PATCH**: Documentation improvements; no signature change.
- **MINOR**: New optional parameters with defaults; new `LLMResponse` states (additive).
- **MAJOR**: Signature change to `complete()` or `embed()`; removal of a `LLMResponse` state.

Current version: **0.1.0**
