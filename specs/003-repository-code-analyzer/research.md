# Research & Technical Decisions: TRACE Phase 2 — F02: Repository / Code Analyzer

**Feature Branch**: `003-repository-code-analyzer`  
**Date**: 2026-09-29  
**Status**: Completed  
**Spec Reference**: [spec.md](./spec.md)

---

## 1. Static Analysis Engine & AST Extraction

### Decision
Use Python's standard library `ast` module (supplemented by `tokenize` for comment/encoding handling) as the core parser for `PythonCodeAnalyzer`.

### Rationale
- **Zero External Dependencies**: The standard library `ast` is maintained directly by the Python core team and supports all syntax features of the host interpreter (Python 3.12+).
- **Security & Safety**: `ast.parse()` inspects source code purely as text tokens and grammar structures without executing any module-level code, avoiding arbitrary code execution vulnerabilities during repository analysis.
- **Speed & Predictability**: In-process AST parsing takes less than 1–2 milliseconds per average Python file, easily satisfying the requirement to analyze a 100-file repository in under 5.0 seconds.
- **Non-abortive error handling**: `ast.parse` raises standard exceptions (`SyntaxError`, `IndentationError`, `UnicodeDecodeError`) with exact line numbers and column offsets, making per-file diagnostic capture straightforward.

### Alternatives Considered
- **Tree-sitter**: Provides fast incremental multi-language parsing and error recovery. However, it requires compiled C/Rust bindings and separate grammar packages (`tree-sitter-python`). Deferred to future phases when non-Python languages are introduced.
- **LibCST**: Excellent for concrete syntax tree modification and refactoring, but significantly slower and higher memory overhead than standard `ast` for read-only analysis.
- **Bytecode Inspection (`dis` module) / Runtime `inspect`**: Requires importing/compiling Python code, which violates security boundaries by executing unvetted third-party repository code during analysis.

---

## 2. Repository Scanning & Exclusion Filtering

### Decision
Implement a deterministic filesystem scanner using Python's `pathlib.Path` that prunes ignored directory subtrees at directory traversal time before examining individual files.

### Rationale
- **Performance**: Pruning `.git`, `.venv`, and `node_modules` at the directory boundary prevents `os.walk` or `Path.rglob` from descending into tens of thousands of irrelevant files, reducing directory discovery time from seconds to milliseconds.
- **Determinism**: Sorting directory entries alphabetically ensures that file discovery order and analysis run output are 100% reproducible across different OS platforms.
- **Standard Default Exclusions**: Hardcoded defaults match standard Python and web projects:
  - Version control: `.git`, `.svn`, `.hg`
  - Virtual environments: `.venv`, `venv`, `env`, `.virtualenv`
  - Cache: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
  - Build & Distribution: `build`, `dist`, `*.egg-info`, `wheels`
  - Dependencies & IDEs: `node_modules`, `.idea`, `.vscode`, `.tox`
- **Configurability**: Accepts optional `exclude_patterns: list[str]` in the analysis request payload for custom project layouts.

### Alternatives Considered
- **Invoking `git ls-files`**: Fast, but fails on repositories where changes are uncommitted or where the repository is an uninitialized local folder.
- **Using `pathlib.Path.rglob("*")`**: Evaluates every path in the entire tree without early pruning, resulting in severe performance degradation when scanning repositories with large virtual environments.

---

## 3. Static Call Resolution & Handling of Ambiguity

### Decision
Construct a per-module symbol table tracking locally defined classes/functions and imported aliases. Statically resolvable calls are mapped to fully qualified target names with status `RESOLVED_INTERNAL` or `RESOLVED_EXTERNAL`. Calls with ambiguous receivers, dynamic attribute lookups (`getattr`), or runtime metaprogramming are recorded with status `UNRESOLVED_DYNAMIC`, and **zero** speculative `CALLS` edges are created.

### Rationale
- **Constitution Compliance**: TRACE Constitution §I (*Evidence over Hallucination*) and §II (*Deterministic Analysis before Probabilistic Inference*) strictly prohibit inventing structural relationships that cannot be proven by repository evidence.
- **Downstream Safety for F03/F05**: Downstream impact analysis relies on high-precision dependency paths. Fabricating speculative call edges creates false-positive blast radiuses that erode developer trust.
- **Static Symbol Table Mechanics**:
  - `import foo.bar as b`: Maps alias `b` to module `foo.bar`.
  - `from foo.bar import baz`: Maps symbol `baz` to `foo.bar.baz`.
  - Direct local calls (e.g. `helper()`) resolve to `<current_module>.helper`.
  - Method calls within a class (e.g. `self.method()`) resolve to `<current_module>.<CurrentClass>.method`.
  - Polymorphic or chained calls (e.g. `obj.process().run()`) record callee expression `obj.process().run` and mark `UNRESOLVED_DYNAMIC`.

### Alternatives Considered
- **Full Type-Inference Engine (e.g., Pyright / Mypy internals)**: Enormously complex, slow, and fragile in untyped or partially typed legacy repositories.
- **LLM-Based Call Disambiguation**: Violates Constitution §I, §II, and prompt requirement that F02 must not use an LLM for structural discovery.

---

## 4. Pattern Detectors (APIs, Configuration, Databases, Tests, Documentation, Dependencies)

### Decision
Implement isolated static pattern detectors that run as visitor passes over the AST and project manifests:

1. **API Endpoints (`APIDetector`)**:
   - Inspects function decorators matching web routing signatures:
     - FastAPI/Starlette: `@app.<method>`, `@router.<method>` (where `<method>` is `get`, `post`, `put`, `delete`, `patch`, etc.), extracting route path string from the first positional or `path=` keyword argument.
     - Flask: `@app.route(path, methods=[...])` and `@bp.route(...)`.
   - Records `APIEndpoint` entity and creates an `EXPOSES` relationship linking the handler function to the endpoint.

2. **Configuration References (`ConfigDetector`)**:
   - Matches AST nodes accessing configuration sources:
     - `os.environ[...]`, `os.environ.get(...)`, `os.getenv(...)`.
     - Subclasses of Pydantic `BaseSettings` or references to settings instances (e.g., `settings.<KEY>`, `config.<KEY>`).
   - Records `ConfigurationReference` entity and creates `CONFIGURED_BY` and `READS` relationships.

3. **Database References (`DatabaseDetector`)**:
   - Identifies SQLAlchemy Declarative models (classes inheriting from `Base`, `DeclarativeBase`, or possessing `__tablename__`).
   - Identifies database query and execution call sites: `session.execute(...)`, `session.query(...)`, `session.add(...)`, `session.delete(...)`.
   - Records `DatabaseReference` entity and creates `READS` or `WRITES` relationships linked to the target model or table.

4. **Test References (`TestDetector`)**:
   - Classifies files located in `tests/` or matching `test_*.py` / `*_test.py`.
   - Identifies test functions (`test_*`) and test classes (`Test*`).
   - Synthesizes `TESTED_BY` relationships by examining the internal symbols imported and called within each test function.

5. **Documentation References (`DocumentationDetector`)**:
   - Extracts module, class, and function docstrings (`ast.get_docstring`).
   - Catalogs repository documentation files (`README.md`, `CONTRIBUTING.md`, `docs/*.md`) as `DocumentationReference` and links them via `DOCUMENTED_BY`.

6. **External Dependencies (`DependencyDetector`)**:
   - Deterministically parses dependency manifests:
     - `pyproject.toml`: Uses standard library `tomllib` (built into Python 3.11+) to parse `[project.dependencies]`, `[project.optional-dependencies]`, and `[tool.poetry.dependencies]`.
     - `requirements.txt` / `requirements-dev.txt`: Line-by-line regex parsing extracting package names, version specifiers (e.g., `>=2.0.0`), and environment markers.
     - `setup.cfg` / `setup.py`: AST or configparser extraction of `install_requires`.
   - Records `ExternalDependency` and creates `DEPENDS_ON` relationships from modules to external packages.

### Rationale
- Clean separation of concerns: Each detector is an independent visitor/extractor focusing on a single domain pattern.
- High extensibility: Additional framework detectors (e.g., Django, Celery) can be added as isolated modules without modifying core AST parsing.

---

## 5. Persistence Architecture: Dual-Tier Storage

### Decision
Store `AnalysisRun` operational records and summary counts in PostgreSQL, and persist the complete, detailed `RepositoryAnalysis` domain aggregate as an immutable versioned JSON artifact on disk within the TRACE storage directory (`storage/artifacts/analyses/{run_id}.json`).

### Rationale
- **Relational Overhead Avoidance**: A real-world repository produces tens of thousands of AST nodes (parameters, line ranges, docstrings, calls, imports). Mapping every granular AST token to individual relational PostgreSQL tables would require 15+ normalized tables, heavy ORM hydration, and expensive transactions, only for F03 to immediately convert them into Neo4j graph nodes.
- **Relational Observability**: PostgreSQL stores exactly what is needed for relational indexing, run management, and operational queries:
  - Run ID, repository ID, project ID, target commit/branch, lifecycle status (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`), timestamps, elapsed duration, summary counters (total files, python files, modules, classes, functions, relationships, diagnostics), error messages, and `artifact_path`.
  - Seamlessly links to F01's `repositories.last_analysis_run_id`.
- **Fast, Verifiable Handoff to F03 & F04**: The versioned JSON artifact contains the complete typed `RepositoryAnalysis` structure. F03 can ingest the entire graph structure in a single stream, and F04 can inspect prior analysis artifacts without running heavy SQL joins.

### Alternatives Considered
- **All Data in PostgreSQL Tables**: Hundreds of thousands of rows per run, requiring database schema migrations for internal AST representations.
- **All Data in Filesystem (Zero PostgreSQL)**: Violates TRACE Constitution §VIII and §XI by breaking relational integrity, transactional run status updates, and foreign key linkage with `repositories`.
- **Direct Insertion into Neo4j in F02**: Explicitly forbidden by project boundaries (F03 owns Neo4j persistence).

---

## 6. Asynchronous Execution & API Lifecycle

### Decision
Execute repository analysis asynchronously via `FastAPI BackgroundTasks` in-process. `POST /api/v1/repositories/{id}/analyze` creates the `AnalysisRun` record in PostgreSQL with status `PENDING`, dispatches the background task, and returns `HTTP 202 Accepted`. Clients query `GET /api/v1/analyses/{run_id}` to observe status transitions and inspect results.

### Rationale
- **User Decision**: Confirmed in clarification session (Option B).
- **Non-blocking API**: Repository analysis can take 1–10 seconds depending on repository size. Running in a background task prevents blocking the HTTP event loop or triggering reverse-proxy request timeouts.
- **Zero Premature Distributed Infrastructure**: Adheres to Constitution §XIII (Maintainability/YAGNI). Avoids introducing Redis or Celery workers before a concrete production scaling need is demonstrated.

### Alternatives Considered
- **Synchronous HTTP execution**: Blocks the client connection until analysis completes; risks HTTP gateway timeouts on large repositories.
- **Celery / RabbitMQ**: Heavy distributed infrastructure with external daemon processes and brokers, inappropriate for Phase 2 baseline.

---

## 7. Streamlit Evaluation Interface

### Decision
Create a lightweight, read-only Streamlit evaluation dashboard in `frontend/app.py` that interacts with the backend REST API (or directly with the service layer if running locally).

### Rationale
- **User Requirement**: The prompt explicitly requests an evaluation interface in Streamlit to show: repository being analyzed, status, file counts, module counts, class counts, function counts, test counts, dependency counts, detected APIs, discovered symbols, and diagnostics.
- **Decoupled Architecture**: The backend code in `backend/src/trace` contains zero references or dependencies on Streamlit. Streamlit is treated as an external consumer of the FastAPI REST API.

---

## 8. Downstream Integration Contracts: F03 & F04

### Decision
Define explicit domain serialization schemas and contracts:
- **Phase 3A (F03: Dependency Graph)**:
  - F03 receives `RepositoryAnalysis`.
  - F03 maps `Module`, `Class`, `Function`, `APIEndpoint`, `DatabaseReference` entities directly to Neo4j Node labels (`(:Module)`, `(:Class)`, `(:Function)`, `(:Endpoint)`, etc.).
  - F03 maps `AnalysisRelationship` records directly to Neo4j Cypher edges (`[:IMPORTS]`, `[:CALLS]`, `[:EXTENDS]`, `[:EXPOSES]`, `[:READS]`, `[:WRITES]`, `[:TESTED_BY]`, `[:DEPENDS_ON]`).
- **Phase 3B (F04: Version / Change Analyzer)**:
  - F04 takes Git commit diffs (modified file path, deleted line numbers, added line numbers).
  - F04 matches modified line ranges against `SourceLocation` (`file_path`, `start_line`, `end_line`) of F02 symbols to pinpoint exactly which functions, methods, or classes were altered between versions.
