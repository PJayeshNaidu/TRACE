# Quickstart Validation Guide: TRACE Phase 1 — F01

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Feature**: F01 Project & Repository Management

This guide documents the end-to-end operational scenarios to validate that F01 (Project & Repository Management) is properly implemented and functional.

---

## Prerequisites

1. PostgreSQL database running (or Docker container from Phase 0: `docker compose up -d postgres`).
2. Environment file configured (`.env`) with valid `DATABASE_URL`.
3. Virtual environment synced: `uv sync`.

---

## Scenario 1: Apply Database Migrations (SC-001)

Apply the newly created migration `0002_project_repository.py` to PostgreSQL:

```bash
cd backend
uv run alembic upgrade head
```

**Expected Outcome**: Alembic executes `0002_project_repository` and creates tables `projects` and `repositories` with composite unique constraint `uq_project_location`.

---

## Scenario 2: Start Backend Service

```bash
uv run uvicorn trace.main:app --reload --port 8000
```

**Expected Outcome**: FastAPI starts with structured startup logs. Health endpoint remains healthy:
```bash
curl -s http://localhost:8000/health | python -m json.tool
```

---

## Scenario 3: Create a TRACE Project (FR-001, SC-001)

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "TRACE Core Platform", "description": "Core analysis platform"}' \
  | python -m json.tool
```

**Expected Outcome** (`HTTP 201 Created`):
```json
{
  "id": "<project-id-uuid>",
  "name": "TRACE Core Platform",
  "description": "Core analysis platform",
  "status": "ACTIVE",
  "repository_count": 0,
  "created_at": "...",
  "updated_at": "..."
}
```

---

## Scenario 4: Register Local Repository (FR-011, FR-013)

Use the current TRACE repository as the local target:

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project-id-uuid>/repositories \
  -H "Content-Type: application/json" \
  -d '{"type": "LOCAL", "location": "C:/Course Work/Course Tasks/TRACE"}' \
  | python -m json.tool
```

**Expected Outcome** (`HTTP 201 Created`):
- `status`: `"REGISTERED"`
- `type`: `"LOCAL"`
- `last_analysis_run_id`: `null` (guaranteeing unanalyzed state per SC-005)

---

## Scenario 5: Rejection of Embedded Credentials in Remote URLs (FR-034, NFR-006)

Attempt to register a remote URL containing an embedded personal access token:

```bash
curl -i -X POST http://localhost:8000/api/v1/projects/<project-id-uuid>/repositories \
  -H "Content-Type: application/json" \
  -d '{"type": "REMOTE", "location": "https://user:ghp_secretToken123@github.com/org/repo.git"}'
```

**Expected Outcome** (`HTTP 422 Unprocessable Entity`):
Response clearly rejects embedded credentials with a descriptive validation error:
```json
{
  "detail": [
    {
      "msg": "Repository URL must not contain embedded basic-auth credentials or tokens. Configure host-level ambient authentication (SSH keys or Git credential helper) instead."
    }
  ]
}
```

---

## Scenario 6: Validate Local Repository Connectivity (FR-021, FR-023)

```bash
curl -X POST http://localhost:8000/api/v1/repositories/<repository-id-uuid>/validate \
  | python -m json.tool
```

**Expected Outcome** (`HTTP 200 OK`):
```json
{
  "repository_id": "<repository-id-uuid>",
  "is_connected": true,
  "status": "CONNECTED",
  "detected_branch": "Repo-Mngmnt-Jayesh",
  "error_message": null,
  "latency_ms": 12.4,
  "validated_at": "..."
}
```

---

## Scenario 7: Validate Remote Public Repository Connectivity (FR-021, FR-024)

Register a reachable public repository:

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project-id-uuid>/repositories \
  -H "Content-Type: application/json" \
  -d '{"type": "REMOTE", "location": "https://github.com/psf/requests.git"}' \
  | python -m json.tool
```

Trigger validation probe:
```bash
curl -X POST http://localhost:8000/api/v1/repositories/<requests-repo-id-uuid>/validate \
  | python -m json.tool
```

**Expected Outcome** (`HTTP 200 OK`):
- `is_connected`: `true`
- `status`: `"CONNECTED"`
- `detected_branch`: `"main"`
- Elapsed `latency_ms` < 10000ms.

---

## Scenario 8: Project Archival and Reactivation (FR-006, FR-007)

Archive the project:
```bash
curl -X POST http://localhost:8000/api/v1/projects/<project-id-uuid>/archive | python -m json.tool
```
Confirm `status` is now `"ARCHIVED"`. Attempting to register another repository returns `HTTP 409 Conflict`.

Reactivate the project:
```bash
curl -X POST http://localhost:8000/api/v1/projects/<project-id-uuid>/activate | python -m json.tool
```
Confirm `status` is restored to `"ACTIVE"`.

---

## Scenario 9: Delete an Unanalyzed Repository (FR-020a)

```bash
curl -i -X DELETE http://localhost:8000/api/v1/repositories/<requests-repo-id-uuid>
```

**Expected Outcome**: `HTTP 204 No Content`. Subsequent `GET` returns `HTTP 404 Not Found`.

---

## Scenario 10: Run Deterministic Automated Test Suite (SC-004, NFR-011)

```bash
cd backend
uv run pytest
```

**Expected Outcome**: All unit, API, service, and fixture tests pass deterministically without connecting to external networks. Test coverage remains ≥ 80%.
