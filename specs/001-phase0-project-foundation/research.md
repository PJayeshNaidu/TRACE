# Research: TRACE Phase 0 — Technical Decisions

**Branch**: `001-phase0-project-foundation` | **Date**: 2026-09-25

All decisions below are resolved from: the TRACE master specification, project constitution,
the Phase 0 specification, clarification sessions, and established Python/FastAPI ecosystem
knowledge as of 2025-2026. No external research agent was required; all decisions were
deterministic given the fully-specified clarifications.

---

## 1. Python Version

**Decision**: Python 3.12

**Rationale**:
- Current stable release with full upstream support through 2028.
- Introduces significant performance improvements over 3.11 (~25% interpreter speedup).
- `tomllib` in stdlib; improved typing with `TypeAlias`, `Self`, `ParamSpec` built-in.
- Native `match` statement for pattern-matching `LLMResponse` discriminated union states.
- Broad compatibility with FastAPI ≥0.111, SQLAlchemy 2.x, LangGraph 0.2+, neo4j ≥5.x.

**Alternatives considered**:
- Python 3.11: Safe but misses performance improvements; no compelling reason to stay back.
- Python 3.13: Too new for stable LangGraph and neo4j async driver compatibility as of mid-2026.

---

## 2. Package Management

**Decision**: `uv` + `pyproject.toml` + committed `uv.lock`

**Rationale**:
- `uv` installs in sub-second time compared to pip (10–100× faster).
- `uv.lock` is committed for fully reproducible installs in CI and Docker.
- PEP 517/518 compliant; `pyproject.toml` is the single source of all project metadata.
- `uv run` prefix executes commands in the managed virtual environment without activation.

**Alternatives considered**:
- `Poetry`: Mature but significantly slower than uv; `poetry.lock` format is proprietary.
- `pip` + `requirements.txt`: No lock file without `pip-tools`; lacks `pyproject.toml` integration.
- `pip-tools`: Lock file support but still pip-speed installs; two-file overhead.

---

## 3. LLM Provider Abstraction

**Decision**: `Protocol` (structural subtyping) for `LLMProvider` interface

**Rationale**:
- Python 3.12 `Protocol` requires no explicit inheritance — any class with matching methods
  satisfies the protocol. This makes test stubs trivially simple (no ABC import required).
- `isinstance()` checks work with `@runtime_checkable` decorator if needed.
- Cleaner than ABC for interface-only contracts with no shared implementation.

**Alternatives considered**:
- `ABC` + `abstractmethod`: Requires explicit inheritance; heavier than needed for a pure interface.
- Duck typing (no Protocol): Loses mypy type safety; violations only caught at runtime.

**Decision**: `LLMResponse` discriminated union using `dataclasses` + `Literal` type tags

**Rationale**:
- Dataclasses are lightweight (no Pydantic overhead for internal types).
- `Literal["success"]`, `Literal["configuration_error"]`, etc. allow `mypy` to narrow the
  type in `match` blocks without runtime overhead.
- Python 3.12 `match` statement is the canonical pattern-match mechanism.

**Alternatives considered**:
- Pydantic union with discriminator: Heavier; Pydantic is for API layer, not internal domain types.
- Plain `typing.Union`: Less ergonomic; no exhaustiveness checking.

**Decision**: `httpx.AsyncClient` as singleton, created in FastAPI lifespan

**Rationale**:
- A shared `AsyncClient` instance reuses connection pools across requests (vs per-request client).
- FastAPI lifespan events (async context manager pattern) are the idiomatic way to manage
  shared resources since FastAPI 0.95.
- Injected via `app.state` and passed to the `OpenRouterAdapter` at startup.

**Decision**: Default free model = `mistralai/mistral-7b-instruct:free`

**Rationale**:
- Confirmed free-tier availability on OpenRouter (`:free` suffix models have no token billing).
- 7B parameter open-weight model with broad instruction-following capability.
- Sufficient for Phase 0 (no actual LLM calls made in Phase 0).
- Configurable: `LLM_DEFAULT_MODEL` overrides at any time.

**Alternatives considered**:
- `meta-llama/llama-3.1-8b-instruct:free`: Also free; switch is trivial via config.
- Any other `:free` model on OpenRouter: Config-driven, no code change required.

**Decision**: `tenacity` for retry logic in `OpenRouterAdapter`

**Rationale**:
- Declarative retry/backoff without a vendor SDK.
- Supports jitter, exponential backoff, per-exception retry conditions.
- Retry only on `ProviderError` (5xx); never retry `ConfigurationError` or `TimeoutError`.

---

## 4. PostgreSQL / SQLAlchemy / Alembic

**Decision**: SQLAlchemy 2.x async ORM + `asyncpg` driver

**Rationale**:
- SQLAlchemy 2.x provides native `async` engine and session (`AsyncEngine`, `AsyncSession`).
- `asyncpg` is the fastest Python async PostgreSQL driver with no GIL contention.
- Connection string format: `postgresql+asyncpg://user:pass@host:5432/dbname`
- SQLAlchemy ORM mapped classes (2.x `MappedColumn` style) will be used for Phase 1+ entities;
  Phase 0 uses only the engine and session factory with no mapped tables.

**Decision**: FastAPI lifespan event for engine lifecycle

**Rationale**:
- FastAPI's `@asynccontextmanager` lifespan is the current idiomatic pattern
  (replaces deprecated `startup`/`shutdown` events since FastAPI 0.95).
- Engine is created once, disposed on shutdown.

**Decision**: Alembic with async env.py

**Rationale**:
- Alembic is the only production-grade migration tool for SQLAlchemy.
- Async engines require the `asyncio.run(run_async_upgrade())` pattern in `env.py`.
- Phase 0 creates a single empty baseline migration (`0001_baseline.py`) that stamps
  the `alembic_version` table without creating any domain tables.

**Decision**: Health probe = `SELECT 1` via SQLAlchemy `text()`

**Rationale**:
- Minimal query; completes in <1ms; verifies connection pool is live.
- Executed in `async with engine.connect() as conn: await conn.execute(text("SELECT 1"))`.
- Wrapped in `try/except Exception`; returns `True`/`False`, never raises.

**Decision**: Test double = SQLite in-memory via `aiosqlite`

**Rationale**:
- `create_async_engine("sqlite+aiosqlite:///:memory:")` provides an async-compatible
  in-memory database that satisfies the `DatabaseGateway` Protocol.
- Requires `aiosqlite` as a dev dependency.
- Unit tests never connect to real PostgreSQL.

---

## 5. Neo4j

**Decision**: `neo4j` Python driver 5.x async session (`AsyncGraphDatabase.driver()`)

**Rationale**:
- Only production-grade driver for Neo4j; implements Bolt protocol.
- Async session support native in driver 5.x.
- `AsyncDriver.verify_connectivity()` provides a no-Cypher health probe.

**Decision**: Health probe = `driver.verify_connectivity()`

**Rationale**:
- No Cypher query required; validates Bolt connection and auth.
- Returns `None` on success; raises `ServiceUnavailable` or `AuthError` on failure.
- Wrapped in `try/except`; maps to `GraphConnectivityState.REACHABLE` or `UNREACHABLE`.

**Decision**: Docker healthcheck for Neo4j = HTTP probe on port 7474

**Rationale**:
- Neo4j community image exposes an HTTP discovery API on port 7474.
- `wget -q -O - http://localhost:7474` returns JSON on success.
- More reliable than Cypher-based checks at container startup.

---

## 6. Logging

**Decision**: `structlog` configured for JSON (production/test) + key-value (development)

**Rationale**:
- `structlog` is the dominant structured logging library for Python.
- `APP_ENV=production|test` → JSON renderer; `APP_ENV=development` → `ConsoleRenderer`.
- `BoundLogger` context binding (`structlog.contextvars`) enables per-request field injection.
- Redaction processor runs before any renderer to strip secret field values.

**Decision**: Redaction via custom `structlog` processor

**Rationale**:
- A `SecretRedactingProcessor` inspects every event dict before rendering.
- If a key matches `SECRET_FIELDS`, value is replaced with `"[REDACTED]"`.
- Runs unconditionally at any log level — no bypass possible.

---

## 7. Configuration

**Decision**: `pydantic-settings` with `BaseSettings`

**Rationale**:
- Type-validated at import time; raises `ValidationError` with field-level messages on missing values.
- Supports `.env` file loading out of the box.
- `model_validator(mode="before")` implements the empty-string-as-absent rule.
- `SecretStr` type masks values in `repr()` output to prevent accidental logging.

**Decision**: `LLM_ENABLE_EXTERNAL_CALLS` and `LLM_ENABLE_EXTERNAL_TRANSMISSION` default to `False`

**Rationale**:
- Opt-out defaults for both flags: system is safe by default with no external LLM calls or
  source-code transmission, even if the env var is absent.
- `pydantic-settings` `Field(default=False)` implements this without special handling.

---

## 8. Testing Framework

**Decision**: `pytest` + `pytest-asyncio` (auto mode) + `httpx.AsyncClient` + `pytest-cov` + `pytest-socket`

**Rationale**:
- `pytest-asyncio` in `asyncio_mode = "auto"` (configured in `pyproject.toml`) eliminates
  the need for `@pytest.mark.asyncio` decorators on every async test.
- `httpx.AsyncClient(app=app, base_url="http://test")` provides a zero-network ASGI test client.
- `pytest-cov` measures coverage across development; `--cov-fail-under=80` enforces the 80% gate at the explicit Phase 0 release gate verification.
- `pytest-socket` disables external network access by default to ensure deterministic offline execution.

**Decision**: `aiosqlite` as dev dependency for SQLite async test double

**Rationale**:
- Enables `create_async_engine("sqlite+aiosqlite:///:memory:")` for `DatabaseGateway` tests.
- Only installed in `[dev]` optional group; not in production dependencies.

---

## 9. Linting and Type Checking

**Decision**: `ruff` (lint + format) + `mypy` (strict mode)

**Rationale**:
- `ruff` replaces `flake8`, `isort`, `pyupgrade`, `pydocstyle`, and `black` in a single tool.
- Configuration in `pyproject.toml` under `[tool.ruff]`.
- `mypy` with `--strict` catches missing return types, implicit `Any`, and untyped imports.
- `mypy` plugins: `pydantic.mypy` and `sqlalchemy.ext.mypy.plugin` for correct inference.

---

## 10. Docker

**Decision**: Docker Compose v2 (`docker compose`) with `condition: service_healthy`

**Rationale**:
- `condition: service_healthy` in `depends_on` is only available in Compose Spec (v2 format).
- Requires Docker Engine ≥20.10 and Docker Compose ≥2.1.
- No Compose v1 (`docker-compose` legacy binary) support required.

**Decision**: Backend healthcheck = `curl -f http://localhost:8000/health || exit 1`

**Rationale**:
- `curl -f` returns exit code 22 on non-2xx HTTP responses.
- Available in the `python:3.12-slim` base image without additional installation.
- Simple and correct: verifies the actual FastAPI health endpoint.

---

## Unresolved Items

None. All Phase 0 technical decisions are resolved. No `NEEDS CLARIFICATION` items remain.
