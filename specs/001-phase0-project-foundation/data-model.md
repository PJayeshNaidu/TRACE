# Data Model: TRACE Phase 0 — Project Foundation

**Branch**: `001-phase0-project-foundation` | **Date**: 2026-09-25

Phase 0 defines no domain database tables. The entities below are the **interface types,
domain value objects, and configuration structures** that constitute the Phase 0 data model.
They are implemented as Python dataclasses, Pydantic models, or enumerations — not as
PostgreSQL tables.

---

## Domain Value Objects (`trace/domain/`)

### `HealthState`

```
HealthState (str Enum)
├── HEALTHY = "healthy"
└── DEGRADED = "degraded"
```

| Field | Type | Rules |
|---|---|---|
| `value` | `Literal["healthy", "degraded"]` | Exactly two states; no nullable state |

**Lifecycle**: Computed per health request; never persisted in Phase 0.

**State transition**:
```
all services {reachable | not_configured} → HEALTHY
any service unreachable → DEGRADED
```

---

### `GraphConnectivityState`

```
GraphConnectivityState (str Enum)
├── NOT_CONFIGURED = "not_configured"   ← NEO4J_URI absent
├── REACHABLE = "reachable"             ← probe succeeded
└── UNREACHABLE = "unreachable"         ← probe failed
```

**Identity rule**: The three states are mutually exclusive. Only one can be active per request.

**Uniqueness**: Not persisted; computed per health check call.

---

## Configuration Entities (`trace/core/`)

### `ApplicationConfig`

```
ApplicationConfig (pydantic BaseSettings)
│
├── Database
│   └── database_url: SecretStr         REQUIRED  postgresql+asyncpg://…
│
├── Graph
│   ├── neo4j_uri: str | None           OPTIONAL  bolt://localhost:7687
│   ├── neo4j_username: str | None      OPTIONAL  neo4j
│   └── neo4j_password: SecretStr | None OPTIONAL <password>
│
├── LLM
│   ├── openrouter_api_key: SecretStr | None  OPTIONAL (required if LLM enabled)
│   ├── openrouter_base_url: str              OPTIONAL  https://openrouter.ai/api/v1
│   ├── llm_default_model: str               DEFAULT   mistralai/mistral-7b-instruct:free
│   ├── llm_reasoning_model: str             OPTIONAL
│   ├── llm_fast_model: str                  OPTIONAL
│   └── llm_fallback_models: list[str]       DEFAULT   []
│
├── LLM Behaviour
│   ├── llm_enable_external_calls: bool      DEFAULT   False
│   └── llm_enable_external_transmission: bool DEFAULT False
│
├── Infrastructure (slots)
│   ├── vector_store_url: str | None         OPTIONAL  (for Phase 4+)
│   └── app_env: Literal["development","production","test"]  DEFAULT "development"
│
└── Observability
    └── log_level: Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"] DEFAULT "INFO"
```

**Validation rules**:
- Empty string (`""`) is treated as `None` for all optional fields; as a validation error
  for required fields. Implemented in `model_validator(mode="before")`.
- `SecretStr` fields are masked in `repr()` and log output.
- If `llm_enable_external_calls=True` but `openrouter_api_key` is absent → `ValidationError`
  at startup (fail-fast; do not start in a broken LLM state).

**Identity**: Singleton — one instance loaded at startup; injected as FastAPI dependency.

---

## LLM Abstraction Entities (`trace/infrastructure/llm/`)

### `LLMConfig`

```
LLMConfig (frozen dataclass)
├── base_url: str                    e.g., "https://openrouter.ai/api/v1"
├── api_key_env_name: str            name of env var, not the value
├── timeout_seconds: float           DEFAULT 30.0
└── max_retries: int                 DEFAULT 3
```

**Note**: `api_key_env_name` stores the *name* of the environment variable, not the key
itself. The adapter reads the actual value from `os.environ` at call time.

---

### `ModelConfig`

```
ModelConfig (frozen dataclass)
├── default: str                     DEFAULT "mistralai/mistral-7b-instruct:free"
├── reasoning: str                   (configured via LLM_REASONING_MODEL)
├── fast: str                        (configured via LLM_FAST_MODEL)
└── fallback: list[str]              (configured via LLM_FALLBACK_MODELS, comma-separated)
```

**Rules**:
- `default` MUST reference a freely available model (`:free` suffix on OpenRouter).
- `default` defaults to `"mistralai/mistral-7b-instruct:free"`, and setting `LLM_DEFAULT_MODEL` in the environment overrides this value without source-code modification while preserving the application default as fallback when unset.
- Paid model selection is never automatic; fallback exhaustion returns `ProviderError`.

---

### `LLMResponse` (discriminated union)

```
LLMResponse = Success | ConfigurationError | ProviderError | TimeoutError

Success (frozen dataclass)
├── kind: Literal["success"] = "success"
├── content: str
├── model: str                       actual model used
└── usage: TokenUsage | None

TokenUsage (frozen dataclass)
├── prompt_tokens: int
└── completion_tokens: int

ConfigurationError (frozen dataclass)
├── kind: Literal["configuration_error"] = "configuration_error"
└── message: str                     human-readable, no secrets

ProviderError (frozen dataclass)
├── kind: Literal["provider_error"] = "provider_error"
├── status_code: int                 HTTP status from provider
└── message: str

TimeoutError (frozen dataclass)
├── kind: Literal["timeout_error"] = "timeout_error"
└── timeout_seconds: float
```

**State transitions**:
```
LLM_ENABLE_EXTERNAL_CALLS=False  → ConfigurationError (before any network call)
API key absent                   → ConfigurationError
HTTP 401/403                     → ConfigurationError
HTTP 429, 5xx                    → ProviderError
Request exceeds timeout          → TimeoutError
HTTP 200 with content            → Success
```

**Rules**:
- Callers MUST use `match response.kind: case "success": ...` pattern.
- `LLMProvider.complete()` and `LLMProvider.embed()` MUST NOT raise any exception;
  all error conditions are returned as `LLMResponse` states.

---

### `LLMProvider` (Protocol)

```
LLMProvider (Protocol, runtime_checkable)
├── async def complete(
│       prompt: str,
│       model: ModelConfig,
│       config: LLMConfig,
│   ) -> LLMResponse
└── async def embed(
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse
```

**Implementations in Phase 0**:
- `OpenRouterAdapter` (production) — `trace/infrastructure/llm/adapters/openrouter.py`:
  - `def __init__(self, config: ApplicationConfig, http_client: httpx.AsyncClient) -> None`
  - Instantiated ONLY in the application composition/startup wiring layer (`trace/main.py` lifespan).
  - Receives `ApplicationConfig` via constructor injection (never imports global config directly).
  - API, domain, and orchestration layers depend only on the `LLMProvider` Protocol.
- `StubLLMProvider` (test double) — `tests/conftest.py`

---

## API Response Entities (`trace/api/health/`)

### `ServiceStatus`

```
ServiceStatus (Pydantic BaseModel)
└── status: Literal["reachable", "unreachable", "not_configured"]
```

---

### `HealthStatus`

```
HealthStatus (Pydantic BaseModel)
├── status: Literal["healthy", "degraded"]
├── version: str                     from importlib.metadata; "unknown" if unavailable
└── services: dict[str, ServiceStatus]
    ├── "postgres": ServiceStatus
    └── "neo4j": ServiceStatus
```

**Example — all healthy**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgres": {"status": "reachable"},
    "neo4j": {"status": "not_configured"}
  }
}
```

**Example — degraded**:
```json
{
  "status": "degraded",
  "version": "0.1.0",
  "services": {
    "postgres": {"status": "unreachable"},
    "neo4j": {"status": "reachable"}
  }
}
```

**HTTP status mapping**:
- `status="healthy"` → HTTP 200
- `status="degraded"` → HTTP 503

**Validation rules**:
- `version` field MUST NOT contain API keys, passwords, or connection strings.
- `services` dict MUST contain exactly the keys `"postgres"` and `"neo4j"` in Phase 0.

---

## Gateway Interfaces (`trace/infrastructure/*/`)

### `DatabaseGateway` (Protocol)

```
DatabaseGateway (Protocol, runtime_checkable)
├── def session(self) -> AsyncContextManager[AsyncSession]
└── async def health_check(self) -> bool
    # True = reachable, False = unreachable; never raises
```

**Implementations**:
- `SQLAlchemyDatabaseGateway` (production): real asyncpg engine
- `InMemoryDatabaseGateway` (test): aiosqlite in-memory engine

---

### `GraphGateway` (Protocol)

```
GraphGateway (Protocol, runtime_checkable)
└── async def health_check(self) -> GraphConnectivityState
    # Never raises; maps all exceptions to UNREACHABLE
```

**Implementations**:
- `Neo4jGraphGateway` (production): `AsyncDriver.verify_connectivity()` probe
- `UnconfiguredGraphGateway` (when NEO4J_URI absent): returns NOT_CONFIGURED immediately
- `StubGraphGateway` (test): returns configurable state

---

## Future Phase 1+ Entities (declared, not implemented)

The following entity names are reserved for Phase 1+ and MUST NOT be implemented in Phase 0:

```
PostgreSQL tables (Phase 1+):
├── projects
├── repositories
├── versions
├── analysis_runs
├── change_sets
├── risk_assessments
├── upgrade_plans
├── upgrade_tasks
├── validation_runs
└── human_reviews

Neo4j nodes (Phase 3A+):
├── :Module
├── :Function
├── :Class
├── :Package
└── [relationship types TBD]
```

No Alembic migration creates these tables in Phase 0.
No Neo4j schema (indexes, constraints, node labels) is established in Phase 0.
