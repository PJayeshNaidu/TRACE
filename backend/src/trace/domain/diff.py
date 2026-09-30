"""Pure domain entities and value objects for Version & Change Analysis (F04).

Per Constitution §XIV, domain entities contain zero framework, database, or I/O imports.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class FileChangeType(StrEnum):
    """Classification of file modification in a changeset."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


class SymbolChangeKind(StrEnum):
    """Classification of code symbol modification."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


class RiskLevel(StrEnum):
    """Overall change impact risk rating."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DiffHunk:
    """Represents a contiguous diff hunk in a modified file."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str = ""
    content: str = ""


@dataclass(frozen=True)
class FileDiff:
    """Represents the diff of a single file between two revisions."""

    old_path: str | None
    new_path: str | None
    change_type: FileChangeType
    insertions: int = 0
    deletions: int = 0
    hunks: tuple[DiffHunk, ...] = ()


@dataclass(frozen=True)
class SymbolDiff:
    """Represents an AST symbol (function, class, endpoint) affected by changes."""

    symbol_id: str
    qualified_name: str
    kind: str  # "function", "class", "endpoint", "module"
    file_path: str
    change_kind: SymbolChangeKind
    is_breaking: bool = False
    breaking_reason: str | None = None
    old_signature: str | None = None
    new_signature: str | None = None


@dataclass(frozen=True)
class BlastRadiusItem:
    """Represents a downstream or upstream dependency affected by a changed symbol."""

    target_symbol_id: str
    affected_symbol_id: str
    affected_qualified_name: str
    affected_kind: str
    relationship_kind: str  # "CALLS", "EXTENDS", "DEPENDS_ON", "TESTED_BY"
    affected_file_path: str | None = ""
    depth: int = 1


@dataclass(frozen=True)
class CommitInfo:
    """Git commit metadata item."""

    commit_hash: str
    short_hash: str
    message: str
    author: str
    timestamp: datetime | str


@dataclass(frozen=True)
class VersionComparison:
    """Immutable domain aggregate representing a complete version/branch comparison."""

    id: uuid.UUID
    repository_id: uuid.UUID
    base_ref: str
    target_ref: str
    base_commit_hash: str
    target_commit_hash: str
    created_at: datetime
    risk_level: RiskLevel
    total_files_changed: int
    total_insertions: int
    total_deletions: int
    total_symbols_changed: int
    total_breaking_changes: int
    file_diffs: tuple[FileDiff, ...] = ()
    symbol_diffs: tuple[SymbolDiff, ...] = ()
    blast_radius: tuple[BlastRadiusItem, ...] = ()
    commit_messages: tuple[str, ...] = ()
