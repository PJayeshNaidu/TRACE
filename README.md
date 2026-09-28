# TRACE — Transformation Risk Analysis & Change Evaluation

TRACE is an AI-powered software change-impact and upgrade analysis platform designed to understand how changes in a software system propagate through its architecture, dependencies, APIs, databases, services, tests, configuration, and documentation.

## Status: Phase 0 (Project Foundation) Complete & Verified

Phase 0 establishes the complete foundational architecture and developer tooling for TRACE:
- **FastAPI Application**: Asynchronous backend skeleton with lifespan lifecycle management.
- **Typed Central Configuration**: Strict schema validation via `pydantic-settings` with safe defaults and free-first LLM policies.
- **Structured Observability**: High-performance JSON logging with `structlog`, contextual metadata binding, and automatic credential redaction.
- **Replaceable Storage Boundaries**:
  - Relational database gateway backed by SQLAlchemy 2.x async engine with `asyncpg` and Alembic baseline migrations.
  - Structural graph gateway wrapping the official async Neo4j driver without leaking vendor types.
- **Vendor-Isolated LLM Provider**: Runtime-checkable `LLMProvider` Protocol, OpenRouter adapter via raw `httpx`, and a security transmission gate blocking external repository transmission by default.
- **Deterministic Quality Gates**: Offline test suite protected by `pytest-socket`, 90%+ branch and line coverage exceeding the 80% release gate, and zero violations on `ruff` and `mypy` strict checks.
- **Local Container Stack**: Docker Compose configuration running PostgreSQL 16, Neo4j 5, and backend with native container health checks.

Verification report: [docs/phase0-verification.md](docs/phase0-verification.md).

---

## Quickstart

### Prerequisites
- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) (Python package manager, ≥ 0.4.0)
- Docker & Docker Compose (optional for local multi-service testing)

### Local Native Execution
```bash
# 1. Clone repository and navigate to backend
git clone <repo-url> TRACE
cd TRACE/backend

# 2. Install dependencies via uv
uv sync --extra dev

# 3. Configure local environment
cp ../.env.example .env
# Edit .env with your local PostgreSQL and Neo4j connection strings

# 4. Run baseline database migration
uv run alembic upgrade head

# 5. Start development server
uv run uvicorn trace.main:app --reload

# 6. Verify system health
curl http://localhost:8000/health
```

### Running the Test Suite
```bash
cd backend

# Default deterministic test run (offline, unit + API):
uv run pytest -m "not integration" --cov=trace --cov-branch

# Explicit Phase 0 Release Gate command (enforcing >=80% coverage):
uv run pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80 --cov-report=term-missing

# Static analysis and linting:
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

### Docker Compose Stack
```bash
# From repository root:
cp .env.example .env
docker compose up --build -d

# Verify health:
curl http://localhost:8000/health
```

---

## Documentation

- [Phase 0 Verification & Release Gate Report](docs/phase0-verification.md)
- [Local Setup Guide](docs/local-setup.md)
- [Architecture Overview & Layer Boundaries](docs/architecture.md)
- [Environment Variables Reference](docs/environment-variables.md)
- [Testing Guide & Quality Gates](docs/testing.md)
- [LLM Configuration & Free-First Policy](docs/llm-configuration.md)
- [Technical Implementation Plan](specs/001-phase0-project-foundation/plan.md)
