# Tasks: TRACE Phase 3A — F03: Dependency Graph

**Feature Branch**: `Dependency-Graph`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](./spec.md)

---

## Task Overview

```
T01 — Domain models (GraphBuildRun, GraphNode, GraphRelationship)
T02 — PostgreSQL ORM (GraphBuildRunOrm, migration)
T03 — Neo4j write infrastructure (constraints + batch MERGE builder)
T04 — Extend GraphGateway Protocol with write methods
T05 — GraphService (orchestration layer)
T06 — Auto-trigger graph build on analysis completion
T07 — API schemas (Pydantic)
T08 — API router (graph endpoints)
T09 — Wire into main.py and api/router.py
T10 — Unit tests: domain + service
T11 — Unit tests: gateway + builder
T12 — Integration test (live Neo4j, optional)
T13 — Update docs/architecture.md
```

---

## T01 — Domain Models

**File**: `trace/domain/graph.py`

Create the following pure domain models:
- `GraphBuildStatus(StrEnum)` — `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`
- `GraphBuildRun` — frozen dataclass tracking a build run lifecycle
- `GraphNode` — read model for API node responses
- `GraphRelationship` — read model for API relationship responses

**No framework imports. No I/O. Pure Python stdlib only.**

---

## T02 — PostgreSQL ORM & Migration

**Files**:
- `trace/infrastructure/database/models/graph_build_run.py` — `GraphBuildRunOrm`
- `alembic/versions/XXXX_add_graph_build_runs.py` — migration

`GraphBuildRunOrm` maps to the `graph_build_runs` table (see data-model.md §2).  
Add `to_domain() -> GraphBuildRun` method.

Add `GraphBuildRunOrm` to `trace/infrastructure/database/models/__init__.py`.

---

## T03 — Neo4j Write Infrastructure

**File**: `trace/infrastructure/graph/neo4j_builder.py`

Create `Neo4jGraphBuilder` class responsible for:
- `ensure_constraints(driver)` — runs all `CREATE CONSTRAINT IF NOT EXISTS` Cypher
- `build_graph(driver, analysis: RepositoryAnalysis) -> tuple[int, int]` — returns `(nodes_created, rels_created)`
  - Projects nodes in batches of 100 via `UNWIND` + `MERGE`
  - Projects relationships in batches of 100 via `UNWIND` + `MERGE`

Internal helper methods:
- `_node_rows(analysis)` — produces list of node property dicts
- `_rel_rows(analysis)` — produces list of edge property dicts
- `_node_id(label, key, run_id)` — stable unique node ID generator

**Must NOT import FastAPI, SQLAlchemy, or service layer.**

---

## T04 — Extend GraphGateway Protocol

**File**: `trace/infrastructure/graph/gateway.py`

Extend `GraphGateway(Protocol)` with:
```python
async def ensure_constraints(self) -> None: ...
async def build_graph(self, analysis: RepositoryAnalysis) -> tuple[int, int]: ...
async def clear_graph(self, analysis_run_id: str) -> int: ...  # returns nodes deleted
```

Implement these on `Neo4jGraphGateway` (delegates to `Neo4jGraphBuilder`).

Add no-op implementations on `UnconfiguredGraphGateway` (raises `GraphNotConfiguredError`).
Add stub implementations on `StubGraphGateway` (returns controlled values).

---

## T05 — GraphService

**File**: `trace/services/graph.py`

Create `GraphService`:
```python
class GraphService:
    def __init__(self, db_gateway, graph_gateway, analysis_service): ...

    async def build_dependency_graph(self, analysis_run_id: UUID) -> GraphBuildRun:
        # 1. Validate analysis run exists and is COMPLETED
        # 2. Create GraphBuildRun record in PENDING
        # 3. Mark IN_PROGRESS
        # 4. Load RepositoryAnalysis artifact
        # 5. Call graph_gateway.build_graph(analysis)
        # 6. Mark COMPLETED with stats
        # Return GraphBuildRun

    async def get_build_run(self, build_run_id: UUID) -> GraphBuildRun: ...
    async def get_latest_build_run(self, analysis_run_id: UUID) -> GraphBuildRun | None: ...
```

Error handling:
- `AnalysisRunNotFoundError` if analysis_run_id missing
- `InvalidAnalysisStateError` if analysis is not COMPLETED
- `GraphNotConfiguredError` if Neo4j not available (wraps `UnconfiguredGraphGateway` response)

---

## T06 — Auto-Trigger on Analysis Completion

**File**: `trace/services/analysis.py`

After `execute_analysis_task()` marks a run COMPLETED and commits, fire:
```python
loop.create_task(
    self._graph_service.build_dependency_graph(analysis_run_id)
)
```

`GraphService` is injected into `AnalysisService` as optional (`graph_service: GraphService | None = None`).  
If `None`, skip graph build (backward-compatible with existing tests).

---

## T07 — API Schemas

**File**: `trace/api/graph/schemas.py`

Pydantic schemas:
- `GraphBuildRunResponse` — from `GraphBuildRun` domain model
- `GraphBuildTriggerResponse` — returns `build_run_id`, `status`, `message`
- `GraphNodeItem` — node id, label, qualified_name, properties
- `GraphNodeListResponse` — paginated items + total
- `GraphRelationshipItem` — source, type, target, evidence
- `GraphRelationshipListResponse` — paginated items + total
- `GraphTraversalResponse` — node + list of connected nodes

---

## T08 — API Router

**File**: `trace/api/graph/router.py`

```
POST   /api/v1/analyses/{run_id}/graph/build
GET    /api/v1/analyses/{run_id}/graph/status
GET    /api/v1/analyses/{run_id}/graph/nodes
GET    /api/v1/analyses/{run_id}/graph/relationships
GET    /api/v1/analyses/{run_id}/graph/dependents/{node_id}
GET    /api/v1/analyses/{run_id}/graph/dependencies/{node_id}
```

---

## T09 — Wiring

**Files**: `trace/api/router.py`, `trace/main.py`

- Register `graph_router` in `api_router`
- Instantiate `Neo4jGraphBuilder` and inject into `Neo4jGraphGateway`
- Instantiate `GraphService` and store as `app.state.graph_service`
- Pass `GraphService` into `AnalysisService` construction

---

## T10 — Unit Tests: Domain + Service

**File**: `tests/unit/test_graph_service.py`

- Test `build_dependency_graph` happy path using `StubGraphGateway`
- Test failure when analysis not found
- Test failure when analysis not COMPLETED
- Test graceful behavior when `GraphNotConfiguredError` raised
- Test `get_latest_build_run` returns None when no builds exist

---

## T11 — Unit Tests: Builder + Gateway

**File**: `tests/unit/test_neo4j_builder.py`

- Test `_node_rows()` produces correct count and structure from a minimal `RepositoryAnalysis`
- Test `_rel_rows()` produces correct count and structure
- Test node ID generation is stable and unique
- Test `StubGraphGateway.build_graph()` returns controlled values

---

## T12 — Integration Test (optional, `@pytest.mark.integration`)

**File**: `tests/integration/test_graph_integration.py`

- End-to-end: trigger analysis on test repo → verify graph nodes appear in Neo4j
- Requires live Neo4j (`@pytest.mark.integration`)

---

## T13 — Architecture Doc Update

**File**: `docs/architecture.md`

Add F03 section:
- `trace/domain/graph.py` purpose
- `trace/services/graph.py` purpose
- `trace/infrastructure/graph/neo4j_builder.py` purpose
- New API endpoints table
