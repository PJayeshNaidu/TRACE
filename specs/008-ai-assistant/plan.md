# Implementation Plan: TRACE Phase 8 — F10: AI Assistant (Contextual Q&A Layer)

**Feature Branch**: `008-ai-assistant` | **Date**: 2026-10-07 | **Spec Reference**: [spec.md](spec.md)  
**Related Documents**: [research.md](research.md) | [data-model.md](data-model.md) | [contracts/api.md](contracts/api.md) | [quickstart.md](quickstart.md)  
**Status**: Evolution Plan (Baseline Implemented, Dynamic LangGraph Architecture Refined for Context Retrieval & Quality)

---

## 1. Executive Summary & Evolution Overview

### 1.1 Baseline Implementation (Phases 1–6 Completed)
Phase 8 (F10) of TRACE has completed its baseline implementation:
- **Pydantic Contracts**: `AssistantQueryRequest` and `AssistantQueryResponse` in `backend/src/trace/schemas/assistant.py`.
- **Single-Pass Retrieval**: `AssistantRetrievalService` in `backend/src/trace/services/assistant/retrieval.py` performing deterministic symbol matching and fixed, parallel extraction across Neo4j, PostgreSQL impact analyses, upgrade plans, and version comparisons.
- **Synthesis & Fallback Engine**: `AssistantSynthesisService` in `backend/src/trace/services/assistant/synthesis.py` connecting to OpenRouter (`meta-llama/llama-3.3-70b-instruct:free`) with tenacity retries and `DeterministicFallbackGenerator` when offline.
- **FastAPI Endpoints**: `POST /api/v1/assistant/ask` and `GET /api/v1/assistant/status` in `backend/src/trace/api/assistant/router.py`.
- **Neo-Brutalist Observatory UI**: Collapsible assistant drawer in `frontend/app.py` with suggestion chips and source cards, strictly isolating canvas renderers (lines 51–643 and 870–1239).

### 1.2 Evolution to Context Retrieval & Quality Refinement (Target Architecture)
Real-world testing of the dynamic workflow identified that the assistant was overly restrictive and frequently returned `INSUFFICIENT_EVIDENCE` for answerable questions (e.g. language/stack questions, broad dependencies, extension feasibility, general knowledge, or incomplete upgrade plan task retrieval).

This plan details the evolutionary refinement of F10 into a **resilient, tool-augmented reasoning copilot** within the established LangGraph state machine:

```text
                                [ User Question & Bounded History ]
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │       Node 1: Understand Question     │
                             │  - Semantic intent classification     │
                             │  - Entity / scope / task resolution   │
                             │  - General knowledge bypass check     │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │        Node 2: Select Tools           │
                             │  - Composable 9-tool TRACE suite      │
                             │  - Non-exclusive multi-tool dispatch  │
                             │  - Binds project_id & analysis_run_id │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │        Node 3: Execute Tools          │
                             │  - Concurrent async tool dispatch     │
                             │  - Bounded AST snippets & graph edges │
                             │  - Graceful per-tool error capture    │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                     ┌──────►│     Node 4: Evaluate Sufficiency      │
                     │       │  - Sufficient? -> Synthesize          │
                     │       │  - Insufficient & hops < 2? -> Loop   │
                     │       │  - Insufficient & hops = 2? -> Report │
                     │       └───────────┬───────────────┬───────────┘
   [Hop 2 Retrieval] │                   │               │
  (e.g., inspect AST │     [Sufficient]  │               │ [Max Hops Reached /
   diff for caller)  │                   ▼               │  Missing Evidence]
                     └───────────────────┘               ▼
                             ┌───────────────────────────────────────┐
                             │       Node 5: Synthesize Answer       │
                             │  - Prompt budget < 1,500 tokens       │
                             │  - Grounded reasoning (facts vs infer)│
                             │  - Narrowed Missing Entity Guard      │
                             │  - Deterministic offline fallback     │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │       Node 6: Assemble Response       │
                             │  - Clean natural engineering answer   │
                             │  - On-demand "View evidence" expander │
                             │  - Observability & latency telemetry  │
                             └───────────────────────────────────────┘
```

---

## 2. Technical Context & Infrastructure Verification

### 2.1 Runtime & Frameworks
- **Language/Runtime**: Python 3.12+
- **Backend Framework**: FastAPI (async REST APIs), Pydantic v2 (Validation & Strict Schemas)
- **Agent Workflow Engine**: `langgraph>=0.2.0` (compiled `StateGraph`), `langchain-core`
- **Persistence & Graph Access**: PostgreSQL 16 (SQLAlchemy 2.0 `asyncpg`), Neo4j 5.x Bolt driver (Cypher parameterized traversal), `FileArtifactStore` (`.trace/artifacts/`)
- **LLM Provider**: OpenRouter API (`meta-llama/llama-3.3-70b-instruct:free` default) via `httpx` and `tenacity` retry wrapper
- **Frontend**: Streamlit with custom Neo-Brutalist CSS tokens (`frontend/app.py`)
- **Testing & Benchmarking**: `pytest`, `pytest-asyncio`

### 2.2 Dependency & Infrastructure Change Verification
A strict audit of project configuration confirms:
| Asset | Change Required? | Architectural Justification |
| :--- | :---: | :--- |
| **`backend/pyproject.toml`** | **NO** | `langgraph>=0.2.0` is already declared in dependencies. |
| **`backend/uv.lock`** | **NO** | `langgraph 1.2.12`, `langgraph-checkpoint 4.2.0`, and `langchain-core` are locked and resolved. |
| **`backend/Dockerfile`** | **NO** | Container build runs `uv sync --no-dev`, which installs all locked dependencies including LangGraph. |
| **`docker-compose.yml`** | **NO** | No new services, companion containers, or ports are required. |
| **PostgreSQL Schema** | **NO** | Operates over existing ORM models (`AnalysisRunOrm`, `ImpactAnalysisOrm`, `UpgradePlanOrm`, etc.). |
| **Neo4j Schema** | **NO** | Operates over existing graph nodes and edges (`CALLS`, `IMPORTS`, `DEPENDS_ON`). |
| **Environment Variables** | **NO** | Operates using existing `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` configuration. |

---

## 3. Constitution & Guardrail Compliance

| Principle | Compliance Status | Implementation Evidence |
| :--- | :---: | :--- |
| **I. Evidence over Hallucination** | **PASS** | Every factual statement in generated answers must cite a verified `EvidenceSource`. Speculative prompt substitution is eliminated. The LLM explicitly distinguishes directly retrieved facts, reasonable inferences, and unavailable information. |
| **II. Deterministic before Probabilistic** | **PASS** | Tool execution, symbol extraction, sufficiency evaluation, and offline fallback use deterministic code before LLM synthesis. |
| **III. Controlled Tool Abstraction** | **PASS** | The LLM interacts exclusively through 9 typed Python tools. No raw SQL or Cypher query generation is permitted. |
| **IV. Bounded Execution** | **PASS** | Hard cap of 2 retrieval iterations (max 3 tool calls per hop) and $< 1,500$ prompt tokens. |
| **V. Provider Independence** | **PASS** | Synthesis invokes OpenRouter adapter with fallback models; offline deterministic generator executes when unkeyed. |
| **VI. Strict Scoping & Isolation** | **PASS** | All tools require and enforce `project_id` and `analysis_run_id`. Stale cross-run queries are eliminated. |
| **VII. Frontend Protection & Clean UX** | **PASS** | Canvas rendering blocks (lines 51–643 and 870–1239 in `frontend/app.py`) are strictly preserved. Answers are clean and readable; raw JSON/SVG dumps are hidden behind an on-demand expander. |
| **VIII. Observability over Assumptions** | **PASS** | Unmeasured latency claims are replaced by active timing instrumentation across tool execution and LLM synthesis. |

---

## 4. Project Structure & File Layout

### 4.1 Specification & Plan Documentation
```text
specs/008-ai-assistant/
├── spec.md                     # Evolved feature requirements & 10 acceptance benchmarks
├── plan.md                     # Incremental implementation plan (this document)
├── research.md                 # Architectural decisions & LangGraph audit
├── data-model.md               # Pydantic schemas, AssistantState & tool contracts
├── quickstart.md               # Validation guide for 10 benchmark queries
└── contracts/
    └── api.md                  # REST contract for POST /api/v1/assistant/ask
```

### 4.2 Source Code Layout
```text
backend/src/trace/
├── schemas/
│   └── assistant.py                    # Update: add execution telemetry, ChatMessage, intent, grounding_status
├── services/
│   └── assistant/
│       ├── __init__.py
│       ├── tools.py                    # 9 typed, composable, run-scoped retrieval tools wrapping TRACE domain services
│       ├── state.py                    # Typed AssistantState & evidence merge reducers
│       ├── workflow.py                 # Compiled LangGraph StateGraph, semantic routing & multi-tool dispatch
│       ├── retrieval.py                # Candidate symbol extractor & source assembler
│       └── synthesis.py                # Grounded prompt construction, facts vs inference guard, offline fallback
└── api/
    └── assistant/
        └── router.py                   # REST endpoints with execution latency headers/telemetry

frontend/
└── app.py                              # Clean answer presentation, unobtrusive evidence expander (canvas untouched)

backend/tests/
├── unit/
│   ├── test_assistant_schemas.py       # Schema validation tests
│   ├── test_assistant_retrieval.py     # Candidate extraction tests
│   ├── test_assistant_synthesis.py     # Synthesis & offline fallback tests
│   ├── test_assistant_tools.py         # Unit tests for the 9 typed TRACE tools
│   ├── test_assistant_workflow.py      # Workflow routing, multi-tool selection, and sufficiency tests
│   └── test_assistant_benchmarks.py    # Acceptance Scenarios A through J verification
└── api/
    └── test_assistant_api.py           # API integration tests
```

---

## 5. Detailed Design: The 9-Tool Suite, State, and Graph Topology

### 5.1 The Composable 9-Tool Suite (`backend/src/trace/services/assistant/tools.py`)

The assistant operates over 9 composable, typed Python retrieval tools. No additional tools are introduced, preserving a small and focused architecture:

```python
class AssistantTools:
    """Encapsulates typed retrieval tools operating over existing TRACE domain services."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        graph_gateway: GraphGateway,
        analysis_service: AnalysisService,
        impact_service: ImpactService,
        planner_service: PlannerService,
        diff_service: VersionChangeService,
        artifact_store: FileArtifactStore,
    ) -> None: ...
```

#### Detailed Tool Contracts:

1. **`get_project_overview(project_id: UUID, analysis_run_id: UUID | None = None) -> dict[str, Any]`**
   - *Role*: **Primary** retrieval tool for broad repository-level questions (*"What language is this?"*, *"What is this project?"*).
   - *Reuses*: `AnalysisService.get_repository_summary(analysis_run_id)` + `AnalysisRunOrm`.
   - *Output*: Primary languages, file counts, total code symbols, framework indicators, entry points, and repository scale.
   - *Scoping*: Strict `analysis_run_id` (or latest completed run for `project_id`).

2. **`search_codebase(query: str, analysis_run_id: UUID | None = None) -> list[dict[str, Any]]`**
   - *Role*: Search for files, modules, classes, and functions across the codebase without requiring exact match.
   - *Behavior*: Does **not** trigger Missing Entity Guard on zero matches (supports exploratory questions like *"Can I add payment functionality?"*).
   - *Output*: Matching symbols with file paths, kinds, line spans, and architectural placement hints.

3. **`get_symbol_context(qualified_name: str, analysis_run_id: UUID | None = None) -> dict[str, Any]`**
   - *Role*: Focused inspection of a specific code entity.
   - *Behavior*: Retrieves signature, parameters, docstrings, complexity metrics, bounded source snippet ($\le 40$ lines), and direct callers/callees.
   - *Guard*: If a specific requested symbol is not found, marks symbol as missing for Narrow Missing Entity Guard evaluation.

4. **`get_dependencies(symbol: str | None = None, direction: str = "both", depth: int = 1, analysis_run_id: UUID | None = None) -> dict[str, Any]`**
   - *Role*: Retrieve internal call/import graph edges and external package dependencies.
   - *Broad Query Behavior*: When `symbol` is omitted (e.g. *"What dependencies are present?"*), returns:
     - `external_dependencies`: Package requirements (e.g. `fastapi`, `pydantic`, `neo4j`).
     - `internal_relationships`: Top internal module dependency couplings (`CALLS`, `IMPORTS`, `DEPENDS_ON`).
   - *Focused Query Behavior*: When `symbol` is specified, returns directional call graph edges up to requested depth ($\le 2$).

5. **`get_change_analysis(repository_id: UUID | None = None, revision_range: str | None = None) -> dict[str, Any]`**
   - *Role*: Retrieve AST-level diffs, parameter modifications, breaking change flags, and modified/added/deleted files from F04 records.
   - *Reuses*: `VersionComparisonOrm` and `VersionChangeService.get_comparison`.

6. **`get_risk_analysis(symbol_or_component: str | None = None, analysis_run_id: UUID | None = None) -> dict[str, Any]`**
   - *Role*: Retrieve blast radius, numerical risk score, risk level (`HIGH`, `MEDIUM`, `LOW`), contributing risk factors, and recommended remediations from F05/F06 records.
   - *Behavior*: When querying run-level risk (e.g. *"Why is python-proj high risk?"*), retrieves overall run risk metrics without requiring a code symbol.

7. **`get_upgrade_plan(task_identifiers: list[str] | None = None, repository_id: UUID | None = None) -> list[dict[str, Any]]`**
   - *Role*: Retrieve upgrade tasks, phase tiers, prerequisite task DAG relationships, and execution rationales from F07 records.
   - *Natural Language Resolution*: Resolves references like `"Task 1"` and `"Task 4"` to `["TASK-001", "TASK-004"]` or their respective step numbers, retrieving all requested tasks concurrently.

8. **`get_test_coverage(component: str | None = None, analysis_run_id: UUID | None = None) -> dict[str, Any]`**
   - *Role*: Retrieve test functions, test suites, and test references for affected components.
   - *Deficit Handling*: If line-level coverage is not analyzed, cleanly returns explicit deficit status (`coverage_analyzed: False`) without raising an evidence failure.

9. **`search_project_knowledge(query: str, analysis_run_id: UUID | None = None) -> list[dict[str, Any]]`**
   - *Role*: **Supplementary / fallback** tool for broad unstructured or semi-structured analysis metadata when specialized tools do not yield complete context.

---

### 5.2 Agent State Design (`backend/src/trace/services/assistant/state.py`)

```python
from typing import Annotated, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from trace.schemas.assistant import ChatMessage, EvidenceSource


def merge_evidence(current: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reducer combining evidence items without duplicates, capped at 25 items."""
    seen = {f"{item.get('type')}:{item.get('identifier')}" for item in current}
    merged = list(current)
    for item in new_items:
        key = f"{item.get('type')}:{item.get('identifier')}"
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged[:25]


class AssistantState(BaseModel):
    # Context & Scope
    project_id: UUID
    analysis_run_id: UUID | None = None
    question: str
    history: list[ChatMessage] = Field(default_factory=list)

    # Workflow Reasoning
    intents: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)
    task_identifiers: list[str] = Field(default_factory=list)
    pending_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    iteration_count: int = 0
    is_sufficient: bool = False
    is_general_knowledge: bool = False

    # Evidence Store
    raw_evidence: Annotated[list[dict[str, Any]], merge_evidence] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)

    # Output & Observability
    final_answer: str = ""
    grounding_status: Literal[
        "DETERMINISTIC_GROUNDED",
        "PARTIAL_EVIDENCE",
        "FALLBACK_DETERMINISTIC",
        "INSUFFICIENT_EVIDENCE",
    ] = "INSUFFICIENT_EVIDENCE"
    model_used: str = ""
    suggested_followups: list[str] = Field(default_factory=list)
    error_message: str | None = None
    execution_time_ms: float = 0.0
```

---

### 5.3 LangGraph StateGraph Topology & Refined Node Responsibilities

```python
from langgraph.graph import END, StateGraph
from trace.services.assistant/state import AssistantState


def build_assistant_graph(tools: AssistantTools, synthesis_svc: AssistantSynthesisService) -> Any:
    workflow = StateGraph(AssistantState)

    workflow.add_node("understand_question", create_understand_node())
    workflow.add_node("select_tools", create_select_tools_node())
    workflow.add_node("execute_tools", create_execute_tools_node(tools))
    workflow.add_node("evaluate_sufficiency", create_sufficiency_node())
    workflow.add_node("synthesize_answer", create_synthesize_node(synthesis_svc))
    workflow.add_node("assemble_response", create_assemble_node())

    workflow.set_entry_point("understand_question")
    
    # Conditional bypass for general knowledge
    workflow.add_conditional_edges(
        "understand_question",
        route_after_understand,
        {
            "bypass_to_synthesis": "synthesize_answer",
            "proceed_to_tools": "select_tools",
        },
    )

    workflow.add_edge("select_tools", "execute_tools")
    workflow.add_edge("execute_tools", "evaluate_sufficiency")

    # Conditional Branch: Loop back if insufficient and budget remains
    workflow.add_conditional_edges(
        "evaluate_sufficiency",
        route_after_sufficiency,
        {
            "loop_retrieval": "select_tools",
            "proceed_to_synthesis": "synthesize_answer",
        },
    )

    workflow.add_edge("synthesize_answer", "assemble_response")
    workflow.add_edge("assemble_response", END)

    return workflow.compile()
```

#### Detailed Node Responsibilities:

1. **`understand_question` (Semantic Classification & Bypass)**:
   - **Semantic Intent Classification**: Classifies intent semantically rather than relying on exact keyword triggers. Taxonomy: `PROJECT_OVERVIEW`, `CODE_SEARCH`, `SYMBOL_CONTEXT`, `DEPENDENCY`, `CHANGE_ANALYSIS`, `IMPACT_ANALYSIS`, `RISK_ANALYSIS`, `UPGRADE_PLAN`, `TEST_ANALYSIS`, `GENERAL_KNOWLEDGE`.
   - **Multi-Intent Detection**: Detects multiple intents (e.g. `UPGRADE_PLAN` + `DEPENDENCY`, or `CODE_SEARCH` + `PROJECT_OVERVIEW`).
   - **Entity Extraction**: Distinguishes code symbols from project names (`python-proj`), revision tags (`HEAD`), and task references (`Task 1`, `Task 4`).
   - **General Knowledge Bypass**: If question is general knowledge (*"Why is the sky blue?"*), sets `is_general_knowledge = True` and routes directly to `synthesize_answer`.

2. **`select_tools` (Non-Exclusive Multi-Tool Scheduling)**:
   - Tool selection is **not mutually exclusive**. A single question can schedule multiple tools concurrently:
     - *"Why does Task 1 precede Task 4?"* $\to$ `get_upgrade_plan(task_identifiers=["TASK-001", "TASK-004"])` + `get_dependencies`.
     - *"Why is OrderService high risk?"* $\to$ `search_codebase("OrderService")` + `get_risk_analysis("OrderService")`.
     - *"What dependencies are present?"* $\to$ `get_dependencies(symbol=None)` (retrieves both internal edges and external packages).
     - Broad questions (*"What is this project?"*) $\to$ `get_project_overview` (primary) + `search_project_knowledge` (supplementary).

3. **`execute_tools` (Concurrent Async Execution)**:
   - Executes scheduled tools concurrently via `asyncio.gather`.
   - Normalizes tool findings into `raw_evidence` and creates `EvidenceSource` objects.
   - Increments `iteration_count`.

4. **`evaluate_sufficiency` (Narrow Missing Entity Guard)**:
   - **Narrow Scope**: The Missing Entity Guard is restricted **strictly** to queries classified as `SYMBOL_CONTEXT` where a specific code symbol was claimed to exist.
   - **Exploratory Protection**: Exploratory queries (`CODE_SEARCH`, `PROJECT_OVERVIEW`, e.g. *"Can I add payment functionality?"*) MUST NOT be marked insufficient merely because payment symbols do not exist.
   - If `iteration_count >= 2` or tools returned relevant records, marks `is_sufficient = True`.

5. **`synthesize_answer` (Grounded Reasoning & Facts vs. Inference)**:
   - Formats compact prompt ($< 1,500$ tokens).
   - Instructs LLM to clearly distinguish:
     - **Directly retrieved facts** (e.g. exact risk scores, declared dependencies, task tiers).
     - **Reasonable architectural inferences** (e.g. recommended module structure for new payment features).
     - **Unavailable information** (e.g. explicitly stating test coverage is unanalyzed rather than guessing).
   - Never manufactures dependencies, risk factors, or task relationships.
   - When offline or unkeyed, executes `DeterministicFallbackGenerator`.

6. **`assemble_response` (Clean UX & Observability)**:
   - Formats final response with clean engineering answer text (no raw JSON, SVG, or internal ID dumps).
   - Provides clean on-demand expander contract for full evidence inspection.
   - Captures tool and synthesis execution timings for telemetry.

---

## 6. Incremental Implementation Phases

```text
Phase 14A: Composable 9-Tool Suite Refinements
                   │
                   ▼
Phase 14B: Semantic Routing & Multi-Tool Dispatch
                   │
                   ▼
Phase 14C: Grounded Synthesis & Narrow Entity Guard
                   │
                   ▼
Phase 14D: Clean Frontend Expander UI
                   │
                   ▼
Phase 14E: Acceptance Benchmark Suite (Scenarios A–J)
```

### Phase 14A: Composable 9-Tool Suite Refinements
- **Target File**: `backend/src/trace/services/assistant/tools.py`
- Refine existing tools and add missing operations to complete the 9-tool suite:
  1. `get_project_overview`: primary tool returning language, frameworks, scale.
  2. `search_codebase`: exploratory search without strict symbol existence enforcement.
  3. `get_symbol_context`: signature, AST parameters, docstrings, $\le 40$-line snippet.
  4. `get_dependencies`: distinguish internal graph edges vs external packages.
  5. `get_change_analysis`: diffs, breaking changes, modified parameters.
  6. `get_risk_analysis`: handle project/run-level risk as well as symbol-level risk.
  7. `get_upgrade_plan`: parse natural task identifiers (`Task 1`, `Task 4`) and fetch all requested tasks.
  8. `get_test_coverage`: component tests and clean deficit reporting when unanalyzed.
  9. `search_project_knowledge`: supplementary analysis metadata fallback.
- **Verification**: `pytest backend/tests/unit/test_assistant_tools.py -v`.

### Phase 14B: Semantic Routing & Multi-Tool Dispatch
- **Target File**: `backend/src/trace/services/assistant/workflow.py`
- Implement semantic intent classification covering the 10 taxonomy categories.
- Implement multi-tool scheduling (non-mutually-exclusive dispatch).
- Implement general knowledge bypass directly to synthesis.
- Narrow the Missing Entity Guard in `evaluate_sufficiency` so exploratory queries are never aborted.
- **Verification**: `pytest backend/tests/unit/test_assistant_workflow.py -v`.

### Phase 14C: Grounded Synthesis & Reasoning Prompting
- **Target File**: `backend/src/trace/services/assistant/synthesis.py`
- Update system prompt to mandate explicit separation of verified facts, reasonable inferences, and unavailable information.
- Enhance `DeterministicFallbackGenerator` to format clean summaries for project overviews, dependencies (internal/external), and upgrade plans.
- Add latency measurement telemetry.
- **Verification**: `pytest backend/tests/unit/test_assistant_synthesis.py -v`.

### Phase 14D: Clean Frontend Expander UI
- **Target File**: `frontend/app.py` (lines 1840–1920)
- **STRICT BOUNDARY**: Preserve lines 51–643 and 870–1239 (Force-Directed Graph canvas).
- Clean normal answer display: remove raw JSON dumps and tool payloads from message body.
- Render evidence sources in an optional, collapsible Streamlit expander (`st.expander("View Evidence Sources")`).
- **Verification**: `python -m py_compile frontend/app.py`.

### Phase 14E: Acceptance Benchmark Suite (Scenarios A through J)
- **Target File**: `backend/tests/unit/test_assistant_benchmarks.py`
- Implement automated test scenarios verifying Acceptance Scenarios A through J:
  - Scenario A: *"What language is this project written in?"*
  - Scenario B: *"What dependencies are present?"*
  - Scenario C: *"Why does Task 1 precede Task 4?"*
  - Scenario D: *"Why is python-proj classified as high risk?"*
  - Scenario E: *"What changed between revisions?"*
  - Scenario F: *"Show me everything affected by PaymentAPI."*
  - Scenario G: *"Which affected components have low test coverage?"*
  - Scenario H: *"Can I add payment-related functionality?"*
  - Scenario I: *"What is this project?"*
  - Scenario J: *"Why is the sky blue?"*
- Measure execution latency during benchmark execution.
- **Verification**: `pytest backend/tests/unit/test_assistant_benchmarks.py -v`.

---

## 7. Acceptance Benchmark Matrix (Scenarios A through J)

| Scenario | Question | Expected Tool Selection | Grounding Expectation |
| :--- | :--- | :--- | :--- |
| **A: Language/Stack** | *"What language is this project written in?"* | `get_project_overview` | Cites Python and repository file metrics; does not fail on symbol extraction. |
| **B: Dependencies** | *"What dependencies are present?"* | `get_dependencies(symbol=None)` | Cites external package dependencies and internal graph relationships. |
| **C: Task Precedence** | *"Why does Task 1 precede Task 4?"* | `get_upgrade_plan` + `get_dependencies` | Explains prerequisite DAG edge and tier hierarchy between Task 1 and 4. |
| **D: Project Risk** | *"Why is python-proj classified as high risk?"* | `get_risk_analysis` | Cites overall run risk score, changed entities count, and blast radius. |
| **E: Revision Diffs** | *"What changed between revisions?"* | `get_change_analysis` | Summarizes changed files and breaking parameter alterations with diff citations. |
| **F: Blast Radius** | *"Show me everything affected by PaymentAPI."* | `get_dependencies(symbol="PaymentAPI", depth=2)` | Groups direct and transitive downstream dependents. |
| **G: Test Coverage** | *"Which affected components have low test coverage?"* | `get_test_coverage` + `get_risk_analysis` | Cites components with missing tests or reports unanalyzed coverage cleanly. |
| **H: Feasibility** | *"Can I add payment-related functionality?"* | `search_codebase` + `get_project_overview` | Does not trigger Missing Entity Guard; suggests architectural integration point. |
| **I: Project Overview**| *"What is this project?"* | `get_project_overview` | Explains project purpose, scale, and entry points from analysis metadata. |
| **J: General Knowledge**| *"Why is the sky blue?"* | *None (Bypassed)* | Answers scientific Rayleigh scattering question without querying TRACE tools. |

---

## 8. Summary of Complexity Tracking & Guardrail Justification

| Decision | Why Needed | Alternative Rejected |
| :--- | :--- | :--- |
| **9 Composable Tools** | Covers all TRACE intelligence domains without tool proliferation or complex agent handoffs. | Adding separate specialized tools for every query nuance rejected: creates tool selection confusion. |
| **Semantic Routing + Multi-Tool Dispatch** | Questions naturally cross domains (e.g. task order + DAG, or component search + risk). | Rigid mutual exclusivity rejected: led directly to observed `INSUFFICIENT_EVIDENCE` failures. |
| **Narrow Missing Entity Guard** | Protects against hallucinating non-existent symbols while permitting architectural extension queries. | Blanket missing entity abort rejected: caused false negatives on exploratory questions. |
| **Clean UI Expander** | Keeps answers natural, concise, and senior-engineer-friendly without raw JSON visual clutter. | Dumping raw tool payloads into answer text rejected: degrades user experience. |
| **Telemetry over Hard Claims** | Enables empirical measurement across local and cloud environments rather than unverified SLA assertions. | Hardcoding `<35ms` or `1.0–2.5s` SLA assertions rejected: unverified and environment-dependent. |
