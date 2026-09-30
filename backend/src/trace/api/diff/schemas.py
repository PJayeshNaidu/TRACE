"""Pydantic schemas for F04: Version / Change Analyzer API."""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CompareTriggerRequest(BaseModel):
    """Request payload to trigger a version / branch / commit comparison."""

    model_config = ConfigDict(extra="forbid")

    repository_id: uuid.UUID = Field(
        ...,
        description="Target repository UUID.",
    )
    base_ref: str | None = Field(
        default=None,
        description="Base branch, tag, or commit SHA. Defaults to HEAD~1.",
        examples=["main", "HEAD~1"],
    )
    target_ref: str | None = Field(
        default=None,
        description="Target branch, tag, or commit SHA. Defaults to HEAD.",
        examples=["development", "feature/auth", "HEAD"],
    )


class DiffHunkSchema(BaseModel):
    """Line range interval of a diff hunk."""

    model_config = ConfigDict(from_attributes=True)

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str = ""
    content: str = ""


class FileDiffSchema(BaseModel):
    """File-level delta item."""

    model_config = ConfigDict(from_attributes=True)

    old_path: str | None = None
    new_path: str | None = None
    change_type: str
    insertions: int = 0
    deletions: int = 0
    hunks: list[DiffHunkSchema] = []


class SymbolDiffSchema(BaseModel):
    """AST code symbol delta item."""

    model_config = ConfigDict(from_attributes=True)

    symbol_id: str
    qualified_name: str
    kind: str
    file_path: str
    change_kind: str
    is_breaking: bool = False
    breaking_reason: str | None = None
    old_signature: str | None = None
    new_signature: str | None = None


class BlastRadiusItemSchema(BaseModel):
    """Graph dependent component affected by a changed symbol."""

    model_config = ConfigDict(from_attributes=True)

    target_symbol_id: str
    affected_symbol_id: str
    affected_qualified_name: str
    affected_kind: str
    affected_file_path: str | None = ""
    relationship_kind: str
    depth: int = 1


class ComparisonSummarySchema(BaseModel):
    """Metrics summary of a version comparison."""

    total_files_changed: int
    total_insertions: int
    total_deletions: int
    total_symbols_changed: int
    total_breaking_changes: int


class CompareTriggerResponse(BaseModel):
    """Response returned immediately after triggering or completing a comparison."""

    model_config = ConfigDict(from_attributes=True)

    comparison_id: uuid.UUID
    repository_id: uuid.UUID
    base_ref: str
    target_ref: str
    base_commit_hash: str
    target_commit_hash: str
    risk_level: str
    created_at: datetime
    summary: ComparisonSummarySchema


class ComparisonDetailResponse(BaseModel):
    """Full detail of a version comparison including symbols, breaking changes, and blast radius."""

    model_config = ConfigDict(from_attributes=True)

    comparison_id: uuid.UUID
    repository_id: uuid.UUID
    base_ref: str
    target_ref: str
    base_commit_hash: str
    target_commit_hash: str
    risk_level: str
    created_at: datetime
    summary: ComparisonSummarySchema
    file_diffs: list[FileDiffSchema] = []
    symbol_diffs: list[SymbolDiffSchema] = []
    blast_radius: list[BlastRadiusItemSchema] = []
    commit_messages: list[str] = []


class BranchListResponse(BaseModel):
    """Available branches in repository."""

    repository_id: uuid.UUID
    default_branch: str
    branches: list[str]


class CommitItemSchema(BaseModel):
    """Commit metadata item."""

    commit_hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str


class CommitListResponse(BaseModel):
    """List of recent commits for a branch."""

    repository_id: uuid.UUID
    branch: str | None
    commits: list[CommitItemSchema]
