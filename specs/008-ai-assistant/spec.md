# Feature Specification: TRACE Phase 8 — F10: AI Assistant (Contextual Q&A Layer)

**Feature Branch**: `008-ai-assistant`  
**Created**: 2026-10-05  
**Updated (Evolution Spec)**: 2026-10-07  
**Phase**: Phase 8 (F10)  
**Status**: Specification Evolved (Baseline Implemented, Dynamic Workflow Specified)  
**Depends On**: F01 (Project & Repository Management), F02 (Repository Code Analyzer), F03 (Dependency Graph), F04 (Version Change Analyzer), F05 & F06 (Impact Analysis & Risk Engine), F07 (Upgrade Planner)  
**Feeds Into**: F08 (Interactive Observatory Web Dashboard)  

---

## 1. Overview & Executive Summary

While **F02–F07** extract static code structure, construct Neo4j call graphs, compute version diffs, evaluate blast-radius risk, and synthesize upgrade sequences, understanding the interconnected implications of repository modernization remains cognitively demanding.

**F10 (AI Assistant — Contextual Q&A Layer)** acts as an interactive code intelligence copilot for the TRACE Observatory web interface. It enables software architects and developers to ask natural-language questions about code changes, dependencies, risk factors, and upgrade plans, receiving precise, hallucination-free explanations backed by inspectable evidence sources.

### 1.1 Evolution from Baseline to Context Retrieval & Quality Refinement

F10 has progressed through three phases of specification and implementation:
- **Baseline F10 (Completed)**: Delivered single-pass retrieval combining regex symbol matching with fixed parallel database queries (Neo4j, Impact, Plans, Diffs), compact context pruning ($< 1,500$ tokens), OpenRouter free-tier LLM synthesis, deterministic offline markdown fallback, and a Neo-Brutalist drawer in the Streamlit Observatory UI.
- **F10 Dynamic Workflow Evolution (Completed)**: Introduced the bounded LangGraph state machine (`understand_question` $\to$ `select_tools` $\to$ `execute_tools` $\to$ `evaluate_sufficiency` $\to$ `synthesize_answer`), 2-hop retrieval bounding, and run-scoped tool interfaces.
- **Context Retrieval & Response Quality Refinement (Current Evolution)**: Directly addresses the over-restrictiveness and premature `INSUFFICIENT_EVIDENCE` failures identified during real-world testing. Evolves the assistant into a resilient, tool-augmented reasoning copilot featuring:
  1. A composable **9-tool retrieval suite** covering project overview, codebase search, symbol context, dependencies (internal and external), change analysis, risk analysis, upgrade plans, test coverage, and project knowledge fallback.
  2. **Semantic intent classification** replacing rigid keyword matching, with explicit support for **multi-tool retrieval** within and across hops.
  3. **Direct bypass for general knowledge questions** (e.g. *"Why is the sky blue?"*) avoiding irrelevant codebase searches.
  4. **A narrowed Missing Entity Guard** that protects against hallucinations on specific symbol lookups without discarding valid exploratory queries (e.g. *"Can I add payment functionality?"*).
  5. **Grounded engineering synthesis** where the LLM clearly distinguishes verified facts, reasonable architectural inferences, and unavailable data, while keeping evidence available through an unobtrusive on-demand UI expander rather than raw JSON dumps.

```text
                                [ User Question & Bounded History ]
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │       1. Question Understanding       │
                             │  - Semantic Intent Classification     │
                             │  - Entity / Scope Extraction          │
                             │  - General Knowledge Bypass Detect    │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │     2. Composable Tool Selection      │
                             │  - Non-exclusive multi-tool dispatch  │
                             │  - 9-Tool Structured TRACE Suite      │
                             │  - Strict project & run_id isolation  │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │       3. Tool Execution Layer         │
                             │  - Concurrent async execution         │
                             │  - Bounded AST snippets & graph edges │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                     ┌──────►│    4. Evidence Sufficiency Check      │
                     │       │  - Sufficient? -> Synthesize          │
                     │       │  - Insufficient & hops < 2? -> Loop   │
                     │       │  - Insufficient & hops = 2? -> Report │
                     └───────┴───────────┬───────────────┬───────────┘
   [Hop 2 Retrieval]                     │               │
  (e.g., inspect AST /     [Sufficient]  │               │ [Max Hops Reached /
   diff for caller)                      ▼               │  Missing Evidence]
                     ────────────────────┘               ▼
                             ┌───────────────────────────────────────┐
                             │    5. Grounded LLM Reasoning Node     │
                             │  - Distinguishes facts vs inference   │
                             │  - Senior engineer natural tone       │
                             │  - Narrowed Missing Entity Guard      │
                             │  - Deterministic offline fallback     │
                             └───────────────────┬───────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │     6. Response & Source Assembly     │
                             │  - Canonical POST /api/v1/assistant/ask│
                             │  - Clean engineering answer           │
                             │  - On-demand unobtrusive evidence UI  │
                             │  - Observability & timing telemetry   │
                             └───────────────────────────────────────┘
```

### 1.2 Architectural Principles & Governance Compliance

1. **Deterministic Grounding over Hallucination (Principle I & II)**:
   The assistant MUST NOT guess call chains, invent repository files, or extrapolate beyond retrieved TRACE facts. When evidence is missing, the assistant MUST state the lack of data explicitly rather than generating generic software engineering advice.
2. **Controlled Tool Abstraction (No Raw Database Access)**:
   The LLM interacts exclusively through 9 typed, bounded retrieval tools operating over existing TRACE services (`GraphGateway`, `AnalysisService`, `ImpactService`, `PlannerService`, `VersionChangeService`). The LLM NEVER receives raw Cypher or SQL query capabilities.
3. **Composable Multi-Tool Retrieval & Bounded Multi-Hop (Max 2 Retrieval Hops)**:
   Tool selection is non-mutually-exclusive. Queries requiring multi-domain intelligence (e.g. upgrade plan sequence + dependency graph, or codebase search + risk assessment) MUST retrieve all relevant context across up to 2 retrieval iterations (max 3 tool calls per hop). Runaway agent loops are strictly prevented.
4. **Strict Project and Analysis Run Isolation**:
   Every retrieval tool MUST require and enforce `project_id` and `analysis_run_id` scoping. Tools MUST NEVER return stale or cross-run data from older or unrelated analyses.
5. **Free-Model Compatibility & Compact Context Budgeting (Principle V & VI)**:
   Prompts and aggregated evidence stay strictly under 1,500 tokens (approx. 6,000 characters). Operates reliably on free-tier models (default: `meta-llama/llama-3.3-70b-instruct:free` or `mistralai/mistral-7b-instruct:free`).
6. **Robust Deterministic Offline Fallback (Principle VII)**:
   When external LLM access is unconfigured, disabled (`llm_enable_external_calls = False`), or failing, the assistant generates structured deterministic markdown responses directly from retrieved tool evidence.
7. **Frontend Canvas Protection & Clean Evidence Presentation**:
   The Observatory chat assistant integrates seamlessly without modifying or compromising the core graph canvas renderer in `frontend/app.py` (lines 51–643 and 870–1239). Answers must be clean and readable; raw JSON, SVG, or internal ID dumps are avoided in the primary response and kept accessible on-demand via an expander.
8. **Performance Observability**:
   Tool execution and LLM response timings are instrumented for telemetry and measurement rather than asserting unverified hard latency figures.

---

## 2. User Scenarios & Acceptance Criteria

### 2.1 Core User Stories

#### User Story 1 - Contextual Impact & Dependency Q&A (Priority: P1)
As a developer evaluating a proposed code change, I want to ask questions like *"Why is component X affected?"*, *"What depends on X?"*, or *"Show all callers of X"*, so that I can understand transitive ripple effects, exact call hierarchies, and AST-level modifications without manually cross-referencing raw graph views and diff logs.

#### User Story 2 - Explainable Risk Justification & Scoring Drilldown (Priority: P1)
As a technical lead or release manager, I want to ask *"Why is component X classified as High Risk?"* or *"What factors contributed to the risk score of service Y?"*, so that I can validate automated risk assessments and inspect the specific metrics (fan-in, breaking contracts, test deficits) that drove the score.

#### User Story 3 - Upgrade Plan Sequencing & Prerequisite Explanation (Priority: P1)
As an engineer executing a migration, I want to ask *"Why does Task 1 precede Task 4 in the upgrade plan?"* or *"Which tasks should be implemented first?"*, so that I understand DAG ordering rationales and execution phase tiers resolved against the actual plan.

#### User Story 4 - Repository & Codebase Exploration (Priority: P2)
As a developer exploring a codebase, I want to ask *"What language is the code written in?"*, *"What framework does it use?"*, or *"Can I add payment functionality to this codebase?"*, so that I receive an accurate architectural answer grounded in analyzed repository metadata and symbols without being blocked by premature insufficient evidence errors.

#### User Story 5 - Grounded Source Attribution & Inspectable Evidence (Priority: P2)
As an engineer auditing an analysis, I need every assistant answer to include typed, inspectable source references (`graph`, `risk`, `plan`, `diff`, `ast`, `test`, `project`), cleanly accessible on-demand in the UI without cluttering the primary answer.

#### User Story 6 - Free-Model Resiliency, Budgeting & Graceful Degradation (Priority: P3)
As a system administrator running TRACE under zero-cost constraints, I want the assistant to stay strictly within prompt token budgets (< 1,500 tokens), retry transient provider failures, and cleanly degrade to deterministic structured summaries when offline.

---

### 2.2 Concrete Acceptance Scenarios & Evaluation Benchmark

The refined assistant MUST satisfy the following 10 observable acceptance criteria (A through J):

#### Scenario A: Project Language & Stack
- **Question**: *"What language is this project written in?"*
- **Target Category**: `PROJECT_OVERVIEW`
- **Expected Behavior**: Invokes `get_project_overview`. Synthesizes answer directly from repository metadata and file metrics (e.g. Python, total files). Does NOT attempt code symbol extraction or report `INSUFFICIENT_EVIDENCE`.

#### Scenario B: Dependency Architecture (Internal & External)
- **Question**: *"What dependencies are present?"*
- **Target Category**: `DEPENDENCY`
- **Expected Behavior**: Invokes `get_dependencies(symbol=None)`. Distinguishes external/package dependencies (e.g. `fastapi`, `neo4j`, `pydantic`) from internal project graph call/import relationships (`CALLS`, `IMPORTS`). Does NOT force a code symbol lookup.

#### Scenario C: Upgrade Plan Task Sequencing
- **Question**: *"Why does Task 1 precede Task 4?"*
- **Target Category**: `UPGRADE_PLAN`
- **Expected Behavior**: Invokes `get_upgrade_plan(task_identifiers=["task_1", "task_4"])` and `get_dependencies`. Resolves both tasks against the active plan, compares their tiers and topological DAG prerequisites, and explains why Step 1 is executed before Step 4 without reporting `INSUFFICIENT_EVIDENCE`.

#### Scenario D: Project / Run Risk Rationale
- **Question**: *"Why is python-proj classified as high risk?"*
- **Target Category**: `RISK_ANALYSIS`
- **Expected Behavior**: Invokes `get_risk_analysis(analysis_run_id=...)`. Retrieves actual risk records, numerical score, and contributing factors (e.g. changed entities, downstream files impacted, callers at risk). Does NOT treat `python-proj` or `HEAD` as an unverified code symbol.

#### Scenario E: Revision Change Analysis
- **Question**: *"What changed between revisions?"*
- **Target Category**: `CHANGE_ANALYSIS`
- **Expected Behavior**: Invokes `get_change_analysis`. Summarizes modified, added, and deleted files, distinguishing breaking parameter alterations from non-breaking changes with diff citations.

#### Scenario F: Transitive Blast Radius Exploration
- **Question**: *"Show me everything affected by PaymentAPI."*
- **Target Category**: `IMPACT_ANALYSIS`
- **Expected Behavior**: Invokes `get_dependencies(symbol="PaymentAPI", depth=2)`. Identifies direct and transitive callers, partitioning downstream dependents by distance.

#### Scenario G: Deficit & Test Coverage Analysis
- **Question**: *"Which affected components have low test coverage?"*
- **Target Category**: `TEST_ANALYSIS`
- **Expected Behavior**: Invokes `get_test_coverage` and `get_risk_analysis`. If coverage data is available, reports affected components with low coverage. If coverage is unanalyzed, explicitly states: *"TRACE does not currently have line-level coverage data for this repository"* without failing with an evidence error.

#### Scenario H: Codebase Exploration & Extension Feasibility
- **Question**: *"Can I add payment-related functionality to this codebase?"*
- **Target Category**: `CODE_SEARCH` / `PROJECT_OVERVIEW`
- **Expected Behavior**: Invokes `search_codebase("payment")` and `get_project_overview`. If payment symbols do not exist, does NOT trigger Missing Entity Guard. Instead, explains existing architecture modules and where new payment endpoints or services can fit.

#### Scenario I: General Project Overview
- **Question**: *"What is this project?"*
- **Target Category**: `PROJECT_OVERVIEW`
- **Expected Behavior**: Invokes `get_project_overview` as primary source (with `search_project_knowledge` supplementary). Explains project name, repository purpose, entry points, and structural scale.

#### Scenario J: General Knowledge Bypass
- **Question**: *"Why is the sky blue?"*
- **Target Category**: `GENERAL_KNOWLEDGE`
- **Expected Behavior**: Bypasses TRACE repository retrieval tools entirely. Answers the scientific question naturally using LLM knowledge without searching the repository or returning `INSUFFICIENT_EVIDENCE`.

---

## 3. Requirements

### 3.1 Semantic Intent Understanding & Multi-Tool Selection
- **FR-001 (Semantic Intent Classification)**: The system MUST classify user queries semantically rather than relying on rigid keyword trigger phrases. The classification taxonomy includes:
  - `PROJECT_OVERVIEW`: Language, framework, repository structure, high-level summary.
  - `CODE_SEARCH`: Codebase search for existing symbols, classes, files, or extension feasibility.
  - `SYMBOL_CONTEXT`: Focused AST signature, implementation, docstrings, and callers of a specific symbol.
  - `DEPENDENCY`: External packages/libraries and internal graph relationships (`CALLS`, `IMPORTS`, `DEPENDS_ON`).
  - `CHANGE_ANALYSIS`: Revision comparisons, diff hunks, parameter deltas, breaking modifications.
  - `IMPACT_ANALYSIS`: Blast radius, transitive callers, ripple effects of changes.
  - `RISK_ANALYSIS`: Risk levels, numerical scores, contributing factors, remediations.
  - `UPGRADE_PLAN`: Step sequencing, tier hierarchy, prerequisite task dependencies.
  - `TEST_ANALYSIS`: Test suites, test references, component coverage availability.
  - `GENERAL_KNOWLEDGE`: Non-codebase questions (e.g. general science, logic) bypassing TRACE tools.
- **FR-002 (Non-Exclusive Multi-Tool Retrieval)**: Tool selection MUST NOT be mutually exclusive. A query requiring cross-domain information (e.g. upgrade plan sequencing requiring both task records and DAG dependencies) MUST schedule multiple tools concurrently.
- **FR-003 (General Knowledge Bypass)**: When a query is classified as `GENERAL_KNOWLEDGE`, the workflow MUST route directly to synthesis without invoking repository retrieval tools.

### 3.2 Composable 9-Tool Retrieval Suite
- **FR-004 (Typed Tool Interface)**: The assistant MUST retrieve TRACE intelligence exclusively through 9 typed, programmatic tools operating over existing services. The LLM MUST NOT have access to arbitrary SQL execution, arbitrary Cypher execution, or filesystem write permissions.
- **FR-005 (Tool Suite Definition)**: The system MUST expose the following 9 bounded retrieval tools:
  1. `get_project_overview(project_id, analysis_run_id)`: Primary tool for broad project-level questions; returns languages, frameworks, file counts, and entry points.
  2. `search_codebase(query, analysis_run_id)`: Searches analyzed metadata for files, functions, classes, and architectural components.
  3. `get_symbol_context(qualified_name, analysis_run_id)`: Retrieves AST details (parameters, return types, docstrings, complexity) and bounded code snippets ($\le 40$ lines).
  4. `get_dependencies(symbol, direction, depth, analysis_run_id)`: Retrieves internal graph edges (`CALLS`, `IMPORTS`, `DEPENDS_ON`) and external package dependencies (`fastapi`, `pydantic`, etc.).
  5. `get_change_analysis(repository_id, revision_range)`: Retrieves AST diffs, parameter modifications, breaking change flags, and diff summaries from F04 records.
  6. `get_risk_analysis(symbol_or_component, analysis_run_id)`: Retrieves blast radius records, numerical risk scores, contributing factors, callers at risk, and remediation steps from F05/F06 records.
  7. `get_upgrade_plan(task_identifiers, repository_id)`: Retrieves upgrade tasks, tier categories, DAG prerequisite IDs, and ordering rationales from F07 records, supporting natural language numbers (e.g. "Task 1", "Task 4").
  8. `get_test_coverage(component, analysis_run_id)`: Retrieves test functions and test references; explicitly reports if line-level coverage is unanalyzed.
  9. `search_project_knowledge(query, analysis_run_id)`: Supplementary/fallback retrieval over broader structured analysis data when questions do not map to a single specialized tool.
- **FR-006 (Source Code Awareness & Bounding)**: The system MUST allow retrieving relevant AST signatures, parameter lists, and source code snippets, enforcing a hard upper bound of 40 lines per snippet and at most 3 snippets per query.

### 3.3 Multi-Step Workflow & Refined Sufficiency Evaluation
- **FR-007 (LangGraph Workflow Execution)**: The assistant orchestrator MUST execute as a compiled LangGraph `StateGraph`:
  `UnderstandQuestion` $\to$ `SelectTools` $\to$ `ExecuteTools` $\to$ `EvaluateSufficiency` $\to$ `SynthesizeAnswer` $\to$ `AssembleResponse`.
- **FR-008 (Evidence Sufficiency Evaluation)**: After tool execution, the orchestrator MUST evaluate whether retrieved evidence satisfies the semantic intent:
  - If **sufficient**, execution routes directly to `SynthesizeAnswer`.
  - If **insufficient** and iteration count $< 2$, execution selects additional tools (e.g. inspecting dependencies for unsequenced tasks) and loops to `ExecuteTools`.
  - If **insufficient** and iteration count $\ge 2$, execution routes to `SynthesizeAnswer` without hard failure unless the target is a missing explicit code symbol.
- **FR-009 (Strict Iteration & Token Budget Limits)**:
  - Maximum tool retrieval hops MUST NOT exceed 2 iterations (maximum 3 tool calls per hop).
  - Total prompt context payload passed to the LLM synthesizer MUST NOT exceed 1,500 tokens (approx. 6,000 characters).

### 3.4 Strict Project and Analysis Run Isolation
- **FR-010 (Scope Enforcement)**: Every retrieval tool MUST filter records strictly by `project_id` and `analysis_run_id`.
- **FR-011 (Elimination of Cross-Run Data Leaks)**: Retrieval of impact analyses, version comparisons, upgrade plans, and graph nodes MUST NOT query solely by `repository_id` with `LIMIT 1` when an `analysis_run_id` is active.

### 3.5 Bounded Conversational Context
- **FR-012 (Multi-Turn History Support)**: The assistant endpoint MUST accept an optional `history` list representing previous dialogue turns.
- **FR-013 (History Trimming)**: The backend MUST trim conversational history to a maximum of the 2 most recent dialogue turns (4 messages).
- **FR-014 (Follow-up Disambiguation)**: When a query contains anaphoric references (e.g. *"Why?"*, *"Explain that caller"*), the orchestrator MUST extract target entities from dialogue history before dispatching retrieval tools.

### 3.6 Grounded Reasoning & Narrow Missing Entity Guard
- **FR-015 (Grounded Fact Attribution)**: Synthesized answers MUST distinguish:
  - Directly retrieved facts from TRACE static analysis and graph data.
  - Reasonable inferences drawn from those facts.
  - Information not available in the current analysis snapshot.
- **FR-016 (Narrow Missing Entity Guard)**: The Missing Entity Guard MUST ONLY trigger when a query specifically targets an explicit code symbol (`SYMBOL_CONTEXT` or targeted `IMPACT_ANALYSIS`) and that symbol cannot be found in the codebase. It MUST NEVER trigger for exploratory queries (`CODE_SEARCH`), project overviews (`PROJECT_OVERVIEW`), upgrade plan comparisons (`UPGRADE_PLAN`), or general knowledge (`GENERAL_KNOWLEDGE`).

### 3.7 Canonical REST API Contract & Response Format
- **FR-017 (Canonical Endpoint)**: The system MUST expose `POST /api/v1/assistant/ask` as the authoritative assistant query endpoint.
- **FR-018 (Request Payload Structure)**: `project_id` (UUID), `analysis_run_id` (UUID, optional), `question` (string, 3..1000 chars), `history` (list of `ChatMessage`, optional).
- **FR-019 (Response Payload Structure)**: `answer` (string), `intent` (string), `sources` (list of `EvidenceSource`), `grounding_status` (string), `model_used` (string), `suggested_followups` (list of strings).
- **FR-020 (Status Endpoint)**: The system MUST expose `GET /api/v1/assistant/status` returning current service status, configured model, and whether external LLM calls are enabled.

### 3.8 Deterministic Offline Fallback Mode
- **FR-021 (Deterministic Fallback Execution)**: If `llm_enable_external_calls` is `False`, `OPENROUTER_API_KEY` is missing, or upstream LLM requests fail, the orchestrator MUST format retrieved tool evidence into clean markdown tables.
- **FR-022 (Zero Network Overhead Offline)**: In offline fallback mode, responses MUST execute locally without external network attempts.

### 3.9 Frontend Observatory UI & Clean Evidence Presentation
- **FR-023 (Canvas Isolation)**: Frontend assistant integration in `frontend/app.py` MUST NOT modify, replace, or interfere with graph canvas rendering logic in lines 51–643 and 870–1239.
- **FR-024 (Clean Presentation)**: The primary answer in the chat UI MUST NOT display raw JSON dumps, SVG payloads, internal UUIDs, or tool execution arguments.
- **FR-025 (On-Demand Evidence Expander)**: Returned `EvidenceSource` records MUST be accessible through a clean, collapsed expander (`📚 View Evidence ({count})`), allowing users to inspect attribution on-demand without visual clutter.

### 3.10 Performance Observability & Latency Telemetry
- **FR-026 (Telemetry Logging)**: The system MUST record internal execution timing (in milliseconds) for each tool execution, graph traversal, and LLM synthesis invocation, exposing metrics via structured application logs for performance evaluation.

---

## 4. Key Entities & Data Contracts

### 4.1 Schema Definitions (`backend/src/trace/schemas/assistant.py`)

```python
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Dialogue turn in the conversational context."""
    role: Literal["user", "assistant"] = Field(...)
    content: str = Field(..., min_length=1, max_length=4000)


class EvidenceSource(BaseModel):
    """Verifiable repository evidence element grounding an assistant answer."""
    model_config = ConfigDict(extra="ignore")

    type: Literal["graph", "risk", "plan", "diff", "ast", "test"] = Field(
        ...,
        description="Domain category of evidence."
    )
    identifier: str = Field(
        ...,
        description="Unique identifier for the evidence item (node name, diff hunk, task ID, file line span)."
    )
    summary: str = Field(
        ...,
        description="Concise human-readable summary of the evidence finding."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value metrics, locations, and properties."
    )


class AssistantQueryRequest(BaseModel):
    """Request payload to query the TRACE AI Code Intelligence Assistant."""
    model_config = ConfigDict(extra="forbid")

    project_id: UUID = Field(..., description="Authoritative UUID of the active TRACE project.")
    analysis_run_id: UUID | None = Field(default=None, description="Optional UUID of a specific analysis run snapshot.")
    question: str = Field(..., min_length=3, max_length=1000, description="User's natural-language query.")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Recent conversation turns (at most 2 user/assistant pairs evaluated)."
    )


class AssistantQueryResponse(BaseModel):
    """Response payload containing synthesized answer, evidence sources, and grounding indicators."""
    model_config = ConfigDict(extra="ignore")

    answer: str = Field(..., description="Synthesized natural-language response strictly grounded in repository evidence.")
    intent: str = Field(default="GENERAL_OBSERVATORY", description="Identified primary query intent.")
    sources: list[EvidenceSource] = Field(default_factory=list, description="Ordered list of verified evidence sources.")
    grounding_status: Literal[
        "DETERMINISTIC_GROUNDED",
        "PARTIAL_EVIDENCE",
        "FALLBACK_DETERMINISTIC",
        "INSUFFICIENT_EVIDENCE",
    ] = Field(..., description="Level of evidence grounding achieved.")
    model_used: str = Field(..., description="Identifier of the LLM model used or 'offline-deterministic-fallback'.")
    suggested_followups: list[str] = Field(default_factory=list, description="Context-aware follow-up prompt chips.")
```

### 4.2 LangGraph Agent State (`backend/src/trace/services/assistant/state.py`)

```python
from typing import Annotated, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from trace.schemas.assistant import ChatMessage, EvidenceSource


def merge_evidence(current: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reducer combining evidence dictionaries without duplicates, capped at 25 items."""
    seen = {f"{item.get('type')}:{item.get('id')}" for item in current}
    merged = list(current)
    for item in new_items:
        key = f"{item.get('type')}:{item.get('id')}"
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged[:25]


class AssistantState(BaseModel):
    """Typed execution state for the LangGraph assistant workflow."""
    # Context
    project_id: UUID
    analysis_run_id: UUID | None
    question: str
    history: list[ChatMessage] = Field(default_factory=list)

    # Workflow Reasoning
    intents: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)
    pending_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    iteration_count: int = 0
    is_sufficient: bool = False

    # Evidence Store
    raw_evidence: Annotated[list[dict[str, Any]], merge_evidence] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)

    # Output
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
```

---

## 5. Success Criteria

- **SC-001 (Grounding Precision)**: 100% of factual statements regarding dependencies, callers, risk levels, and task order in generated answers cite at least one verified `EvidenceSource`.
- **SC-002 (Zero Speculative Hallucination)**: In automated evaluation with missing entities, 0% of answers generate fictitious call chains; 100% of missing entity queries return `INSUFFICIENT_EVIDENCE` status.
- **SC-003 (Token Budget Adherence)**: 100% of LLM prompts constructed across all query types stay strictly under 1,500 tokens.
- **SC-004 (Bounded Retrieval Hops)**: 100% of assistant queries complete within a maximum of 2 retrieval iterations (at most 3 tool calls total).
- **SC-005 (Multi-Turn Follow-Up Resolution)**: The assistant successfully resolves follow-up queries (e.g. *"Why?"*, *"Show its callers"*) by incorporating entities from the prior 2 dialogue turns with $> 90\%$ accuracy.
- **SC-006 (Zero-Downtime Deterministic Fallback)**: When LLM calls are disabled or unreachable, 100% of queries return valid deterministic markdown summaries and typed sources without HTTP 500 errors.
- **SC-007 (Strict Run Scoping)**: 0% of retrieved records originate from outside the specified `project_id` and `analysis_run_id`.
- **SC-008 (Frontend Canvas Isolation)**: 100% of existing graph canvas features, node interactions, and physics simulations in `frontend/app.py` continue to function identically with zero visual or behavioral regressions.
- **SC-009 (Benchmark Pass Rate)**: The assistant achieves a 100% pass rate across the 10 concrete acceptance scenarios (A through J) defined in Section 2.2.

---

## 6. Assumptions & Architectural Guardrails

- **Zero New Dependencies**: `langgraph>=0.2.0` and `langchain-core` are already locked in `backend/pyproject.toml` and `backend/uv.lock`. No new packages, Docker images, or container services are introduced.
- **Deterministic Tool Primacy**: Tools wrap existing verified services (`GraphGateway`, `AnalysisService`, `ImpactService`, `PlannerService`, `VersionChangeService`). No probabilistic vector databases are required for V1.
- **Immutable Historical Baselines**: The initial implementation (T001–T025) remains intact as the verified foundation; evolution occurs by introducing the modular tool layer and LangGraph workflow orchestrator.
- **Stateless Server Lifecycle**: Conversational history is passed ephemerally from the client in `AssistantQueryRequest`, eliminating the need for server-side multi-user session databases in V1.

---

## 7. Evolution Traceability & Baseline Comparison

| Architectural Dimension | BASELINE F10 (Completed) | EVOLVED F10 (This Specification) |
| :--- | :--- | :--- |
| **Retrieval Architecture** | Monolithic, fixed single-pass pipeline; executes 4 queries unconditionally. | Dynamic, tool-based LangGraph `StateGraph` with semantic intent classification and multi-tool dispatch. |
| **Tool Capabilities** | None; hardcoded internal queries in `retrieval.py`. | 9 typed, composable retrieval tools wrapping existing TRACE domain services. |
| **Source-Code Awareness** | 0%; cannot inspect AST bodies, function signatures, docstrings, or file lines. | Direct AST inspection (`get_symbol_context`) with bounded snippets ($\le 40$ lines). |
| **Multi-Hop Traversal** | None; cannot use Hop 1 results to trigger secondary queries. | Bounded multi-hop investigation (up to 2 iterations, max 3 tool calls per hop). |
| **Evidence Sufficiency** | None; blindly forwards whatever was found (even `{}`) to LLM. | Explicit `EvaluateSufficiency` check prior to synthesis. |
| **Analysis Run Scoping** | Defective; queries risk, plan, and diff by `repository_id` with `LIMIT 1`. | Strict `analysis_run_id` and `project_id` isolation across all tools. |
| **Conversation Memory** | 0% Backend history; requests are completely stateless. | Bounded dialogue history (last 2 turns) supporting follow-up queries like *"Why?"*. |
| **Missing Evidence Behavior**| System prompt Rule 2 encouraged general software engineering speculation. | Strict anti-hallucination guard with narrowed Missing Entity Guard (only for specific code symbol lookups; does not block exploratory queries). |
| **API Contract** | `POST /api/v1/assistant/ask` returning `{answer, sources, model_used}`. | Reconciled `POST /api/v1/assistant/ask` returning `{answer, intent, sources, grounding_status, model_used, suggested_followups}`. |
| **Deterministic Fallback** | Markdown generator formatting raw evidence when offline. | Preserved as a dedicated first-class branch in the LangGraph workflow. |
| **Frontend UI Integration**| Neo-Brutalist right-hand drawer in `frontend/app.py` (canvas untouched). | Clean answer presentation with unobtrusive "View evidence" expander and grounding status badge (canvas untouched). |
