# Implementation Plan: TRACE Phase 6 — F07: Upgrade Planner

**Feature Branch**: `007-upgrade-planner` | **Date**: 2026-10-01 | **Spec Reference**: [spec.md](spec.md)  
**Related Documents**: [research.md](research.md) | [data-model.md](data-model.md) | [contracts/api.md](contracts/api.md) | [quickstart.md](quickstart.md)

---

## 1. Summary

Implement Phase 6 (F07) of TRACE: the **Upgrade Planner**.
While F04 detects *what changed* and F05/F06 detects *what is impacted and its risk*, F07 transforms that raw diagnostic intelligence into an **actionable, dependency-ordered engineering transformation workflow**.

Key technical mechanisms:
1. **Topological DAG Sequencer**: Translates impacted AST entities and multi-hop callers ($G^T$) into a directed task graph $G_{plan} = (V_{task}, E_{dep})$.
2. **7-Tier Architectural Precedence**: Automatically sequences modifications across architectural layers: `CONTRACT_API` $\to$ `CORE_LOGIC` $\to$ `DATA_MAPPING` $\to$ `CONSUMER_HANDLER` $\to$ `CLIENT_UI` $\to$ `INTEGRATION_TEST` $\to$ `DOCUMENTATION_CONFIG`.
3. **Resilient Cycle & Subgraph Handling**: Employs Tarjan's Strongly Connected Components (SCC) algorithm to detect cycles, grouping circular tasks into atomic co-dependent batches with `is_circular: true`, and computes Weakly Connected Components to identify parallelizable work streams (`parallel_group_id`).
4. **Comprehensive Task Metadata**: Synthesizes `component`, `reason`, `dependencies`, `expected_changes`, `required_tests`, `risk_level`, `status`, and `evidence` (diff snippets and call graph paths).
5. **Dual-Track Reasoner**: 100% deterministic offline heuristic generation as default baseline; optional OpenRouter LLM enrichment when API credentials are provided.
6. **Authoritative State Persistence**: Relational storage in PostgreSQL (`upgrade_plans`, `upgrade_tasks`, `task_dependencies`) with Alembic migration `0007_upgrade_plans.py`, complemented by JSON artifact caching.
7. **Interactive Observatory UI**: Dedicated `"📋 Upgrade Planner (F07)"` tab in Streamlit with progress metrics, risk/status filtering, expandable cards, and reactive task status toggling.

---

## 2. Technical Context

- **Language/Runtime**: Python 3.12+
- **Backend Framework**: FastAPI (async REST APIs), Pydantic v2 (Validation & Schemas)
- **Persistence**: PostgreSQL 16 (SQLAlchemy 2.0 with `asyncpg`), Alembic migrations, FileArtifactStore (`.trace/artifacts/plans/`)
- **Graph & Algorithms**: In-memory adjacency representation for $G_{plan}$, Tarjan's SCC cycle detector, Kahn's topological sort, Neo4j driver (for `TESTED_BY` links)
- **Frontend**: Streamlit (Observatory UI)
- **Testing**: `pytest`, `pytest-asyncio`
- **Target Platform**: Containerized Linux / Docker Compose, local developer environments
- **Performance Targets**:
  - Plan DAG construction and topological sort $< 1.5\text{s}$ for up to 200 impacted components.
  - Task status updates persisted and returned in $< 200\text{ms}$.
  - Offline mode requires 0 network requests, 0 external API calls, and 0 latency overhead.
- **Constraints**:
  - Full compliance with TRACE Constitution: Evidence over hallucination (Principle I), Deterministic before probabilistic (Principle II), Human-in-the-loop (Principle III), and Explicit contracts (Principle VIII).
  - Existing F01–F06 implementations remain untouched and fully backward-compatible.

---

## 3. Constitution Check

*GATE: Must pass before implementation. Validated against `.specify/memory/constitution.md`.*

| Principle | Compliance Status | Justification / Architectural Evidence |
| :--- | :--- | :--- |
| **I. Evidence over Hallucination** | **PASS** | Every task is anchored to an inspectable Git diff hunk, AST line span, or Neo4j call graph path. The planner never invents components. |
| **II. Deterministic before Probabilistic** | **PASS** | Topological DAG sequencing, architectural tiering, syntax delta inference, and test associations execute deterministically offline. LLM is strictly an optional narrative overlay. |
| **III. Human-in-the-Loop** | **PASS** | The planner produces an advisory task checklist. Humans inspect evidence, set statuses (`IN_PROGRESS`, `COMPLETED`, `SKIPPED`), and execute changes. No autonomous code edits. |
| **VIII. Explicit Contracts** | **PASS** | Domain entities (`trace.domain.plan`), database models (`UpgradePlanOrm`), and API schemas (`UpgradePlanResponse`) are strictly decoupled across layers. |
| **X. Incremental Delivery** | **PASS** | F07 delivers complete standalone value as an actionable upgrade planner, consuming F01–F06 outputs and feeding into future F08/F09 verification. |
| **XVII. No Fabricated Implementation State** | **PASS** | Task statuses strictly reflect developer actions and verified test outcomes. |

---

## 4. Project Structure & File Layout

### Documentation (this feature)
```text
specs/007-upgrade-planner/
├── spec.md                     # Feature requirements & user stories
├── plan.md                     # Implementation plan (this document)
├── research.md                 # Architecture decisions & algorithms
├── data-model.md               # Domain entities, state machines & DB schema
├── quickstart.md               # End-to-end validation guide
├── contracts/
│   └── api.md                  # REST API schemas & payload contracts
└── checklists/
    └── requirements.md         # Quality checklist
```

### Source Code Changes & New Files

#### New Files to Create:
```text
backend/src/trace/
├── domain/
│   └── plan.py                         # Domain models: UpgradePlan, UpgradeTask, TaskStatus, TaskCategory, TaskEvidence
├── analysis/
│   └── planner/
│       ├── __init__.py
│       ├── dag_sequencer.py            # Tarjan SCC cycle detector & Kahn's topological sort engine
│       ├── tier_mapper.py              # 7-tier architectural categorization engine
│       └── task_synthesizer.py         # Dual-track task metadata & prescriptive guidance synthesizer
├── infrastructure/
│   └── database/models/
│       └── upgrade_plan.py             # SQLAlchemy ORM models: UpgradePlanOrm, UpgradeTaskOrm, TaskDependencyOrm
├── services/
│   └── planner.py                      # UpgradePlanService orchestrating generation, persistence & lifecycle
└── api/
    └── planner/
        ├── __init__.py
        ├── router.py                   # REST endpoints: POST /generate, GET /{id}, PATCH /tasks/{id}, etc.
        └── schemas.py                  # Pydantic v2 request/response schemas

backend/alembic/versions/
└── 0007_upgrade_plans.py               # Alembic migration for upgrade_plans & upgrade_tasks tables

backend/tests/unit/
├── test_dag_sequencer.py               # Unit tests for topological ordering, cycles, disconnected subgraphs
└── test_tier_mapper.py                 # Unit tests for architectural tier classification

backend/tests/integration/
├── test_planner_service.py             # Integration test for plan generation from F05 impact aggregate
└── test_planner_api.py                 # API integration tests for /api/v1/upgrade-plans endpoints
```

#### Existing Files to Modify:
```text
backend/src/trace/
├── infrastructure/database/models/__init__.py  # Export UpgradePlanOrm, UpgradeTaskOrm, TaskDependencyOrm
└── api/router.py                               # Mount planner_router under /api/v1/upgrade-plans

frontend/
└── app.py                                      # Add "📋 Upgrade Planner (F07)" tab with interactive checklist & controls
```

---

## 5. Architectural Component Flow

```text
[HTTP Request: POST /api/v1/upgrade-plans/generate]
                       │
                       ▼
[PlannerRouter: trace/api/planner/router.py]
                       │
                       ▼
[UpgradePlanService: trace/services/planner.py]
  │
  ├──► 1. Ingest Impact Analysis:
  │       Resolve ImpactAnalysisAggregate (F05) via ImpactAnalysisService or artifact cache.
  │
  ├──► 2. Architectural Tier Mapping (TierMapper):
  │       Categorize each DetailedImpact and CallerAtRisk into 7 tiers:
  │       (Contract -> Core -> Data -> Consumer -> Client -> Test -> Docs)
  │
  ├──► 3. Directed Task Graph Construction (DagSequencer):
  │       - Add nodes for all candidate entities.
  │       - Add edges: callee -> caller (callee must precede caller).
  │       - Add edges: lower tier -> higher tier.
  │
  ├──► 4. Cycle Detection & Condensation:
  │       - Execute Tarjan's SCC algorithm.
  │       - If cycles detected, group participating tasks into co-dependent batches.
  │       - Tag circular tasks with `is_circular = True`.
  │
  ├──► 5. Topological Sorting & Parallel Partitioning:
  │       - Run Kahn's algorithm on condensation DAG to assign 1-indexed `step_number`.
  │       - Compute Weakly Connected Components (WCC) to assign `parallel_group_id`.
  │
  ├──► 6. Dual-Track Task Metadata Synthesis (TaskSynthesizer):
  │       - Offline Heuristic: Synthesize `reason` and `expected_changes` via syntax deltas.
  │       - Look up test targets from Neo4j or test file associations -> `required_tests`.
  │       - Inherit risk level & bind diff snippet + caller chain into `evidence`.
  │       - Optional Online LLM: Enrich task descriptions via OpenRouter if configured.
  │
  ├──► 7. Authoritative Persistence:
  │       - Write UpgradePlanOrm & UpgradeTaskOrm records to PostgreSQL.
  │       - Write full JSON artifact to `.trace/artifacts/plans/{plan_id}.json`.
  │
  └──► 8. Return 201 Created with UpgradePlanResponse
```

---

## 6. Implementation Phases & Milestones

### Phase 1: Domain Entities & Database Persistence
- **Deliverables**:
  - Define `TaskStatus`, `TaskCategory`, `TaskEvidence`, `UpgradeTask`, and `UpgradePlan` in `trace.domain.plan`.
  - Create SQLAlchemy ORM models (`UpgradePlanOrm`, `UpgradeTaskOrm`, `TaskDependencyOrm`) in `trace.infrastructure.database.models.upgrade_plan`.
  - Register models in `trace.infrastructure.database.models.__init__.py`.
  - Create Alembic migration `0007_upgrade_plans.py` and verify upgrade/downgrade.
- **Verification**: `pytest` database model tests, migration runs cleanly.

### Phase 2: Algorithmic DAG Sequencer & Tier Mapper
- **Deliverables**:
  - Implement `TierMapper` classifying AST entity types and file paths into 7 architectural categories.
  - Implement `DagSequencer` building the dependency graph, executing Tarjan's SCC cycle detector, running Kahn's topological sort, and partitioning parallel streams.
  - Implement `TaskSynthesizer` generating deterministic metadata (`reason`, `expected_changes`, `required_tests`, `evidence`).
- **Verification**: Unit tests verifying linear ordering, cycle handling without infinite loops, and disconnected graph partitioning.

### Phase 3: Service Layer & Dual-Track Reasoner Integration
- **Deliverables**:
  - Implement `UpgradePlanService` in `trace.services.planner`.
  - Connect to `ImpactAnalysisService` to fetch `ImpactAnalysisAggregate`.
  - Implement optional LLM enrichment hook using existing `OpenRouterLlmReasoner`, falling back gracefully to heuristic synthesis.
  - Implement plan artifact saving to `.trace/artifacts/plans/`.
  - Implement task status update and real-time progress metric recalculation.
- **Verification**: Service integration tests passing with synthetic and real impact payloads.

### Phase 4: REST API Endpoints & Request/Response Contracts
- **Deliverables**:
  - Implement Pydantic v2 schemas in `trace.api.planner.schemas`.
  - Implement FastAPI router in `trace.api.planner.router` with endpoints:
    - `POST /api/v1/upgrade-plans/generate`
    - `GET /api/v1/upgrade-plans/{plan_id}`
    - `GET /api/v1/upgrade-plans/{plan_id}/tasks`
    - `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}`
    - `GET /api/v1/repositories/{repo_id}/upgrade-plans`
  - Mount router in `trace.api.router.py`.
- **Verification**: API integration tests verifying status codes, schema validation, filtering, pagination, and status patching.

### Phase 5: Streamlit Observatory UI & E2E Verification
- **Deliverables**:
  - Add 4th top-level tab in `frontend/app.py`: `"📋 Upgrade Planner (F07)"`.
  - Build progress banner with progress bar (% completed, remaining high-risk tasks).
  - Build filter controls (Status, Risk Level, Category).
  - Build expandable task cards showing step numbers, badges, reasons, expected changes, required tests, and diff snippets.
  - Add interactive status toggle (mark task `COMPLETED` or `IN_PROGRESS`) with immediate reactive refresh.
  - Add JSON plan download button.
- **Verification**: Browser walkthrough confirming all scenarios in [quickstart.md](quickstart.md) operate end-to-end.

---

## 7. Testing Strategy

### Unit Tests (`backend/tests/unit/`)
1. **`test_dag_sequencer.py`**:
   - `test_linear_chain_ordering`: $A \to B \to C$ yields steps 1, 2, 3 in correct topological order.
   - `test_architectural_tier_precedence`: Contracts precede services, which precede tests, regardless of insertion order.
   - `test_circular_dependency_handling`: Cycle $A \to B \to C \to A$ terminates, tags tasks with `is_circular: true`, and does not crash.
   - `test_disconnected_subgraphs`: Disjoint components $X \to Y$ and $P \to Q$ receive distinct `parallel_group_id` values.
   - `test_empty_impact_plan`: Zero modified entities returns a clean empty plan with status `COMPLETED`.
2. **`test_tier_mapper.py`**:
   - Correctly maps routes/endpoints to `CONTRACT_API`, models to `DATA_MAPPING`, tests to `INTEGRATION_TEST`, and docs to `DOCUMENTATION_CONFIG`.

### Integration Tests (`backend/tests/integration/`)
1. **`test_planner_service.py`**:
   - Ingests a real `ImpactAnalysisAggregate` from F05 and successfully produces a populated `UpgradePlan` stored in PostgreSQL.
   - Verifies that task status transitions update `completed_tasks` and `progress_percentage`.
2. **`test_planner_api.py`**:
   - Test plan generation endpoint (`POST /generate`) with `201 Created`.
   - Test task filtering by `status=PENDING` and `risk_level=HIGH`.
   - Test status update endpoint (`PATCH /tasks/{id}`) with `200 OK`.
   - Test repository plan listing endpoint.
