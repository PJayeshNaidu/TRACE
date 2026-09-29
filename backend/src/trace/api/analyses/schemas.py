"""Pydantic v2 schemas for TRACE static code analysis API contracts."""

from datetime import datetime
from trace.domain.analysis import (
    AnalysisRun,
    AnalysisStatus,
    DiagnosticSeverity,
    EntityKind,
    RelationshipKind,
    SourceLocation,
)
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceLocationSchema(BaseModel):
    """Source file coordinate span."""

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(..., description="Repository-relative file path")
    start_line: int = Field(..., ge=1, description="1-indexed starting line")
    end_line: int = Field(..., ge=1, description="1-indexed ending line")
    start_column: int = Field(default=0, ge=0, description="0-indexed starting column")
    end_column: int = Field(default=0, ge=0, description="0-indexed ending column")

    @classmethod
    def from_domain(cls, loc: SourceLocation) -> "SourceLocationSchema":
        return cls(
            file_path=loc.file_path,
            start_line=loc.start_line,
            end_line=loc.end_line,
            start_column=loc.start_column if loc.start_column is not None else 0,
            end_column=loc.end_column if loc.end_column is not None else 0,
        )


class AnalysisTriggerRequest(BaseModel):
    """Payload to trigger an asynchronous repository analysis run."""

    model_config = ConfigDict(extra="forbid")

    target_ref: str | None = Field(
        default=None,
        description="Target git branch, tag, or commit SHA to analyze (defaults to HEAD)",
    )
    exclude_patterns: list[str] = Field(
        default_factory=list,
        description="Optional glob patterns of files/directories to exclude from analysis",
    )


class AnalysisRunResponse(BaseModel):
    """Response representing an analysis run lifecycle state and summary counters."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    repository_id: UUID
    project_id: UUID
    status: AnalysisStatus
    target_ref: str | None = None
    commit_hash: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    total_files: int = 0
    python_files: int = 0
    total_modules: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_relationships: int = 0
    total_diagnostics: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, run: AnalysisRun) -> "AnalysisRunResponse":
        return cls(
            id=run.id,
            repository_id=run.repository_id,
            project_id=run.project_id,
            status=run.status,
            target_ref=run.target_ref,
            commit_hash=run.commit_hash or run.resolved_revision,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.duration_ms,
            total_files=run.total_files,
            python_files=run.python_files,
            total_modules=run.total_modules,
            total_classes=run.total_classes,
            total_functions=run.total_functions,
            total_relationships=run.total_relationships,
            total_diagnostics=run.total_diagnostics,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


class AnalysisRunListResponse(BaseModel):
    """Paginated collection of analysis runs."""

    items: list[AnalysisRunResponse]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=500)
    offset: int = Field(..., ge=0)


class AnalysisSummaryResponse(BaseModel):
    """Detailed summary metrics for a completed analysis run."""

    analysis_run_id: UUID
    repository_id: UUID
    status: AnalysisStatus
    duration_ms: float | None = None
    metrics: dict[str, int | float] = Field(default_factory=dict)


class EntityItem(BaseModel):
    """Individual discovered code entity."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(..., description="Entity category (e.g. MODULE, CLASS, FUNCTION, SERVICE)")
    name: str = Field(..., description="Short symbol name")
    qualified_name: str = Field(..., description="Globally unambiguous qualified name")
    module_name: str | None = Field(default=None, description="Enclosing module qualified name")
    location: SourceLocationSchema
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntityListResponse(BaseModel):
    """Paginated list of code entities."""

    items: list[EntityItem]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=500)
    offset: int = Field(..., ge=0)


class RelationshipItem(BaseModel):
    """Synthesized directional relationship between two entities."""

    model_config = ConfigDict(frozen=True)

    source_type: EntityKind
    source_identifier: str
    relationship_type: RelationshipKind
    target_type: EntityKind
    target_identifier: str
    evidence_location: SourceLocationSchema | None = None


class RelationshipListResponse(BaseModel):
    """Paginated list of synthesized structural relationships."""

    items: list[RelationshipItem]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=500)
    offset: int = Field(..., ge=0)


class DiagnosticItem(BaseModel):
    """Parser diagnostic, syntax error, or warning."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    severity: DiagnosticSeverity
    code: str
    message: str
    line: int | None = None
    column: int | None = None


class DiagnosticListResponse(BaseModel):
    """Paginated list of parser diagnostics."""

    items: list[DiagnosticItem]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=500)
    offset: int = Field(..., ge=0)
