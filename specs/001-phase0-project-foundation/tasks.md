# Tasks: TRACE Phase 0 — Project Foundation

**Branch**: `001-phase0-project-foundation` | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

<!--
  PHASE 0 TASK LIST — REVISION 2 (post-consistency-analysis F1–F17 corrections)
  Source: spec.md (User Stories US1–US4), plan.md (implementation order), data-model.md, contracts/
  Total: 63 tasks across 7 phases (T001–T063; strictly sequential IDs)
  User story mapping:
    US1 = Developer Onboards and Verifies the System Runs (P1)
    US2 = Developer Runs the Test Suite Deterministically (P2)
    US3 = Developer Understands the Architecture Boundaries (P3)
    US4 = Operator Starts the Local Dev Environment via Docker (P4)

  Corrections applied (F1–F17):
    F1+F2: T004 is the SOLE pyproject.toml owner. T033/T046/T047 verify only without modifying.
    F3: --cov-fail-under=80 removed from addopts; enforced explicitly at release gate (T051).
    F4: T024 clarified — OpenRouterAdapter instantiation only in main.py lifespan.
    F5: T010 explicitly includes LLM_DEFAULT_MODEL; T016 adds deterministic env-override test and fallback preservation.
    F6: [P] removed from T018; depends-on T017 Protocol definition noted.
    F7: T025 creates empty skeleton; T028 creates health router AND registers it.
    F8: T011 and T034 add explicit deterministic test environment isolation assertions.
    F9: T022 clarified — empty upgrade()/downgrade() stubs required without schema creation.
    F10: T044 documents verified neo4j:5-community cypher-shell healthcheck command.
    F11: T019 clarified — ApplicationConfig injected via __init__, not imported globally.
    F12: T049 includes deterministic structured logging context binding test (project_id, analysis_run_id).
    F13: T037 uses deterministic automated pytest-socket network-isolation check.
    F14: Standalone PHASE0-COMPLETE.md file removed; release verification incorporated into T062/T063.
    F15: T062 references SC-001–SC-009 and FR-001–FR-050; removes stale "16 criteria".
    F16: T043 given concrete verification test for all public interfaces.
    F17: [P] removed from T052, T053, T054, T055, T058, T059, T060, T061 (shared local port/environment).
-->

---

## Phase 1: Setup — Repository Bootstrap

**Purpose**: Establish the committed repository skeleton before any Python code is written.
Everything downstream depends on this phase.

- [X] T001 Create top-level directory structure: `backend/`, `docs/`, `frontend/`, `specs/` in repo root
- [X] T002 Create `frontend/README.md` placeholder noting Streamlit/React scope is deferred to future phases
- [X] T003 Create root `.gitignore` covering `.env`, `__pycache__`, `.venv`, `*.pyc`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `htmlcov/`, `dist/`
- [X] T004 Create `backend/pyproject.toml` — the **single canonical configuration file** for the entire backend project; this task is the SOLE owner of `pyproject.toml` and no other task may create or modify it; it MUST declare: (a) `[project]` metadata with `name = "trace"`, `version = "0.1.0"`, `requires-python = ">=3.12"`, and all production dependencies (`fastapi`, `uvicorn[standard]`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `neo4j`, `structlog`, `httpx`, `tenacity`, `langgraph`); (b) `[project.optional-dependencies]` dev group with `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-socket`, `httpx`, `aiosqlite`, `mypy`, `ruff`; (c) `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `addopts = "-m 'not integration' --cov=trace --cov-branch --cov-report=term-missing"` (**without** `--cov-fail-under`), and `markers = ["integration: marks tests as requiring live services"]`; (d) `[tool.coverage.run]` with `source = ["trace"]` and `branch = true`; (e) `[tool.ruff]` with `line-length = 100`, selected rules `["E","F","I","UP","B","C4","PT"]`, and `[tool.ruff.format]` with `quote-style = "double"`; (f) `[tool.mypy]` with `strict = true` and plugins `["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]`
- [X] T005 [P] Create root `README.md` with project overview, quickstart pointer, and links to `docs/`
- [X] T006 [P] Create `backend/Dockerfile` using `python:3.12-slim` base, installing `uv`, copying source, running `uv sync --no-dev`, and starting uvicorn
- [X] T007 Run `uv sync` inside `backend/` to generate `backend/uv.lock`; commit both `pyproject.toml` and `uv.lock`

**Checkpoint**: `git status` shows a clean working tree; `cat backend/pyproject.toml` contains all tool sections; `uv run pytest --co -q` lists tests without error.

---

## Phase 2: Foundational — Core Infrastructure (Blocks All User Stories)

**Purpose**: Core configuration, logging, domain enums, FastAPI app skeleton, and all gateway interfaces.
**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

### 2A — Typed Configuration (FR-008, FR-011, FR-012, FR-046)

- [X] T008 Create `backend/src/trace/__init__.py` as the package entry point; version string populated from `importlib.metadata`
- [X] T009 Create `backend/src/trace/core/config.py` implementing `ApplicationConfig(BaseSettings)` with all environment variable fields from FR-011/FR-012, a `model_validator(mode="before")` that treats empty strings as absent for required fields, and `SecretStr` for secret fields; the class MUST be loadable without a real `.env` file when fields are supplied directly (enabling test isolation)
- [X] T010 Create `backend/.env.example` listing every variable consumed by `ApplicationConfig` with a safe placeholder value and one-line comment per variable (FR-046 bidirectional completeness); MUST explicitly include the following entries (among others): `DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trace`, `LLM_DEFAULT_MODEL=mistralai/mistral-7b-instruct:free`, `LLM_REASONING_MODEL=`, `LLM_FAST_MODEL=`, `LLM_FALLBACK_MODELS=`, `LLM_ENABLE_EXTERNAL_CALLS=false`, `LLM_ENABLE_EXTERNAL_TRANSMISSION=false`, `APP_ENV=development`, `LOG_LEVEL=INFO`; no real credentials anywhere in this file
- [X] T011 Write `backend/tests/unit/test_config.py` covering: (a) all required variables present → valid config; (b) `DATABASE_URL` absent → `ValidationError` with field name in message; (c) `DATABASE_URL` set to `""` → `ValidationError` (empty-string-as-absent rule); (d) `LLM_ENABLE_EXTERNAL_TRANSMISSION` defaults to `False` when absent; (e) **environment isolation**: instantiate `ApplicationConfig` with explicit `_env_file=None` and direct field kwargs — assert it does NOT read from the host environment's `DATABASE_URL` if one happens to be set; use `monkeypatch.delenv("DATABASE_URL", raising=False)` to ensure isolation

**Checkpoint** (T008–T011): `uv run pytest tests/unit/test_config.py -m "not integration"` passes; no live DB needed.

### 2B — Structured Logging (FR-031, FR-032, FR-033)

- [X] T012 Create `backend/src/trace/core/logging.py` configuring `structlog` with: JSON renderer when `APP_ENV` is `production` or `test`; `ConsoleRenderer` when `development`; a `SecretRedactingProcessor` that replaces values of keys matching `SECRET_FIELDS = {"api_key","password","token","secret","credential","DATABASE_URL","NEO4J_PASSWORD","OPENROUTER_API_KEY"}` with `"[REDACTED]"` before any renderer; named context fields (`project_id`, `analysis_run_id`, `agent_name`, `stage`, `duration`, `status`, `model`, `provider`, `error`) bindable via `structlog.contextvars.bind_contextvars()`

**Checkpoint** (T012): `uv run python -c "from trace.core.logging import configure_logging; configure_logging()"` exits without error.

### 2C — Domain Layer (FR data model)

- [X] T013 [P] Create `backend/src/trace/domain/__init__.py`
- [X] T014 [P] Create `backend/src/trace/domain/health.py` defining `HealthState(str, Enum)` with values `HEALTHY="healthy"` and `DEGRADED="degraded"`, and `GraphConnectivityState(str, Enum)` with values `NOT_CONFIGURED="not_configured"`, `REACHABLE="reachable"`, `UNREACHABLE="unreachable"`

**Checkpoint** (T013–T014): `uv run mypy src/trace/domain/` → zero violations; no external imports in domain files.

### 2D — LLM Abstraction Foundation (FR-014, FR-015, FR-016, FR-018)

- [X] T015 Create `backend/src/trace/infrastructure/llm/response.py` implementing the `LLMResponse` discriminated union as four frozen dataclasses (`Success`, `ConfigurationError`, `ProviderError`, `TimeoutError`) each with a `kind: Literal[...]` field and appropriate payload fields; also define `TokenUsage(frozen dataclass)` with `prompt_tokens: int` and `completion_tokens: int`
- [X] T016 Create `backend/src/trace/infrastructure/llm/config.py` implementing `LLMConfig(frozen dataclass)` and `ModelConfig(frozen dataclass)`; `ModelConfig.default` MUST default to `"mistralai/mistral-7b-instruct:free"` (a free-tier model per FR-013) but this default MUST be **overridable** by the `LLM_DEFAULT_MODEL` environment variable at runtime without source-code modification; the application default MUST be preserved as a safe free-model fallback when unset; write a deterministic unit test in `backend/tests/unit/test_llm_config.py` asserting both that `LLM_DEFAULT_MODEL` overrides the default and that the fallback default is preserved when unset; no paid model MUST appear as any default anywhere in `ModelConfig`
- [X] T017 Create `backend/src/trace/infrastructure/llm/provider.py` defining `LLMProvider(Protocol, runtime_checkable)` with `async def complete(self, prompt: str, model: ModelConfig, config: LLMConfig) -> LLMResponse` and `async def embed(self, text: str, model: ModelConfig, config: LLMConfig) -> LLMResponse`; annotate with docstrings per FR contract (see T043)
- [X] T018 Write `backend/tests/unit/test_llm_response.py` **(depends on T017 — do NOT run before T017 is complete; [P] marker intentionally omitted)**: assert each dataclass has the correct `kind` literal; assert pattern-match on all four states is exhaustive (mypy narrowing); assert `isinstance(stub, LLMProvider)` is `True` for a conforming stub class (validates `runtime_checkable`)

**Checkpoint** (T015–T018): `uv run pytest tests/unit/test_llm_response.py` passes; `uv run mypy src/trace/infrastructure/llm/` zero violations.

### 2E — OpenRouter Adapter (FR-017, FR-045)

- [X] T019 Create `backend/src/trace/infrastructure/llm/adapters/openrouter.py` implementing `OpenRouterAdapter` that satisfies `LLMProvider`; the constructor signature MUST be `def __init__(self, config: ApplicationConfig, http_client: httpx.AsyncClient) -> None` — `ApplicationConfig` is injected at construction time (from `main.py` lifespan only) and MUST NOT be imported at module level or accessed via a global; uses the injected `httpx.AsyncClient`; checks `config.llm_enable_external_calls` before any HTTP call (returns `ConfigurationError` if `False`); checks `config.llm_enable_external_transmission` before sending any source-code payload (intercepts and logs `WARNING` with provider + content size if `False`); maps HTTP 401/403 → `ConfigurationError`, 429/5xx → `ProviderError`, timeout → `TimeoutError`; retries via `tenacity` on `ProviderError` (max 3, exponential backoff, jitter); never raises to caller; `openrouter.ai` URL and API key reference MUST appear only in this file (FR-016)
- [X] T020 [P] Write `backend/tests/unit/test_llm_provider.py` using a `StubLLMProvider` fixture (implements `LLMProvider` Protocol without inheriting from it) that returns each of the four `LLMResponse` states on demand; assert caller receives all four states without exception; assert `isinstance(StubLLMProvider(), LLMProvider)` is `True`

**Checkpoint** (T019–T020): `uv run pytest tests/unit/test_llm_provider.py` passes; no live HTTP call made; `grep -r "openrouter.ai" src/` returns only `adapters/openrouter.py`.

### 2F — Database Gateway (FR-019, FR-020, FR-021)

- [X] T021 Create `backend/src/trace/infrastructure/database/gateway.py` defining `DatabaseGateway(Protocol, runtime_checkable)` with `def session(self) -> AsyncContextManager[AsyncSession]` and `async def health_check(self) -> bool`; implement `SQLAlchemyDatabaseGateway` wrapping an `AsyncEngine` from `ApplicationConfig.database_url`; `health_check()` executes `SELECT 1` via `engine.connect()` and returns `True`/`False` (never raises, logs exceptions at WARNING); provide `InMemoryDatabaseGateway` using `create_async_engine("sqlite+aiosqlite:///:memory:")` for tests; annotate public methods with docstrings
- [X] T022 Configure Alembic: create `backend/alembic.ini`, `backend/alembic/env.py` using the async migration pattern (`asyncio.run(run_async_upgrade())`), and `backend/alembic/versions/0001_baseline.py` as the empty baseline migration; the migration file MUST contain syntactically valid Python including `def upgrade() -> None: pass` and `def downgrade() -> None: pass` stubs — an Alembic migration file without these functions is a parse error; no schema operations are performed in this migration; domain tables MUST NOT be created

**Checkpoint** (T021–T022): `uv run mypy src/trace/infrastructure/database/` zero violations; `uv run alembic check` exits code 0 (no pending migrations against a test DB).

### 2G — Graph Gateway (FR-023, FR-024, FR-025, FR-026)

- [X] T023 Create `backend/src/trace/infrastructure/graph/gateway.py` defining `GraphGateway(Protocol, runtime_checkable)` with `async def health_check(self) -> GraphConnectivityState`; implement `Neo4jGraphGateway` wrapping `AsyncGraphDatabase.driver()`, calling `driver.verify_connectivity()` in `health_check()`, catching all exceptions and returning `UNREACHABLE` (never raises); implement `UnconfiguredGraphGateway` returning `NOT_CONFIGURED` immediately without any network call; annotate public methods with docstrings

**Checkpoint** (T023): `uv run mypy src/trace/infrastructure/graph/` zero violations.

### 2H — FastAPI App Factory and Lifespan (FR-003, FR-004, FR-007, FR-039, FR-047, FR-048)

- [X] T024 Create `backend/src/trace/main.py` implementing the FastAPI application factory with an `@asynccontextmanager` lifespan; the lifespan is the **only permitted location** for adapter instantiation — it MUST: load `ApplicationConfig` (raises startup error on `ValidationError`); call `configure_logging()`; create `SQLAlchemyDatabaseGateway` and store on `app.state.db`; select and store the appropriate `GraphGateway` impl on `app.state.graph` based on `NEO4J_URI`; create a singleton `httpx.AsyncClient`, then pass `(config, http_client)` to `OpenRouterAdapter(config, http_client)` and store on `app.state.llm`; dispose engine and close driver and HTTP client on shutdown; IMPORTANT — `OpenRouterAdapter` is imported here and ONLY here; no other module in `api/`, `domain/`, or `services/` may import `OpenRouterAdapter` or access `app.state.llm` as a concrete type
- [X] T025 Create `backend/src/trace/api/__init__.py` and `backend/src/trace/api/router.py` defining the top-level APIRouter as an **empty skeleton** at this point — do NOT import or include the health sub-router yet (the health router does not exist until T028); T028 will both create the health router and register it here

**Checkpoint** (T024–T025): `uv run python -c "from trace.main import app"` imports without error; `uv run uvicorn trace.main:app --host 0.0.0.0 --port 8001 &; sleep 2; kill %1` exits without crash.

**Foundational Checkpoint**: All Phase 2 tasks complete → `uv run mypy src/` passes; `uv run ruff check src/` passes; core imports work; no live services needed.

---

## Phase 3: User Story 1 — Developer Onboards and Verifies the System Runs (P1) 🎯 MVP

**Goal**: A developer with no prior TRACE context can follow instructions, configure the environment, start the backend, and receive a successful `GET /health` HTTP 200 response within 30 minutes.

**Independent Test**:
```bash
# 1. Set up .env with local DB credentials
# 2. Start backend:
uv run uvicorn trace.main:app --reload
# 3. Verify health:
curl -s http://localhost:8000/health
# Expected: HTTP 200 with {"status":"healthy","version":"...","services":{...}}
```

### Implementation for User Story 1

- [X] T026 [US1] Create `backend/src/trace/api/health/schemas.py` defining `ServiceStatus(BaseModel)` with `status: Literal["reachable","unreachable","not_configured"]` and `HealthStatus(BaseModel)` with `status: Literal["healthy","degraded"]`, `version: str`, and `services: dict[str, ServiceStatus]`; add docstrings to both models
- [X] T027 [US1] Write `backend/tests/unit/test_health_schemas.py` asserting: `HealthStatus` serialises to the correct JSON structure; `ServiceStatus` rejects values outside the three valid literals; `HealthStatus` with `status="degraded"` serialises correctly; `version` field accepts `"unknown"` as a valid value
- [X] T028 [US1] Create `backend/src/trace/api/health/router.py` implementing `GET /health`; the router is created in this file AND registered into the top-level router in `backend/src/trace/api/router.py` (i.e., this task both creates the health router and performs the `api_router.include_router(health_router)` call that T025 left pending); the endpoint: reads probes from `app.state.db.health_check()` and `app.state.graph.health_check()`; populates `version` from `importlib.metadata.version("trace")` with `"unknown"` fallback (never raises); returns `JSONResponse(content=health_status.model_dump(), status_code=200)` when healthy and `status_code=503` when degraded; body always conforms to `HealthStatus` schema
- [X] T029 [US1] Write `backend/tests/api/test_health_200.py` using `httpx.AsyncClient(app=app, base_url="http://test")` with all stubs wired via FastAPI dependency override: DB stub returns `True`, graph stub returns `NOT_CONFIGURED`; assert HTTP 200; assert `response.json()["status"] == "healthy"`; assert `"version"` key present; assert response body contains no values matching known secret field names
- [X] T030 [US1] Write `backend/tests/api/test_health_503.py` with two scenarios: (a) DB stub returns `False` → assert HTTP 503 + `status="degraded"` + `services["postgres"]["status"]=="unreachable"`; (b) graph stub returns `UNREACHABLE` → assert HTTP 503 + `services["neo4j"]["status"]=="unreachable"`; in both cases assert response body conforms to `HealthStatus` schema (body always returned, even on 503)
- [X] T031 [US1] Write `backend/tests/api/test_health_version_fallback.py` mocking `importlib.metadata.version` to raise `PackageNotFoundError`; assert `response.json()["version"] == "unknown"`; assert HTTP status is still 200 (version fallback does not degrade health)
- [X] T032 [US1] Write `backend/tests/unit/test_config_empty_string.py` specifically exercising the empty-string-as-absent edge case with explicit env-var isolation: `DATABASE_URL=""` supplied directly → `ValidationError`; `NEO4J_URI=""` supplied directly → treated as `None` (optional field, no error); use `ApplicationConfig(_env_file=None, ...)` constructor to prevent reading from host environment

**Checkpoint** (T026–T032): `uv run pytest tests/unit/ tests/api/ -m "not integration"` all pass; `GET /health` returns HTTP 200 when all stubs are healthy; no live services needed.

---

## Phase 4: User Story 2 — Developer Runs the Test Suite Deterministically (P2)

**Goal**: A developer runs the default test command and receives a deterministic pass/fail result without connecting to any live external service.

**Independent Test**:
```bash
cd backend
uv run pytest -m "not integration" --cov=trace --cov-branch --cov-report=term-missing
# Expected: all tests pass; coverage report printed; exits code 0
# (80% enforcement is the Phase 7 release gate, not the daily development command)
```

### Implementation for User Story 2

- [X] T033 [US2] Verify pytest/coverage configuration behaviour **without modifying `pyproject.toml`** (T004 owns that file): (a) confirm `asyncio_mode = "auto"` is active by asserting an `async def test_...` function runs without `@pytest.mark.asyncio`; (b) confirm default run excludes integration-marked tests; (c) confirm `--cov=trace --cov-branch` produces a coverage report; (d) confirm that without `--cov-fail-under=80`, the default test command exits code 0 even if coverage is below 80% (the 80% gate is only at T051)
- [X] T034 [US2] Create `backend/tests/conftest.py` providing shared fixtures: `app_config_stub` (constructs `ApplicationConfig(_env_file=None, DATABASE_URL="postgresql+asyncpg://test:test@localhost/test", ...)` without reading host environment — the fixture MUST use `monkeypatch` or equivalent to ensure no host env variable can override stub values); `stub_db_gateway` (returns `InMemoryDatabaseGateway` or a simple stub that returns `True` from `health_check()`); `stub_graph_gateway` (returns a configurable `StubGraphGateway`); `stub_llm_provider` (returns `StubLLMProvider`); `async_test_client` (returns `httpx.AsyncClient(app=app, base_url="http://test")` with all stubs wired via FastAPI dependency override)
- [X] T035 [US2] Create `backend/tests/integration/__init__.py` and `backend/tests/integration/test_postgres_live.py` with a single `@pytest.mark.integration` test that runs `SQLAlchemyDatabaseGateway.health_check()` against a real PostgreSQL instance specified by `DATABASE_URL`; assert returns `True`
- [X] T036 [US2] Create `backend/tests/integration/test_neo4j_live.py` with a single `@pytest.mark.integration` test that runs `Neo4jGraphGateway.health_check()` against a real Neo4j instance specified by `NEO4J_URI`; assert returns `GraphConnectivityState.REACHABLE`
- [X] T037 [US2] Add `pytest-socket` to the dev dependencies (already in `pyproject.toml` T004) and configure it to **block all network access by default** in the test suite: add `@pytest.mark.usefixtures("socket_disabled")` globally in `conftest.py` or configure via `pytest.ini` equivalent `socket_allow_hosts = []`; any test that requires network access MUST explicitly mark itself with `@pytest.mark.usefixtures("socket_enabled")` or `@pytest.mark.integration`; run `uv run pytest -m "not integration"` and confirm it exits code 0 with no SocketBlockedError — proving all default tests are network-free

**Checkpoint** (T033–T037): Default test command exits code 0; integration tests excluded; `pytest-socket` confirms zero network calls in default run; live services not required.

---

## Phase 5: User Story 3 — Developer Understands the Architecture Boundaries (P3)

**Goal**: A developer unfamiliar with TRACE can identify the correct location for any concern (API route, domain model, infrastructure adapter, configuration value) by reading only the project documentation.

**Independent Test**: A reviewer reads `docs/architecture.md` and `docs/local-setup.md` and can correctly answer all four orientation questions without inspecting source files.

### Implementation for User Story 3

- [X] T038 [P] [US3] Create `docs/architecture.md` containing: the 5-layer diagram (API → Service → Domain → Ports → Adapters); a directory map of every `backend/src/trace/` subdirectory with its single-sentence responsibility; the layer-boundary rule ("no layer may import from a layer above it — specifically `api/` may import only `LLMProvider`/`DatabaseGateway`/`GraphGateway` Protocols, never the concrete adapters; `domain/` imports nothing from `trace/`"); a note that `main.py` is the **only** permitted location for concrete adapter instantiation (OpenRouterAdapter wired here only); a table of where each concern belongs; references to contract documents in `specs/001-phase0-project-foundation/contracts/`
- [X] T039 [P] [US3] Create `docs/local-setup.md` with step-by-step instructions: prerequisites (Python 3.12, uv, Docker); `uv sync`; copy `.env.example` to `.env`; fill in required variables; start backend natively with `uv run uvicorn trace.main:app --reload`; verify with `curl http://localhost:8000/health`; expected output including exact JSON shape; Docker Compose workflow: `docker compose up --build`
- [X] T040 [P] [US3] Create `docs/environment-variables.md` listing every variable in `.env.example` with: variable name, type, required/optional, default value, description; this document and `.env.example` must remain in sync (FR-046); any variable not consumed by `ApplicationConfig` must be annotated as optional/dev-only
- [X] T041 [P] [US3] Create `docs/testing.md` covering: default test command (`uv run pytest -m "not integration" --cov=trace --cov-branch`); what `@pytest.mark.integration` means and how to run integration tests; the Phase 0 release-gate command enforcing 80% coverage (`uv run pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80`); `ruff check`, `ruff format --check`, and `mypy src/` commands; expected clean-run output; note that `pytest-socket` blocks network by default
- [X] T042 [P] [US3] Create `docs/llm-configuration.md` covering: the free-first model policy (Constitution §VI); all four `LLM_*` model role variables and how they override application defaults; what `LLM_ENABLE_EXTERNAL_CALLS` controls; what `LLM_ENABLE_EXTERNAL_TRANSMISSION` controls and why it defaults to `false`; how to switch models by changing only env vars; how to add a new provider (implement `LLMProvider` Protocol + new adapter in `adapters/`; wire in `main.py` lifespan)
- [X] T043 [US3] Add docstrings and schema descriptions to all public interfaces listed below, and write `backend/tests/unit/test_public_interface_docs.py` as an objective automated verification asserting non-empty `__doc__` and `description` attributes: (a) `LLMProvider` Protocol (`complete`, `embed`); (b) `DatabaseGateway` Protocol (`session`, `health_check`); (c) `GraphGateway` Protocol (`health_check`); (d) relevant configuration and public contracts: `ApplicationConfig` (all fields documented via `Field(description="...")`), `HealthStatus` and `ServiceStatus` schemas (all fields documented via `Field(description="...")`), `LLMConfig`, `ModelConfig`, and `LLMResponse`; run `uv run pytest tests/unit/test_public_interface_docs.py` to confirm zero missing docstrings

**Checkpoint** (T038–T043): All five docs exist with non-placeholder content; `uv run pytest tests/unit/test_public_interface_docs.py` passes; `uv run mypy --strict src/trace/infrastructure/llm/provider.py` passes.

---

## Phase 6: User Story 4 — Operator Starts the Local Dev Environment via Docker (P4)

**Goal**: A developer or operator runs one command and the full local development stack (backend + PostgreSQL + Neo4j) starts in dependency order with health verification.

**Independent Test**:
```bash
# From repo root (with .env configured):
docker compose up --build
# Then in another terminal:
curl http://localhost:8000/health
# Expected: HTTP 200 with services.postgres="reachable" AND services.neo4j="reachable"
```

### Implementation for User Story 4

- [X] T044 [US4] Create `docker-compose.yml` at repo root with three services; credential values MUST come from environment variables only — no hardcoded values: (a) `postgres` using `image: postgres:16-alpine` with `healthcheck: {test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"], interval: 5s, timeout: 5s, retries: 5}`; (b) `neo4j` using `image: neo4j:5-community` with verified native healthcheck: `healthcheck: {test: ["CMD-SHELL", "cypher-shell -u ${NEO4J_USERNAME:-neo4j} -p ${NEO4J_PASSWORD:-password} 'RETURN 1'"], interval: 10s, timeout: 5s, retries: 5, start_period: 30s}` — this probe uses the native CLI pre-installed in the official image without assuming `curl`/`wget` availability; (c) `backend` with `build: ./backend`, `depends_on: {postgres: {condition: service_healthy}, neo4j: {condition: service_healthy}}`, `healthcheck: {test: ["CMD", "curl", "-f", "http://localhost:8000/health"], interval: 10s, timeout: 5s, retries: 5}`, and `env_file: .env`
- [X] T045 [US4] Verify `depends_on` conditions use Compose Spec v2 syntax with `condition: service_healthy`; update `docs/local-setup.md` Docker Compose section with: the single startup command, expected console output showing service health progression, and verification command `curl http://localhost:8000/health`

**Checkpoint** (T044–T045): `docker compose up --build` starts all three services in correct dependency order; backend `/health` returns HTTP 200 with both database services reachable.

---

## Phase 7: Polish — Static Quality, Security, Logging, and Release Verification

**Purpose**: Cross-cutting quality gates that span all user stories. All tasks in this phase are verification tasks — no new code should be required if all previous tasks were correctly implemented.

### Static Analysis (FR-030, SC-003)

- [X] T046 [P] Verify Ruff configuration **without modifying `pyproject.toml`** (depends on T004 canonical configuration): run `uv run ruff check src/ tests/` — fix any violations found in Phase 2–6 implementation; run `uv run ruff format --check src/ tests/` — fix any formatting violations; both commands MUST exit code 0
- [X] T047 [P] Verify mypy configuration **without modifying `pyproject.toml`** (depends on T004 canonical configuration): run `uv run mypy src/` — fix any type violations found in Phase 2–6 implementation; MUST exit code 0 with zero errors; ensure `pydantic.mypy` and `sqlalchemy.ext.mypy.plugin` are active per T004 configuration

### Security Verification (FR-010, FR-033, FR-045, FR-046, SC-005)

- [X] T048 [P] Verify `.gitignore` explicitly lists `.env` and that `git check-ignore -v .env` confirms the match; scan `*.py`, `*.toml`, `*.yml`, `*.yaml` for credential patterns (`api.key`, `sk-`, literal passwords); verify `.env.example` contains only placeholder values; add `backend/.gitignore` if needed for `__pycache__`, `.venv`
- [X] T049 Write `backend/tests/unit/test_logging_redaction.py` with two test scenarios: (a) **Redaction test** — configure structlog in test mode; bind a log event containing key `"api_key"` with value `"real-secret-123"`; capture rendered JSON output; assert output contains `"[REDACTED]"` not `"real-secret-123"`; assert no test health-check cycle emits raw API key values at any severity level; (b) **Structured binding test** — call `structlog.contextvars.bind_contextvars(project_id="proj-123", analysis_run_id="run-456")`; emit a log event; capture rendered JSON output; assert `"project_id": "proj-123"` and `"analysis_run_id": "run-456"` appear in the output — this verifies FR-032 (named context fields are actually bindable and appear in output, not merely declared)
- [X] T050 [P] Write `backend/tests/unit/test_transmission_gate.py`: construct `OpenRouterAdapter(config=stub_config_with_transmission_disabled, http_client=mock_httpx_client)`; call `adapter.complete(prompt="def main(): pass", model=stub_model_config, config=stub_llm_config)`; assert return value is `ConfigurationError`; assert the mock `httpx.AsyncClient.send` was never called; assert a `WARNING` log event was emitted containing `"provider"` and `"content_bytes"` keys; assert log event does NOT contain the prompt content

### Coverage Gate Verification (FR-042, SC-009)

- [X] T051 Run the explicit Phase 0 release-gate command: `uv run pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80 --cov-report=term-missing`; this is the **only** command that enforces 80% — it is NOT part of the daily development `addopts`; if coverage is below 80%, add targeted tests for uncovered branches in `trace/core/config.py` or `trace/infrastructure/`; the command MUST exit code 0 before Phase 0 is declared complete

### Final Integration Verification (quickstart.md Scenarios 1–10)

*Note: Scenarios 1–10 share a single local environment (port 8000 / Docker network). Execute sequentially.*

- [X] T052 Execute Quickstart Scenario 1: fresh `uv sync` + `cp .env.example .env` + fill values + `uv run uvicorn trace.main:app` → confirm backend starts without errors and logs show structured output
- [X] T053 Execute Quickstart Scenario 2: `curl -s http://localhost:8000/health` → confirm HTTP 200 + correct `HealthStatus` schema
- [X] T054 Execute Quickstart Scenario 3: set `DATABASE_URL` to unreachable host → restart backend → confirm HTTP 503 + `status="degraded"` + application did not crash on startup
- [X] T055 Execute Quickstart Scenario 4: `DATABASE_URL="" uv run uvicorn trace.main:app` → confirm non-zero exit + error message identifying `DATABASE_URL` as the missing variable
- [X] T056 Execute Quickstart Scenario 5: full default pytest command (`uv run pytest -m "not integration" --cov=trace --cov-branch`) → confirm all tests pass + coverage report printed + elapsed < 2 minutes + exit code 0
- [X] T057 Execute Quickstart Scenario 6: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/` → all three exit code 0
- [X] T058 Execute Quickstart Scenario 7: `docker compose up --build` → all services healthy; backend `/health` returns HTTP 200 with both database services reachable
- [X] T059 Execute Quickstart Scenario 8: `uv run alembic upgrade head` → exits code 0; `uv run alembic current` shows baseline revision; confirm no domain tables exist (only `alembic_version`)
- [X] T060 Execute Quickstart Scenario 9: `git check-ignore -v .env` confirms match; `git grep -E "(api[_-]?key|password|sk-)" -- "*.py" "*.toml" "*.yml"` returns no matches in source files
- [X] T061 Execute Quickstart Scenario 10: run the three boundary grep checks: (a) `grep -r "from trace.infrastructure" src/trace/domain/` → zero matches; (b) `grep -r "from trace.infrastructure.llm.adapters" src/trace/api/` → zero matches; (c) `grep -r "openrouter.ai" src/` → exactly one match in `adapters/openrouter.py`
- [X] T062 Document Phase 0 completion verification: in `docs/local-setup.md` (or a dedicated `docs/phase0-verification.md`), add a "Phase 0 Release Gate" section listing each success criterion SC-001 through SC-009 and confirming the exact verification command used to demonstrate each is met; do NOT imply any criterion is met unless the corresponding verification command has actually passed; also list the 50 functional requirements FR-001 through FR-050 as a coverage summary table referencing the tasks that satisfy each (Constitution §XVII — No Fabricated Implementation State); do NOT create a `PHASE0-COMPLETE.md` file at repo root
- [X] T063 [P] Update root `README.md` with accurate content: project status (Phase 0 complete), quickstart commands (`uv sync`, `cp .env.example .env`, `uv run uvicorn trace.main:app --reload`, `curl http://localhost:8000/health`), link to `docs/local-setup.md`, link to `docs/phase0-verification.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — **BLOCKS** all user stories; T004 must be committed before any Phase 2 Python work begins
  - Internal: T008→T009→T010→T011; T012; T013→T014; T015→T016→T017→T018 (T018 depends T017); T019→T020; T021→T022; T023; T024→T025
- **Phase 3 (US1 — P1)**: Depends on Phase 2 complete — no dependency on Phase 4/5/6
- **Phase 4 (US2 — P2)**: Depends on Phase 2 complete — can run in parallel with Phase 3
- **Phase 5 (US3 — P3)**: Depends on Phase 2 complete — can run in parallel with Phase 3/4
- **Phase 6 (US4 — P4)**: Depends on Phase 2 AND Phase 3 (needs `GET /health` route from T028) — can start after T028
- **Phase 7 (Polish)**: Depends on all previous phases complete

### T004 Ownership Rule

`backend/pyproject.toml` is created and fully configured by T004 in Phase 1.
No subsequent task (T033, T046, T047, or any other) may add new sections, modify existing sections, or create the file again. If implementation reveals a missing dependency or config value, the correction is applied to T004 and the lock file regenerated via T007.

### Within Phase 2 (Internal Dependencies)

```
T008 → T009 → T010 → T011    (config chain)
T012                          (logging, independent)
T013 → T014 → T023           (domain enums → graph gateway)
T015 → T016 → T017 → T018    (LLM stack; T018 depends T017 — [P] intentionally absent)
T019 → T020                  (adapter depends T017; T020 parallel after T019)
T021 → T022                  (DB gateway + Alembic)
T025                          (empty router skeleton, independent)
T024 ← (T009, T021, T023, T025 all must exist first)
```

### Within Phase 3 (US1)

```
T026 → T027 (parallel after T026)
T028        (depends T026 schemas AND T025 router skeleton)
T029        (depends T028)
T030        (depends T028)
T031        (depends T028)
T032        (parallel with T027)
```

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no US dependencies
- **US2 (P2)**: Can start after Phase 2 — no US dependencies
- **US3 (P3)**: Can start after Phase 2 — no US dependencies; docs can be written as implementation proceeds
- **US4 (P4)**: Depends on US1 complete (needs `GET /health` from T028)

---

## Parallel Opportunities

### Parallelisable within Phase 2

```
Stream A: T008 → T009 → T010 → T011 → T024
Stream B: T012 (logging, independent)
Stream C: T013 → T014 → T023
Stream D: T015 → T016 → T017 → T018 → T019 → T020
Stream E: T021 → T022
Stream F: T025 (empty router skeleton, independent)
```

### Parallelisable User Story Phases

```
After Phase 2 complete:
Developer A → Phase 3 (US1) → then Phase 6 (US4) after T028
Developer B → Phase 4 (US2)
Developer C → Phase 5 (US3 docs)
```

### Phase 7 Parallelisable

T046, T047, T048, T050 may run in parallel (different files, no shared state).
T049 may run in parallel with T046/T047/T048/T050.
T052–T061 are sequential (shared port 8000 / Docker environment). T062 and T063 may run in parallel (different files).

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete **Phase 1** (T001–T007) — especially T004 (canonical pyproject.toml)
2. Complete **Phase 2** (T008–T025) — all foundation infrastructure
3. Complete **Phase 3** (T026–T032) — health endpoint + US1 tests
4. **STOP AND VALIDATE**: `curl http://localhost:8000/health` → HTTP 200; unit tests pass
5. Phase 0 MVP is functional — proceed to US2/US3/US4

### Incremental Delivery

1. Phase 1 → Phase 2 → Foundation verified
2. Phase 3 (US1) → `GET /health` working, native backend startable → **MVP**
3. Phase 4 (US2) → Deterministic test suite; network isolation proven
4. Phase 5 (US3) → Documentation complete → Developer can onboard independently
5. Phase 6 (US4) → Docker Compose stack operational
6. Phase 7 → Release gate: 80% coverage enforced; all quickstart scenarios pass

---

## Notes

- `[P]` tasks = can be executed concurrently with other `[P]` tasks (operate on different files, no shared state)
- `[USn]` label maps task to a specific user story from `spec.md`
- **T004 is the sole owner of `backend/pyproject.toml`** — no other task creates or modifies it
- T018 has no `[P]` marker because it depends on T017 completing first
- T052–T061 have no `[P]` marker because they share a single running local environment (port 8000/Docker); execute sequentially
- All tasks must be verified with a concrete command before marking `[x]`
- Do not mark any task complete until its checkpoint command actually passes (Constitution §XVII)
- The 80% coverage gate appears ONLY in T051 (and verified at quickstart release Scenario 5 in T056) — it is a release gate, not a daily development check
- Integration tests (`@pytest.mark.integration`) are written in Phase 4 but excluded from the default run by `pytest-socket` and `-m "not integration"`
- `pytest-socket` blocks all network access by default — any test that inadvertently opens a socket will fail immediately, making live-service dependency visible
