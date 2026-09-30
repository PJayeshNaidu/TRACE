# Contract: CodeAnalyzer Protocol & Service Boundary

**Feature Branch**: `003-repository-code-analyzer`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](../spec.md)

---

## 1. Domain Protocol: `CodeAnalyzer`

The `CodeAnalyzer` protocol defines the interface between TRACE application services and language-specific static analysis engines. It enforces Constitution §XIV (*Replaceability*) and ensures that language-specific parsing engines (e.g., Python AST, future Go or TypeScript parsers) remain isolated from business domain logic.

```python
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from trace.domain.analysis import RepositoryAnalysis


@dataclass(frozen=True)
class AnalysisContext:
    """Contextual metadata and configuration passed to an analyzer."""
    run_id: UUID
    repository_id: UUID
    working_tree_path: Path
    target_ref: str | None = None
    resolved_revision: str | None = None  # Exact 40-character Git commit SHA
    commit_hash: str | None = None  # Alias/legacy
    exclude_patterns: tuple[str, ...] = ()


@runtime_checkable
class CodeAnalyzer(Protocol):
    """Protocol for static code analysis engines in TRACE."""

    @property
    def supported_language(self) -> str:
        """The primary programming language supported by this analyzer (e.g. 'python')."""
        ...

    def analyze(self, context: AnalysisContext) -> RepositoryAnalysis:
        """Execute deterministic static analysis over the repository working tree.

        Args:
            context: Execution context containing working tree path and configuration.

        Returns:
            The complete, strongly typed RepositoryAnalysis domain aggregate.

        Raises:
            AnalysisExecutionError: If repository traversal cannot be performed.
        """
        ...
```

---

## 2. Python Analyzer Implementation: `PythonCodeAnalyzer`

`PythonCodeAnalyzer` is the concrete implementation of `CodeAnalyzer` for Python repositories.

### Internal Pipeline Flow

```
AnalysisContext (working_tree_path, resolved_revision)
           │
           ▼
[1. FileScanner] ────────► Discovers files, checks byte sizes, applies exclusions, skips binary/large (>1MB)
           │
           ▼
[2. AST Parser] ─────────► Parses Python files into ast.AST; catches SyntaxError -> AnalysisDiagnostic
           │
           ▼
[3. Symbol Extractor] ───► Traverses AST; extracts Modules, Classes, Functions, Decorators, Parameters
           │
           ▼
[4. Pattern Detectors] ──► Specialized visitor passes:
           │               ├── ServiceDetector (domain/app services, *Service classes)
           │               ├── APIDetector (FastAPI, Flask)
           │               ├── ConfigDetector (os.environ, BaseSettings, SettingsConfigDict)
           │               ├── DatabaseDetector (SQLAlchemy Declarative, queries, writes)
           │               ├── TestDetector (pytest functions, test classes)
           │               ├── DocDetector (inline docstrings, README/docs markdown)
           │               └── DependencyDetector (pyproject.toml, requirements.txt)
           │
           ▼
[5. Relationship Synthesizer] ──► Links IMPORTS, CALLS, EXTENDS, EXPOSES, READS, WRITES, TESTED_BY
           │
           ▼
RepositoryAnalysis Aggregate
```

### Safety & Isolation Rules
- **No AST Node Exposure**: Standard library `ast.AST` nodes and syntax tokens MUST NOT be exposed outside `PythonCodeAnalyzer`.
- **Pure Static Execution**: No `importlib`, `exec()`, `eval()`, or dynamic code execution is permitted.
- **Fail-Safe Processing**: File-level parser failures append an `AnalysisDiagnostic` and continue processing remaining files.

---

## 3. Service Boundary: `AnalysisService`

The `AnalysisService` orchestrates analysis execution between F01 repositories, the `CodeAnalyzer`, PostgreSQL persistence, artifact storage, and the FastAPI API layer.

```python
class AnalysisService:
    """Service layer managing the lifecycle of repository analysis runs."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        git_provider: GitProvider,
        analyzer: CodeAnalyzer,
        artifact_storage_path: Path,
    ) -> None:
        self._db_gateway = db_gateway
        self._git_provider = git_provider
        self._analyzer = analyzer
        self._artifact_storage_path = artifact_storage_path

    async def trigger_analysis(
        self,
        repository_id: UUID,
        target_ref: str | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> AnalysisRun:
        """Initiate an analysis run for a connected repository.

        1. Validates repository exists, is CONNECTED, and project is ACTIVE.
        2. Creates an AnalysisRun record in PostgreSQL with status PENDING.
        3. Returns the pending AnalysisRun record immediately (for HTTP 202 response).
        """
        ...

    async def execute_analysis_task(
        self,
        run_id: UUID,
    ) -> None:
        """Background worker task executing the actual static analysis.

        1. Updates AnalysisRun status to IN_PROGRESS.
        2. Resolves repository working tree (local path or temporary clone workspace).
        3. Invokes analyzer.analyze(context).
        4. Serializes RepositoryAnalysis to JSON artifact on disk.
        5. Updates AnalysisRun with summary metrics, artifact path, and COMPLETED status.
        6. Updates repositories.last_analysis_run_id with run_id.
        7. On fatal error: catches exception, records error_message, updates status to FAILED.
        """
        ...

    async def get_analysis_run(self, run_id: UUID) -> AnalysisRun:
        """Retrieve operational metadata and status of an analysis run."""
        ...

    async def list_analysis_runs(
        self,
        repository_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: AnalysisStatus | None = None,
    ) -> tuple[list[AnalysisRun], int]:
        """List historical analysis runs for a repository with pagination."""
        ...

    async def get_analysis_artifact(self, run_id: UUID) -> RepositoryAnalysis:
        """Load and return the complete structured RepositoryAnalysis domain artifact."""
        ...
```

---

## 4. Execution Boundary: `AnalysisExecutor` Protocol

To decouple FastAPI-specific background tasks (`fastapi.BackgroundTasks`) from application service logic, an explicit `AnalysisExecutor` protocol is introduced.

```python
@runtime_checkable
class AnalysisExecutor(Protocol):
    """Protocol for dispatching analysis execution tasks asynchronously."""

    async def dispatch(self, run_id: UUID) -> None:
        """Dispatch analysis run execution to an asynchronous worker or background runner.

        Args:
            run_id: The UUID of the pending AnalysisRun record.
        """
        ...


class BackgroundTasksAnalysisExecutor:
    """FastAPI in-process background task implementation of AnalysisExecutor."""

    def __init__(self, background_tasks: BackgroundTasks, service: AnalysisService) -> None:
        self._background_tasks = background_tasks
        self._service = service

    async def dispatch(self, run_id: UUID) -> None:
        self._background_tasks.add_task(self._service.execute_analysis_task, run_id)
```

---

## 5. Workspace Acquisition Boundary: `GitProvider`

To guarantee deterministic analysis of an exact repository revision, `GitProvider` provides explicit workspace acquisition:

```python
class GitProvider(Protocol):
    """Protocol extension for repository workspace acquisition."""

    def acquire_workspace(
        self,
        repository: Repository,
        target_ref: str | None = None,
    ) -> tuple[Path, str]:
        """Acquire a readable local workspace and resolve the exact commit SHA.

        - For LOCAL repositories: Validates directory readability, resolves Git HEAD SHA
          (or uses repository ID / synthetic hash if not a Git repo), and returns (path, resolved_revision).
        - For REMOTE repositories: Clones or fetches target_ref into an isolated cache workspace
          at `storage/workspaces/{repository_id}_{commit_hash}`, and returns (path, resolved_revision).

        Returns:
            A tuple of (local_filesystem_path, resolved_revision_40_char_sha).
        """
        ...
```
