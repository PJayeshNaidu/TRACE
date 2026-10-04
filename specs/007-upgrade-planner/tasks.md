# Tasks: TRACE Phase 6 — F07: Upgrade Planner

**Input**: Design documents from `specs/007-upgrade-planner/` (`spec.md`, `plan.md`, `data-model.md`, `research.md`, `contracts/api.md`, `quickstart.md`)  
**Prerequisites**: F01 (Repo Management), F02 (AST Code Extraction), F03 (Neo4j Graph), F04 (Version Change Diffing), F05 & F06 (Impact Analysis & Risk Evaluation Engine)  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.  

## Format: `[TaskID] [P?] [Story] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Target user story (`US1`, `US2`, `US3`, `US4`, `US5`)

---

## Phase 1: Setup & Data Modeling (Shared Infrastructure)

**Purpose**: Core domain entities, PostgreSQL schema, Alembic migration, and artifact store helpers.

- [x] T001 Define domain entities (`UpgradePlan`, `UpgradeTask`, `TaskStatus`, `TaskCategory`, `TaskEvidence`, `TaskDependency`) in `backend/src/trace/domain/plan.py`
- [x] T002 [P] Create SQLAlchemy ORM models `UpgradePlanOrm`, `UpgradeTaskOrm`, and `TaskDependencyOrm` in `backend/src/trace/infrastructure/database/models/upgrade_plan.py`
- [x] T003 [P] Export ORM models in `backend/src/trace/infrastructure/database/models/__init__.py`
- [x] T004 [P] Create Alembic migration script `0007_upgrade_plans.py` for `upgrade_plans` and `upgrade_tasks` tables in `backend/alembic/versions/0007_upgrade_plans.py`
- [x] T005 Setup artifact storage directory helper for upgrade plans in `backend/src/trace/infrastructure/storage/artifact_store.py`

---

## Phase 2: Foundational Engine Infrastructure

**Purpose**: Core graph sequencing and architectural tiering algorithms blocking downstream user stories.

- [x] T006 Implement `TierMapper` classifying AST entity types and file paths into 7 architectural categories (`CONTRACT_API` to `DOCUMENTATION_CONFIG`) in `backend/src/trace/analysis/planner/tier_mapper.py`
- [x] T007 [P] Implement `DagSequencer` building directed task graph $G_{plan} = (V_{task}, E_{dep})$ in `backend/src/trace/analysis/planner/dag_sequencer.py`
- [x] T008 [P] Implement Kahn's topological sort on directed acyclic task graph in `backend/src/trace/analysis/planner/dag_sequencer.py`
- [x] T009 [P] Write unit tests for tier mapping and linear DAG sequencing in `backend/tests/unit/test_tier_mapper.py` and `backend/tests/unit/test_dag_sequencer.py`

**Checkpoint**: Foundation ready — user story implementation can proceed.

---

## Phase 3: User Story 1 - Dependency-Aware Upgrade Plan Generation from Impact Data (Priority: P1) 🎯 MVP

**Goal**: Ingest F05/F06 impact data, build the task DAG, and generate a sequentially ordered upgrade plan via API.  
**Independent Test**: Provide an impact analysis aggregate with multi-hop callers, trigger plan generation via `POST /api/v1/upgrade-plans/generate`, and verify tasks are ordered such that prerequisites precede callers with sequential step numbers.

### Implementation for User Story 1
- [x] T010 [US1] Implement `UpgradePlanService.generate_plan` skeleton ingesting `ImpactAnalysisAggregate` in `backend/src/trace/services/planner.py`
- [x] T011 [US1] Connect `TierMapper` and `DagSequencer` to assign 1-indexed `step_number` to each task in `backend/src/trace/services/planner.py`
- [x] T012 [US1] Handle zero-impact edge case producing empty `UpgradePlan` (`total_tasks: 0`, status `COMPLETED`) in `backend/src/trace/services/planner.py`
- [x] T013 [US1] Implement Pydantic v2 schemas (`GenerateUpgradePlanRequest`, `UpgradePlanResponse`, `UpgradeTaskResponse`) in `backend/src/trace/api/planner/schemas.py`
- [x] T014 [US1] Implement FastAPI endpoint `POST /api/v1/upgrade-plans/generate` in `backend/src/trace/api/planner/router.py`
- [x] T015 [US1] Implement FastAPI endpoint `GET /api/v1/upgrade-plans/{plan_id}` in `backend/src/trace/api/planner/router.py`
- [x] T016 [US1] Mount `planner_router` under `/api/v1` in `backend/src/trace/api/router.py`
- [x] T017 [P] [US1] Write integration test verifying plan generation and retrieval from impact aggregate in `backend/tests/integration/test_planner_api.py`

**Checkpoint**: User Story 1 provides a functional MVP increment: generating and retrieving an ordered plan.

---

## Phase 4: User Story 2 - Comprehensive Task Metadata with Prescriptive Guidance & Verified Evidence (Priority: P1)

**Goal**: Populate every task with target component, reason, dependencies, expected changes, required tests, risk level, and supporting evidence.  
**Independent Test**: Verify that generated tasks contain populated `reason`, `dependencies`, `expected_changes`, `required_tests`, `risk_level`, and `evidence` (diff snippets and caller chains).

### Implementation for User Story 2
- [x] T018 [US2] Implement `TaskSynthesizer` in `backend/src/trace/analysis/planner/task_synthesizer.py` extracting `reason`, `dependencies`, and `expected_changes` from syntax deltas
- [x] T019 [US2] Connect `TaskSynthesizer` with Neo4j `TESTED_BY` relationships and test filename patterns to populate `required_tests` in `backend/src/trace/analysis/planner/task_synthesizer.py`
- [x] T020 [US2] Inherit risk levels and bind diff snippets + call graph chains into `TaskEvidence` in `backend/src/trace/analysis/planner/task_synthesizer.py`
- [x] T021 [US2] Integrate `TaskSynthesizer` into `UpgradePlanService` in `backend/src/trace/services/planner.py`
- [x] T022 [P] [US2] Write unit tests verifying that all required metadata fields (`reason`, `expected_changes`, `required_tests`, `evidence`) are populated accurately in `backend/tests/unit/test_task_synthesizer.py`

**Checkpoint**: User Story 2 delivers rich, prescriptive guidance and verified evidence for each task.

---

## Phase 5: User Story 3 - Interactive Task Lifecycle & Progress Tracking (Priority: P2)

**Goal**: Provide task status transitions (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`), progress calculation, and filtered querying via API and Observatory UI.  
**Independent Test**: Update task statuses via `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}`, verifying that plan summary metrics update dynamically and display in the Observatory.

### Backend Implementation for User Story 3
- [x] T023 [US3] Implement `UpgradePlanService.update_task_status` in `backend/src/trace/services/planner.py` supporting `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`
- [x] T024 [US3] Implement automatic plan status transition to `COMPLETED` when all tasks reach `COMPLETED` or `SKIPPED` in `backend/src/trace/services/planner.py`
- [x] T025 [US3] Implement real-time recalculation of `summary_metrics` (`total_tasks`, `completed_tasks`, `progress_percentage`) in `backend/src/trace/services/planner.py`
- [x] T026 [US3] Implement `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}` in `backend/src/trace/api/planner/router.py`
- [x] T027 [US3] Implement `GET /api/v1/upgrade-plans/{plan_id}/tasks` with filtering and pagination in `backend/src/trace/api/planner/router.py`
- [x] T028 [US3] Implement `GET /api/v1/repositories/{repository_id}/upgrade-plans` in `backend/src/trace/api/planner/router.py`
- [x] T029 [P] [US3] Write integration tests for task lifecycle updates and progress metric recalculation in `backend/tests/integration/test_planner_api.py`

### Frontend Observatory Implementation for User Story 3
- [x] T030 [US3] Add top-level tab `"📋 Upgrade Planner (F07)"` in `frontend/app.py`
- [x] T031 [US3] Implement Plan Generation trigger controls (linking to active impact analysis) in `frontend/app.py`
- [x] T032 [US3] Implement Upgrade Plan header banner displaying progress bar (% completed, task counts, risk badge) in `frontend/app.py`
- [x] T033 [US3] Implement task filtering controls (by Status, Risk Tier, Architectural Category) in `frontend/app.py`
- [x] T034 [US3] Render interactive task cards displaying step numbers, category badges, reasons, dependencies, expected changes, required tests, and diff snippets in `frontend/app.py`
- [x] T035 [US3] Implement interactive status selectbox/checkbox on task cards making `PATCH` calls to update task state with immediate UI refresh in `frontend/app.py`
- [x] T036 [US3] Implement "Download Upgrade Plan JSON" button in `frontend/app.py`

**Checkpoint**: User Story 3 enables interactive task lifecycle management across API and UI.

---

## Phase 6: User Story 4 - Resilient Graph Topology Handling (Cycles, Disconnected Subgraphs & Massive Changes) (Priority: P2)

**Goal**: Guarantee robust termination on cyclic code graphs, partition disconnected subgraphs into parallel streams, and handle large changesets.  
**Independent Test**: Feed a call graph with cycles ($A \to B \to C \to A$) and disconnected components into the planner, asserting that cycles are tagged and grouped with zero infinite loops.

### Implementation for User Story 4
- [x] T037 [US4] Implement Tarjan's Strongly Connected Components (SCC) algorithm in `backend/src/trace/analysis/planner/dag_sequencer.py` to identify cycles
- [x] T038 [US4] Implement cyclic condensation and tag participating tasks with `is_circular: true` with co-dependency warnings in `backend/src/trace/analysis/planner/dag_sequencer.py`
- [x] T039 [US4] Implement Weakly Connected Components (WCC) decomposition to partition disconnected components into `parallel_group_id`s in `backend/src/trace/analysis/planner/dag_sequencer.py`
- [x] T040 [US4] Implement batching and pagination optimizations for massive changesets (>200 tasks) in `backend/src/trace/services/planner.py`
- [x] T041 [US4] Render parallel execution stream badges (`parallel_group_id`) and circular dependency alerts in `frontend/app.py`
- [x] T042 [P] [US4] Write unit tests for cycle detection, circular tagging, and parallel stream partitioning in `backend/tests/unit/test_dag_sequencer.py`

**Checkpoint**: User Story 4 guarantees resilience against enterprise codebase complexities.

---

## Phase 7: User Story 5 - Dual-Track Plan Enrichment (Optional OpenRouter AI Synthesis) (Priority: P3)

**Goal**: Support optional OpenRouter LLM enrichment for contextual refactoring instructions with 100% offline fallback.  
**Independent Test**: Verify plan generation with valid LLM config (enriched output) and invalid/missing LLM config (heuristic fallback with zero errors).

### Implementation for User Story 5
- [x] T043 [US5] Implement optional OpenRouter prompt and payload generator for contextual refactoring instructions in `backend/src/trace/analysis/planner/task_synthesizer.py`
- [x] T044 [US5] Implement graceful offline fallback in `backend/src/trace/services/planner.py` when OpenRouter credentials are absent or timeout
- [x] T045 [P] [US5] Write unit tests mocking OpenRouter enrichment and verifying fallback to deterministic heuristics in `backend/tests/unit/test_task_synthesizer.py`

**Checkpoint**: User Story 5 delivers dual-track reasoning fulfilling TRACE Constitution Principles I & II.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Logging, linting, type-checking, and end-to-end validation.

- [x] T046 [P] Ensure structured logging with `structlog` across all planner components in `backend/src/trace/services/planner.py` and `backend/src/trace/analysis/planner/`
- [x] T047 [P] Run static analysis and linting (`ruff check`, `ruff format`, `mypy`) across all new and modified planner files
- [x] T048 Execute end-to-end quickstart validation scenarios from `specs/007-upgrade-planner/quickstart.md`

---

## Dependencies & Execution Order

```text
Phase 1: Setup & Data Modeling (T001-T005)
         │
         ▼
Phase 2: Foundational Engine Infrastructure (T006-T009)
         │
         ▼
Phase 3: User Story 1 - Plan Generation (T010-T017) 🎯 MVP
         │
         ▼
Phase 4: User Story 2 - Task Metadata & Guidance (T018-T022)
         │
         ▼
Phase 5: User Story 3 - Interactive Lifecycle & UI (T023-T036)
         │
         ▼
Phase 6: User Story 4 - Resilient Graph Handling (T037-T042)
         │
         ▼
Phase 7: User Story 5 - Dual-Track LLM Enrichment (T043-T045)
         │
         ▼
Phase 8: Polish & E2E Validation (T046-T048)
```

---

## Parallel Execution Opportunities

- **Phase 1**: `T002`, `T003`, `T004` can execute in parallel once `T001` is defined.
- **Phase 2**: `T007`, `T008` (DAG Sequencer) can execute in parallel with `T006` (Tier Mapper).
- **Phase 4**: `T018`, `T019`, `T020` can be developed concurrently in `task_synthesizer.py`.
- **Phase 5**: Backend API endpoints (`T026`-`T028`) can be implemented in parallel with Frontend Observatory components (`T030`-`T036`).
- **Phase 8**: Linting (`T047`) and logging (`T046`) can execute in parallel.
