"""GitProvider protocol definition for non-destructive repository probing.

Per Constitution §XIV (Clean Architecture) and §XVII (No Fabricated Implementation State),
this interface defines only genuine, targeted probe operations implemented in F01.
No stubbed or unimplemented methods for cloning, checkout, diffing, or AST parsing
are declared in this phase.
"""

from pathlib import Path
from trace.domain.repository import ConnectionValidationResult, RepositoryType
from typing import Protocol, runtime_checkable


@runtime_checkable
class GitProvider(Protocol):
    """Protocol defining non-destructive probe and reference operations on Git repositories."""

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
