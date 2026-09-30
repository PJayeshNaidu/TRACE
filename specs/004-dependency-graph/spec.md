# Feature Specification: TRACE Phase 3A — F03: Dependency Graph

**Feature Branch**: `Dependency-Graph`  
**Date**: 2026-09-29  
**Phase**: 3A  
**Status**: In Development  
**Depends On**: F01 (Project & Repository Management), F02 (Repository / Code Analyzer)  
**Feeds Into**: F05 (Impact Analysis), F10 (AI Assistant)

---

## Overview & Scope Boundaries

F03 converts the structured code intelligence produced by F02 into a **persistent Neo4j knowledge graph**.

F02 answers: *"What does this repository contain?"*  
F03 answers: *"How are those components structurally related to each other in a queryable graph?"*

F03 receives the `RepositoryAnalysis` artifact from F02 and projects every entity and relationship into Neo4j as labelled property graph nodes and directed typed edges.

The resulting graph is the **structural backbone** of TRACE. Every downstream feature — impact analysis, risk scoring, upgrade planning, and the AI assistant — traverses this graph.

### What F03 Does

- Reads completed `RepositoryAnalysis` artifacts from the artifact store
- Maps domain entities (Module, Class, Function, Service, Endpoint, etc.) to Neo4j nodes
- Maps `AnalysisRelationship` records to Neo4j directed edges
- Scopes every node to its `analysis_run_id` for multi-run isolation
- Exposes a query API for nodes, relationships, and graph traversal (dependents / dependencies)
- Auto-triggers after analysis completes (background task)
- Supports idempotent rebuild (MERGE-based, safe to re-run)

### What F03 Does NOT Do

- F03 does **not** run static code analysis (owned by F02)
- F03 does **not** compute change deltas between versions (owned by F04)
- F03 does **not** perform impact analysis (owned by F05)
- F03 does **not** reason or generate LLM explanations (owned by F10)
- F03 does **not** create or manage projects / repositories (owned by F01)

---

## Functional Requirements

### FR-001 — Graph Build Trigger

The system SHALL automatically trigger a dependency graph build after an analysis run transitions to `COMPLETED` status, as a background task without blocking the HTTP response.

### FR-002 — Idempotent Graph Build

Graph build operations SHALL be idempotent. Rebuilding the graph for the same `analysis_run_id` SHALL overwrite (MERGE) existing nodes and relationships without creating duplicates.

### FR-003 — Node Projection

The system SHALL project the following F02 domain entities as Neo4j nodes, each scoped to `analysis_run_id`:

| Domain Entity | Neo4j Label | Primary Key Properties |
|---|---|---|
| `RepositoryAnalysis` root | `:AnalysisRoot` | `analysis_run_id`, `repository_id` |
| `Module` | `:Module` | `qualified_name`, `analysis_run_id` |
| `Class` | `:Class` | `qualified_name`, `analysis_run_id` |
| `Function` | `:Function` | `qualified_name`, `analysis_run_id` |
| `Service` | `:Service` | `qualified_name`, `analysis_run_id` |
| `APIEndpoint` | `:Endpoint` | `http_method + path`, `analysis_run_id` |
| `DatabaseReference` | `:DatabaseEntity` | `target_entity`, `analysis_run_id` |
| `ConfigurationReference` | `:ConfigSetting` | `key_name`, `analysis_run_id` |
| `TestReference` | `:TestUnit` | `test_qualified_name`, `analysis_run_id` |
| `ExternalDependency` | `:ExternalPackage` | `package_name`, `analysis_run_id` |
| `DocumentationReference` | `:DocArtifact` | `file_path`, `analysis_run_id` |

### FR-004 — Relationship Projection

The system SHALL project all `AnalysisRelationship` records from F02 as typed Neo4j directed edges using `MERGE` to prevent duplicates.

All F02 `RelationshipKind` values SHALL map 1-to-1 to Neo4j edge types:
`IMPORTS`, `CALLS`, `EXTENDS`, `DEPENDS_ON`, `EXPOSES`, `READS`, `WRITES`, `TESTED_BY`, `DOCUMENTED_BY`, `CONFIGURED_BY`

Each edge SHALL carry `evidence_file_path` and `evidence_start_line` properties from the source `AnalysisRelationship.evidence_location`.

### FR-005 — Graph Query API

The system SHALL expose REST API endpoints for:
- Querying nodes for a given `analysis_run_id` with pagination and optional label filter
- Querying relationships for a given `analysis_run_id` with pagination and optional type filter
- Traversing forward (what does node X depend on?)
- Traversing backward (what depends on node X?)

### FR-006 — Graph Build Status

The system SHALL track and expose the status of a graph build via an API endpoint, including:
- Build status (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`)
- Node count created
- Relationship count created
- Duration in milliseconds
- Error message if failed

### FR-007 — Graph Scoping by Analysis Run

Every Neo4j node SHALL carry an `analysis_run_id` property. All graph queries SHALL be scoped to a specific `analysis_run_id`. This ensures multiple analysis runs for the same repository can coexist in Neo4j without interference.

### FR-008 — Constraint & Index Initialization

On application startup (or first graph build), the system SHALL ensure Neo4j uniqueness constraints and indexes exist for all node labels to guarantee MERGE correctness.

### FR-009 — Graceful Degradation

If Neo4j is not configured (`UnconfiguredGraphGateway`), graph build operations SHALL fail gracefully with a structured error response (HTTP 503 with a clear message) rather than raising unhandled exceptions.

### FR-010 — Manual Graph Rebuild

The system SHALL expose a `POST /api/v1/analyses/{analysis_run_id}/graph/build` endpoint to manually trigger (or re-trigger) a graph build for a completed analysis run.

---

## Non-Functional Requirements

### NFR-001 — Idempotency

Graph writes SHALL use Neo4j `MERGE` semantics throughout. Re-running a build SHALL produce the same graph state as running it once.

### NFR-002 — Architectural Isolation

F03 SHALL NOT import from `trace.analysis.*` (that is F02's responsibility). F03 consumes only the `RepositoryAnalysis` domain aggregate loaded from the artifact store via `AnalysisService`.

### NFR-003 — Domain Boundary

The `GraphService` SHALL depend only on `GraphGateway` (Protocol) and `AnalysisService`. It SHALL NOT directly use the Neo4j driver.

### NFR-004 — Performance

A graph build for a repository with 500 nodes and 1000 relationships SHALL complete within 30 seconds in a local development environment.

### NFR-005 — Observability

Graph build operations SHALL emit structured `structlog` log events at the start, completion, and on failure of each build, including `analysis_run_id`, node count, relationship count, and duration.

---

## Architectural Decisions

### Decision 1: Auto-trigger on Analysis Completion

The graph build is triggered automatically when `AnalysisService.execute_analysis_task()` marks a run as `COMPLETED`, dispatched as an additional background task. This keeps the analysis and graph-build concerns separated while ensuring the graph is always populated after a successful analysis.

### Decision 2: Cypher MERGE-based Idempotent Writes

All node and relationship writes use `MERGE` (not `CREATE`) to guarantee idempotency. Duplicate builds are safe.

### Decision 3: analysis_run_id Scoping

Nodes are scoped to `analysis_run_id` in their primary key. This allows:
- Multiple analysis runs for the same repo to coexist
- Impact analysis to target a specific run's graph
- Clean deletion of an old run's graph without affecting others

### Decision 4: Batch Cypher Execution

Node and relationship writes are sent in batches (e.g. 100 nodes per transaction) via `UNWIND` Cypher to reduce round-trip overhead versus one-by-one MERGE calls.

---

## API Endpoints

| Method | Path | Description | Status Code |
|---|---|---|---|
| `POST` | `/api/v1/analyses/{run_id}/graph/build` | Trigger or re-trigger graph build | 202 Accepted |
| `GET` | `/api/v1/analyses/{run_id}/graph/status` | Get graph build status and stats | 200 OK |
| `GET` | `/api/v1/analyses/{run_id}/graph/nodes` | List nodes (paginated, filterable by label) | 200 OK |
| `GET` | `/api/v1/analyses/{run_id}/graph/relationships` | List relationships (paginated, filterable by type) | 200 OK |
| `GET` | `/api/v1/analyses/{run_id}/graph/dependents/{node_id}` | What components depend on this node? | 200 OK |
| `GET` | `/api/v1/analyses/{run_id}/graph/dependencies/{node_id}` | What does this node depend on? | 200 OK |

---

## Implementation Files

### New Files

| File | Layer | Purpose |
|---|---|---|
| `trace/domain/graph.py` | Domain | `GraphBuildStatus`, `GraphBuildRun`, `GraphNode`, `GraphRelationship` domain models |
| `trace/services/graph.py` | Service | `GraphService` — orchestrates graph build lifecycle |
| `trace/infrastructure/graph/neo4j_builder.py` | Infrastructure | Neo4j Cypher write logic (node/rel projection, batch MERGE) |
| `trace/api/graph/__init__.py` | API | Module init |
| `trace/api/graph/router.py` | API | FastAPI router with all graph endpoints |
| `trace/api/graph/schemas.py` | API | Pydantic request/response schemas |
| `tests/unit/test_graph_service.py` | Tests | Unit tests for `GraphService` |
| `tests/unit/test_neo4j_builder.py` | Tests | Unit tests for the Neo4j builder |

### Modified Files

| File | Change |
|---|---|
| `trace/infrastructure/graph/gateway.py` | Extend `GraphGateway` Protocol + `Neo4jGraphGateway` with write operations |
| `trace/services/analysis.py` | Auto-trigger `GraphService.build_dependency_graph()` on analysis COMPLETED |
| `trace/api/router.py` | Include `graph_router` |
| `trace/main.py` | Instantiate and wire `GraphService` into `app.state` |

---

## Acceptance Criteria

- [ ] AC-001: After an analysis run completes, a graph build is automatically triggered and nodes/relationships appear in Neo4j.
- [ ] AC-002: Rebuilding the graph for the same run_id produces the same node/relationship count with no duplicates.
- [ ] AC-003: `GET /graph/nodes?label=Function` returns only Function nodes for the given run.
- [ ] AC-004: `GET /graph/dependents/{node_id}` returns all nodes that depend on (have a relationship pointing to) the given node.
- [ ] AC-005: `GET /graph/dependencies/{node_id}` returns all nodes that the given node points to.
- [ ] AC-006: When Neo4j is not configured, `POST /graph/build` returns HTTP 503 with a clear message.
- [ ] AC-007: Graph build status transitions correctly through PENDING → IN_PROGRESS → COMPLETED (or FAILED).
- [ ] AC-008: All unit tests pass without a live Neo4j instance.
