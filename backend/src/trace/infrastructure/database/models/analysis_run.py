"""SQLAlchemy ORM model for analysis_runs table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.domain.analysis import AnalysisRun
    from trace.infrastructure.database.models.project import ProjectOrm
    from trace.infrastructure.database.models.repository import RepositoryOrm


class AnalysisRunOrm(Base):
    """Declarative ORM model mapping to 'analysis_runs' relational table."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    target_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_revision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    python_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_modules: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_classes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_functions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_relationships: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_diagnostics: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    repository: Mapped[RepositoryOrm] = relationship(
        "RepositoryOrm",
        foreign_keys=[repository_id],
    )
    project: Mapped[ProjectOrm] = relationship(
        "ProjectOrm",
        foreign_keys=[project_id],
    )

    __table_args__ = (
        Index("idx_analysis_runs_repo_created", "repository_id", created_at.desc()),
        Index("idx_analysis_runs_status", "status"),
    )

    def to_domain(self) -> AnalysisRun:
        from trace.domain.analysis import AnalysisRun, AnalysisStatus

        return AnalysisRun(
            id=self.id,
            repository_id=self.repository_id,
            project_id=self.project_id,
            status=AnalysisStatus(self.status),
            target_ref=self.target_ref,
            resolved_revision=self.resolved_revision,
            commit_hash=self.commit_hash,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=self.duration_ms,
            total_files=self.total_files,
            python_files=self.python_files,
            total_modules=self.total_modules,
            total_classes=self.total_classes,
            total_functions=self.total_functions,
            total_relationships=self.total_relationships,
            total_diagnostics=self.total_diagnostics,
            error_message=self.error_message,
            artifact_path=self.artifact_path,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
