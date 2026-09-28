# Contract: DatabaseGateway Interface — Phase 0

**Version**: 0.1.0 | **Phase**: 0 | **Date**: 2026-09-25

This document defines the `DatabaseGateway` interface contract through which all
relational (PostgreSQL) database operations flow. No code outside
`trace/infrastructure/database/` MUST import SQLAlchemy directly (Constitution §VIII, §XIV).

---

## Interface Definition

**Module**: `trace/infrastructure/database/gateway.py`

**Mechanism**: Python `Protocol` (structural subtyping, PEP 544)

```python
from typing import Protocol, AsyncContextManager, runtime_checkable
from sqlalchemy.ext.asyncio import AsyncSession

@runtime_checkable
class DatabaseGateway(Protocol):
    def session(self) -> AsyncContextManager[AsyncSession]: ...
    async def health_check(self) -> bool: ...
```

---

## Operation Contracts

### `session() → AsyncContextManager[AsyncSession]`

Returns an async context manager that yields a SQLAlchemy `AsyncSession`.

**Usage pattern**:
```python
async with gateway.session() as db:
    result = await db.execute(query)
```

**Guarantees**:
1. Each call returns a fresh session (not a shared singleton).
2. The session is committed (or rolled back on exception) before the context exits.
3. MUST NOT hold a connection open outside the `async with` block.

---

### `health_check() → bool`

Executes a minimal connectivity probe against the database.

**Returns**: `True` if the database is reachable; `False` if unreachable.

**Guarantees**:
1. MUST NOT raise any exception to the caller — all errors are caught internally.
2. MUST execute an actual network probe (`SELECT 1` or equivalent), not return a cached state.
3. MUST complete within the configured database timeout.
4. Logs the exception internally at `WARNING` level before returning `False`.

---

## Known Implementations

| Implementation | Module | Use |
|---|---|---|
| `SQLAlchemyDatabaseGateway` | `trace/infrastructure/database/gateway.py` | Production (asyncpg) |
| `InMemoryDatabaseGateway` | `tests/conftest.py` | Unit tests (aiosqlite in-memory) |

---

## Connection String Format

```
postgresql+asyncpg://user:password@host:5432/dbname
```

For unit tests (SQLite in-memory):
```
sqlite+aiosqlite:///:memory:
```

---

## Health Probe Implementation

The production `SQLAlchemyDatabaseGateway.health_check()` uses:

```python
async with engine.connect() as conn:
    await conn.execute(text("SELECT 1"))
return True
```

Wrapped in `try/except Exception as e: log.warning(...); return False`.

---

## Migration Contract

All schema changes MUST go through Alembic migration scripts.

| Command | Purpose |
|---|---|
| `uv run alembic upgrade head` | Apply all pending migrations |
| `uv run alembic downgrade -1` | Roll back one migration |
| `uv run alembic current` | Show current schema version |
| `uv run alembic revision --autogenerate -m "description"` | Generate a new migration |

The Phase 0 baseline migration (`0001_baseline.py`) creates no tables — it only stamps
the `alembic_version` table to establish the migration baseline.

---

## Future Domain Tables (Phase 1+)

The following tables MUST NOT be created in Phase 0 migrations:

```
projects, repositories, versions, analysis_runs, change_sets,
risk_assessments, upgrade_plans, upgrade_tasks, validation_runs, human_reviews
```

---

## Prohibited Patterns

- ❌ Any code outside `trace/infrastructure/database/` importing `sqlalchemy` directly
- ❌ Direct SQL string concatenation (always use SQLAlchemy `text()` with bind parameters)
- ❌ Committing schema changes without an Alembic migration script
- ❌ `health_check()` returning `True` without executing an actual connectivity probe

---

## Versioning Policy

- **PATCH**: Documentation only.
- **MINOR**: New optional operations added to the Protocol.
- **MAJOR**: Signature change to `session()` or `health_check()`; new required operations.

Current version: **0.1.0**
