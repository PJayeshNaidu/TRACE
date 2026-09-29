# Feature Specification: TRACE Phase 2 — F02: Repository / Code Analyzer

**Feature Branch**: `003-repository-code-analyzer`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "TRACE Phase 2 — F02 Repository / Code Analyzer. Implement Phase 2 — F02 Repository / Code Analyzer only. The authoritative product baseline is the TRACE README. Transform a connected Python repository from raw source files into structured software intelligence using deterministic/static-analysis-first principles."

---

## Overview & Scope Boundaries

TRACE (Transformation Risk Analysis & Change Evaluation) requires transforming connected software repositories from raw source files and directory listings into structured, queryable software intelligence. While Phase 1 (F01) established project boundaries, repository registration, and non-destructive connectivity validation, Phase 2 (F02) introduces the static code analysis engine that inspects codebases to discover files, modules, classes, functions, calls, imports, relationships, tests, APIs, configurations, and database references without executing source code or relying on probabilistic AI hallucinations.

### Architectural Boundaries

**F02 Owns**:
- Static analysis engine abstraction (`CodeAnalyzer` protocol) isolating language-specific parsing from domain models.
- Python-specific deterministic static analyzer (`PythonCodeAnalyzer`) utilizing standard library AST and static extraction.
- Repository workspace acquisition via `GitProvider` (analyzing local repositories in place, or acquiring remote repositories into an isolated cache workspace using ambient credentials).
- Repository file filtering and exclusion enforcement (excluding `.git`, virtual environments, build artifacts, caches, `node_modules`, binary files, large files >1MB, and tracking generated code).
- Source root discovery (`src/` layout or repository root) and module/package resolution (including PEP 420 namespace packages).
- Structural symbol discovery: Python files, modules, packages, classes, services, methods, functions, decorators, and imports.
- Deterministic relationship extraction supported by repository evidence:
  - `IMPORTS` (module and symbol imports)
  - `CALLS` (statically resolvable function and method invocations)
  - `EXTENDS` (class inheritance hierarchies)
  - `DEPENDS_ON` (package/module dependencies and external packages)
  - `EXPOSES` (detected web/API endpoints from framework routing patterns)
  - `READS` / `WRITES` (database and configuration read/write operations)
  - `TESTED_BY` (associations between implementation units and test functions/classes)
  - `DOCUMENTED_BY` (inline docstrings and documentation files associated with code entities)
  - `CONFIGURED_BY` (settings and configuration keys referenced by components)
- External dependency manifest extraction (e.g., `pyproject.toml`, `requirements.txt`, `setup.cfg`, `setup.py`).
- Source location tracking (file path, line ranges, column offsets, qualified names, parent relationships).
- Graceful partial analysis and structured diagnostic collection (handling syntax errors, unreadable files, unsupported constructs without crashing).
- Analysis run lifecycle management and persistence:
  - PostgreSQL persistence for `AnalysisRun` state (`analysis_runs.repository_id` as authoritative foreign key), execution metrics, exact analyzed revision SHA (`resolved_revision`), and summary counters.
  - File/artifact persistence for comprehensive structured `RepositoryAnalysis` domain intelligence.
- Asynchronous analysis execution via an `AnalysisExecutor` abstraction (with in-process execution as default MVP).
- REST API endpoints for triggering analysis, polling run status, retrieving high-level summaries, and inspecting detailed analysis findings.

**F02 Explicitly Does NOT Own (Out of Scope)**:
- Multi-language analyzers outside Python (deferred to future language extensions).
- Neo4j graph database population and Cypher-based graph traversals (owned by Phase 3A — F03: Dependency Graph).
- Git commit diffing, version-to-version semantic delta comparisons, or AST diffing (owned by Phase 3B — F04: Version / Change Analyzer).
- Change impact propagation, blast-radius calculation, or downstream risk scoring (owned by Phase 4 — F05/F06).
- Automated upgrade planning or migration playbook synthesis (owned by Phase 5 — F07).
- Production React-based Observatory UI (Streamlit in `frontend/app.py` serves strictly as an evaluation interface for this phase).
- LLM-driven probabilistic code interpretation, summarization, or chat querying (F02 operates completely offline and deterministically without external LLM dependencies, adhering to TRACE Constitution §I, §II, and §VI).

### F01 Foundation Integration

F02 builds directly on the baseline established in Phase 1 (F01):
1. **Parent Context**: F02 analyses are initiated against existing registered repositories belonging to active TRACE projects.
2. **Repository Metadata**: F02 consumes repository location (`LOCAL` filesystem paths or `REMOTE` Git URLs), default branch hints, and operational status (`CONNECTED`).
3. **Run Linkage & Authoritative Ownership**: `analysis_runs.repository_id` serves as the authoritative foreign-key relationship for all analysis runs. Upon completing a run, the system updates `repositories.last_analysis_run_id` strictly as an optional denormalized convenience pointer, locking the repository against unverified deletion per F01 FR-020a and Constitution §I.
4. **Git Provider Boundary**: F02 leverages the `GitProvider` infrastructure to acquire or access repository working trees (directly via local path for `LOCAL` repositories, or via `acquire_workspace` for `REMOTE` repositories).

---

## Clarifications

### Session 2026-09-29

- **Q: How should comprehensive code intelligence (thousands of symbols and relationships) be persisted between PostgreSQL and filesystem artifacts?**  
  → **A**: Dual-tier storage model. PostgreSQL stores the `AnalysisRun` entity (run ID, repository ID, project ID, resolved revision SHA, lifecycle status, start/end timestamps, summary counts of files/symbols/relationships/errors). The full detailed `RepositoryAnalysis` domain model is persisted as an immutable, versioned JSON artifact on disk within the TRACE storage directory (`storage/artifacts/analyses/{run_id}.json`), linked by `artifact_path`. The REST API serves both summary metrics and detailed entity/relationship queries directly from this verified structure. F03 will consume this artifact to build the Neo4j graph.
- **Q: How should remote repositories be analyzed if F01 only performed non-destructive reference probes without cloning?**  
  → **A**: Working tree acquisition via Git workspace. For `LOCAL` repositories, F02 analyzes the repository files directly at the registered filesystem path. For `REMOTE` repositories, F02 acquires a shallow copy (`--depth 1`) of the target branch or commit SHA into an isolated workspace directory (`storage/workspaces/{repository_id}/{revision}`) using ambient credentials before running static analysis. If acquisition fails, the analysis run terminates with `FAILED` status and explicit diagnostic error logs.
- **Q: How are static calls and ambiguous dynamic references resolved deterministically?**  
  → **A**: Evidence-backed resolution only. Statically resolvable calls (direct function calls, method calls within the same module/class hierarchy, and imported symbols with clear origin) generate `CALLS` relationships with the target qualified name. Dynamic invocations (e.g., `getattr()`, variable function pointers, runtime metaprogramming) are tagged as unresolvable dynamic calls without fabricating hypothetical edges, adhering to TRACE Constitution §I (Evidence over Hallucination).
- **Q: How are syntax errors and malformed Python files handled during repository analysis?**  
  → **A**: Non-abortive diagnostic capture. A syntax error, tokenization failure, or encoding issue in one file produces an `AnalyzedFile` marked with status `ERROR`, accompanied by an `AnalysisDiagnostic` recording file path, line number, column offset, and parser message. The analyzer continues processing all remaining files in the repository.
- **Q: Should the repository analysis initiation endpoint execute analysis synchronously within the HTTP request or dispatch it as an in-process background task?**  
  → **A**: Option B — Strictly asynchronous execution via `AnalysisExecutor` abstraction. `POST /api/v1/repositories/{id}/analyze` creates an `AnalysisRun` record with status `PENDING`, dispatches analysis via an `AnalysisExecutor` (with in-process execution as the default MVP implementation), and returns HTTP 202 Accepted with the initial run representation. Clients, tests, and future UI components poll `GET /api/v1/analyses/{analysis_run_id}` to observe status transitions (`PENDING` → `IN_PROGRESS` → `COMPLETED` / `FAILED`) and retrieve results once finalized.
- **Q: How are services identified in F02?**  
  → **A**: Deterministic service identification. A specialized `ServiceDetector` identifies service components using explicit static evidence: classes subclassing recognized service base classes, classes or modules with `*Service` naming conventions containing public business methods, or classes decorated with explicit service markers.
- **Q: How is the analyzed revision identified to guarantee reproducibility?**  
  → **A**: Immutable resolved revision SHA. Every `AnalysisRun` resolves and records `resolved_revision` (the exact 40-character Git commit SHA analyzed), ensuring that analysis runs are strictly reproducible per TRACE Constitution §XII.
- **Q: How are source roots and package namespaces resolved?**  
  → **A**: Automated source-root detection. The scanner identifies whether the repository uses a root layout or a `src/` layout (via `pyproject.toml` package declarations or the presence of a top-level `src/` directory). Module qualified names are generated relative to the detected source root. Directories containing Python files without `__init__.py` are recognized as PEP 420 namespace packages (`is_package = True`).
- **Q: How are binary, large, symlink, and generated files handled?**  
  → **A**: Safe file classification. Binary files (null bytes or binary extensions) are marked `FileKind.OTHER` and skipped from Python parsing. Large files (> 1MB) are marked `FileStatus.SKIPPED` with an informational diagnostic. Symlinks are resolved safely without escaping repository boundaries. Generated files (e.g., protobuf, migrations, or files containing `@generated` markers) are tagged with `is_generated: bool`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic Repository Code Analysis (Priority: P1)

A developer or engineering lead wants to analyze a registered Python repository to gain a complete, structured understanding of its internal architecture. They trigger an analysis run for a connected repository. TRACE traverses the codebase, ignores non-source and build artifacts, parses all Python files using standard AST analysis, and extracts modules, classes, methods, functions, decorators, docstrings, and imports into a unified software intelligence model.

**Why this priority**: Without deterministic extraction of core software entities, TRACE cannot understand codebase structure, and downstream dependency graphs (F03) or change analyzers (F04) have no source evidence on which to operate.

**Independent Test**: Can be fully tested using a local Python fixture repository. The test triggers analysis, verifies that all valid Python files are parsed into modules, confirms that classes, functions, methods, decorators, and imports are accurately cataloged with correct line numbers and qualified names, and checks that no external network calls or LLM invocations occur.

**Acceptance Scenarios**:

1. **Given** a connected repository containing Python source files, **When** a user triggers an analysis run, **Then** the system scans the repository, identifies all Python source files while skipping excluded paths (such as `.git`, virtual environments, and caches), and extracts modules, classes, functions, and imports into a structured analysis result.
2. **Given** a Python module defining a class with inheritance, instance methods, and decorators, **When** the analyzer processes the module, **Then** the system identifies the class, its parent classes (`EXTENDS`), each defined method with parameter signatures, applied decorators, line ranges, and qualified symbol paths.
3. **Given** a Python module containing standalone functions and module-level variables, **When** the analyzer processes the module, **Then** the system captures each function name, line range, docstring, and decorator.
4. **Given** import statements (`import foo`, `from bar import baz as alias`), **When** the analyzer processes the file, **Then** the system records each import statement with original name, imported symbol, alias, line number, and whether it represents an internal relative import or external package.
5. **Given** a repository with documentation files (`README.md`, docstrings), **When** the analyzer processes the repository, **Then** the system extracts docstrings associated with classes and functions and identifies documentation references.
6. **Given** an analysis execution, **When** the run completes, **Then** the system updates the repository's `last_analysis_run_id` and records the total count of discovered files, modules, classes, and functions.

---

### User Story 2 - Relationship & Reference Extraction (Priority: P2)

A developer or downstream analysis service wants to understand how components in a Python codebase interact with each other and with external resources. The analyzer evaluates the parsed ASTs to identify structural relationships including statically resolvable function/method calls, package dependencies, web API endpoints, database operations, configuration accesses, and test associations.

**Why this priority**: TRACE's primary mission is change impact analysis. Identifying relationships (`IMPORTS`, `CALLS`, `EXPOSES`, `READS`, `WRITES`, `TESTED_BY`) is essential for mapping how a modification to one component propagates to others.

**Independent Test**: Can be tested against a fixture repository containing cross-module function calls, FastAPI/Flask route decorators, SQLAlchemy or database queries, configuration file lookups, and `pytest` test functions. The test verifies that each relationship is created with explicit source and target coordinates.

**Acceptance Scenarios**:

1. **Given** a function in module A that calls a function in module B, **When** the analyzer processes the call site, **Then** the system creates a `CALLS` relationship linking the caller to the resolvable callee symbol.
2. **Given** a function decorated with a web framework route decorator (e.g., `@app.get("/items")` or `@router.post("/submit")`), **When** the analyzer processes the function, **Then** the system identifies an `APIEndpoint` entity and creates an `EXPOSES` relationship linking the function to the HTTP method and route path.
3. **Given** source code referencing environment variables or configuration objects (e.g., `os.environ`, `settings.DATABASE_URL`), **When** the analyzer evaluates the AST, **Then** the system creates a `CONFIGURED_BY` relationship linking the component to the detected configuration key.
4. **Given** source code performing database operations (e.g., ORM models, session queries, SQL executions), **When** the analyzer evaluates the AST, **Then** the system creates `READS` or `WRITES` relationships linked to the identified database entity or table.
5. **Given** test files (e.g., `tests/test_service.py` with test functions testing `service.py`), **When** the analyzer processes the test suite, **Then** the system identifies `TestReference` entities and associates them via `TESTED_BY` relationships based on explicit imports and naming conventions.
6. **Given** dependency configuration files (e.g., `pyproject.toml`, `requirements.txt`), **When** the analyzer scans repository metadata, **Then** the system extracts `ExternalDependency` entities with package names and version constraints, establishing `DEPENDS_ON` relationships.
7. **Given** a call site with dynamic resolution that cannot be determined statically, **When** the analyzer processes the site, **Then** the system does not fabricate a speculative relationship edge and records the call as unresolvable.

---

### User Story 3 - Observable Analysis Lifecycle & Fault-Tolerant Diagnostics (Priority: P3)

A developer or CI system initiates an analysis run on a repository that may contain syntax errors, unsupported language features, or unreadable files. The system accepts the request asynchronously (HTTP 202 Accepted), exposes observable status transitions (`PENDING` → `IN_PROGRESS` → `COMPLETED` / `FAILED`), and collects structured diagnostics without crashing or discarding valid findings from other files.

**Why this priority**: Real-world repositories frequently contain legacy files, syntax experiments, or transient errors. The analyzer must be robust and auditable so operators know exactly what succeeded and what diagnostics were raised.

**Independent Test**: Can be tested by running an analysis against a repository fixture containing one valid Python file and one file with intentional syntax errors. The test verifies that the valid file is fully analyzed, the invalid file yields a diagnostic error record, the analysis completes with status `COMPLETED` (or partial warning status), and the diagnostic details are accessible via API.

**Acceptance Scenarios**:

1. **Given** a request to analyze a repository via `POST /api/v1/repositories/{id}/analyze`, **When** the request is accepted, **Then** the system creates an `AnalysisRun` record with status `PENDING`, assigns a unique identifier, dispatches the analysis task asynchronously via background tasks, and returns HTTP 202 Accepted with the pending run envelope.
2. **Given** an in-progress analysis, **When** a user queries `GET /api/v1/analyses/{analysis_run_id}`, **Then** the system returns the run's current status, elapsed time, repository reference, and progress indicators.
3. **Given** a repository file with invalid Python syntax, **When** the analyzer encounters the file, **Then** the system logs a structured diagnostic with line number and syntax error message, marks that file's status as `ERROR`, and continues analyzing the remaining files.
4. **Given** a repository with non-Python files and binary assets, **When** the analyzer scans the tree, **Then** non-Python files are cataloged under general file inventory without triggering Python AST errors.
5. **Given** an analysis run that finishes with one or more file diagnostics, **When** the run completes, **Then** the status transitions to `COMPLETED`, the diagnostic count is recorded, and the detailed diagnostics are accessible via `GET /api/v1/analyses/{analysis_run_id}/diagnostics`.
6. **Given** a repository identifier that does not exist or belongs to an archived project, **When** an analysis is requested, **Then** the system returns an appropriate HTTP 404 or HTTP 409 error without creating an analysis run.

---

### User Story 4 - Multi-Language Analyzer Abstraction (Priority: P4)

A software architect wants TRACE to have a clean, decoupled architecture so that additional programming languages (e.g., TypeScript, Go, Java) can be plugged in during future phases without altering the core analysis domain models, API contracts, or repository orchestration logic.

**Why this priority**: Clean architecture and replaceability are constitutional requirements (TRACE Constitution §XIV). Language-specific AST mechanics must be strictly separated from core software intelligence domain entities.

**Independent Test**: Can be tested by verifying that `PythonCodeAnalyzer` implements the generic `CodeAnalyzer` interface/protocol, and that mocking or substituting the analyzer interface in service tests produces valid `RepositoryAnalysis` results without changing service or API code.

**Acceptance Scenarios**:

1. **Given** the `CodeAnalyzer` protocol definition, **When** inspecting its contract, **Then** it accepts a repository context (path, metadata, configuration) and returns a typed `RepositoryAnalysis` domain object without exposing raw AST nodes or interpreter internals.
2. **Given** `PythonCodeAnalyzer`, **When** executed, **Then** all standard library AST parsing and visitor logic remains private to the analyzer package, returning strictly domain entities (`AnalyzedFile`, `Module`, `Class`, `Function`, `Import`, `Call`).
3. **Given** an unsupported language file extension in a repository, **When** the Python analyzer processes the file inventory, **Then** the file is categorized as a generic file and safely ignored by the Python parser without raising exceptions.

---

### Edge Cases

- **Circular Imports**: When two or more modules import each other (e.g., `a.py` imports `b.py` and `b.py` imports `a.py`), the static analyzer must not enter an infinite loop or recurse endlessly. Each file is parsed independently, and relationship linking operates on symbol references.
- **Duplicate Symbol Names Across Modules**: When multiple modules define classes or functions with identical names (e.g., `models.User` and `schemas.User`), all entities must be fully qualified by their module path (`pkg.models.User` vs. `pkg.schemas.User`) to prevent collisions.
- **Deeply Nested Packages and Namespaces**: Packages without `__init__.py` (PEP 420 namespace packages) or packages nested 5+ directories deep must resolve their module dot-paths accurately relative to the repository root or detected source root.
- **Complex Dynamic Decorators**: Decorators with arguments, chained decorators (`@app.get()`, `@auth_required(role='admin')`), or custom wrapper factories must be captured with their full decorator expression and arguments string.
- **Star Imports (`from module import *`)**: When star imports are encountered, the analyzer records the star import relationship and logs an informational diagnostic indicating that individual imported symbol resolution is non-explicit.
- **Empty Repositories or Repositories with Zero Python Files**: If a repository contains no Python source files, the analyzer completes successfully with zero Python modules, zero errors, and an explicit informational diagnostic.
- **Files with Non-UTF-8 Encoding**: Files containing invalid byte sequences or non-UTF-8 encodings must be decoded using fallback encodings (e.g., `utf-8` with error replacement, or Latin-1) or flagged with an encoding diagnostic rather than crashing the process.
- **Monorepos with Nested Projects / Multiple `pyproject.toml` Files**: If multiple dependency files exist in subdirectories, external dependencies must be captured with their respective file locations.
- **Ignored Directories**: Directories such as `.git`, `.venv`, `venv`, `node_modules`, `dist`, `build`, `__pycache__`, and `.pytest_cache` must be strictly pruned during filesystem traversal to prevent wasted processing and phantom entities.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Core Analyzer Abstraction & File Discovery
- **FR-001**: The system MUST define a generic `CodeAnalyzer` protocol in the domain layer that accepts a repository analysis context and returns a strongly typed `RepositoryAnalysis` aggregate.
- **FR-002**: The system MUST provide a `PythonCodeAnalyzer` implementation that implements `CodeAnalyzer` and operates strictly via deterministic static analysis without external LLM invocations.
- **FR-003**: The analyzer MUST discover and inventory all files within the repository working tree, capturing relative path, file extension, byte size, and whether the file is identified as Python source, test, configuration, documentation, or generic asset.
- **FR-003a**: The analyzer MUST enforce deterministic file-safety and categorization rules:
  - **Large Files**: Files exceeding 1MB in size MUST be marked with `status: SKIPPED` and emit an informational diagnostic to prevent memory exhaustion during parsing.
  - **Binary Files**: Files containing null bytes (`\x00`) or matching binary extensions (.pyc, .so, .dll, images, archives) MUST be categorized as `FileKind.OTHER` and excluded from AST parsing.
  - **Symlinks**: Symlinks MUST be resolved safely; symlinks pointing outside the repository root boundary or forming cyclic links MUST be skipped with a warning diagnostic.
  - **Generated Files**: Source files containing explicit generation headers (e.g., `# @generated`, `# Generated by`, protobuf `*_pb2.py`) MUST be tagged with `is_generated: true` while remaining eligible for structural extraction.
- **FR-004**: The analyzer MUST enforce configurable directory exclusions by default, strictly skipping:
  - Version control directories: `.git`, `.svn`, `.hg`
  - Virtual environments: `.venv`, `venv`, `env`, `.virtualenv`, `virtualenv`
  - Cache directories: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
  - Build/distribution directories: `build`, `dist`, `*.egg-info`, `wheels`
  - Package manager directories: `node_modules`
  - Hidden tool directories: `.idea`, `.vscode`, `.tox`
- **FR-005**: The analyzer MUST support custom exclusion patterns provided via analysis configuration.
- **FR-006**: The analyzer MUST calculate basic repository metadata including total file count, total line count, Python file count, test file count, and detected primary framework(s).

#### Python Structural Entity Extraction
- **FR-007**: The analyzer MUST parse Python source files into standard library Abstract Syntax Trees (`ast` module) and extract code entities without executing repository code.
- **FR-008**: The analyzer MUST detect the repository source root (`src/` layout or repository root based on `pyproject.toml` package declarations or top-level layout) and identify Python **Modules** and **Packages**:
  - Captured attributes include dot-separated qualified names relative to the source root (e.g., `trace.domain.repository`), relative file paths, docstrings, and package indicators.
  - Standard packages are identified by the presence of `__init__.py` (`is_package: true`).
  - Directories containing Python files without `__init__.py` within the source root tree MUST be recognized and cataloged as PEP 420 namespace packages (`is_package: true`).
- **FR-009**: The analyzer MUST identify all **Classes**, capturing:
  - Class name
  - Fully qualified class name
  - Base/parent class expressions (`EXTENDS` candidates)
  - Applied decorators
  - Docstring (if present)
  - Source location (start line, end line, column offset)
  - Parent module or enclosing class
- **FR-010**: The analyzer MUST identify all **Functions** and **Methods**, capturing:
  - Function/method name
  - Fully qualified name
  - Parent entity (module or class)
  - Parameter list (parameter names, default value indicators, type annotation strings where present)
  - Return type annotation string (where present)
  - Applied decorators
  - Docstring (if present)
  - Source location (start line, end line, column offset)
  - Function kind (`FUNCTION`, `METHOD`, `CLASS_METHOD`, `STATIC_METHOD`, `ASYNC_FUNCTION`, `ASYNC_METHOD`)
- **FR-010a**: The analyzer MUST deterministically identify **Services** (`Service` entities), capturing:
  - Service name and fully qualified identifier
  - Supporting evidence: classes subclassing recognized service base classes, classes or modules matching `*Service` naming conventions containing public domain operations, or classes decorated with explicit service markers
  - Source location coordinates

#### Import & Call Extraction
- **FR-011**: The analyzer MUST identify all **Import** statements, capturing:
  - Import type (`IMPORT` or `IMPORT_FROM`)
  - Source module string
  - Imported symbol name
  - Assigned alias (if any)
  - Relative import level (0 for absolute, 1+ for relative dots)
  - Source line number
  - Target classification (`INTERNAL` to repository vs. `EXTERNAL` third-party / standard library)
- **FR-012**: The analyzer MUST extract statically resolvable **Function Calls** with strict resolution boundaries:
  - Caller qualified name (enclosing function or method)
  - Callee expression as written in source
  - Resolved target qualified name (for direct function calls in local/module scope, `self.method()` within the same class hierarchy, or imported symbols with resolvable origins)
  - Source line number
  - Resolution status (`RESOLVED_INTERNAL`, `RESOLVED_EXTERNAL`, `UNRESOLVED_DYNAMIC`)
  - The system MUST mark dynamic invocations (e.g., `getattr()`, polymorphic variable receivers, runtime metaprogramming) as `UNRESOLVED_DYNAMIC` and MUST NOT create speculative `CALLS` edges without deterministic proof.

#### Semantic Patterns & Reference Extraction
- **FR-013**: The analyzer MUST identify **API Endpoints** for common web framework patterns (at minimum: FastAPI, Flask, and Starlette routing decorators such as `@app.get`, `@router.post`, `@app.route`), capturing:
  - HTTP method(s) (GET, POST, PUT, DELETE, PATCH, etc.)
  - URL path / route pattern
  - Handler function qualified name
  - Source location
- **FR-014**: The analyzer MUST identify **Configuration References**, capturing:
  - Configuration key / environment variable name (from `os.environ[...]`, `os.getenv(...)`, Pydantic `BaseSettings` / `SettingsConfigDict` field definitions, and attribute accesses on settings instances like `settings.KEY`)
  - Referencing function or module
  - Access kind (`READ` or `WRITE`)
  - Source location
- **FR-015**: The analyzer MUST identify **Database References** with explicit operation evidence, capturing:
  - `MODEL_DECLARATION`: Declarative ORM model classes (inheriting from `Base`, `DeclarativeBase`, or defining `__tablename__`)
  - `READS`: Database query operations (e.g. `session.execute(select(...))`, `session.query(...)`, `.filter()`, `.all()`, `.first()`)
  - `WRITES`: Database mutation operations (e.g. `session.add(...)`, `session.delete(...)`, `session.flush()`, `session.commit()`, `insert(...)`, `update(...)`, `delete(...)`)
  - Target entity or table name and referencing symbol
  - Source location
- **FR-016**: The analyzer MUST identify **Test References**, classifying files matching test patterns (e.g., `test_*.py`, `*_test.py`, `tests/` directory) and capturing:
  - Test functions, test methods, and test classes
  - Target component under test (inferred from imports and naming conventions)
  - Test framework indicator (e.g., `pytest`, `unittest`)
  - Source location
- **FR-017**: The analyzer MUST extract **External Dependencies** from repository manifests (supporting at minimum `pyproject.toml`, `requirements.txt`, `setup.cfg`, `setup.py`), capturing:
  - Package name
  - Version specification / constraint string (if specified)
  - Manifest file path
- **FR-018**: The analyzer MUST identify **Documentation References**, capturing top-level `README.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/*.md` files, and module/class/function docstrings.

#### Deterministic Relationship Synthesis
- **FR-019**: The analyzer MUST synthesize explicit `AnalysisRelationship` records supported by deterministic repository evidence, covering:
  - `IMPORTS`: Source module/file imports target module/symbol
  - `CALLS`: Source function/method invokes target function/method
  - `EXTENDS`: Child class inherits from parent class
  - `DEPENDS_ON`: Module or package depends on internal module or external dependency
  - `EXPOSES`: Handler function exposes an API endpoint
  - `READS`: Function/module reads configuration or database entity
  - `WRITES`: Function/module writes configuration or database entity
  - `TESTED_BY`: Code component is tested by a test function or test module
  - `DOCUMENTED_BY`: Code component is documented by a docstring or documentation file
  - `CONFIGURED_BY`: Code component is configured by a configuration key or settings object
- **FR-020**: The system MUST NOT synthesize or invent speculative relationship edges when evidence is inconclusive or dynamic, strictly adhering to TRACE Constitution §I (Evidence over Hallucination).

#### Diagnostics & Fault Tolerance
- **FR-021**: The analyzer MUST catch syntax errors, decoding failures, and unexpected AST visitor exceptions on a per-file basis, creating an `AnalysisDiagnostic` and continuing the analysis of remaining files.
- **FR-022**: An `AnalysisDiagnostic` MUST record:
  - File path
  - Line number and column offset (where applicable)
  - Diagnostic severity (`ERROR`, `WARNING`, `INFO`)
  - Diagnostic code (e.g., `SYNTAX_ERROR`, `ENCODING_ERROR`, `UNRESOLVED_IMPORT`, `DYNAMIC_CALL`)
  - Human-readable message
- **FR-023**: An analysis run containing one or more file errors MUST complete with status `COMPLETED` and record the diagnostic count, provided at least one file was successfully processed. If zero files can be processed due to fatal repository corruption, the run MUST complete with status `FAILED`.

#### API Endpoints & Run Management
- **FR-024**: The system MUST expose the following RESTful API endpoints under `/api/v1`:
  - `POST /api/v1/repositories/{repository_id}/analyze`: Trigger an analysis run asynchronously for a registered repository (accepts optional branch or commit reference and custom exclusion rules), dispatching via an `AnalysisExecutor` abstraction (with default in-process background task execution) and returning HTTP 202 Accepted with the pending `AnalysisRun` record.
  - `GET /api/v1/repositories/{repository_id}/analyses`: List all analysis runs for a given repository with pagination and status filtering.
  - `GET /api/v1/analyses/{analysis_run_id}`: Retrieve metadata, status, summary counts, and execution duration for an analysis run.
  - `GET /api/v1/analyses/{analysis_run_id}/summary`: Retrieve high-level metrics (file counts, symbol counts, relationship counts, diagnostic counts).
  - `GET /api/v1/analyses/{analysis_run_id}/entities`: Retrieve discovered code entities (modules, classes, functions, services, endpoints, etc.) with pagination and type filtering.
  - `GET /api/v1/analyses/{analysis_run_id}/relationships`: Retrieve discovered structural relationships with pagination and relationship type filtering.
  - `GET /api/v1/analyses/{analysis_run_id}/diagnostics`: Retrieve diagnostic records and warnings generated during analysis.
- **FR-025**: The system MUST persist `AnalysisRun` records in PostgreSQL via the `DatabaseGateway`. `analysis_runs.repository_id` is the authoritative relational foreign key link.
- **FR-026**: Upon completion of an analysis run, the system MUST update `repositories.last_analysis_run_id` as an optional denormalized convenience reference (accelerating repository status lookups and preventing deletion of analyzed repositories), while `analysis_runs.repository_id` remains the authoritative relational reference.
- **FR-027**: The system MUST persist the complete, detailed `RepositoryAnalysis` domain intelligence artifact as a versioned JSON artifact on disk within the TRACE storage directory.

---

### Non-Functional Requirements

#### Persistence & Database Contracts
- **NFR-001**: PostgreSQL MUST be the authoritative source of application state for `AnalysisRun` lifecycle records and summary metrics.
- **NFR-002**: Database schema changes for `analysis_runs` MUST be implemented exclusively via Alembic migration scripts. Direct SQL mutations outside migrations are prohibited.
- **NFR-003**: F02 MUST NOT execute any write operations, create node labels, or establish relationship edges in Neo4j. F03 will own all Neo4j graph operations.
- **NFR-004**: Architecture MUST adhere to the 5-layer onion architecture established in Phase 0: domain entities must contain zero framework, database, or I/O imports; the analyzer implementation must reside in domain/services/infrastructure layers with strict protocol interfaces.

#### Determinism & Offline Operation
- **NFR-005**: All F02 static analysis MUST execute deterministically and offline without requiring external network connectivity or LLM provider API access.
- **NFR-006**: Given the identical repository commit and exclusion configuration, repeated analysis runs MUST yield identical entity and relationship outputs (TRACE Constitution §XII: Reproducibility).

#### Observability & Structured Logging
- **NFR-007**: Every analysis run MUST emit structured log events using `structlog` containing `run_id`, `repository_id`, `project_id`, `status`, and `duration_ms`.
- **NFR-008**: Analysis warnings and file diagnostics MUST be logged at `WARNING` level with sanitized file paths and no sensitive environment data.

#### Deterministic Testability & Fixtures
- **NFR-009**: All F02 unit and service tests MUST execute deterministically using temporary local repository fixtures without network calls.
- **NFR-010**: The test suite MUST provide deterministic repository fixtures covering:
  - Standard multi-module Python repository with classes, inheritance, decorators, functions, calls, and imports
  - Web API endpoint patterns (e.g., FastAPI)
  - Configuration usage (`os.environ`, settings)
  - Database usage (SQLAlchemy model and session queries)
  - Tests (`pytest` test file and functions)
  - Manifests (`pyproject.toml`, `requirements.txt`)
  - Intentional syntax errors
  - Empty repository
  - Ignored directories (`.git`, `venv`, `__pycache__`)
  - Duplicate symbol names in distinct modules
- **NFR-011**: The test suite MUST achieve minimum 80% line and branch test coverage across all new F02 modules.

---

### Key Entities

```
┌────────────────────────────────────────────────────────┐
│                      AnalysisRun                       │
├────────────────────────────────────────────────────────┤
│ id: UUIDv4 [PK]                                        │
│ repository_id: UUIDv4 [FK -> Repository.id, Indexed]   │
│ project_id: UUIDv4 [FK -> Project.id, Indexed]         │
│ status: AnalysisStatus (PENDING|IN_PROGRESS|COMPLETED| │
│                         FAILED)                        │
│ target_ref: String(100) [Nullable]                     │
│ resolved_revision: String(40) [Nullable] (exact commit)│
│ commit_hash: String(40) [Nullable]                     │
│ started_at: DateTime [Nullable]                        │
│ completed_at: DateTime [Nullable]                      │
│ duration_ms: Float [Nullable]                          │
│ total_files: Integer                                   │
│ python_files: Integer                                  │
│ total_modules: Integer                                 │
│ total_classes: Integer                                 │
│ total_functions: Integer                               │
│ total_relationships: Integer                           │
│ total_diagnostics: Integer                             │
│ error_message: Text [Nullable]                         │
│ artifact_path: String(500) [Nullable]                  │
│ created_at: DateTime (UTC)                             │
│ updated_at: DateTime (UTC)                             │
└────────────────────────────────────────────────────────┘
```

#### Domain Models (Pure Python Dataclasses / Pydantic)

- **`RepositoryAnalysis`**: Root aggregate containing complete code intelligence:
  - `run_id`: UUIDv4
  - `repository_id`: UUIDv4
  - `analyzed_at`: ISO 8601 DateTime
  - `resolved_revision`: Optional string (exact 40-char commit SHA)
  - `commit_hash`: Optional string
  - `files`: List of `AnalyzedFile`
  - `modules`: List of `Module`
  - `classes`: List of `Class`
  - `functions`: List of `Function`
  - `services`: List of `Service`
  - `imports`: List of `Import`
  - `calls`: List of `Call`
  - `endpoints`: List of `APIEndpoint`
  - `configurations`: List of `ConfigurationReference`
  - `database_references`: List of `DatabaseReference`
  - `tests`: List of `TestReference`
  - `documentation`: List of `DocumentationReference`
  - `dependencies`: List of `ExternalDependency`
  - `relationships`: List of `AnalysisRelationship`
  - `diagnostics`: List of `AnalysisDiagnostic`
  - `summary`: Analysis summary metrics value object

- **`SourceLocation`**: Value object identifying precise code coordinates:
  - `file_path`: Relative POSIX path
  - `start_line`: Integer (1-indexed)
  - `end_line`: Integer (1-indexed)
  - `start_column`: Optional integer
  - `end_column`: Optional integer

- **`AnalyzedFile`**: Represents any file discovered in the repository:
  - `path`: Relative POSIX path
  - `file_type`: Enum (`PYTHON`, `TEST`, `CONFIG`, `DOCUMENTATION`, `DEPENDENCY`, `OTHER`)
  - `size_bytes`: Integer
  - `status`: Enum (`PARSED`, `SKIPPED`, `ERROR`)

- **`Module`**: Represents a Python module or package:
  - `qualified_name`: String (e.g., `trace.services.repository`)
  - `file_path`: Relative POSIX path
  - `is_package`: Boolean (`__init__.py`)
  - `docstring`: Optional string
  - `location`: `SourceLocation`

- **`Class`**: Represents a Python class:
  - `name`: String
  - `qualified_name`: String (e.g., `trace.domain.repository.Repository`)
  - `module_name`: String
  - `parent_classes`: List of base class name expressions
  - `decorators`: List of decorator expressions
  - `docstring`: Optional string
  - `location`: `SourceLocation`

- **`Function`**: Represents a Python function or method:
  - `name`: String
  - `qualified_name`: String (e.g., `trace.services.repository.RepositoryService.register_repository`)
  - `module_name`: String
  - `enclosing_class`: Optional string
  - `kind`: Enum (`FUNCTION`, `METHOD`, `CLASS_METHOD`, `STATIC_METHOD`, `ASYNC_FUNCTION`, `ASYNC_METHOD`)
  - `parameters`: List of parameter descriptors (name, type annotation, has default)
  - `return_type`: Optional string
  - `decorators`: List of decorator expressions
  - `docstring`: Optional string
  - `location`: `SourceLocation`

- **`Service`**: Represents a business or domain service component:
  - `name`: String
  - `qualified_name`: String (e.g., `trace.services.repository.RepositoryService`)
  - `module_name`: String
  - `service_kind`: Enum (`CLASS_SERVICE`, `FUNCTIONAL_SERVICE`)
  - `methods`: List of service method names
  - `location`: `SourceLocation`

- **`Import`**: Represents an import statement:
  - `source_module`: String
  - `imported_symbol`: String
  - `alias`: Optional string
  - `import_type`: Enum (`IMPORT`, `IMPORT_FROM`)
  - `is_relative`: Boolean
  - `is_external`: Boolean
  - `location`: `SourceLocation`

- **`Call`**: Represents a function/method call site:
  - `caller_qualified_name`: String
  - `callee_expression`: String
  - `resolved_target`: Optional string (fully qualified target if resolved)
  - `resolution_status`: Enum (`RESOLVED_INTERNAL`, `RESOLVED_EXTERNAL`, `UNRESOLVED_DYNAMIC`)
  - `location`: `SourceLocation`

- **`APIEndpoint`**: Represents an exposed HTTP endpoint:
  - `http_method`: String (GET, POST, etc.)
  - `path`: String (e.g., `/api/v1/projects`)
  - `handler_qualified_name`: String
  - `framework`: String (e.g., `FastAPI`)
  - `location`: `SourceLocation`

- **`ConfigurationReference`**: Represents a configuration/environment usage:
  - `key_name`: String (e.g., `DATABASE_URL`)
  - `access_kind`: Enum (`READ`, `WRITE`)
  - `location`: `SourceLocation`

- **`DatabaseReference`**: Represents a database model or query interaction:
  - `target_entity`: String (model or table name)
  - `operation`: String (e.g., `MODEL_DECLARATION`, `QUERY`, `EXECUTE`)
  - `location`: `SourceLocation`

- **`TestReference`**: Represents a test component:
  - `test_name`: String
  - `target_symbol`: Optional string (inferred target of test)
  - `framework`: String (`pytest`, `unittest`)
  - `location`: `SourceLocation`

- **`ExternalDependency`**: Represents a package dependency declared in manifests:
  - `package_name`: String
  - `version_spec`: Optional string
  - `manifest_path`: String

- **`AnalysisRelationship`**: Directed structural relationship between entities:
  - `source_type`: String (e.g., `MODULE`, `CLASS`, `FUNCTION`, `FILE`)
  - `source_identifier`: String (qualified name or path)
  - `relationship_type`: Enum (`IMPORTS`, `CALLS`, `EXTENDS`, `DEPENDS_ON`, `EXPOSES`, `READS`, `WRITES`, `TESTED_BY`, `DOCUMENTED_BY`, `CONFIGURED_BY`)
  - `target_type`: String
  - `target_identifier`: String
  - `evidence_location`: `SourceLocation`

- **`AnalysisDiagnostic`**: Error or warning record during analysis:
  - `file_path`: Relative POSIX path
  - `severity`: Enum (`ERROR`, `WARNING`, `INFO`)
  - `code`: String
  - `message`: String
  - `line`: Optional integer
  - `column`: Optional integer

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The analyzer successfully discovers and parses 100% of syntactically valid Python files in a registered repository, producing structured module, class, and function representations.
- **SC-002**: A standard Python repository fixture containing up to 100 files completes static analysis in under 5.0 seconds under local execution.
- **SC-003**: 100% of discovered entities include valid source location coordinates (file path, start line, end line) matching actual source file positions.
- **SC-004**: 100% of relationships created by the analyzer are supported by inspectable source code evidence (import statements, AST call nodes, class base tuples, routing decorators); zero synthetic or hallucinated relationships are generated.
- **SC-005**: In the presence of syntax errors or unreadable files, 100% of valid remaining files in the repository are analyzed, and the faulty files produce structured `AnalysisDiagnostic` records with exact file paths and error messages.
- **SC-006**: 0 calls to external LLM providers (e.g., OpenRouter, OpenAI, Anthropic) and 0 mutations to Neo4j are executed during F02 repository analysis.
- **SC-007**: Analysis initiation requests return HTTP 202 Accepted and produce an identifiable `AnalysisRun` record in PostgreSQL queryable via `GET /api/v1/analyses/{id}`, with observable lifecycle status transitions (`PENDING` → `IN_PROGRESS` → `COMPLETED`/`FAILED`), and `last_analysis_run_id` updated on the repository upon completion.
- **SC-008**: 100% of unit and integration tests for F02 pass deterministically with zero external network access, and the existing Phase 0 and F01 test suites continue to pass with 0 regressions.

---

## Assumptions

- **Python-First Scope**: F02 specifically implements analysis for Python repositories. Multi-language parsing (TypeScript, Go, etc.) will follow the established `CodeAnalyzer` interface in later phases.
- **Python Version Compatibility**: The analyzer uses standard library `ast` capable of parsing Python 3.10 through Python 3.14 syntax constructs.
- **Local Working Trees**: For `LOCAL` repositories registered in F01, the files exist on the host filesystem and are readable by the TRACE backend process. For `REMOTE` repositories, the Git provider acquires a local working tree in a cache workspace prior to analysis.
- **F03 Graph Handoff**: F02 outputs the complete `RepositoryAnalysis` domain intelligence model and persists it to structured storage; converting this data into Neo4j nodes and Cypher edges is the responsibility of Phase 3A (F03).
- **No LLM Requirement**: F02 operates entirely via static analysis and deterministic parsing; LLM-based semantic reasoning or code summarization is out of scope for this phase.
