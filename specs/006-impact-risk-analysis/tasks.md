# Tasks: TRACE Phase 4 — F05: Impact Analysis & Risk Evaluation Engine

**Input**: Design documents from `specs/006-impact-risk-analysis/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/api.md`)  
**Prerequisites**: F01 (Repo Management), F02 (AST Code Extraction), F03 (Neo4j Graph), F04 (Version Change Diffing)  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[TaskID] [P?] [Story] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Target user story (US1, US2, US3, US4, US5)

---

## Phase 1: Setup & Data Modeling (Shared Infrastructure)

**Purpose**: Define core domain models, database schema, and storage scaffolding.

- [x] T001 Define domain entities (`DetailedImpact`, `CallerAtRisk`, `RiskFactor`, `RemediationStep`, `ImpactAnalysisAggregate`) in `backend/src/trace/domain/impact.py`
- [x] T002 [P] Create SQLAlchemy ORM model `ImpactAnalysisOrm` in `backend/src/trace/infrastructure/database/models/impact_analysis.py`
- [x] T003 [P] Add Alembic migration script for `impact_analyses` table in `backend/alembic/versions/`
- [x] T004 Setup artifact storage directory helper for impact analyses in `backend/src/trace/infrastructure/storage/artifact_store.py`

---

## Phase 2: Foundational Engine Infrastructure

**Purpose**: Core mathematical and graph infrastructure blocking downstream user stories.

- [x] T005 Implement `IntervalOverlapEngine` with interval condition $\max(F_s, H_s) \le \min(F_e, H_e)$ in `backend/src/trace/analysis/interval_overlap.py`
- [x] T006 Implement Decorator Expansion Rule in `backend/src/trace/analysis/interval_overlap.py` ensuring $F_{start} \le \text{decorator start}$
- [x] T007 [P] Implement `TransposedGraphEngine` supporting in-memory graph inversion $G^T = (V, E^T)$ in `backend/src/trace/analysis/graph_traversal.py`
- [x] T008 [P] Implement bounded BFS traversal (depth $\le 3$) on $G^T$ in `backend/src/trace/analysis/graph_traversal.py`
- [x] T009 Write unit tests for interval overlap and transposed BFS in `backend/tests/unit/test_interval_and_traversal.py`

**Checkpoint**: Foundation ready — user story implementation can proceed.

---

## Phase 3: User Story 1 - Zero-Context Diff Hunk Slicing & AST Intersection (Priority: P1) 🎯 MVP

**Goal**: Isolate changed lines via `git diff -U0`, map them to enclosing AST symbols, and capture hunk patch slices as `diff_snippet`.  
**Independent Test**: Given a unified diff, verify that only functions whose interval $[F_s, F_e]$ intersects hunk $[H_s, H_e]$ are returned with accurate lines affected and patch text.

### Implementation for User Story 1
- [x] T010 [US1] Extend `GitProvider` in `backend/src/trace/infrastructure/git/provider.py` to support zero-context diffing (`-U0`)
- [x] T011 [US1] Integrate `IntervalOverlapEngine` with `GitDiffParser` and `RepositoryAnalysis` in `backend/src/trace/services/impact.py`
- [x] T012 [US1] Attach exact hunk patch lines to each intersecting entity as `diff_snippet` (capped at 350 chars for LLM safety) in `backend/src/trace/analysis/interval_overlap.py`
- [x] T013 [P] [US1] Write unit tests for diff snippet extraction and decorator expansion in `backend/tests/unit/test_interval_and_traversal.py`

**Checkpoint**: User Story 1 works as a standalone slice — accurately maps diff lines to AST entities with snippets.

---

## Phase 4: User Story 2 - Multi-Hop Blast Radius via Graph Transposition $G^T$ (Priority: P1)

**Goal**: Trace upstream callers up to 3 hops away (direct callers $\to$ callers of callers $\to$ API endpoints) using $G^T$.  
**Independent Test**: In a test graph `A -> B -> C (modified)`, verify BFS on $G^T$ yields `B` (depth 1) and `A` (depth 2) with exact call chains.

### Implementation for User Story 2
- [x] T014 [US2] Connect `TransposedGraphEngine` to `RepositoryAnalysis.relationships` (AST) and Neo4j Cypher in `backend/src/trace/services/impact.py`
- [x] T015 [US2] Implement cycle detection and path distance tracking in `backend/src/trace/analysis/graph_traversal.py`
- [x] T016 [US2] Populate `inbound_callers` and `callers_at_risk` for each modified entity in `backend/src/trace/services/impact.py`
- [x] T017 [P] [US2] Write unit tests for multi-hop blast radius with cyclic and deep call chains in `backend/tests/unit/test_interval_and_traversal.py`

**Checkpoint**: User Story 2 delivers full multi-hop blast radius reachability.

---

## Phase 5: User Story 3 - Deterministic Transformation Intelligence & Actionable Remediation (Priority: P2)

**Goal**: Analyze diff snippets using deterministic syntax delta rules (`def`, `return`, `raise`) and synthesize a 4-step remediation plan.  
**Independent Test**: Feed diff snippets into `DeltaInferenceEngine` without network access, verifying accurate `change_summary`, `remediation_guidance`, and checklist generation.

### Implementation for User Story 3
- [x] T018 [US3] Implement `DeltaInferenceEngine` in `backend/src/trace/analysis/delta_inference.py` with regex rules for signature (`def`), return value (`return`), exception (`raise`), and logic statements
- [x] T019 [US3] Implement `HeuristicRuleEngine` in `backend/src/trace/analysis/reasoner/heuristic.py` generating `change_summary`, `justification`, and `remediation_guidance`
- [x] T020 [US3] Implement 4-step Actionable Remediation Plan synthesizer in `backend/src/trace/analysis/delta_inference.py` (Contract Changes $\to$ Missing Modules $\to$ Direct Callers $\to$ Integration Validation)
- [x] T021 [P] [US3] Implement `MermaidGenerator` in `backend/src/trace/analysis/graph_traversal.py` generating styled Mermaid diagrams (#ef4444 modified, #f59e0b at-risk)
- [x] T022 [P] [US3] Write unit tests for deterministic delta inference and remediation checklist in `backend/tests/unit/test_delta_inference.py`

**Checkpoint**: User Story 3 provides comprehensive remediation guidance offline with 100% determinism.

---

## Phase 6: User Story 4 - Dual-Track LLM Reasoning with Graceful Offline Fallback (Priority: P2)

**Goal**: Provide optional OpenRouter LLM enrichment when API key is provided, falling back gracefully to heuristic rules if absent or failing.  
**Independent Test**: Test pipeline with valid key (verifying enriched output), invalid key (verifying heuristic fallback), and null key (verifying offline execution).

### Implementation for User Story 4
- [x] T023 [US4] Define `DualTrackReasoner` protocol in `backend/src/trace/analysis/reasoner/base.py`
- [x] T024 [US4] Implement `OpenRouterLlmReasoner` in `backend/src/trace/analysis/reasoner/llm.py` with structured JSON prompt, entity summaries, and diff snippets
- [x] T025 [US4] Implement automatic fallback logic in `backend/src/trace/services/impact.py` catching timeout/rate limits and invoking `HeuristicRuleEngine`
- [x] T026 [P] [US4] Write unit tests mocking OpenRouter success, rate limits, and fallback in `backend/tests/unit/test_text_discovery_and_reasoner.py`

**Checkpoint**: User Story 4 delivers dual-track reasoning fulfilling TRACE Constitution Principles I & II.

---

## Phase 7: User Story 5 - Cross-Module Text & Configuration Reference Discovery (Priority: P3)

**Goal**: Discover non-code references (`\b<name>\b`) in YAML, JSON, Markdown, and test files outside the Python AST.  
**Independent Test**: Verify that modifying a function referenced in `deploy/tasks.yaml` populates `downstream_dependent_files`.

### Implementation for User Story 5
- [x] T027 [US5] Implement `TextDiscoveryEngine` in `backend/src/trace/analysis/text_discovery.py` using word-boundary regex across non-code files
- [x] T028 [US5] Exclude entity's own source file from matches to prevent self-referential false positives in `backend/src/trace/analysis/text_discovery.py`
- [x] T029 [US5] Wire discovered files into `downstream_dependent_files` in `backend/src/trace/services/impact.py`
- [x] T030 [P] [US5] Write unit tests for text discovery across configs and documentation in `backend/tests/unit/test_text_discovery_and_reasoner.py`

**Checkpoint**: Non-code configuration and documentation references are successfully tracked.

---

## Phase 8: Service Orchestration, REST API, & Frontend Observatory

**Purpose**: Assemble the complete pipeline, expose REST endpoints, and visualize in the Observatory dashboard.

- [x] T031 Implement `ImpactAnalysisService` in `backend/src/trace/services/impact.py` orchestrating slicing, BFS, text discovery, dual-track reasoning, and artifact persistence
- [x] T032 Implement Pydantic v2 schemas in `backend/src/trace/api/impact/schemas.py` matching the 4-key JSON contract
- [x] T033 Implement FastAPI router in `backend/src/trace/api/impact/router.py` (`POST /api/v1/impact/evaluate`, `GET /api/v1/impact/{id}`)
- [x] T034 Wire `impact_router` into `backend/src/trace/api/router.py` and `backend/src/trace/main.py`
- [x] T035 Add "⚡ Impact & Risk Analysis (F05)" tab in `frontend/app.py`
- [x] T036 Add OpenRouter API key and model selection controls in `frontend/app.py` sidebar
- [x] T037 Render unified impact cards, multi-hop caller trees, remediation checklist, and styled Mermaid canvas in `frontend/app.py`
- [x] T038 Write end-to-end integration tests in `backend/tests/api/test_impact_api.py`

---

## Phase 9: Nuanced Risk Analysis & Documentation-Only Classification Enhancement

**Purpose**: Prevent false-positive high-risk evaluations on cosmetic, docstring, comment, and non-code asset modifications.

- [x] T039 [Nuanced Risk] Add `is_doc_only` attribute to `DetailedImpact` domain entity and `DetailedImpactSchema` in `backend/src/trace/domain/impact.py` and `backend/src/trace/api/impact/schemas.py`
- [x] T040 [Nuanced Risk] Implement docstring, Sphinx/RST tag, and comment classification in `DeltaInferenceEngine` (`is_doc_only_diff`) in `backend/src/trace/analysis/delta_inference.py`
- [x] T041 [Nuanced Risk] Update `HeuristicRuleEngine` in `backend/src/trace/analysis/reasoner/heuristic.py` to produce non-breaking justifications and report `is_doc_only`
- [x] T042 [Nuanced Risk] Separate source code modules from non-code asset deletions and exclude doc-only modifications from caller risk escalation in `ImpactAnalysisService` in `backend/src/trace/services/impact.py`
- [x] T043 [Nuanced Risk] Update `_evaluate_risk` to assign `RiskLevel.LOW` for all-doc-only changes and non-code file deletions in `backend/src/trace/services/impact.py`
- [x] T044 [Nuanced Risk] Add comprehensive unit tests in `backend/tests/unit/test_nuanced_risk.py` verifying docstring typo, comment, and non-code deletion risk scoring

---

## Dependencies & Completion Order

```text
Phase 1: Setup & Models
      │
      ▼
Phase 2: Foundational Engines (Overlap & Transposed BFS)
      │
      ├───────────────────────┬────────────────────────┐
      ▼                       ▼                        ▼
Phase 3: US1 (Diff Slicing)  Phase 4: US2 (Multi-Hop) Phase 7: US5 (Text Discovery)
      │                       │                        │
      └───────────────────────┼────────────────────────┘
                              ▼
                 Phase 5: US3 (Heuristics & Plan)
                              │
                              ▼
                 Phase 6: US4 (Dual-Track LLM)
                              │
                              ▼
                 Phase 8: Service, API, & Streamlit Observatory
                              │
                              ▼
                 Phase 9: Nuanced Risk & Doc-Only Enhancement
```
