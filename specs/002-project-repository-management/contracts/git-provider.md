# Contract: `GitProvider` Protocol (`trace/infrastructure/git/provider.py`)

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Feature**: F01 Project & Repository Management

This document defines the formal boundary protocol for Git repository interactions in TRACE, established pursuant to TRACE Constitution §VIII (Explicit Contracts) and §XIV (Replaceable Infrastructure).

---

## 1. Protocol Definition

```python
from pathlib import Path
from typing import Protocol, runtime_checkable
from trace.domain.repository import ConnectionValidationResult, RepositoryType

@runtime_checkable
class GitProvider(Protocol):
    """Abstract interface defining non-destructive Git probe and discovery operations.

    In F01, this protocol is intentionally limited to connectivity validation,
    default branch resolution, and reference discovery without cloning codebases.
    Downstream features (F02 and F04) will extend this interface or introduce
    dedicated workspace protocols for clone, tree walk, and diff operations.
    """

    async def validate_local(self, path: Path) -> ConnectionValidationResult:
        """Validate that a local filesystem path exists and is a valid Git repository.

        Args:
            path: Normalized absolute filesystem path to check.

        Returns:
            ConnectionValidationResult indicating reachability, detected branch,
            diagnostics, and probe latency. Never raises unhandled exceptions.
        """
        ...

    async def validate_remote(
        self, url: str, timeout_seconds: float = 10.0
    ) -> ConnectionValidationResult:
        """Query a remote Git URL for accessibility and reference advertisement.

        Executes a non-destructive remote probe (e.g. ls-remote) without cloning.

        Args:
            url: Normalized remote Git URL (https://, http://, or ssh://).
            timeout_seconds: Hard upper bound for network probe execution.

        Returns:
            ConnectionValidationResult indicating reachability, detected branch,
            diagnostics, and probe latency. Never raises unhandled exceptions.
        """
        ...

    async def detect_default_branch(
        self, location: str, repo_type: RepositoryType
    ) -> str | None:
        """Deterministically resolve the default branch name (HEAD target).

        Args:
            location: Normalized filesystem path or Git URL.
            repo_type: RepositoryType.LOCAL or RepositoryType.REMOTE.

        Returns:
            Discovered default branch string (e.g., 'main', 'master') or None if unresolvable.
        """
        ...

    async def list_remote_references(
        self, url: str, timeout_seconds: float = 10.0
    ) -> list[str]:
        """List advertised remote branch and tag reference names.

        Args:
            url: Normalized remote Git URL.
            timeout_seconds: Network probe timeout in seconds.

        Returns:
            List of reference names (e.g., ['refs/heads/main', 'refs/tags/v1.0.0']).
            Returns an empty list on failure without raising exceptions.
        """
        ...
```

---

## 2. Concrete Implementations in F01

1. **`SubprocessGitProvider`** (`trace/infrastructure/git/adapters/subprocess.py`):
   - Production implementation using `asyncio.create_subprocess_exec("git", ...)`.
   - Injected with `GIT_TERMINAL_PROMPT=0` to guarantee non-interactive exit on missing credentials.
   - Enforces timeout via `asyncio.wait_for`.
2. **`StubGitProvider`** (`tests/conftest.py`):
   - In-memory test double for unit and API test suites.
   - Configurable returns for `validate_local`, `validate_remote`, and `detect_default_branch`.
   - Guarantees 0 external network requests during standard test execution.

---

## 3. Extensibility for F02 & F04

F02 (Code Analyzer) and F04 (Version / Change Analyzer) will consume this interface. When F02 is introduced, a `GitWorkspaceProvider` protocol will be added or `GitProvider` will be extended with:
- `clone(url, target_path, branch, depth) -> Path`
- `checkout(path, ref) -> None`
- `get_commit_history(path, limit) -> list[Commit]`
- `get_diff(path, base_ref, target_ref) -> DiffSummary`

F01 strictly avoids defining these methods now in accordance with Constitution §XVII (No Fabricated Implementation State).
