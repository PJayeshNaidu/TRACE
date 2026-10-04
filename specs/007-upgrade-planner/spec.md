# Feature Specification: TRACE Phase 6 — F07: Upgrade Planner

**Feature Branch**: `007-upgrade-planner`  
**Created**: 2026-10-01  
**Phase**: Phase 6 (F07)  
**Status**: Draft  
**Depends On**: F01 (Project & Repository Management), F02 (Repository / Code Analyzer), F03 (Dependency Graph), F04 (Version / Change Analyzer), F05 & F06 (Impact Analysis & Risk Evaluation Engine)  
**Feeds Into**: F08 (Interactive Observatory Visualization), F09 (Verification), F10 (Observatory AI Assistant)  
**Input**: User description: "Implement F07 Upgrade Planner to transform impact and risk information into an actionable, dependency-ordered upgrade plan with comprehensive task metadata, status tracking, graph topological sequencing, cycle and edge-case handling, and interactive Observatory UI."

---

## 1. Overview & Executive Summary

While **F04 (Version / Change Analyzer)** detects *what changed* between two revisions, and **F05/F06 (Impact Analysis & Risk Evaluation Engine)** identifies *what components are affected* and *how critical that risk is*, **F07 (Upgrade Planner)** answers the essential engineering delivery question:

> *"In what specific order must the transformation be executed, what exact changes and tests are required for each component, and what is our real-time upgrade completion progress?"*

F07 bridges the gap between passive diagnostic discovery and active software remediation by constructing a stateful, dependency-ordered **Upgrade Plan**:

```text
[F05/F06: Impact & Risk Intelligence]
  ├── DetailedImpact (AST scopes, diff snippets, syntax delta)
  ├── Blast Radius Callers ($G^T$ BFS distance 1..3)
  └── Evaluated Risk Factors & Recommendations
               │
               ▼
[F07: Topological DAG Task Sequencer]
  ├── Phase Tiering (Contracts ➜ Core ➜ Data ➜ Consumers ➜ Clients ➜ Tests ➜ Docs)
  ├── Cycle Detection & Disconnected Subgraph Resolution
  └── Task Evidence & Dependency Binding
               │
               ▼
[F07: Stateful Upgrade Plan & Observatory UI]
  ├── Authoritative Persistence (PostgreSQL `upgrade_plans` & `upgrade_tasks`)
  ├── Real-Time Task Lifecycle (PENDING ➜ IN_PROGRESS ➜ COMPLETED)
  └── Interactive Streamlit Observatory Plan Explorer
```

F07 operates in strict compliance with the **TRACE Constitution**:
- **Evidence over Hallucination (Principle I)**: Every generated task is anchored to verifiable Git diff hunks, AST scopes, and call graph paths.
- **Deterministic Before Probabilistic (Principle II)**: The task sequence and dependency DAG are computed deterministically using graph topology and syntax deltas. LLM-assisted enrichment is strictly an optional overlay.
- **Human-in-the-Loop (Principle III)**: Engineers retain full agency to inspect evidence, adjust task states, annotate decisions, and execute steps at their own pace.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dependency-Aware Upgrade Plan Generation from Impact Data (Priority: P1)

As a software architect or engineer reviewing a complex changeset, I need TRACE to convert impact analysis results and risk profiles into an actionable, sequentially ordered sequence of upgrade tasks (modifying contract boundaries and base dependencies before downstream callers, consumers, tests, and documentation), so that the team can execute the migration without introducing broken intermediate states or compilation failures.

**Why this priority**: Without dependency-aware topological ordering, developers are left with a flat list of affected components and no guidance on the sequence of operations, leading to circular debugging and integration chaos.

**Independent Test**: Can be tested independently by taking a completed impact analysis payload with multi-hop callers (e.g. `API` $\to$ `Service` $\to$ `Handler` $\to$ `Test`), executing plan generation, and asserting that the resulting task DAG enforces that prerequisites precede dependents.

**Acceptance Scenarios**:
1. **Given** an impact analysis where function `process_payment` has changed and endpoint `checkout_endpoint` invokes it, **When** an upgrade plan is generated, **Then** the task for updating `process_payment` has a lower step number than `checkout_endpoint`, and `checkout_endpoint` explicitly lists `process_payment` as a required dependency.
2. **Given** a change that touches a data model, a service, an endpoint, a test suite, and a documentation file, **When** plan sequencing executes, **Then** tasks are assigned to ordered architectural tiers: Contract/Data $\to$ Service $\to$ Endpoint $\to$ Test $\to$ Documentation.
3. **Given** an impact analysis with zero changed entities (e.g., whitespace-only commit), **When** plan generation is triggered, **Then** the system produces an empty plan (`total_tasks: 0`, status: `COMPLETED`) with an informative summary and zero errors.

---

### User Story 2 - Comprehensive Task Metadata with Prescriptive Guidance & Verified Evidence (Priority: P1)

As a developer assigned to perform an upgrade task, I need the task card to clearly detail the target component, the architectural reason for the change, prerequisite tasks, expected code changes, required validation tests, inherited risk tier, and concrete supporting evidence (diff snippets and call graph chains), so that I can implement and verify the change with zero ambiguity and without consulting external tools.

**Why this priority**: Developers cannot execute remediation tasks efficiently if they are only given a symbol name. Clear expectations, test targets, and verified evidence prevent implementation regressions.

**Independent Test**: Can be tested independently by inspecting generated tasks against a known diff, verifying that fields `component`, `reason`, `dependencies`, `expected_changes`, `required_tests`, `risk_level`, `status`, and `evidence` are fully populated with accurate, inspectable data.

**Acceptance Scenarios**:
1. **Given** a modified function whose parameter list changed in the diff, **When** its task is generated, **Then** `expected_changes` specifies updating call signatures, `reason` cites the upstream contract modification, and `evidence` includes the exact patch hunk snippet and file line numbers.
2. **Given** an affected component with existing test targets identified in the dependency graph, **When** the task is generated, **Then** `required_tests` contains the qualified names of the associated test functions or test suites.
3. **Given** a high-risk component identified in F06, **When** its upgrade task is created, **Then** the task inherits `risk_level: HIGH` and includes the specific risk justification in its metadata.

---

### User Story 3 - Interactive Task Lifecycle & Progress Tracking (Priority: P2)

As an engineering lead or developer working through an upgrade, I need to track the status of each task (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`) via REST API and the Observatory UI, and observe aggregate completion metrics, so that our team maintains visibility into migration velocity and remaining high-risk items.

**Why this priority**: Upgrade plans are dynamic operational checklists. Without state persistence and progress tracking, teams cannot collaborate or verify when an upgrade is ready for release.

**Independent Test**: Can be tested independently by creating an upgrade plan, transitioning task statuses via `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}`, and asserting that the plan aggregate reflects updated completion percentages and timestamps.

**Acceptance Scenarios**:
1. **Given** a task in `PENDING` state with unsatisfied prerequisites, **When** a user attempts to set it to `COMPLETED`, **Then** the system warns the user of uncompleted prerequisite dependencies but permits override with an audit flag.
2. **Given** a plan with 10 tasks where 5 are marked `COMPLETED` and 1 `SKIPPED`, **When** the plan summary is queried, **Then** `progress_percentage` reports `60.0%` and `completed_tasks` reflects `6`.
3. **Given** all tasks in a plan are set to `COMPLETED` or `SKIPPED`, **When** the last task is saved, **Then** the plan status automatically updates to `COMPLETED`.

---

### User Story 4 - Resilient Graph Topology Handling: Cycles, Disconnected Subgraphs & Massive Changes (Priority: P2)

As a platform engineer dealing with real-world enterprise codebases containing circular imports, disjoint microservices, and large multi-file refactors, I need the planner to handle cyclic dependencies, parallelizable disconnected components, and changesets exceeding 100 files without infinite loops, crashes, or timeout degradation.

**Why this priority**: Real software graphs frequently contain mutual imports or isolated subgraphs. If the topological planner crashes on cycles or hangs on large graphs, the tool becomes unusable for complex refactoring.

**Independent Test**: Can be tested independently by feeding a synthetic call graph containing a cycle ($A \to B \to C \to A$) and a disconnected component ($D \to E$) into the planner, asserting that cycles are detected, grouped into a co-dependent batch, and ordered without infinite recursion.

**Acceptance Scenarios**:
1. **Given** a mutual dependency cycle between components $A$ and $B$, **When** topological sequencing runs, **Then** the planner detects the cycle via Tarjan's or Kosaraju's strongly connected components algorithm, groups them into an atomic co-dependent task batch, and tags them with `circular_dependency: true`.
2. **Given** two completely disconnected impacted components $X$ and $Y$ with their own downstream callers, **When** the plan is synthesized, **Then** the tasks for $X$ and $Y$ are marked as independent parallel streams, allowing concurrent team execution.
3. **Given** a large changeset modifying $>100$ files and producing hundreds of callers, **When** plan generation executes, **Then** task synthesis completes within $< 2.0\text{ seconds}$ and results are paginated via the API.

---

### User Story 5 - Dual-Track Plan Enrichment (Optional OpenRouter AI Synthesis with Offline Heuristic Baseline) (Priority: P3)

As a team lead using TRACE, I want the option to provide an OpenRouter API key and model to enrich upgrade tasks with natural-language architectural instructions, refactoring tips, and detailed assertion suggestions, while guaranteeing that 100% of the plan DAG, task ordering, and verified evidence remain fully operational offline without an external API.

**Why this priority**: Maintains adherence to the TRACE Constitution ("Free-First LLM Architecture" and "Deterministic Analysis before Probabilistic Inference"). AI enhances comprehension but deterministic graph analysis provides the core guarantee.

**Independent Test**: Can be tested by generating a plan twice: once in offline mode (validating deterministic heuristics and zero latency), and once with OpenRouter credentials (validating enriched descriptions and backward-compatible JSON schema).

**Acceptance Scenarios**:
1. **Given** no external API key is provided, **When** plan generation runs, **Then** tasks are generated using deterministic AST delta rules, syntax patterns, and graph distances with zero cost and zero network calls.
2. **Given** valid OpenRouter credentials and a selected model, **When** plan generation executes, **Then** task descriptions and expected changes are enriched with contextual refactoring recommendations capped to standard payload lengths.
3. **Given** an invalid OpenRouter key or network timeout during generation, **When** the planner runs, **Then** it automatically logs a warning, falls back to the deterministic heuristic engine, and successfully returns the plan.

---

## Edge Cases

- **Circular Dependencies ($A \to B \to A$)**: The topological planner MUST detect strongly connected components (SCCs) and group circular nodes into a single consolidated task or sibling batch with clear circularity warnings rather than entering an infinite loop.
- **Zero Impact / Whitespace Diffs**: When an impact evaluation contains zero modified entities, generate a valid `UpgradePlan` with `total_tasks: 0`, status `COMPLETED`, and an explanatory note ("No architectural impact detected").
- **Deleted Files / Missing Modules**: When a file or module was deleted in the diff, generate high-priority initial tasks categorized as `MISSING_MODULE`, instructing callers to remove or replace broken imports before updating other logic.
- **Unreachable / Orphaned Callers**: If an upstream caller is identified through text discovery rather than AST edges, place it in an `INTEGRATION_VALIDATION` tier with an evidence note stating it is a textual/config reference.
- **Massive Changesets (>500 entities)**: Tasks must be indexed by `step_number` and queryable with pagination (`limit`, `offset`, `category`, `status`, `risk_level`) to prevent frontend lag.
- **Plan Re-generation**: If a user re-evaluates impact on the same commit pair, support generating a new plan revision or updating existing pending tasks without overwriting user-completed tasks.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Plan Generation & Input Ingestion
- **FR-001**: The system SHALL ingest an `impact_analysis_id` (or repository ID with base and target Git refs) to initiate upgrade plan construction.
- **FR-002**: The system SHALL extract all modified entities from `detailed_impacts` and all upstream callers from `callers_at_risk` as task candidates.
- **FR-003**: The system SHALL map impacted entities to architectural tiers based on AST symbol types and structural roles:
  1. `CONTRACT_API`: Public endpoints, API contracts, route signatures, schema definitions.
  2. `CORE_LOGIC`: Internal domain functions, business services, core classes.
  3. `DATA_MAPPING`: Database models, ORM mappings, migration files.
  4. `CONSUMER_HANDLER`: Background workers, event handlers, webhook receivers, depth-1 callers.
  5. `CLIENT_UI`: Frontend views, client API wrappers, UI callers.
  6. `INTEGRATION_TEST`: Test suites and validation units referencing modified symbols.
  7. `DOCUMENTATION_CONFIG`: Non-code configs, deployment manifests, Markdown documentation.
- **FR-004**: The system SHALL persist the root `UpgradePlan` in PostgreSQL with a unique UUID, linking to the source `impact_analysis_id` and `repository_id`.

#### Dependency-Aware Topological Sequencing
- **FR-005**: The system SHALL construct an internal directed acyclic task graph $G_{plan} = (V_{task}, E_{dep})$ where directed edge $(u, v)$ indicates that task $u$ MUST be completed before task $v$.
- **FR-006**: The system SHALL establish dependency edges based on:
  - Call hierarchy ($G$ and $G^T$): A modified dependency MUST precede its caller.
  - Architectural tiers: Contracts precede core services; services precede consumer handlers; code precedes tests and documentation.
- **FR-007**: The system SHALL execute topological sorting (e.g. Kahn's algorithm or DFS with cycle detection) on $G_{plan}$ to assign a sequential, 1-indexed `step_number` to every task.
- **FR-008**: The system SHALL detect cycles using strongly connected component analysis; when a cycle is detected, the participating tasks SHALL be grouped into an atomic co-dependent batch and tagged with `is_circular: true`.
- **FR-009**: The system SHALL identify independent subgraphs and assign a `parallel_group_id`, indicating tasks that can be worked on concurrently by different engineers.

#### Task Metadata & Prescriptive Guidance
- **FR-010**: Every `UpgradeTask` SHALL include the following mandatory fields:
  - `component`: Fully qualified symbol or file path.
  - `reason`: Architectural rationale explaining why this component must change.
  - `dependencies`: List of prerequisite task IDs or component names that must be resolved first.
  - `expected_changes`: Concrete prescriptive instructions on what code, parameters, exceptions, or contracts to modify.
  - `required_tests`: Specific test functions, test files, or CI commands needed to validate this component.
  - `risk_level`: Inherited risk rating (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `status`: Execution lifecycle state (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`).
  - `evidence`: Verified diff patch snippet, line intervals, and call graph path.
- **FR-011**: The system SHALL populate `expected_changes` and `reason` deterministically using syntax delta inference (inspecting `def`, `return`, `raise`, and AST diff hunks) in offline mode.
- **FR-012**: The system SHALL support optional LLM enrichment via OpenRouter to augment `expected_changes` and `reason` with contextual natural-language refactoring advice, strictly preserving the deterministic DAG sequence and schema.

#### Task Lifecycle & Status Management
- **FR-013**: The system SHALL support updating task status to `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, or `SKIPPED`.
- **FR-014**: When all tasks in an `UpgradePlan` reach `COMPLETED` or `SKIPPED`, the plan status SHALL automatically transition to `COMPLETED`.
- **FR-015**: The system SHALL calculate and expose plan progress metrics: `total_tasks`, `completed_tasks`, `in_progress_tasks`, `pending_tasks`, `blocked_tasks`, and `progress_percentage`.
- **FR-016**: The system SHALL allow users to record execution notes and assignees against individual tasks.

#### API Contract
- **FR-017**: The system SHALL expose the following REST API endpoints under `/api/v1/upgrade-plans`:
  - `POST /api/v1/upgrade-plans/generate`: Generates an upgrade plan from an existing `impact_analysis_id` or Git revision range. Accepts optional LLM configuration.
  - `GET /api/v1/upgrade-plans/{plan_id}`: Retrieves the plan header, summary metrics, and full ordered task list.
  - `GET /api/v1/upgrade-plans/{plan_id}/tasks`: Retrieves filtered/paginated tasks (`status`, `category`, `risk_level`, `limit`, `offset`).
  - `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}`: Updates a task's `status`, `notes`, or `assignee`.
  - `GET /api/v1/repositories/{repo_id}/upgrade-plans`: Lists all upgrade plans generated for a repository.

#### Observatory UI (Streamlit Laboratory)
- **FR-018**: The system SHALL provide a dedicated `"📋 Upgrade Planner (F07)"` tab in the Streamlit Observatory.
- **FR-019**: The UI SHALL display an interactive Upgrade Plan summary header showing overall progress percentage, total task count, remaining high-risk tasks, and active plan status.
- **FR-020**: The UI SHALL provide filtering controls for:
  - Task Status (`ALL`, `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`)
  - Risk Level (`ALL`, `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`)
  - Architectural Category (`ALL`, `Contract`, `Core Service`, `Data Mapping`, `Consumer/Handler`, `Client/UI`, `Test`, `Docs`)
- **FR-021**: The UI SHALL render task cards displaying Step Number, Category Badge, Component Name, Risk Badge, Status Dropdown/Checkbox, Reason, Dependencies, Expected Changes, Required Tests, and an expandable Diff Snippet/Evidence viewer.
- **FR-022**: The UI SHALL enable direct status updates (e.g. marking a task `COMPLETED` or `IN_PROGRESS`) with immediate reactive UI refresh and backend persistence.

#### Actionability Filtering & AI Review Refinement
- **FR-023 (Actionability Classification)**: The system SHALL classify every detected change into an explicit actionability category:
  - `IGNORE`: Whitespace-only, formatting-only, comment wording changes, and docstring typos in code files with no behavioral/API change.
  - `INFORMATIONAL`: Non-behavioral documentation updates, markdown files, and static configuration changes.
  - `REVIEW`: Test-only changes or changes where architectural intent requires human inspection.
  - `UPGRADE`: Executable business logic, signature/contract changes, return types, exceptions, schema, or verified caller-propagated changes.
- **FR-024 (Documentation-Only Caller Suppression)**: Changes classified as `IGNORE` or `INFORMATIONAL` SHALL NOT create direct caller upgrade tasks, transitive caller tasks, or generic regression tasks. They SHALL be separated into `informational_changes` to prevent noise in the execution DAG. When the revision contains only documentation or comment modifications, `ChangeSignificance` SHALL be `MINOR_CHANGE`, overall risk SHALL be strictly `LOW`, task count SHALL be `0`, and clear low-priority advisory suggestions SHALL be provided.
- **FR-025 (Whole-Plan AI Review)**: When LLM enrichment is enabled, the system SHALL perform a whole-plan senior architect review evaluating overall change significance, whether a coordinated upgrade is recommended, topological sequence validity, false-positive detection, missing task suggestions, and concrete test recommendations.
- **FR-026 (Deterministic Evidence as Source of Truth)**: Deterministic static analysis SHALL remain the sole authority for dependency edges, topological order, and component classification. If AI flags a false positive for an entity with verified AST or API changes, deterministic evidence SHALL override AI suppression.
- **FR-027 (Missing Task Safeguards)**: AI missing-task suggestions SHALL be validated against repository AST evidence. Suggestions unverified in the codebase SHALL remain advisory warnings and SHALL NOT be automatically inserted into the DAG.
- **FR-028 (Default Free Model & Offline Fallback)**: The default LLM model SHALL be `mistralai/mistral-7b-instruct:free` (not Claude). If OpenRouter is unavailable, times out, rate-limits, or returns malformed JSON, the deterministic heuristic plan SHALL remain completely valid and intact.
- **FR-029 (Change Significance Classification)**: Before generating the final plan, the changeset SHALL be classified into `MAJOR_CHANGE`, `MODERATE_CHANGE`, `MINOR_CHANGE`, or `NO_ACTION_REQUIRED`.
- **FR-030 (Task Action Type Necessity)**: Every candidate entity in the plan SHALL have an explicit `action_type` evaluated: `REQUIRED_CHANGE`, `VALIDATION_ONLY`, `LOW_PRIORITY_REVIEW`, or `NO_ACTION`. Callers of unchanged signatures SHALL NOT be assigned code changes unless verified evidence warrants adaptation.
- **FR-031 (Human-Readable Tier Descriptions)**: Every task SHALL display a human-readable tier name and description across the 7-tier system (`Tier 1 · API / Contract`, `Tier 2 · Core Logic`, `Tier 3 · Data / Mapping`, `Tier 4 · Handlers / Consumers`, `Tier 5 · Client / UI`, `Tier 6 · Tests / Integration`, `Tier 7 · Documentation / Config`).
- **FR-032 (Ordering Rationale & Task vs Suggestion Separation)**: The plan SHALL expose a concise `order_rationale` explaining why the topological sequence is safe. Non-essential suggestions SHALL be strictly separated in `optional_suggestions` (`TASK ≠ SUGGESTION`) and SHALL NOT inflate task counts, risk ratings, or dependency DAGs.

---

### Key Entities *(mandatory)*

- **UpgradePlan**: Root domain aggregate representing a complete transformation plan.
  - `id`: UUID (Primary Key)
  - `repository_id`: UUID (Foreign Key to `repositories`)
  - `impact_analysis_id`: UUID (Foreign Key to `impact_analyses`)
  - `title`: Short title (e.g., "Upgrade Plan: v1.0 ➜ v2.0")
  - `base_commit`: String
  - `target_commit`: String
  - `risk_level`: String (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
  - `status`: String (`DRAFT`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`)
  - `total_tasks`: Integer
  - `completed_tasks`: Integer
  - `progress_percentage`: Float (0.0 to 100.0)
  - `reasoning_mode`: String (`HEURISTIC` or `LLM_ENRICHED`)
  - `change_significance`: String (`MAJOR_CHANGE`, `MODERATE_CHANGE`, `MINOR_CHANGE`, `NO_ACTION_REQUIRED`)
  - `significance_reasoning`: String (Semantic justification of change significance)
  - `recommended_action`: String ("A coordinated upgrade is recommended." vs "No major upgrade work required.")
  - `order_rationale`: String (Topological progression explanation)
  - `optional_suggestions`: List of Strings (Advisory suggestions separated from execution tasks)
  - `informational_changes`: List of `InformationalChange` objects (omitted from DAG)
  - `ai_plan_review`: Optional whole-plan senior architect review payload
  - `created_at`: DateTime (UTC)
  - `updated_at`: DateTime (UTC)

- **UpgradeTask**: Individual actionable engineering unit of work.
  - `id`: UUID (Primary Key)
  - `plan_id`: UUID (Foreign Key to `upgrade_plans`)
  - `step_number`: Integer (1-indexed topological order)
  - `component`: String (Qualified symbol or file path)
  - `component_type`: String (`function`, `method`, `class`, `endpoint`, `file`, `config`, `test`)
  - `category`: String (`CONTRACT_API`, `CORE_LOGIC`, `DATA_MAPPING`, `CONSUMER_HANDLER`, `CLIENT_UI`, `INTEGRATION_TEST`, `DOCUMENTATION_CONFIG`)
  - `actionability`: String (`UPGRADE`, `REVIEW`, `INFORMATIONAL`, `IGNORE`)
  - `action_type`: String (`REQUIRED_CHANGE`, `VALIDATION_ONLY`, `LOW_PRIORITY_REVIEW`, `NO_ACTION`)
  - `tier_name`: String (e.g., "Tier 2 · Core Logic")
  - `tier_meaning`: String (e.g., "Business rules, services, domain/application logic")
  - `change_significance`: Optional String (`MAJOR_CHANGE`, `MODERATE_CHANGE`, `MINOR_CHANGE`, `NO_ACTION_REQUIRED`)
  - `reason`: String (Why this component must change)
  - `dependencies`: Tuple of Strings (Task IDs or component names that must precede this task)
  - `expected_changes`: String (Specific modifications required)
  - `required_tests`: Tuple of Strings (Target test functions or suites)
  - `risk_level`: String (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
  - `status`: String (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`)
  - `is_circular`: Boolean (True if part of a circular dependency cycle)
  - `parallel_group_id`: Optional Integer (Identifies independent parallel execution streams)
  - `notes`: Optional String (Developer annotations)
  - `ai_confidence`: Optional String (`HIGH`, `MEDIUM`, `LOW`, or float score)
  - `ai_review`: Optional Dictionary (Per-task AI recommendations and justification)
  - `evidence`: Dictionary / JSON (diff snippet, AST intervals, caller path)
  - `created_at`: DateTime (UTC)
  - `updated_at`: DateTime (UTC)

- **InformationalChange**: Non-behavioral, documentation, or minor formatting change.
  - `component`: String (Component name or file path)
  - `file_path`: String
  - `category`: String (`DOCUMENTATION_CONFIG`)
  - `reason`: String
  - `diff_snippet`: String
  - `actionability`: String (`IGNORE` or `INFORMATIONAL`)

- **TaskDependencyEdge**: Explicit directed relationship between tasks for DAG persistence and traversal.
  - `source_task_id`: UUID (Prerequisite task)
  - `target_task_id`: UUID (Dependent task)
  - `dependency_type`: String (`CALLS`, `IMPORTS`, `SCHEMA_CONTRACT`, `TIER_ORDER`)

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Upgrade plan DAG construction and topological sequencing SHALL complete in $< 1.5\text{ seconds}$ for changesets with up to 200 impacted components.
- **SC-002**: 100% of generated tasks SHALL be strictly ordered such that no dependent component is scheduled before its prerequisite contract or callee (except when explicitly tagged as part of a mutual cycle).
- **SC-003**: In offline mode, the system SHALL achieve 100% deterministic reproducibility: identical impact analysis inputs MUST produce bit-for-bit identical task orderings, step numbers, and heuristic metadata.
- **SC-004**: Cycle handling SHALL guarantee termination: circular dependencies in the codebase SHALL NEVER cause an infinite loop or process hang, and SHALL be grouped with 100% accuracy.
- **SC-005**: 100% of tasks with associated test coverage in the dependency graph SHALL have their specific test units listed in `required_tests`.
- **SC-006**: Task status updates executed via the API or Observatory UI SHALL persist to PostgreSQL and reflect in plan progress metrics within $< 200\text{ ms}$.
- **SC-007**: When an OpenRouter API failure occurs (timeout, rate limit, invalid key), plan generation SHALL automatically fall back to the deterministic heuristic engine with 0 downtime and 0 unhandled exceptions.

---

## Assumptions

- F01, F02, F03, F04, F05, and F06 remain authoritative upstream providers and are not modified by F07.
- An impact analysis run (F05/F06) must exist or be executable on-demand for the target revision pair to generate a plan.
- Topological task ordering operates primarily on Python AST dependencies and static call graphs, complemented by non-code file discoveries from F05 text scanning.
- In team development environments, multiple tasks within the same `parallel_group_id` can be safely assigned to different developers concurrently without merge conflicts on the same symbol.
- OpenRouter API keys are optional; the system provides full functionality without any cloud or paid API access.
