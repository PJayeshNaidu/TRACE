# Implementation Plan: TRACE Phase 4 — F05: Impact Analysis & Risk Evaluation Engine

**Feature Branch**: `006-impact-risk-analysis` | **Date**: 2026-09-30 | **Spec Reference**: [spec.md](spec.md)

---

## 1. Summary

Implement Phase 4 (F05) of TRACE: the **Impact Analysis & Risk Evaluation Engine**. 
F05 builds upon F02 (AST Code Extraction), F03 (Neo4j Dependency Graph), and F04 (Git Diff Slicing) to bridge physical line hunks into high-level semantic risk propagation. 

Key technical mechanisms:
1. Zero-context diff hunk slicing (`git diff -U0`) and mathematical interval intersection ($\max(F_s, H_s) \le \min(F_e, H_e)$) with Decorator Expansion.
2. Inverted call graph traversal ($G^T = (V, E^T)$) running BFS up to depth 3 to detect direct callers, callers of callers, and architectural entrypoints.
3. Cross-module word-boundary discovery (`\b<name>\b`) across configs (YAML/JSON) and documentation (Markdown).
4. Deterministic diff syntax delta rules (`def`, `return`, `raise`, statements) generating structured `change_summary`, `justification`, and `remediation_guidance`.
5. Prioritized 4-step actionable remediation plan (Contract Changes $\to$ Missing Modules $\to$ Direct Callers $\to$ Integration Validation).
6. Dual-Track reasoning: Deterministic offline heuristic engine (default) + optional online OpenRouter LLM enrichment.
7. Unified 4-key JSON response schema and Mermaid graph generation with color styling (#ef4444 for modified, #f59e0b for at-risk callers).

---

## 2. Technical Context

**Language/Version**: Python 3.11+  
**Primary Frameworks**: FastAPI (REST APIs), Pydantic v2 (Validation & Schemas), NetworkX / In-memory Adjacency + Neo4j (Graph Traversals), Streamlit (Observatory UI)  
**Storage**: SQLite / PostgreSQL (SQLAlchemy ORM metadata) + FileArtifactStore (`.trace/artifacts/impacts/`)  
**Testing**: `pytest`, `pytest-asyncio`  
**Target Platform**: Linux / Windows containerized environments (Docker Compose)  
**Performance Goals**:
- Diff parsing and AST interval intersection $< 1.0\text{s}$ for changesets under 50 files.
- Transposed multi-hop BFS traversal $< 500\text{ms}$ for graphs up to 5,000 nodes.
- Full impact analysis completed $< 2.0\text{s}$ in deterministic offline mode.
**Constraints**:
- Strict adherence to Constitution Principle I (Evidence over Hallucination) and Principle II (Deterministic Analysis before Probabilistic Inference).
- Offline capability: Zero external network/API dependencies required when no LLM key is configured.
- Backward compatibility: Preserves existing F04 diff APIs while exposing new `/api/v1/impact/` endpoints.

---

## 3. Constitution Check

*GATE: Must pass before implementation. Validated against `.specify/memory/constitution.md`.*

| Principle | Compliance Status | Justification / Architectural Evidence |
| :--- | :--- | :--- |
| **I. Evidence over Hallucination** | **PASS** | Every caller, affected file, and risk factor is mathematically derived from AST spans, Git diff hunks, or graph traversal. LLM never invents dependencies. |
| **II. Deterministic before Probabilistic** | **PASS** | The pipeline runs diff slicing, AST intersection, $G^T$ BFS, and regex delta rules deterministically first. The LLM is strictly an optional reasoning layer. |
| **III. Human-in-the-Loop** | **PASS** | Outputs structured checklists and risk factors for human review in the Observatory UI before applying code changes. |
| **VIII. Architectural Integrity** | **PASS** | Clean separation across domain models, analysis engines, service orchestration, database persistence, and API schemas. |
| **X. Incremental Delivery** | **PASS** | F05 encapsulates impact analysis and risk evaluation; delivers standalone value and feeds into F06 (Upgrade Plan Generator). |

---

## 4. Project Structure & File Layout

### Documentation (this feature)
```text
specs/006-impact-risk-analysis/
├── spec.md                     # Feature requirements & user stories
├── plan.md                     # Implementation plan (this document)
├── data-model.md               # Domain models & database schema
├── contracts/
│   └── api.md                  # REST API contract & JSON schemas
├── checklists/
│   └── requirements.md         # Quality checklist
└── tasks.md                    # Actionable implementation tasks
```

### Source Code Structure
```text
backend/src/trace/
├── domain/
│   └── impact.py               # Domain models: DetailedImpact, ImpactAnalysisRun, RiskProfile, RemediationPlan
├── analysis/
│   ├── interval_overlap.py     # Interval intersection & Decorator Expansion engine
│   ├── graph_traversal.py      # Directed graph inversion G^T & bounded multi-hop BFS engine
│   ├── text_discovery.py       # Cross-module text & config reference scanner (\b<name>\b)
│   ├── delta_inference.py      # Deterministic diff syntax delta rule engine (def, return, raise)
│   └── reasoner/
│       ├── base.py             # DualTrackReasoner abstract interface
│       ├── heuristic.py        # Deterministic HeuristicRuleEngine (offline)
│       └── llm.py              # OpenRouterLlmReasoner (online optional enrichment)
├── infrastructure/
│   └── database/models/
│       └── impact_analysis.py  # SQLAlchemy ORM model for impact_analyses table
├── services/
│   └── impact.py               # ImpactAnalysisService orchestrating pipeline & artifact storage
└── api/
    └── impact/
        ├── router.py           # REST endpoints: POST /api/v1/impact/evaluate, GET /api/v1/impact/{id}
        └── schemas.py          # Pydantic v2 schemas for request & 4-key JSON response payload
```

---

## 5. Architectural Component Flow

```text
[HTTP Request: POST /api/v1/impact/evaluate]
               │
               ▼
[ImpactRouter: trace/api/impact/router.py]
               │
               ▼
[Service: ImpactAnalysisService (trace/services/impact.py)]
  ├──► 1. GitProvider: Resolve base/target commit hashes & run `git diff -U0`
  ├──► 2. GitDiffParser: Extract FileDiffs and hunks with line intervals [H_start, H_end]
  ├──► 3. IntervalOverlapEngine:
  │       ├── Decorator Expansion: Set F_start to first decorator
  │       ├── Filter modified entities: max(F_s, H_s) <= min(F_e, H_e)
  │       └── Bind hunk patch lines as `diff_snippet`
  ├──► 4. TransposedGraphEngine:
  │       ├── Invert call graph edges: E^T = {(v, u) | (u, v) in E}
  │       └── Multi-Hop BFS (depth <= 3) -> CallersAtRisk ordered by distance
  ├──► 5. TextDiscoveryEngine:
  │       └── Scan repository configs/docs (\b<name>\b) -> downstream_dependent_files
  ├──► 6. DualTrackReasoner (Heuristic vs OpenRouter):
  │       ├── DeltaInferenceEngine: Inspect diff_snippets for def, return, raise, statements
  │       ├── Synthesize 4-step Actionable Remediation Plan
  │       └── (Optional) LLM prompt with entity summaries + capped diff snippets (~350 chars)
  ├──► 7. MermaidGenerator:
  │       └── Auto-generate styled Mermaid diagram (#ef4444 modified, #f59e0b at-risk)
  ├──► 8. Storage & Persistence:
  │       ├── FileArtifactStore: Write complete 4-key JSON artifact to .trace/artifacts/impacts/
  │       └── DatabaseGateway: Persist ImpactAnalysisOrm record
  └──► 9. Return Unified 4-Key JSON Payload
```

---

## 6. Implementation Phases & Milestones

- **Phase 1: Domain Entities & Data Layer**:
  - Implement `trace.domain.impact` models.
  - Implement `ImpactAnalysisOrm` model and Alembic migration.
- **Phase 2: Mathematical Slicing & Graph Algorithms**:
  - Implement `IntervalOverlapEngine` with Decorator Expansion.
  - Implement `TransposedGraphEngine` with multi-hop BFS on $G^T$.
  - Implement `TextDiscoveryEngine` for non-code references.
- **Phase 3: Transformation Intelligence & Dual-Track Reasoner**:
  - Implement `DeltaInferenceEngine` (deterministic regex rules).
  - Implement `HeuristicRuleEngine` and `OpenRouterLlmReasoner`.
  - Implement 4-step Remediation Plan synthesizer and Mermaid styling engine.
- **Phase 4: Service Orchestration & REST API**:
  - Implement `ImpactAnalysisService` tying all components together.
  - Implement FastAPI router in `trace.api.impact.router` adhering to the 4-key JSON contract.
- **Phase 5: Frontend Observatory Integration & E2E Verification**:
  - Add "Impact & Risk Analysis (F05)" tab in `frontend/app.py`.
  - Add optional OpenRouter API key and model selection controls in Streamlit sidebar.
  - Display unified impact cards, multi-hop caller trees, and interactive graph visualizations.
  - End-to-end tests validating deterministic execution and optional LLM enrichment.
