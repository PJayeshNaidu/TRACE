"""SQLAlchemy ORM model for graph_build_runs table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.domain.graph import GraphBuildRun
    from trace.infrastructure.database.models.repository import RepositoryOrm


class GraphBuildRunOrm(Base):
    """Declarative ORM model mapping to 'graph_build_runs' relational table.

    Tracks the status and outcome of each Neo4j dependency graph build attempt
    associated with an analysis run.
    """

    __tablename__ = "graph_build_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )
    nodes_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    __table_args__ = (
        Index("idx_graph_build_runs_analysis_id", "analysis_run_id"),
        Index("idx_graph_build_runs_status", "status"),
    )

    def to_domain(self) -> GraphBuildRun:
        """Convert ORM record to the GraphBuildRun domain model."""
        from trace.domain.graph import GraphBuildRun, GraphBuildStatus

        return GraphBuildRun(
            id=self.id,
            analysis_run_id=self.analysis_run_id,
            repository_id=self.repository_id,
            status=GraphBuildStatus(self.status),
            nodes_created=self.nodes_created,
            relationships_created=self.relationships_created,
            duration_ms=self.duration_ms,
            error_message=self.error_message,
            started_at=self.started_at,
            completed_at=self.completed_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
