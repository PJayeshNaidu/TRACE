# Feature Specification: TRACE Phase 4 — F05: Impact Analysis & Risk Evaluation Engine

**Feature Branch**: `006-impact-risk-analysis`  
**Created**: 2026-09-30  
**Phase**: Phase 4 (F05)  
**Status**: Draft  
**Depends On**: F01 (Project & Repository Management), F02 (Repository / Code Analyzer), F03 (Dependency Graph), F04 (Version / Change Analyzer)  
**Feeds Into**: F06 (Upgrade Plan Generator), F10 (Observatory AI Assistant)  
**Input**: User description: "Implement impact analysis and risk analysis bridging Git diffs, AST scopes, transposed multi-hop graph blast radius, deterministic syntax delta inference, dual-track LLM/heuristic reasoning, and prioritized remediation planning."

---

## 1. Overview & Executive Summary

While **F04 (Version / Change Analyzer)** detects *what changed* between two revisions at the symbol level, **F05 (Impact Analysis & Risk Evaluation Engine)** answers the critical downstream questions:
1. *"What can this change affect across the entire call hierarchy?"*
2. *"How far does the risk propagate through direct callers, callers of callers, and architectural entrypoints?"*
3. *"Why did this component break (signature, return contract, exception flow, or internal logic)?"*
4. *"What is the prioritized, actionable remediation checklist the developer must execute to fix it?"*

The system bridges three distinct conceptual layers:
```text
[Layer 1: Textual Git Diff]       --> Lines modified (+ / - hunks with diff_snippet)
              │
              ▼  (Mathematical Interval Intersection)
[Layer 2: Syntactic AST Scope]    --> Containing Function/Class/Endpoint with Decorator Expansion
              │
              ▼  (Graph Transposition G^T & Multi-Hop BFS)
[Layer 3: Behavioral Propagation] --> Inbound Callers (depth 1..3), Text References, Remediation Checklist
```

F05 operates in a **Dual-Track** mode:
- **Offline / Deterministic Track (Default)**: Uses AST interval overlaps, graph transposition ($G^T$), regex-based syntax delta rules (`def`, `return`, `raise`), and graph topological sorting to deliver 100% deterministic analysis with zero latency and zero external API dependencies.
- **Online / LLM Track (Optional)**: When an OpenRouter API key and model are provided via the UI or environment, enriches the exact same payload schema with natural-language architectural synthesis and context-aware remediation explanations.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Zero-Context Diff Hunk Slicing & AST Interval Intersection (Priority: P1)

As a developer reviewing a pull request or commit range, I need TRACE to isolate the exact lines modified and map them directly to containing code symbols (functions, classes, endpoints), so that I don't get a dump of unchanged code and only see entities whose AST boundaries actually intersect changed code.

**Why this priority**: Without high-precision mathematical interval intersection and decorator boundary expansion, all downstream blast radius and risk calculations produce false positives.

**Independent Test**: Can be tested independently by feeding a unified diff against a repository AST, verifying that only functions whose interval $[F_{start}, F_{end}]$ intersects hunk $[H_{start}, H_{end}]$ are tagged as modified, with the exact patch text attached as `diff_snippet`.

**Acceptance Scenarios**:
1. **Given** a commit modifying lines 14–18 in `src/payments.py` inside function `calculate_tax` (lines 10–25), **When** diff slicing runs, **Then** `calculate_tax` is identified as a modified entity with `lines_affected: [14, 18]` and hunk patch text captured in `diff_snippet`.
2. **Given** a route decorator `@app.get("/checkout")` modified on line 9 above function `checkout` starting at line 10, **When** interval intersection runs, **Then** the decorator expansion rule extends $F_{start}$ to line 9 and correctly flags `checkout` as modified.
3. **Given** a file modification in comments or whitespace outside any function, **When** interval intersection runs, **Then** zero functions are returned as modified entities.

---

### User Story 2 - Multi-Hop Blast Radius via Graph Transposition $G^T$ (Priority: P1)

As a software architect, when a core service or function changes, I need to see which upstream callers will break up to 3 hops away (direct callers $\to$ callers of callers $\to$ API endpoints), so that I understand the true architectural blast radius.

**Why this priority**: 1-hop caller detection only sees immediate wrappers and misses the high-level services and user-facing endpoints that actually break in production.

**Independent Test**: Can be tested independently by constructing a directed call graph $G$, computing its transpose $G^T$, and running BFS from a modified node to verify that all upstream callers within depth $\le 3$ are returned, ordered by distance.

**Acceptance Scenarios**:
1. **Given** a call chain `checkout_api` (endpoint) $\to$ `process_payment` $\to$ `calculate_tax` (modified), **When** blast radius runs on `calculate_tax`, **Then** both `process_payment` (depth 1) and `checkout_api` (depth 2) are identified as `CallersAtRisk`.
2. **Given** a cyclic or highly interconnected graph, **When** BFS traversal runs, **Then** traversal visits each node at most once, respects the maximum depth limit of 3, and terminates without infinite loops.

---

### User Story 3 - Deterministic Transformation Intelligence & Actionable Remediation (Priority: P2)

As a developer, I need to know *what* changed within the function (signature, return type, exception flow, or internal statements) and *what exact steps* I must take to remediate downstream callers, even when working completely offline without an LLM.

**Why this priority**: Developers need clear, actionable guidance on call site updates, test executions, and contract validations rather than raw diff chunks.

**Independent Test**: Can be tested independently by passing diff snippets containing `def`, `return`, `raise`, or internal statements into the deterministic rule engine, verifying that corresponding `change_summary`, `justification`, and `remediation_guidance` fields are populated deterministically.

**Acceptance Scenarios**:
1. **Given** a diff snippet adding a parameter to `def calculate_tax(amount, rate, currency):`, **When** the syntax delta engine inspects the snippet, **Then** `change_summary` states "Method signature / parameter definitions modified" and `remediation_guidance` directs auditing of all call sites.
2. **Given** a diff snippet modifying `raise PaymentError(...)`, **When** analyzed, **Then** `change_summary` states "Exception raising / error handling flow updated" and remediation advises updating caller `try/except` blocks.
3. **Given** an analysis result with breaking changes, deleted files, and inbound callers, **When** the plan is synthesized, **Then** an ordered 4-step checklist (Contract Changes $\to$ Missing Modules $\to$ Direct Callers $\to$ Integration Validation) is produced.

---

### User Story 4 - Dual-Track LLM Reasoning (OpenRouter) with Graceful Offline Fallback (Priority: P2)

As a team lead using TRACE Observatory, I want the option to input an OpenRouter API key and model to receive richer natural language reasoning and tailored upgrade guidance, while ensuring the entire platform works flawlessly with heuristic rules if no API key is provided.

**Why this priority**: Adheres to TRACE's core tenet: *"AI proposes. Evidence validates. The system records. Humans decide."* AI is an optional enrichment layer over mathematically verified evidence.

**Independent Test**: Can be tested by executing the analysis pipeline twice: once with an OpenRouter API key (validating enriched JSON response) and once with no API key (validating identical JSON schema populated by the offline rule engine).

**Acceptance Scenarios**:
1. **Given** an active OpenRouter API key and model `anthropic/claude-3.5-sonnet`, **When** comparison analysis completes, **Then** the LLM generates concise, contextual justifications using entity summaries and diff snippets capped to ~350 characters.
2. **Given** no API key is configured, **When** comparison analysis runs, **Then** the heuristic engine populates the exact same JSON schema fields with zero latency, zero cost, and zero errors.

---

### User Story 5 - Cross-Module Text & Configuration Reference Discovery (Priority: P3)

As a DevOps engineer, when a function or route is modified, I need TRACE to scan non-code files (YAML workflows, JSON configurations, Markdown docs) to identify references outside the Python AST, so that config-driven pipelines don't silently fail.

**Why this priority**: ASTs cannot see string-based references in GitHub Actions workflows, Dockerfiles, Celery configs, or documentation.

**Independent Test**: Can be tested by searching for symbol identifiers using word boundaries (`\b<name>\b`) across repository non-code files and checking that matches populate `downstream_dependent_files`.

**Acceptance Scenarios**:
1. **Given** a function `process_payment` referenced in `deploy/tasks.yaml`, **When** cross-module text discovery runs, **Then** `deploy/tasks.yaml` is added to `downstream_dependent_files`.
2. **Given** occurrences of the symbol name inside its own source file, **When** scanning runs, **Then** self-references are excluded from `downstream_dependent_files`.

---

### Edge Cases

- **Empty or Whitespace-Only Changes**: If a diff only touches comments or indentation outside function boundaries, return `total_changed_entities: 0` and `LOW` risk.
- **Documentation & Docstring-Only Modifications**: When diff hunks modify only docstrings, comments, Sphinx/RST roles, or non-executable prose inside an AST entity, the system SHALL flag `is_doc_only: true`, exempt upstream callers from `callers_at_risk` escalation, and assign overall `RiskLevel.LOW`.
- **Non-Code Asset Deletion**: Deletion of markdown, documentation, or asset files (`.md`, `.txt`, `.rst`, `.png`, etc.) SHALL NOT trigger `Code Module Deletion` (HIGH); only source code modules (`.py`, `.ts`, `.go`, etc.) escalate risk to `HIGH`.
- **Dynamic Method Invocation (`getattr`)**: If a function invokes `getattr(self, "pay")`, extract `"pay"` as an outbound call rather than generic `getattr`.
- **Async & Task Queue Wrappers**: If a task is dispatched via `send_email.delay()` or `task.apply_async()`, unwrap the callable to register `send_email`.
- **Large Changesets (>100 files)**: Diff hunks must be sliced per changed code file; diff snippets passed to the LLM must be strictly capped (350 chars per entity) to prevent context window overflow.
- **Disconnection / LLM Rate Limiting**: If OpenRouter fails (timeout, 429, invalid key), automatically fall back to the deterministic heuristic engine without raising an unhandled exception.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Diff Slicing & AST Intersection
- **FR-001**: The system SHALL perform efficient diff hunk extraction using zero-context diffing (`git diff <base> <target> -U0`) and parse hunk line intervals $[H_{start}, H_{end}]$.
- **FR-002**: The system SHALL apply the **Decorator Expansion Rule** during symbol extraction, extending function start line $F_{start}$ to the first decorator node.
- **FR-003**: The system SHALL compute symbol modifications via the interval overlap condition: $\max(F_{start}, H_{start}) \le \min(F_{end}, H_{end})$.
- **FR-004**: The system SHALL bind the exact hunk patch lines to each modified entity as `diff_snippet`.

#### Outbound & Inbound Dependency Extraction
- **FR-005**: The system SHALL normalize imports into canonical fully qualified names using a file-level import table (`import x as y`, `from a.b import c`).
- **FR-006**: The system SHALL sanitize dependencies by filtering out standard library built-ins (`print`, `len`, `range`, `dict`, `list`, `isinstance`) from the outbound call graph.
- **FR-007**: The system SHALL unwrap task queues (`.delay`, `.apply_async`) and string reflection (`getattr(obj, "method")`) into concrete target call edges.

#### Transposed Graph Blast Radius
- **FR-008**: The system SHALL construct the directed call graph $G = (V, E)$ and compute its transpose $G^T = (V, E^T)$ to trace upstream callers.
- **FR-009**: The system SHALL execute Breadth-First Search (BFS) or Single-Source Shortest Path on $G^T$ from each modified symbol up to a maximum depth of 3, recording caller distance.
- **FR-010**: The system SHALL scan repository text and configuration files using word-boundary matching `\b<entity_name>\b` to populate `downstream_dependent_files`.

#### Transformation Intelligence & Remediation
- **FR-011**: The system SHALL implement a deterministic Diff Syntax Delta engine that inspects patch snippets for `def`, `return`, `raise`, and logic modifications to generate `change_summary`, `remediation_guidance`, and `justification`.
- **FR-011b**: The system SHALL classify documentation/docstring/comment-only diffs as `is_doc_only = true`, producing non-breaking justification and exempting upstream callers from risk tier escalation.
- **FR-011c**: The system SHALL distinguish deleted source code modules from non-code assets, scoring non-code deletions at `LOW` severity and source code module deletions at `HIGH` severity.
- **FR-012**: The system SHALL synthesize an actionable remediation plan (contract changes $\to$ missing modules $\to$ direct callers $\to$ integration validation), defaulting to documentation build validation when changes are exclusively documentation-only.
- **FR-013**: The system SHALL support an optional OpenRouter LLM track that enriches justifications and remediation text when an API key is provided, falling back automatically to the deterministic heuristic engine if absent.

#### API & Unified Payload Contract
- **FR-014**: The system SHALL expose REST API endpoints:
  - `POST /api/v1/impact/evaluate`: Accepts repository ID, base ref, target ref, and optional LLM config.
  - `GET /api/v1/impact/{analysis_id}`: Retrieves the structured impact, graph, and risk analysis payload.
- **FR-015**: The system SHALL return the unified 4-key JSON schema containing:
  - `analysis_metadata`: Repository URL, commit SHAs, entity and file counts.
  - `impact_analysis`: Summary sentence and array of `detailed_impacts` (containing `diff_snippet`, `change_summary`, `remediation_guidance`, `justification`, `outbound_calls`, `inbound_callers`, `downstream_dependent_files`).
  - `dependency_graph`: `nodes`, `edges`, and an auto-generated `mermaid` graph string with CSS color styling (#ef4444 for modified, #f59e0b for at-risk callers).
  - `risk_analysis`: Deterministic `risk_level`, `key_risk_factors`, `ci_cd_recommendations`, and `actionable_remediation_plan`.

---

### Key Entities *(include if feature involves data)*

- **ImpactAnalysisAggregate**: The root domain entity representing a complete impact evaluation run, uniquely identified by UUID.
- **DetailedImpact**: Encapsulates a modified symbol with its file path, entity type, line intervals, patch `diff_snippet`, inbound callers (depth 1..3), outbound dependencies, downstream dependent files, change summary, and remediation advice.
- **TransposedCallGraph ($G^T$)**: In-memory graph structure representing inverted dependency edges enabling multi-hop upstream reachability analysis.
- **RiskAnalysisProfile**: The evaluated risk tier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), accompanied by structured risk factors, CI/CD execution recommendations, and the 4-step remediation plan.
- **DualTrackReasoner**: The reasoning interface with two concrete implementations: `HeuristicRuleEngine` (offline, zero-cost) and `OpenRouterLlmReasoner` (online, AI-synthesized).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Diff slicing and AST interval intersection SHALL complete in $< 1.0\text{ second}$ for changesets under 50 files.
- **SC-002**: Multi-hop BFS blast radius calculation on $G^T$ SHALL terminate in $< 500\text{ ms}$ for call graphs up to 5,000 nodes.
- **SC-003**: In offline mode, the system SHALL achieve 100% deterministic reproducibility (identical commits produce bit-for-bit identical JSON schemas).
- **SC-004**: Zero false-negatives on decorator changes: modifying a route or permission decorator SHALL always register the decorated function as modified.
- **SC-005**: When an OpenRouter API key is invalid or unavailable, the system SHALL fallback to heuristic analysis with 0% downtime and 0 unhandled exceptions.
- **SC-006**: Generated Mermaid dependency graphs SHALL render valid syntax with distinct color coding for modified entities (#ef4444) and at-risk upstream callers (#f59e0b).

---

## Assumptions

- Git binary (`git`) is available in the server runtime environment for diff execution.
- Python AST parsing operates on syntactically valid Python code; files with syntax errors are captured as diagnostics without halting the analysis run.
- When OpenRouter API is enabled, the model output is strictly parsed as JSON matching the schema; parsing failures automatically fall back to the heuristic rule engine.
- Multi-hop blast radius traversal defaults to depth 3 as the optimal tradeoff between deep coverage and false-positive explosion.
