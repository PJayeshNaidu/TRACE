"""GitProvider protocol definition for non-destructive repository probing.

Per Constitution §XIV (Clean Architecture) and §XVII (No Fabricated Implementation State),
this interface defines only genuine, targeted probe operations implemented in F01.
No stubbed or unimplemented methods for cloning, checkout, diffing, or AST parsing
are declared in this phase.
"""

from pathlib import Path
from trace.domain.diff import CommitInfo
from trace.domain.repository import ConnectionValidationResult, RepositoryType
from typing import Protocol, runtime_checkable


@runtime_checkable
class GitProvider(Protocol):
    """Protocol defining non-destructive probe, reference, and diff operations on Git repositories."""

    async def validate_local(self, path: Path) -> ConnectionValidationResult:
        """Validate accessibility, structure, and HEAD branch of a local Git repository."""
        ...

    async def validate_remote(
        self, url: str, timeout_seconds: float = 10.0
    ) -> ConnectionValidationResult:
        """Probe remote Git repository reachability and resolve default branch via ls-remote."""
        ...

    async def detect_default_branch(self, location: str, repo_type: RepositoryType) -> str | None:
        """Resolve the default branch name deterministically from HEAD reference."""
        ...

    async def list_remote_references(self, url: str, timeout_seconds: float = 10.0) -> list[str]:
        """Query available remote branch and tag reference names without cloning files."""
        ...

    async def resolve_revision(self, location: str | Path, ref: str = "HEAD") -> str | None:
        """Resolve a Git reference (e.g. branch, tag, HEAD) to a 40-character commit SHA."""
        ...

    async def clone_or_checkout(
        self,
        url: str,
        destination: Path,
        target_ref: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> Path:
        """Clone a remote Git repository or fetch and checkout the target ref."""
        ...

    async def get_diff(
        self,
        location: str | Path,
        base_ref: str,
        target_ref: str,
        timeout_seconds: float = 30.0,
    ) -> str:
        """Generate unified diff between two Git references or commits."""
        ...

    async def list_branches(
        self,
        location: str | Path,
        timeout_seconds: float = 10.0,
    ) -> list[str]:
        """List local and remote branch names available in repository."""
        ...

    async def list_commits(
        self,
        location: str | Path,
        branch: str | None = None,
        limit: int = 30,
        timeout_seconds: float = 10.0,
    ) -> list[CommitInfo]:
        """Retrieve recent commit metadata from specified branch."""
        ...
