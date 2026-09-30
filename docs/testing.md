# TRACE Testing Guide

## 1. Testing Philosophy

TRACE tests are designed to be **deterministic, fast, and completely offline by default** (Constitution §IX).
All external boundaries (PostgreSQL, Neo4j, OpenRouter API) are substituted with in-memory test doubles during standard test runs.

---

## 2. Standard Development Test Command

Run the complete offline test suite with branch coverage measurement:
```bash
cd backend
uv run pytest -m "not integration" --cov=trace --cov-branch --cov-report=term-missing
```

### Network Isolation via `pytest-socket`
- The test suite uses `pytest-socket` to strictly block external network socket creation during the default test run.
- Any attempt by production code or tests to open an unauthorized external socket immediately fails with `SocketConnectBlockedError`.
- No live external services or internet access are required to execute default tests.

---

## 3. Integration Tests (`@pytest.mark.integration`)

Tests that verify connectivity against live, running infrastructure services (e.g. Docker containers) are decorated with `@pytest.mark.integration`:
- `tests/integration/test_postgres_live.py`: Tests real connection to PostgreSQL.
- `tests/integration/test_neo4j_live.py`: Tests real connection to Neo4j.

To run integration tests (requires live services running and environment variables configured):
```bash
uv run pytest -m "integration"
```

---

## 4. Phase 0 Release Gate (80% Coverage Enforcement)

During normal day-to-day development, `--cov-fail-under=80` is **not** present in global `pytest.ini_options` to allow iterative development.
However, before release or merging, the Phase 0 Release Gate command **must** be executed:
```bash
uv run pytest -m "not integration" --cov=trace --cov-branch --cov-fail-under=80 --cov-report=term-missing
```
If overall branch + line coverage is below 80%, this command exits with a non-zero exit code (FR-042, SC-009).

---

## 5. Static Analysis and Type Verification

All code must pass strict linting, formatting, and type-checking without violations (FR-030, SC-003):

### Linting Check:
```bash
uv run ruff check src/ tests/
```

### Formatting Check:
```bash
uv run ruff format --check src/ tests/
```

### Static Type Checking:
```bash
uv run mypy src/ tests/
```
Expected output: `Success: no issues found in XX source files`.
