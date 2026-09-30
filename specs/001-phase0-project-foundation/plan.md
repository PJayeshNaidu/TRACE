# Implementation Plan: TRACE Phase 0 — Project Foundation

**Branch**: `001-phase0-project-foundation` | **Date**: 2026-09-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-phase0-project-foundation/spec.md`

---

## Summary

Phase 0 establishes the engineering foundation for TRACE (Transformation Risk Analysis &
Change Evaluation): a runnable FastAPI backend with typed configuration, a structured LLM
provider abstraction, PostgreSQL and Neo4j connectivity boundaries, structured logging,
Docker Compose local development, and a deterministic test suite enforcing an 80% coverage
gate. No F01–F10 intelligence feature is implemented. The goal is a production-quality
scaffold that every subsequent phase builds on.

---

## Technical Context

**Language/Version**: Python 3.12 (minimum declared in `pyproject.toml`; container base
image `python:3.12-slim`)

**Primary Dependencies**:
- `fastapi` — HTTP API framework (ASGI-compatible)
- `uvicorn[standard]` — ASGI server
- `pydantic` / `pydantic-settings` — typed config + request/response models
- `sqlalchemy[asyncio]` — async ORM / Core
- `asyncpg` — async PostgreSQL driver
- `alembic` — schema migration tool
- `neo4j` — official Neo4j async Python driver
- `structlog` — structured logging
- `httpx` — async HTTP client (for OpenRouter adapter)
- `tenacity` — retry logic for the OpenRouter adapter
- `langgraph` — declared as dependency; not used in Phase 0

**Storage**:
- PostgreSQL (authoritative application state) via SQLAlchemy 2.x async + asyncpg
- Neo4j (structural graph, Phase 3A+) via `neo4j` async driver

**Testing**:
- `pytest` + `pytest-asyncio` + `httpx` (ASGI client) + `pytest-cov` + `pytest-socket`
- Default test command: `pytest -m "not integration" --cov=trace --cov-branch --cov-report=term-missing`
- Phase 0 release gate: `pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80 --cov-report=term-missing`
- Integration marker: `@pytest.mark.integration`
- Network isolation: `pytest-socket` blocks all network access by default

**Target Platform**: Linux server (development: Docker Compose; future: Kubernetes)

**Project Type**: Web service (async FastAPI backend; no frontend in Phase 0)

**Performance Goals**:
- `GET /health` response time < 500 ms under normal conditions
- Test suite completes in < 2 minutes (unit tests only)

**Constraints**:
- Secrets supplied only via environment variables; never hardcoded
- Source-code transmission to external LLM disabled by default
- 80% minimum test coverage enforced at Phase 0 release gate (intermediate dev runs measure coverage without failing solely for sub-80% coverage)
- All constitution principles I–XVII respected without exception

**Scale/Scope**: Phase 0 only — no domain tables, no analysis features, no agents

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Phase 0 Status | Evidence |
|---|---|---|
| **I** Evidence over Hallucination | ✅ Pass | No LLM inference in Phase 0; health probes use real connections |
| **II** Deterministic before Probabilistic | ✅ Pass | No analysis in Phase 0; gateway boundaries established |
| **III** Human-in-the-Loop | ✅ Pass | `LLM_ENABLE_EXTERNAL_TRANSMISSION=false` default; explicit opt-in required |
| **IV** Explainability | ✅ Pass | `HealthStatus` schema with per-service evidence |
| **V** Provider/Model Independence | ✅ Pass | `LLMProvider` Protocol; OpenRouter only in adapter |
| **VI** Free-First LLM | ✅ Pass | Default model = free tier; config-driven; paid models opt-in |
| **VII** Testability | ✅ Pass | All external services replaced by test doubles in default run |
| **VIII** Explicit Contracts | ✅ Pass | API, domain, persistence, graph, provider contracts separated (see contracts/) |
| **IX** Security & Secret Isolation | ✅ Pass | `.env` gitignored; secrets never logged; transmission gate |
| **X** Incremental Delivery | ✅ Pass | F01–F10 explicitly prohibited from Phase 0 |
| **XI** Observability | ✅ Pass | `structlog` JSON; container healthchecks; structured fields |
| **XII** Reproducibility | ✅ Pass | `uv.lock` committed; Alembic baseline migration; pinned Python 3.12 |
| **XIII** Maintainability | ✅ Pass | `src/` layout; single-responsibility modules; minimal dependencies |
| **XIV** Replaceability | ✅ Pass | `LLMProvider`, `DatabaseGateway`, `GraphGateway` all replaceable |
| **XV** Backward-Compatible Evolution | ✅ Pass | Alembic scripted; semver for contracts |
| **XVI** Production Quality | ✅ Pass | 80% coverage gate; ruff + mypy; runtime health verification |
| **XVII** No Fabricated State | ✅ Pass | `"unknown"` version fallback; no phantom features claimed |

**Gate result: PASS — proceed to Phase 1 design.**

No complexity-tracking violations found. No unjustified departures from constitution.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-phase0-project-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 entity/interface model
├── quickstart.md        # Phase 1 validation guide
├── contracts/
│   ├── api.md           # HTTP API contract (GET /health)
│   ├── llm-provider.md  # LLMProvider interface contract
│   ├── db-gateway.md    # DatabaseGateway interface contract
│   └── graph-gateway.md # GraphGateway interface contract
└── tasks.md             # Phase 2 output (speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
TRACE/
├── .env.example                    # All env vars; no real secrets
├── .gitignore                      # Includes .env, __pycache__, .venv
├── docker-compose.yml              # Development stack: backend + postgres + neo4j
├── docs/
│   ├── architecture.md             # Layer map + directory guide
│   ├── environment-variables.md    # Full env var reference
│   ├── local-setup.md              # Step-by-step onboarding
│   ├── llm-configuration.md        # LLM config + free-first policy
│   └── testing.md                  # Test commands + coverage guide
├── frontend/
│   └── README.md                   # Placeholder; Streamlit/React in later phases
├── specs/                          # Spec Kit artifacts
└── backend/
    ├── pyproject.toml              # Python ≥3.12, uv, ruff, mypy, pytest config
    ├── uv.lock                     # Committed lock file
    ├── Dockerfile                  # python:3.12-slim base
    ├── alembic.ini                 # Alembic config pointing to env.py
    ├── alembic/
    │   ├── env.py                  # Async migration runner
    │   └── versions/
    │       └── 0001_baseline.py    # Empty baseline migration
    └── src/
        └── trace/
            ├── __init__.py         # Package version (importlib.metadata target)
            ├── main.py             # FastAPI app factory + lifespan
            ├── api/
            │   ├── __init__.py
            │   ├── router.py       # Top-level router (includes health)
            │   └── health/
            │       ├── __init__.py
            │       ├── router.py   # GET /health endpoint
            │       └── schemas.py  # HealthStatus, ServiceStatus Pydantic models
            ├── core/
            │   ├── __init__.py
            │   ├── config.py       # ApplicationConfig (pydantic-settings)
            │   └── logging.py      # structlog bootstrap
            ├── domain/
            │   ├── __init__.py
            │   └── health.py       # HealthState, GraphConnectivityState enums
            ├── infrastructure/
            │   ├── __init__.py
            │   ├── database/
            │   │   ├── __init__.py
            │   │   ├── gateway.py  # DatabaseGateway Protocol + AsyncSession factory
            │   │   └── health.py   # PostgreSQL connectivity probe
            │   ├── graph/
            │   │   ├── __init__.py
            │   │   ├── gateway.py  # GraphGateway Protocol + Neo4j adapter
            │   │   └── health.py   # Neo4j connectivity probe
            │   └── llm/
            │       ├── __init__.py
            │       ├── provider.py # LLMProvider Protocol
            │       ├── config.py   # LLMConfig, ModelConfig dataclasses
            │       ├── response.py # LLMResponse discriminated union
            │       └── adapters/
            │           └── openrouter.py  # OpenRouter httpx adapter
    tests/
        ├── __init__.py
        ├── conftest.py             # Shared fixtures (app, test client, stubs)
        ├── unit/
        │   ├── test_config.py      # ApplicationConfig validation, empty-string-as-absent
        │   ├── test_health_schemas.py  # HealthStatus Pydantic model validation
        │   ├── test_llm_response.py    # LLMResponse state discrimination
        │   └── test_llm_provider.py   # LLMProvider stub: all four error states
        ├── api/
        │   ├── test_health_200.py  # GET /health → 200 + schema validation
        │   └── test_health_503.py  # GET /health → 503 when DB unreachable
        └── integration/            # Live-service tests (excluded from default run)
            ├── test_postgres_live.py
            └── test_neo4j_live.py
```

**Structure Decision**: Web application layout (Option 2) with `backend/src/trace/` as the
installable package root (PyPA `src/` layout). `tests/` lives inside `backend/` alongside
`pyproject.toml` so `pytest` discovers tests relative to the package. Frontend is a
placeholder only.

---

## Complexity Tracking

No constitution violations requiring justification. All added dependencies are strictly
necessary for the Phase 0 scope:

| Dependency | Justification |
|---|---|
| `tenacity` | Required for retry logic in the OpenRouter adapter without a vendor SDK |
| `langgraph` | Declared now to pin the version; no implementation in Phase 0 |

---

## Architecture

### Layer Diagram

```
Request
  ↓
┌─────────────────────────────────────────────────────────┐
│  API Layer  (trace/api/)                                │
│  FastAPI routers, Pydantic request/response schemas     │
│  Handles HTTP, validation, serialisation, OpenAPI docs  │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Application / Service Layer  (trace/services/ — Phase 1+) │
│  Orchestrates domain operations across boundaries       │
│  Phase 0: health service only (inline in health router) │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Domain Layer  (trace/domain/)                          │
│  Pure Python: enums, value objects, business rules      │
│  No framework imports; no I/O                           │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Ports / Interfaces  (trace/infrastructure/*/gateway.py) │
│  DatabaseGateway Protocol                               │
│  GraphGateway Protocol                                  │
│  LLMProvider Protocol                                   │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Infrastructure Adapters  (trace/infrastructure/)       │
│  PostgreSQL: SQLAlchemy async engine + asyncpg          │
│  Neo4j: official neo4j async driver                     │
│  LLM: httpx-based OpenRouter adapter                    │
│  Config: pydantic-settings (reads env vars)             │
│  Logging: structlog                                     │
└─────────────────────────────────────────────────────────┘
```

### Layer Assignment

| Concern | Layer | Module |
|---|---|---|
| Configuration | Infrastructure (cross-cutting) | `trace/core/config.py` |
| Logging | Infrastructure (cross-cutting) | `trace/core/logging.py` |
| PostgreSQL adapter | Infrastructure | `trace/infrastructure/database/` |
| Neo4j adapter | Infrastructure | `trace/infrastructure/graph/` |
| LLM gateway | Infrastructure | `trace/infrastructure/llm/` |
| Git integration | Infrastructure (Phase 2+) | `trace/infrastructure/git/` — **not in Phase 0** |
| Future analysis engines | Infrastructure (Phase 3+) | `trace/infrastructure/analysis/` — **not in Phase 0** |

### Dependency Rule

```
api/ → domain/, infrastructure/*/gateway.py (Protocol only)
domain/ → nothing (pure Python)
infrastructure/ → external libraries only
core/ → nothing (pydantic-settings, structlog — no trace imports)
```

No reverse dependencies are permitted. The `api/` layer imports `LLMProvider` (the Protocol),
never `openrouter.py` (the adapter). Adapters are wired in `main.py` lifespan only.

---

## Backend Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Python version | 3.12 | Stable LTS with modern typing; broad ecosystem support |
| Package manager | `uv` | Sub-second installs; `uv.lock` committed for reproducibility |
| Web framework | FastAPI | Async-first; Pydantic-native; OpenAPI auto-generated |
| Pydantic | v2 (bundled with FastAPI ≥0.100) | Native async; strict mode support; faster validation |
| ASGI server | `uvicorn[standard]` | Standard FastAPI server; HTTP/2 capable |
| ORM | SQLAlchemy 2.x async ORM | Async-native; Type-mapped models for Phase 1+; best Alembic support |
| DB driver | `asyncpg` | Native async PostgreSQL; highest throughput |
| Migration | Alembic | De facto SQLAlchemy migration tool; supports async env.py |
| Logging | `structlog` | JSON output; key-value context binding; production-ready |
| Config | `pydantic-settings` | Type-validated env var loading; `.env` file support |
| Linter | `ruff` (lint + format) | Replaces flake8/isort/black; single fast tool |
| Type checker | `mypy` | Mature; best FastAPI/SQLAlchemy plugin support |
| Test runner | `pytest` + `pytest-asyncio` | Industry standard; async test support |
| ASGI test client | `httpx` | Native async; works with FastAPI `TestClient` |
| Coverage | `pytest-cov` | Coverage measured in default run; 80% minimum enforced at Phase 0 release gate via `--cov-fail-under=80` |
| Network isolation | `pytest-socket` | Blocks network access by default; ensures deterministic offline unit tests |
| Retry | `tenacity` | Declarative retry/backoff for httpx without vendor SDK |

---

## LLM Abstraction Design

### Interface Hierarchy

```
LLMProvider (Protocol)          ← trace/infrastructure/llm/provider.py
    complete(prompt, model, config) → LLMResponse
    embed(text, model, config) → LLMResponse

LLMConfig (dataclass)           ← trace/infrastructure/llm/config.py
    base_url: str
    api_key_env_name: str       # name of env var, not value
    timeout_seconds: float
    max_retries: int

ModelConfig (dataclass)         ← trace/infrastructure/llm/config.py
    default: str                # free-tier model (defaults to mistralai/mistral-7b-instruct:free, overridable by LLM_DEFAULT_MODEL)
    reasoning: str
    fast: str
    fallback: list[str]

LLMResponse (discriminated union) ← trace/infrastructure/llm/response.py
    Success(content: str, model: str, usage: TokenUsage)
    ConfigurationError(message: str)
    ProviderError(status_code: int, message: str)
    TimeoutError(timeout_seconds: float)

OpenRouterAdapter               ← trace/infrastructure/llm/adapters/openrouter.py
    implements LLMProvider
    __init__(config: ApplicationConfig, http_client: httpx.AsyncClient)
    instantiated ONLY in application composition/startup wiring (trace/main.py lifespan)
    receives ApplicationConfig via constructor injection (never imports global config)
    API/domain/orchestration code depends only on LLMProvider Protocol
    maps HTTP 4xx/5xx → LLMResponse states
    retries via tenacity (max 3, exponential backoff, on ProviderError only)
```

### Model Configuration

Default model (`LLM_DEFAULT_MODEL`): `mistralai/mistral-7b-instruct:free`
— Confirmed free tier on OpenRouter; no billing required; 7B parameter open-weight model.
The application default provides a safe free-tier fallback when `LLM_DEFAULT_MODEL` is unset.
Setting `LLM_DEFAULT_MODEL` overrides the default without requiring source-code modification.

Model selection order: `LLM_DEFAULT_MODEL` → `LLM_FAST_MODEL` → `LLM_FALLBACK_MODELS[0]` → ...
Paid model fallback is **never** automatic. If all configured models fail,
`ProviderError` is returned to the caller.

### Error Mapping (OpenRouter → LLMResponse)

| HTTP Status | LLM_ENABLE_EXTERNAL_CALLS=false | 401/403 | 429 | 5xx | Timeout |
|---|---|---|---|---|---|
| LLMResponse state | ConfigurationError | ConfigurationError | ProviderError | ProviderError | TimeoutError |

### Test Strategy

- `LLMProvider` is a Protocol: any class with matching signatures is a valid stub.
- Unit tests inject a `StubLLMProvider` fixture that returns a predetermined `LLMResponse`
  state (no HTTP call made).
- Integration tests mark `@pytest.mark.integration` and require a real OpenRouter key.

### Transmission Gate

Before the `OpenRouterAdapter` sends any request body containing source code or file
content, it checks `ApplicationConfig.llm_enable_external_transmission`. If `False`
(default), the adapter raises a `ConfigurationError` response (no HTTP call). The event
is logged at `WARNING` with provider name and estimated content size (bytes/files), never
the content itself.

---

## PostgreSQL Foundation Design

### Connection Lifecycle (FastAPI Lifespan)

```python
# trace/main.py (pseudocode)
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(config.database_url)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db = async_session_maker
    yield
    await engine.dispose()
```

### DatabaseGateway Protocol

```python
# trace/infrastructure/database/gateway.py
class DatabaseGateway(Protocol):
    def session(self) -> AsyncContextManager[AsyncSession]: ...
    async def health_check(self) -> bool: ...
```

Concrete implementation: `SQLAlchemyDatabaseGateway` (uses real engine).
Test double: `InMemoryDatabaseGateway` (uses `create_async_engine("sqlite+aiosqlite:///:memory:")`).

### Health Probe

```sql
SELECT 1
```
Executed via `engine.connect()` + `connection.execute(text("SELECT 1"))` inside
a try/except. Returns `True` (reachable) or `False` (unreachable) — never raises.

### Alembic Setup

```
alembic/
├── env.py          # Uses asyncio.run(run_migrations_online()) pattern
└── versions/
    └── 0001_baseline.py   # Empty migration (autogenerated stamp)
```

`alembic upgrade head` must be runnable as a documented command.
No domain tables are created in Phase 0.

### Migration Command

```bash
uv run alembic upgrade head
```

---

## Neo4j Foundation Design

### Driver Lifecycle (FastAPI Lifespan)

```python
# trace/main.py (pseudocode)
@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.neo4j_uri:
        driver = AsyncGraphDatabase.driver(config.neo4j_uri, auth=(user, pass))
        app.state.graph = Neo4jGraphGateway(driver)
        yield
        await driver.close()
    else:
        app.state.graph = UnconfiguredGraphGateway()
        yield
```

### GraphGateway Protocol

```python
# trace/infrastructure/graph/gateway.py
class GraphConnectivityState(str, Enum):
    NOT_CONFIGURED = "not_configured"
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"

class GraphGateway(Protocol):
    async def health_check(self) -> GraphConnectivityState: ...
```

Two concrete implementations:
- `Neo4jGraphGateway`: calls `driver.verify_connectivity()` (non-Cypher probe).
  Returns `REACHABLE` on success, `UNREACHABLE` on exception.
- `UnconfiguredGraphGateway`: returns `NOT_CONFIGURED` immediately. Used when
  `NEO4J_URI` is absent. Never makes a network call.
- `StubGraphGateway` (test double): returns a configurable state. Used in unit tests.

### Health Behavior in Phase 0

Per the Assumptions in the spec:
- Neo4j `NOT_CONFIGURED` → health endpoint still returns HTTP 200 (Neo4j not functional until Phase 3A)
- Neo4j `UNREACHABLE` (configured but unreachable) → HTTP 503
- PostgreSQL unreachable → HTTP 503

---

## Docker Design

### Service Definitions

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 5

  neo4j:
    image: neo4j:5-community
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "-", "http://localhost:7474"]
      interval: 10s
      timeout: 10s
      retries: 5

  backend:
    build: ./backend
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    env_file: .env
```

All credentials via `env_file: .env` or `environment:` block referencing host env vars.
No hardcoded values in compose file.

### Startup Order

```
postgres (healthy) ─┐
                     ├─→ backend starts
neo4j (healthy)   ──┘
```

Backend container will not enter running state until both infra services report healthy.

---

## Health Endpoint Design

### Route

`GET /health` — FastAPI router, no authentication, returns `HealthStatus` always.

### Response Schema

```python
class ServiceStatus(BaseModel):
    status: Literal["reachable", "unreachable", "not_configured"]

class HealthStatus(BaseModel):
    status: Literal["healthy", "degraded"]
    version: str                    # from importlib.metadata; "unknown" if unavailable
    services: dict[str, ServiceStatus]
    # e.g.: {"postgres": {"status": "reachable"}, "neo4j": {"status": "not_configured"}}
```

### HTTP Status Logic

```
postgres=reachable AND (neo4j=reachable OR neo4j=not_configured)
  → HTTP 200, status="healthy"

postgres=unreachable OR neo4j=unreachable
  → HTTP 503, status="degraded"
  body still contains full HealthStatus with per-service evidence
```

### Version Population

```python
try:
    version = importlib.metadata.version("trace")
except importlib.metadata.PackageNotFoundError:
    version = "unknown"
```

---

## Testing Strategy

### Test Categories

| Category | Files | External Services | Marker |
|---|---|---|---|
| Unit: config & isolation | `test_config.py` | None | (default) |
| Unit: schemas | `test_health_schemas.py` | None | (default) |
| Unit: LLM response & config | `test_llm_response.py`, `test_llm_config.py` | None | (default) |
| Unit: LLM provider stub | `test_llm_provider.py` | None (stub) | (default) |
| Unit: logging & redaction | `test_logging_redaction.py` | None | (default) |
| API: health 200 | `test_health_200.py` | None (stubs) | (default) |
| API: health 503 | `test_health_503.py` | None (stubs) | (default) |
| Integration: live DB | `test_postgres_live.py` | PostgreSQL | `integration` |
| Integration: live graph | `test_neo4j_live.py` | Neo4j | `integration` |

### Default Development Test Command

```bash
# From backend/ — measures coverage without failing for sub-80% during intermediate dev
uv run pytest -m "not integration" \
    --cov=trace \
    --cov-branch \
    --cov-report=term-missing
```

### Phase 0 Release Gate Command

```bash
# From backend/ — strictly enforces the 80% coverage minimum
uv run pytest -m "not integration" \
    --cov=trace \
    --cov-branch \
    --cov-fail-under=80 \
    --cov-report=term-missing
```

### Key Test Scenarios

1. **Config: required variable absent** → `ValidationError` raised at `ApplicationConfig()` init
2. **Config: empty string for required field** → treated as absent → `ValidationError`
3. **Config: test environment isolation** → test `ApplicationConfig(_env_file=None, ...)` does not consume ambient host env vars; isolated via monkeypatch
4. **Health 200**: all stubs return healthy → HTTP 200 + `HealthStatus(status="healthy")`
5. **Health 503 (postgres down)**: `DatabaseGateway.health_check()` returns `False` → HTTP 503
6. **Health 503 (neo4j unreachable)**: `GraphGateway.health_check()` returns `UNREACHABLE` → HTTP 503
7. **Health 200 (neo4j not_configured)**: `GraphGateway.health_check()` returns `NOT_CONFIGURED` → HTTP 200
8. **LLM ConfigurationError**: stub returns `ConfigurationError` → caller receives it without exception
9. **LLM ProviderError**: stub returns `ProviderError(status_code=429, ...)` → caller handles
10. **LLM TimeoutError**: stub returns `TimeoutError(timeout_seconds=30.0)` → caller handles
11. **LLM model override & fallback**: `LLM_DEFAULT_MODEL` overrides `ModelConfig.default` without code modification; defaults to `mistralai/mistral-7b-instruct:free` when unset
12. **Version "unknown"**: mock `importlib.metadata.version` to raise `PackageNotFoundError` → `"unknown"`
13. **Transmission gate**: `LLM_ENABLE_EXTERNAL_TRANSMISSION=false` → source content blocked, WARNING logged
14. **Structured logging context binding**: `structlog.contextvars.bind_contextvars()` binds `project_id` and `analysis_run_id` which appear in rendered JSON log output (FR-032)
15. **Secret redaction**: secret field values are replaced with `[REDACTED]` in log output
16. **Network isolation**: `pytest-socket` disables socket connections during default test run; zero external network access required

---

## Security Design

### Secret Handling

```
Source of truth for secrets: Environment variables only
Committed placeholder: .env.example (no real values)
Gitignored: .env (enforced by .gitignore)
Logging redaction: structlog processor strips known secret field names
Health endpoint: returns only status strings, never config values
```

### Prohibited Log Fields (structlog processor)

```python
SECRET_FIELDS = {"api_key", "password", "token", "secret", "credential",
                 "DATABASE_URL", "NEO4J_PASSWORD", "OPENROUTER_API_KEY"}
```
Any log event containing these keys at any level will have values replaced with `[REDACTED]`.

### Transmission Gate (FR-045)

- `LLM_ENABLE_EXTERNAL_TRANSMISSION` defaults to `false` if absent.
- Gate is checked in `OpenRouterAdapter.complete()` before any HTTP call.
- Intercepted events are logged: `WARNING: transmission blocked | provider=openrouter | content_bytes=N`
- Secrets are never in the log message.

---

## Documentation Minimum

Phase 0 is complete only when all of the following exist with accurate content:

| Document | Path | Required Content |
|---|---|---|
| Local setup | `docs/local-setup.md` | Clone → `uv sync` → `.env` → start backend → verify `/health` |
| Env var reference | `docs/environment-variables.md` | All vars from `.env.example` with type, required/optional, description |
| Testing guide | `docs/testing.md` | Default run command, integration marker, coverage gate, linting commands |
| LLM config | `docs/llm-configuration.md` | Model roles, free-first policy, `LLM_ENABLE_EXTERNAL_CALLS`, `LLM_ENABLE_EXTERNAL_TRANSMISSION` |
| Architecture | `docs/architecture.md` | Layer diagram, directory map, layer-boundary rules |
| README | `README.md` (root) | Project overview, quickstart, link to docs/ |

---

## Verification Commands

All of the following MUST pass before Phase 0 is declared complete:

```bash
# From backend/

# 1. Install dependencies
uv sync

# 2. Run release gate test suite (unit + API, no live services, with 80% coverage gate)
uv run pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80 --cov-report=term-missing

# 3. Lint (zero violations)
uv run ruff check src/ tests/

# 4. Format check (zero violations)
uv run ruff format --check src/ tests/

# 5. Type check (zero violations)
uv run mypy src/

# 6. Run database migrations (requires live PostgreSQL)
uv run alembic upgrade head

# 7. Start backend natively (requires .env)
uv run uvicorn trace.main:app --reload

# 8. Verify health endpoint
curl http://localhost:8000/health

# 9. Start full Docker stack
docker compose up --build

# 10. Verify stack health
curl http://localhost:8000/health
```

---

## Implementation Order

Dependencies are explicit; each step must be complete before the next begins.

```
Step 1: Repository skeleton
  → pyproject.toml (T004 canonical owner), uv.lock, .gitignore, .env.example, Dockerfile, docker-compose.yml
  → docs/ placeholder files
  → frontend/README.md

Step 2: Core configuration (ApplicationConfig)
  → trace/core/config.py  (pydantic-settings, all env vars, empty-string rule)
  → tests/unit/test_config.py (includes test environment isolation assertion)
  GATE: config tests pass

Step 3: Core logging (structlog bootstrap)
  → trace/core/logging.py  (JSON in prod/test, key-value in dev, redaction processor)
  → tests/unit/test_logging_redaction.py (verifies redaction + structured context binding)
  GATE: logging initialises and context binding verified

Step 4: Domain layer (enums and value objects)
  → trace/domain/health.py  (HealthState, GraphConnectivityState)
  GATE: no external imports; mypy clean

Step 5: LLM abstraction (interface + response types)
  → trace/infrastructure/llm/provider.py  (LLMProvider Protocol)
  → trace/infrastructure/llm/config.py    (LLMConfig, ModelConfig with env override)
  → trace/infrastructure/llm/response.py  (LLMResponse union)
  → tests/unit/test_llm_response.py       (depends on provider.py runtime Protocol)
  → tests/unit/test_llm_provider.py
  GATE: LLM unit tests pass; mypy clean

Step 6: OpenRouter adapter
  → trace/infrastructure/llm/adapters/openrouter.py
  → __init__(config: ApplicationConfig, http_client: httpx.AsyncClient)
  → Instantiated ONLY in main.py lifespan; receives ApplicationConfig via constructor
  GATE: no live call made in default tests; adapter wires correctly

Step 7: Database gateway
  → trace/infrastructure/database/gateway.py  (Protocol + SQLAlchemy impl)
  → trace/infrastructure/database/health.py
  GATE: gateway protocol defined; mypy clean

Step 8: Graph gateway
  → trace/infrastructure/graph/gateway.py  (Protocol + Neo4j impl + Unconfigured impl)
  → trace/infrastructure/graph/health.py
  GATE: gateway protocol defined; all three states representable

Step 9: Alembic setup
  → alembic.ini, alembic/env.py (async), alembic/versions/0001_baseline.py
  → Baseline migration contains empty upgrade(): pass and downgrade(): pass (no domain tables)
  GATE: alembic upgrade head runs against test DB without error

Step 10: Health API endpoint
  → trace/api/router.py          (top-level router skeleton)
  → trace/api/health/schemas.py  (HealthStatus, ServiceStatus)
  → trace/api/health/router.py   (GET /health, 200/503 logic; registered into top-level router)
  → trace/main.py                (FastAPI app + lifespan wiring: OpenRouterAdapter instantiated here only)
  → tests/api/test_health_200.py
  → tests/api/test_health_503.py
  GATE: all API tests pass; correct HTTP status codes

Step 11: Docker Compose
  → docker-compose.yml with healthchecks (cypher-shell for neo4j) + depends_on:condition
  GATE: docker compose up starts all services; backend /health returns 200

Step 12: Documentation & Public Interface Contracts
  → docs/local-setup.md, environment-variables.md, testing.md,
    llm-configuration.md, architecture.md
  → root README.md
  → Docstrings and contracts for all public interfaces (LLMProvider, DatabaseGateway, GraphGateway, config, schemas)
  GATE: onboarding test passes SC-001 (30-minute target); docstrings verified

Step 13: Final verification
  → All verification commands pass
  → ruff + mypy zero violations
  → 80% coverage gate green (enforced via --cov-fail-under=80)
  → Phase 0 success criteria SC-001–SC-009 and functional requirements FR-001–FR-050 documented as met
```

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `asyncpg` + SQLite incompatibility in tests | Medium | High | Use `aiosqlite` driver for SQLite test double; `asyncpg` only for production |
| Neo4j `verify_connectivity()` raises non-obvious exceptions | Low | Medium | Catch all exceptions in health probe; return UNREACHABLE with logged cause |
| `importlib.metadata` not finding `trace` in development | Medium | Low | `pip install -e .` or `uv sync` sets up editable install; fallback to `"unknown"` |
| OpenRouter free-tier model deprecation | Low | Low | Config-driven; change `LLM_DEFAULT_MODEL` env var to update |
| `depends_on: condition: service_healthy` requires Compose v2 | Low | Medium | Use `docker compose` (not `docker-compose`); document minimum Docker version |
| 80% coverage gate too strict for initial scaffold | Low | Low | Phase 0 tests are comprehensive by design; adjust threshold only with documented rationale |

---

## Interfaces

All cross-boundary interfaces are specified in `contracts/`. The three primary interfaces are:

- **`LLMProvider`** (Protocol): `complete()` + `embed()` — see [contracts/llm-provider.md](contracts/llm-provider.md)
- **`DatabaseGateway`** (Protocol): `session()` + `health_check()` — see [contracts/db-gateway.md](contracts/db-gateway.md)
- **`GraphGateway`** (Protocol): `health_check()` — see [contracts/graph-gateway.md](contracts/graph-gateway.md)
- **`GET /health`** (HTTP): see [contracts/api.md](contracts/api.md)
