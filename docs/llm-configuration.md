# TRACE LLM Configuration & Model Policy

## 1. Free-First Model Policy (Constitution §VI)

TRACE enforces a strict **free-first model policy**:
1. Default configuration MUST use freely accessible open-weight models that require no paid billing accounts or credit cards.
2. The canonical default model is:
   ```
   mistralai/mistral-7b-instruct:free
   ```
3. Paid models are **never** selected automatically. If a free-tier model encounters errors, TRACE returns a `ProviderError` rather than automatically escalating to a paid tier.

---

## 2. Model Roles and Environment Variable Overrides

TRACE defines four distinct model roles, configurable entirely via environment variables without requiring code changes:

| Variable | Role / Purpose | Default / Behavior |
|---|---|---|
| `LLM_DEFAULT_MODEL` | Default model for general completions | `mistralai/mistral-7b-instruct:free` (overridden dynamically by env var) |
| `LLM_REASONING_MODEL` | Heavy reasoning, complex planning | Unset (`None`) unless explicitly configured |
| `LLM_FAST_MODEL` | Low-latency, fast classification tasks | Unset (`None`) unless explicitly configured |
| `LLM_FALLBACK_MODELS` | Ordered list of fallback models | Empty list (`[]`); parsed from comma-separated string |

---

## 3. Security and Transmission Gates

### `LLM_ENABLE_EXTERNAL_CALLS` (Default: `false`)
- Master circuit breaker.
- When `false`, the LLM adapter immediately returns `ConfigurationError` without initiating any HTTP request.
- Prevents unexpected outbound network traffic in offline or air-gapped environments.

### `LLM_ENABLE_EXTERNAL_TRANSMISSION` (Default: `false`)
- Source-code confidentiality gate (Constitution §X, FR-045).
- By default, TRACE strictly forbids transmitting repository code or file content to external LLMs.
- If a prompt contains source code patterns while transmission is disabled:
  1. The adapter intercepts the payload before it reaches the HTTP client.
  2. Emits a `WARNING` log event containing provider name and byte size (never prompt text).
  3. Returns `ConfigurationError(message="External source code transmission is disabled")`.

---

## 4. Switching Models

To switch models, update `.env` without modifying any Python code:
```ini
# Switch to another free model
LLM_DEFAULT_MODEL=meta-llama/llama-3-8b-instruct:free
LLM_FAST_MODEL=google/gemma-2-9b-it:free
```

---

## 5. Adding a New LLM Provider

To integrate a new LLM provider (e.g. Ollama, Anthropic, vLLM):
1. **Implement Interface**: Create `backend/src/trace/infrastructure/llm/adapters/<provider>.py` implementing the `LLMProvider` Protocol (`complete`, `embed`).
2. **Wire in Lifespan**: In `backend/src/trace/main.py`, instantiate the new adapter during the `@asynccontextmanager` startup lifespan and assign it to `app.state.llm`.
3. **Zero Caller Changes**: Because domain, services, and API interact only with the `LLMProvider` Protocol, zero application or API code needs to change.
