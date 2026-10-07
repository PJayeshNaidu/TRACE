# Tasks: TRACE Phase 8 — F10: AI Assistant (Contextual Q&A Layer)

**Input**: Design documents from `specs/008-ai-assistant/` (`spec.md`, `plan.md`, `data-model.md`, `research.md`, `contracts/api.md`, `quickstart.md`)  
**Prerequisites**: F01 (Repo Management), F02 (AST Code Extraction), F03 (Neo4j Graph), F04 (Version Change Diffing), F05 & F06 (Impact Analysis & Risk Evaluation Engine), F07 (Upgrade Planner)  
**Organization**: Tasks are grouped by phase and user story to enable independent implementation and testing of each component.

## Format: `[TaskID] [P?] [Story/Req] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story/Req]**: Target user story (`US1`–`US6`) or functional requirement (`FR-001`–`FR-025`)
- Every task includes an explicit atomic verification step.

---

# COMPLETED BASELINE — F10 V1 (Tasks T001–T025)

The following 25 tasks represent the initial implementation of the F10 AI Assistant (delivered, verified, and passing all unit and API tests). They serve as the stable baseline upon which the dynamic LangGraph evolution is built.

## Phase 1: Setup & Data Contracts (Baseline Infrastructure)
- [x] T001 Initialize assistant packages by creating `backend/src/trace/schemas/__init__.py`, `backend/src/trace/services/assistant/__init__.py`, and `backend/src/trace/api/assistant/__init__.py`  
  *Verification*: `python -m py_compile backend/src/trace/schemas/__init__.py backend/src/trace/services/assistant/__init__.py backend/src/trace/api/assistant/__init__.py`
- [x] T002 [P] Define `EvidenceSource`, `AssistantQueryRequest`, and `AssistantQueryResponse` schemas with strict field validations in `backend/src/trace/schemas/assistant.py`  
  *Verification*: `python -c "from trace.schemas.assistant import AssistantQueryRequest, EvidenceSource, AssistantQueryResponse; print('Schemas OK')"`
- [x] T003 [P] Define internal evidence structures (`GraphNeighborEvidence`, `RiskItemEvidence`, `PlanStepEvidence`, `DiffHunkEvidence`, `CompactEvidenceBundle`) in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `python -c "from trace.services.assistant.retrieval import CompactEvidenceBundle; print('Retrieval models OK')"`
- [x] T004 [P] Write unit tests for schema validation, serialization, and constraints in `backend/tests/unit/test_assistant_schemas.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_schemas.py -v`

## Phase 2: Foundational Retrieval Engine & Subgraph Pruning
- [x] T005 Implement candidate symbol extractor matching regex and AST symbol table entries in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -k test_extract_candidate_symbols`
- [x] T006 [P] Implement 1-hop and 2-hop Neo4j Cypher upstream/downstream graph traversal queries for target symbols in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -k test_cypher_traversals`
- [x] T007 [P] Implement F05 risk factor and F07 upgrade plan step extractor in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -k test_extract_risk_and_plan`
- [x] T008 [P] Implement compact evidence bundling and token budget limiter (< 1,500 tokens / 6,000 chars) in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -k test_compact_bundle_token_budget`
- [x] T009 [P] Write comprehensive unit tests for symbol extraction, Cypher querying, and token budget pruning in `backend/tests/unit/test_assistant_retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -v`

## Phase 3: Impact, Dependency & Risk Synthesis Layer (Baseline MVP)
- [x] T010 [US1] Implement prompt builder formatting compact JSON evidence with strict anti-hallucination system prompt in `backend/src/trace/services/assistant/synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -k test_prompt_formatting`
- [x] T011 [US1] Implement OpenRouter LLM completion invoker using `settings.openrouter_model` (`meta-llama/llama-3.3-70b-instruct:free`) with tenacity retries in `backend/src/trace/services/assistant/synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -k test_openrouter_invocation`
- [x] T012 [US2] Implement deterministic markdown fallback engine formatting raw JSON evidence tables when offline/unkeyed in `backend/src/trace/services/assistant/synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -k test_deterministic_fallback`
- [x] T013 [US1] Implement `AssistantService.ask` orchestrator binding retrieval, token budgeting, and synthesis in `backend/src/trace/services/assistant/synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -k test_assistant_service_ask`
- [x] T014 [P] [US1] Write unit tests for prompt formatting, LLM synthesis, and fallback generation in `backend/tests/unit/test_assistant_synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -v`

## Phase 4: Upgrade Plan Q&A & Source Attribution API
- [x] T015 [US3] Integrate F07 Upgrade Plan step explanations into `backend/src/trace/services/assistant/synthesis.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_synthesis.py -k test_plan_sequence_synthesis`
- [x] T016 [US4] Implement `EvidenceSource` assembler extracting typed sources (`graph`, `risk`, `plan`, `diff`) with identifiers and summaries in `backend/src/trace/services/assistant/retrieval.py`  
  *Verification*: `pytest backend/tests/unit/test_assistant_retrieval.py -k test_evidence_source_assembly`
- [x] T017 [US4] Implement FastAPI endpoint `POST /api/v1/assistant/ask` with dependency injection in `backend/src/trace/api/assistant/router.py`  
  *Verification*: `pytest backend/tests/api/test_assistant_api.py -k test_assistant_ask_endpoint`
- [x] T018 [US4] Register `assistant_router` under prefix `/api/v1` in `backend/src/trace/api/router.py`  
  *Verification*: `python -c "from trace.api.router import api_router; routes = [r.path for r in api_router.routes]; assert '/api/v1/assistant/ask' in routes; print('Route registered OK')"`
- [x] T019 [P] [US4] Write API contract and integration tests for `POST /api/v1/assistant/ask` in `backend/tests/api/test_assistant_api.py`  
  *Verification*: `pytest backend/tests/api/test_assistant_api.py -v`

## Phase 5: Neo-Brutalist Observatory UI & Resiliency
- [x] T020 [US5] Implement docked right-hand Copilot drawer layout with collapse/expand toggle in `frontend/app.py` (Preserving canvas lines 51–643 & 870–1239)  
  *Verification*: `python -m py_compile frontend/app.py`
- [x] T021 [US5] Implement Neo-Brutalist styled question input box and dynamic intent suggestion chips in `frontend/app.py`  
  *Verification*: `python -m py_compile frontend/app.py`
- [x] T022 [US5] Implement response card rendering with model attribution badges and expandable evidence source chips in `frontend/app.py`  
  *Verification*: `python -m py_compile frontend/app.py`
- [x] T023 [US6] Implement client-side error handling, request timeout protection (5s), and deterministic offline fallback notices in `frontend/app.py`  
  *Verification*: `python -m streamlit run frontend/app.py` (Resilience verification)

## Phase 6: Polish, Integration & Baseline Test Verification
- [x] T024 [P] Execute end-to-end validation scenarios per `specs/008-ai-assistant/quickstart.md`  
  *Verification*: Validate sample responses for Impact, Risk, Plan, and Diff queries.
- [x] T025 [P] Run full backend test suite ensuring 100% pass rate and zero regressions across F01–F07  
  *Verification*: `pytest backend/tests/ -v` (24/24 assistant tests passing)

---

# DYNAMIC RETRIEVAL & LANGGRAPH EVOLUTION (Tasks T026–T054)

The following tasks evolve F10 from its baseline single-pass pipeline into a controlled, multi-step, evidence-grounded LangGraph workflow.

---

## Phase 7: Typed Tool Layer & Scoping Correction

**Purpose**: Encapsulate existing TRACE services (`AnalysisService`, `GraphGateway`, `ImpactService`, `PlannerService`, `VersionChangeService`) into 7 typed, run-scoped retrieval tools, correcting the `analysis_run_id` scoping defect.

- [x] T026 [FR-004] Verify LangGraph dependency and environment configuration in `backend/src/trace/services/assistant/__init__.py`  
  *Verification*: `uv run python -c "import langgraph; from langgraph.graph import StateGraph; print('LangGraph OK')"`
- [x] T027 [FR-004] [FR-010] Implement `resolve_target_run` helper in `backend/src/trace/services/assistant/tools.py` resolving omitted `analysis_run_id` to the latest completed analysis run of `project_id`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_resolve_target_run`
- [x] T028 [P] [FR-005] [FR-006] Implement `get_repository_overview`, `search_code_symbols`, and `get_symbol_details` (with parameter metadata and $\le 40$-line source code snippets) in `backend/src/trace/services/assistant/tools.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_ast_and_symbol_tools`
- [x] T029 [P] [FR-005] Implement `get_graph_neighborhood` in `backend/src/trace/services/assistant/tools.py` with parameterized Cypher traversals (depth $\le 2$) and artifact relationship fallback  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_graph_neighborhood_tool`
- [x] T030 [P] [FR-005] [FR-011] Implement `get_impact_and_risk`, `get_upgrade_plan_tasks`, and `get_change_diffs` in `backend/src/trace/services/assistant/tools.py` with strict `analysis_run_id` filtering (eliminating `LIMIT 1` repository-level leaks)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_impact_plan_diff_tools`
- [x] T031 [P] Author comprehensive unit tests for all 7 typed retrieval tools in `backend/tests/unit/test_assistant_tools.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -v`

**Checkpoint**: 7 typed retrieval tools are operational, unit-tested, and strictly scoped by `analysis_run_id`.

---

## Phase 8: LangGraph Workflow Engine & Sufficiency Evaluation

**Purpose**: Build the compiled LangGraph `StateGraph`, typed state, sufficiency check, and bounded iteration controls.

- [x] T032 [FR-007] Implement `AssistantState` model and `merge_evidence` deduplicating reducer (capped at 25 items) in `backend/src/trace/services/assistant/state.py`  
  *Verification*: `uv run python -c "from trace.services.assistant.state import AssistantState; print('State OK')"`
- [x] T033 [FR-001] [FR-002] Implement `understand_question` node in `backend/src/trace/services/assistant/workflow.py` performing deterministic symbol extraction and composite intent classification  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_understand_question_node`
- [x] T034 [FR-005] Implement `select_tools` and `execute_tools` nodes in `backend/src/trace/services/assistant/workflow.py` with concurrent tool dispatch and graceful exception handling  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_tool_execution_node`
- [x] T035 [FR-008] [FR-009] Implement `evaluate_sufficiency` node and conditional routing edge (`route_after_sufficiency`) in `backend/src/trace/services/assistant/workflow.py` enforcing a hard limit of 2 retrieval hops (max 3 tool calls total)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_sufficiency_and_hop_limits`
- [x] T036 [FR-007] Implement `build_assistant_graph` compiling the complete `StateGraph` in `backend/src/trace/services/assistant/workflow.py` and author workflow unit tests in `backend/tests/unit/test_assistant_workflow.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -v`

**Checkpoint**: The LangGraph state machine executes multi-hop investigations with deterministic loop termination.

---

## Phase 9: API Contract & Multi-Turn History Integration

**Purpose**: Update Pydantic request/response schemas to support bounded conversation history (last 2 turns) and enriched response metadata.

- [x] T037 [FR-012] [FR-019] Update `ChatMessage`, `AssistantQueryRequest` (optional `history`), and `AssistantQueryResponse` (`intent`, `grounding_status`, `suggested_followups`) in `backend/src/trace/schemas/assistant.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_schemas.py -v`
- [x] T038 [FR-017] [FR-018] Update `ask_assistant` endpoint in `backend/src/trace/api/assistant/router.py` to forward `request.history` into `AssistantService`  
  *Verification*: `uv run pytest backend/tests/api/test_assistant_api.py -k test_assistant_ask_with_history`
- [x] T039 [FR-014] Implement history-aware follow-up disambiguation in `understand_question` node (`backend/src/trace/services/assistant/workflow.py`) extracting target symbols from the prior turn for questions like *"Why?"* or *"Show its callers"*  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_followup_disambiguation`
- [x] T040 [P] Author contract and multi-turn API integration tests in `backend/tests/api/test_assistant_api.py` asserting schema serialization and history handling  
  *Verification*: `uv run pytest backend/tests/api/test_assistant_api.py -v`

**Checkpoint**: REST endpoint `POST /api/v1/assistant/ask` supports multi-turn history and returns enriched grounding metadata.

---

## Phase 10: Grounding Synthesis Refinement & Offline Fallback

**Purpose**: Eliminate speculative prompt bloviation, enforce strict missing-evidence reporting, and wire LangGraph into `AssistantService.ask`.

- [x] T041 [FR-015] [FR-016] Update `ASSISTANT_SYSTEM_PROMPT` in `backend/src/trace/services/assistant/synthesis.py` removing Rule 2 (no generic programming bloviation on empty context; require explicit `INSUFFICIENT_EVIDENCE` reporting)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_anti_hallucination_prompt`
- [x] T042 [FR-021] [FR-022] Update `DeterministicFallbackGenerator.generate` in `backend/src/trace/services/assistant/synthesis.py` to format multi-domain evidence (AST snippets, test references, and task prerequisites) when offline with $< 100\text{ms}$ latency  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_enhanced_deterministic_fallback`
- [x] T043 [FR-007] Update `AssistantService.ask` in `backend/src/trace/services/assistant/synthesis.py` to execute `build_assistant_graph().ainvoke(...)` and map output to `AssistantQueryResponse`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_assistant_service_langgraph_invocation`

**Checkpoint**: Synthesis layer enforces zero speculative hallucination and cleanly degrades to deterministic tables offline.

---

## Phase 11: Non-Destructive Frontend Integration

**Purpose**: Update the Streamlit Observatory assistant panel to pass bounded conversation history and render grounding status badges while strictly isolating canvas renderers.

- [x] T044 [FR-023] [FR-024] Update `render_assistant_panel` in `frontend/app.py` (lines 1880–1915) to transmit the last 2 conversation turns (`history = st.session_state["assistant_messages"][-4:]`) in request payload (**STRICT CONSTRAINT**: Preserved lines 51–643 and 870–1239 containing graph canvas renderers)  
  *Verification*: `python -m py_compile frontend/app.py`
- [x] T045 [FR-025] Update response rendering in `frontend/app.py` (lines 1840–1870) to display high-contrast Neo-Brutalist badges for `grounding_status` (`GROUNDED`, `PARTIAL`, `FALLBACK`, `INSUFFICIENT`) and render AST snippet cards  
  *Verification*: `python -m py_compile frontend/app.py`
- [x] T046 [FR-023] Perform manual Streamlit smoke testing verifying chat history transmission, badge rendering, and confirming Force-Directed Graph canvas physics remain unaffected  
  *Verification*: Launch Streamlit UI (`python -m streamlit run frontend/app.py`) and verify canvas node drag/zoom behavior.

**Checkpoint**: Observatory web UI renders grounding status badges and conducts multi-turn investigations without canvas regressions.

---

## Phase 12: Comprehensive Benchmark Evaluation Suite

**Purpose**: Author and execute the 9 concrete benchmark queries specified in Section 2.2 of `spec.md` to prove material answer improvement over the baseline.

- [x] T047 [SC-009] Create benchmark test harness with in-memory graph, impact, and plan fixtures in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k test_benchmark_harness_setup`
- [x] T048 [P] [SC-009] Implement and verify Benchmark 1 (*"Why is OrderService affected?"*), Benchmark 2 (*"What changed between two versions?"*), and Benchmark 3 (*"Show everything affected by PaymentAPI"*) in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k "test_benchmark_1 or test_benchmark_2 or test_benchmark_3"`
- [x] T049 [P] [SC-009] Implement and verify Benchmark 4 (*"Which affected components have low test coverage?"*), Benchmark 5 (*"Why was this classified as high risk?"*), and Benchmark 6 (*"Which changes should be implemented first?"*) in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k "test_benchmark_4 or test_benchmark_5 or test_benchmark_6"`
- [x] T050 [P] [SC-009] Implement and verify Benchmark 7 (*"What evidence supports this dependency?"*) asserting exact file path and line number citations in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k test_benchmark_7_evidence_citation`
- [x] T051 [P] [SC-009] Implement and verify Benchmark 8 (Multi-Turn Follow-Up: *"Why?"*) asserting causal resolution via conversation history in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k test_benchmark_8_followup_why`
- [x] T052 [P] [SC-002] [SC-009] Implement and verify Benchmark 9 (Missing Entity Guard) asserting `INSUFFICIENT_EVIDENCE` status and zero fictitious assertions in `backend/tests/unit/test_assistant_benchmarks.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -k test_benchmark_9_missing_entity`

**Checkpoint**: All 9 benchmark scenarios pass with verified evidence citations and zero speculative hallucinations.

---

## Phase 13: Full Regression & Integration Verification

**Purpose**: Execute full test suites across all backend components to guarantee zero regressions across F01–F07.

- [x] T053 Run complete assistant test suite ensuring 100% pass rate across baseline and evolution tests  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant*.py backend/tests/api/test_assistant*.py -v`
- [x] T054 Run complete TRACE backend test suite ensuring zero regressions across all subsystems  
  *Verification*: `uv run pytest backend/tests/ -v`

---

# CONTEXT RETRIEVAL & RESPONSE QUALITY REFINEMENT (Tasks T055–T075)

The following tasks execute the Context Retrieval & Response Quality Refinement evolution, transitioning the assistant from an overly restrictive pipeline into a resilient, tool-augmented reasoning copilot.

---

## Phase 14: Composable 9-Tool Suite Refinements

**Purpose**: Finalize and refine the composable 9-tool retrieval suite in `backend/src/trace/services/assistant/tools.py` with strict `analysis_run_id` scoping and natural language parameter resolution.

- [ ] T055 [FR-004] [FR-005] Refine `get_project_overview(project_id, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` as primary broad query tool, returning languages, total files, python files, entry points, and framework indicators  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_project_overview`
- [ ] T056 [FR-005] Refine `search_codebase(query, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` for flexible exploratory search over modules, classes, and files without requiring exact symbol existence  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_search_codebase`
- [ ] T057 [FR-005] [FR-006] Refine `get_symbol_context(qualified_name, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` retrieving AST parameters, docstrings, complexity metrics, bounded source snippets ($\le 40$ lines), and direct callers/callees  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_symbol_context`
- [ ] T058 [FR-005] Refine `get_dependencies(symbol, direction, depth, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` to distinguish and return both external package dependencies and internal graph edges (`CALLS`, `IMPORTS`, `DEPENDS_ON`), returning both when symbol is omitted  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_dependencies`
- [ ] T059 [FR-005] Refine `get_risk_analysis(symbol_or_component, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` to support project/run-level risk queries (e.g. `python-proj` or `HEAD`) without requiring a code symbol  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_risk_analysis`
- [ ] T060 [FR-005] Refine `get_upgrade_plan(task_identifiers, repository_id)` in `backend/src/trace/services/assistant/tools.py` to resolve natural language task references ("Task 1", "Task 4"), fetch all requested tasks simultaneously, and provide prerequisite DAG edges and tier rationales  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_upgrade_plan`
- [ ] T061 [FR-005] Implement `get_test_coverage(component, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` retrieving associated test functions and cleanly reporting unanalyzed coverage without raising evidence errors  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_get_test_coverage`
- [ ] T062 [FR-005] Implement `search_project_knowledge(query, analysis_run_id)` in `backend/src/trace/services/assistant/tools.py` as a supplementary fallback tool over broader analysis metadata  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -k test_search_project_knowledge`
- [ ] T063 [P] Author unit tests for all 9 composable retrieval tools in `backend/tests/unit/test_assistant_tools.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_tools.py -v`

---

## Phase 15: Semantic Intent Routing & Workflow Refinement

**Purpose**: Implement semantic intent understanding, non-exclusive multi-tool scheduling, narrow Missing Entity Guard, and general knowledge bypass in the LangGraph workflow.

- [ ] T064 [FR-001] [FR-003] Update `understand_question` node in `backend/src/trace/services/assistant/workflow.py` to implement semantic intent classification across 10 categories, detect multi-intent queries, and flag general knowledge questions for bypass  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_understand_semantic_routing`
- [ ] T065 [FR-002] Update `select_tools` node in `backend/src/trace/services/assistant/workflow.py` to support non-exclusive multi-tool scheduling (e.g. `get_upgrade_plan` + `get_dependencies`, `search_codebase` + `get_risk_analysis`, `get_project_overview` + `search_project_knowledge`)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_multi_tool_selection`
- [ ] T066 [FR-008] Update `evaluate_sufficiency` node in `backend/src/trace/services/assistant/workflow.py` to narrow the Missing Entity Guard strictly to `SYMBOL_CONTEXT` queries where a specific symbol was claimed to exist, ensuring exploratory queries (`search_codebase`, "Can I add payment functionality?") are never aborted  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_narrow_missing_entity_guard`
- [ ] T067 [FR-007] Update LangGraph StateGraph topology in `backend/src/trace/services/assistant/workflow.py` adding conditional edge from `understand_question` directly to `synthesize_answer` when `is_general_knowledge` is true  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -k test_general_knowledge_bypass`
- [ ] T068 [P] Update unit tests for workflow semantic routing and multi-tool execution in `backend/tests/unit/test_assistant_workflow.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_workflow.py -v`

---

## Phase 16: Grounded Synthesis, Facts vs. Inference & Telemetry

**Purpose**: Update LLM reasoning prompt to distinguish facts vs. inferences, enhance deterministic fallback formatting, and instrument execution telemetry.

- [ ] T069 [FR-015] [FR-016] Update `ASSISTANT_SYSTEM_PROMPT` in `backend/src/trace/services/assistant/synthesis.py` instructing the LLM to strictly distinguish directly retrieved facts, reasonable architectural inference, and unavailable information (never fabricating dependencies, risk factors, or task relationships)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_facts_vs_inference_prompt`
- [ ] T070 [FR-021] [FR-022] Update `DeterministicFallbackGenerator` in `backend/src/trace/services/assistant/synthesis.py` to format clean, structured deterministic markdown summaries for project overview, internal/external dependencies, and multi-task upgrade plans  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_fallback_generator_multi_domain`
- [ ] T071 [FR-026] Add execution timing telemetry in `workflow.py` and `synthesis.py` measuring tool execution latency and LLM synthesis latency  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -k test_execution_telemetry`
- [ ] T072 [P] Update synthesis unit tests in `backend/tests/unit/test_assistant_synthesis.py`  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_synthesis.py -v`

---

## Phase 17: Clean UI Evidence Expander

**Purpose**: Clean up answer presentation in Streamlit Observatory to keep normal answers uncluttered, moving evidence details into a collapsible expander.

- [ ] T073 [FR-023] [FR-025] Update assistant chat response presentation in `frontend/app.py` (lines 1840–1920) to ensure the normal answer never dumps raw JSON, SVG, or internal ID payloads, placing evidence details and sources into a clean, collapsible `st.expander("View Evidence Sources")` (**STRICT CONSTRAINT**: Preserved lines 51–643 and 870–1239 containing graph canvas renderers)  
  *Verification*: `python -m py_compile frontend/app.py`

---

## Phase 18: Acceptance Benchmark Suite (Scenarios A through J) & Full Regression

**Purpose**: Implement and verify automated benchmark tests covering Acceptance Scenarios A through J, measuring real execution latency and ensuring zero regressions.

- [ ] T074 [SC-009] Implement and verify automated benchmark tests in `backend/tests/unit/test_assistant_benchmarks.py` covering Scenarios A through J:
  - Scenario A: *"What language is this project written in?"* (`get_project_overview`)
  - Scenario B: *"What dependencies are present?"* (`get_dependencies` internal + external)
  - Scenario C: *"Why does Task 1 precede Task 4?"* (`get_upgrade_plan` + `get_dependencies`)
  - Scenario D: *"Why is python-proj classified as high risk?"* (`get_risk_analysis` run-level)
  - Scenario E: *"What changed between revisions?"* (`get_change_analysis`)
  - Scenario F: *"Show me everything affected by PaymentAPI."* (`get_dependencies` depth=2)
  - Scenario G: *"Which affected components have low test coverage?"* (`get_test_coverage` + `get_risk_analysis`)
  - Scenario H: *"Can I add payment-related functionality?"* (`search_codebase` exploratory without entity guard failure)
  - Scenario I: *"What is this project?"* (`get_project_overview`)
  - Scenario J: *"Why is the sky blue?"* (General knowledge bypass)  
  *Verification*: `uv run pytest backend/tests/unit/test_assistant_benchmarks.py -v`
- [ ] T075 Execute full backend regression test suite ensuring 100% pass rate and zero regressions across F01–F10  
  *Verification*: `uv run pytest backend/tests/ -v`

---

## Dependencies & Execution Graph

```text
Phase 14: 9-Tool Suite Refinements (T055-T063)
                 │
                 ▼
Phase 15: Semantic Routing & Workflow Refinement (T064-T068)
                 │
                 ▼
Phase 16: Grounded Synthesis & Telemetry (T069-T072)
                 │
                 ├─────────────────────────────┐
                 ▼                             ▼
Phase 17: Clean UI Expander (T073)       Phase 18: Benchmark Suite Scenarios A–J (T074)
                 │                             │
                 └──────────────┬──────────────┘
                                ▼
                 Full Regression Verification (T075)
```

### Parallel Opportunities:
- **Phase 14**: Tasks **T055, T056, T057, T058, T059, T060, T061, T062** can be developed and refined in parallel once the base method signatures in `tools.py` are mapped.
- **Phase 16 & 17**: Frontend cleanup (**T073**) can run in parallel with telemetry and prompt refinement (**T070–T072**).
- **Phase 18**: Benchmark tests (**T074**) can be authored against mocked state and executed once Phase 16 completes.
