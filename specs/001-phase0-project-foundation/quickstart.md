# Quickstart Validation Guide: TRACE Phase 0

**Branch**: `001-phase0-project-foundation` | **Date**: 2026-09-25

This guide describes how to validate that Phase 0 is complete. Each scenario proves a
specific acceptance criterion from the spec. All scenarios must pass before Phase 0 is
declared done.

---

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | ≥ 3.12 | `python --version` |
| `uv` | ≥ 0.4 | `uv --version` |
| Docker + Docker Compose v2 | ≥ 20.10 | `docker compose version` |
| `curl` | any | `curl --version` |

---

## Scenario 1 — Install and Configure (SC-001: 30-minute onboarding)

**Purpose**: Proves a new developer can go from clone to running in ≤30 minutes.

```bash
# 1. Clone and enter the repository
git clone <repo-url> TRACE && cd TRACE

# 2. Enter the backend directory
cd backend

# 3. Install all dependencies (should complete in <30 seconds)
uv sync

# 4. Copy the example env file and fill in local values
cp ../.env.example ../.env
# Edit ../.env — set DATABASE_URL to your local PostgreSQL instance
# All other values can remain as placeholders for this test

# 5. Start the backend natively (requires local PostgreSQL running)
uv run uvicorn trace.main:app --reload
```

**Expected**: Backend starts without errors. Logs show structured output. No exception printed.

---

## Scenario 2 — Health Endpoint Returns 200 (SC-001, SC-004)

**Purpose**: Proves `GET /health` returns HTTP 200 with correct schema when services are healthy.

```bash
# With backend running (Scenario 1 or Scenario 6):
curl -s http://localhost:8000/health | python -m json.tool
```

**Expected response** (HTTP 200):
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgres": { "status": "reachable" },
    "neo4j": { "status": "not_configured" }
  }
}
```

**Validation checks**:
- HTTP status code is `200`
- `status` is `"healthy"`
- `version` is not `null` and not empty (may be `"unknown"` in dev mode)
- `services.postgres.status` is `"reachable"`
- Response contains no API keys, passwords, or connection strings

---

## Scenario 3 — Health Returns 503 on Degraded Service (SC-004)

**Purpose**: Proves the health endpoint reports degraded status with HTTP 503 when PostgreSQL
is unreachable (not fabricated).

```bash
# Set DATABASE_URL to an unreachable host in .env:
# DATABASE_URL=postgresql+asyncpg://user:pass@unreachable-host:5432/trace

uv run uvicorn trace.main:app
curl -v http://localhost:8000/health
```

**Expected**:
- HTTP status: `503`
- Response body:
```json
{
  "status": "degraded",
  "version": "0.1.0",
  "services": {
    "postgres": { "status": "unreachable" },
    "neo4j": { "status": "not_configured" }
  }
}
```
- Application started (did not crash on startup despite DB being unreachable)

---

## Scenario 4 — Missing Required Config Fails at Startup (FR-004)

**Purpose**: Proves the application fails fast with a clear error when a required variable
is absent.

```bash
# Unset DATABASE_URL in your shell:
DATABASE_URL="" uv run uvicorn trace.main:app
```

**Expected**:
- Application exits with a non-zero code before accepting any connections
- Error message identifies `DATABASE_URL` as the missing variable
- Application does NOT start in a silently broken state

---

## Scenario 5 — Test Suite & Coverage Gate Passes (SC-002, SC-003, FR-042, SC-009)

**Purpose**: Proves the deterministic test suite passes in <2 minutes without any live external service, and enforces the ≥80% coverage gate at release.

```bash
cd backend

# Default test suite (no live services required; network blocked by pytest-socket)
uv run pytest -m "not integration" \
    --cov=trace \
    --cov-branch \
    --cov-report=term-missing

# Explicit Phase 0 Release Gate command (enforces 80% minimum coverage)
uv run pytest -m "not integration" \
    --cov=trace \
    --cov-branch \
    --cov-fail-under=80 \
    --cov-report=term-missing
```

**Expected**:
- All tests pass (exit code 0)
- Intermediate runs measure coverage without failing solely for sub-80% coverage
- Release gate command confirms coverage ≥ 80% (fails if below threshold)
- Elapsed time < 2 minutes
- Zero network connections made (enforced deterministically by `pytest-socket`)

**Key tests that must pass** (see [plan.md §Testing Strategy](../plan.md)):
1. Config: required variable absent → `ValidationError`
2. Config: empty string for required field → `ValidationError`
3. Config: test environment isolation → ambient host env vars do not leak into test config
4. Health 200: all stubs healthy → HTTP 200 + correct schema
5. Health 503: DB stub returns `False` → HTTP 503
6. Health 200: Neo4j stub returns `NOT_CONFIGURED` → HTTP 200
7. LLM: all four `LLMResponse` error states returned without exception
8. LLM: `LLM_DEFAULT_MODEL` overrides default model; preserves `mistralai/mistral-7b-instruct:free` when unset
9. Logging: `structlog.contextvars.bind_contextvars()` binds `project_id` and `analysis_run_id` into JSON output; secrets are redacted
10. Version fallback: `importlib.metadata` unavailable → `version = "unknown"`

---

## Scenario 6 — Static Analysis Passes (SC-003)

**Purpose**: Proves zero linting, formatting, and type violations.

```bash
cd backend

# Lint (zero violations expected)
uv run ruff check src/ tests/

# Format check (zero violations expected)
uv run ruff format --check src/ tests/

# Type check (zero violations expected)
uv run mypy src/
```

**Expected**: All three commands exit with code 0 and produce no violation output.

---

## Scenario 7 — Docker Stack Starts (SC-007)

**Purpose**: Proves the full local development stack starts with a single command after
environment configuration.

```bash
# From repo root:
cp .env.example .env
# Edit .env — fill in POSTGRES_PASSWORD and other required values

docker compose up --build
```

**Expected**:
- All three services (`postgres`, `neo4j`, `backend`) start without manual intervention
- PostgreSQL healthcheck (`pg_isready`) passes before backend starts
- Neo4j healthcheck (verified native `cypher-shell`) passes before backend starts
- Backend logs show "Application startup complete" or equivalent

**Verify backend health through Docker network**:
```bash
curl http://localhost:8000/health
```

**Expected**: HTTP 200 with `HealthStatus` body showing both services connected.

---

## Scenario 8 — Alembic Migrations Run (FR-020)

**Purpose**: Proves the migration mechanism is configured and the baseline migration runs.

```bash
cd backend

# Apply migrations (requires live PostgreSQL)
uv run alembic upgrade head

# Verify current migration state
uv run alembic current
```

**Expected**:
- `alembic upgrade head` completes without error
- `alembic current` shows `0001_baseline` (or equivalent revision ID)
- No domain tables are created (only `alembic_version` table)

---

## Scenario 9 — No Secrets in Committed Files (SC-005)

**Purpose**: Proves `.env` cannot be committed and no secrets exist in the codebase.

```bash
# From repo root:

# Verify .env is gitignored
git check-ignore -v .env
# Expected: output shows .env matches a .gitignore rule

# Verify no API keys, passwords, or tokens in committed files
git grep -i "api.key\|password\|secret\|token\|sk-" -- '*.py' '*.toml' '*.yml' '*.yaml' '*.env.example'
# Expected: no matches in source files; .env.example contains only placeholder values
```

**Expected**:
- `.env` is gitignored (cannot be accidentally committed)
- No real secret values in any committed file
- `.env.example` contains only placeholder strings (e.g., `your-api-key-here`)

---

## Scenario 10 — Architecture Boundary Verification (SC-008)

**Purpose**: Proves each layer's code is in the correct directory and no cross-layer imports exist.

```bash
cd backend

# Verify no domain/ code imports infrastructure/
grep -r "from trace.infrastructure" src/trace/domain/
# Expected: no matches

# Verify no api/ code imports adapters directly
grep -r "from trace.infrastructure.llm.adapters" src/trace/api/
# Expected: no matches

# Verify openrouter.py is the only file containing the OpenRouter URL
grep -r "openrouter.ai" src/
# Expected: only src/trace/infrastructure/llm/adapters/openrouter.py matches
```

---

## Completion Gate

Phase 0 is complete when ALL of the following are true:

| Check | Scenario | Status |
|---|---|---|
| Backend starts natively | 1 | |
| `GET /health` → HTTP 200 | 2 | |
| `GET /health` → HTTP 503 on degraded service | 3 | |
| Missing config → startup failure | 4 | |
| Test suite passes with ≥80% coverage | 5 | |
| ruff + mypy zero violations | 6 | |
| Docker stack starts with one command | 7 | |
| Alembic baseline migration runs | 8 | |
| No secrets in committed files | 9 | |
| Layer boundary rules verified | 10 | |

All checks must be manually verified and marked complete before Phase 0 is declared done
(Constitution §XVII — No Fabricated Implementation State).

---

## References

- [spec.md](spec.md) — Phase 0 specification and acceptance criteria
- [plan.md](plan.md) — Implementation plan and architecture decisions
- [data-model.md](data-model.md) — Entity and interface definitions
- [contracts/api.md](contracts/api.md) — `GET /health` HTTP contract
- [contracts/llm-provider.md](contracts/llm-provider.md) — `LLMProvider` interface contract
- [contracts/db-gateway.md](contracts/db-gateway.md) — `DatabaseGateway` interface contract
- [contracts/graph-gateway.md](contracts/graph-gateway.md) — `GraphGateway` interface contract
