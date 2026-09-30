"""SQLAlchemy ORM model for impact_analyses table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.infrastructure.database.models.repository import RepositoryOrm


class ImpactAnalysisOrm(Base):
    """Declarative ORM model mapping to 'impact_analyses' table."""

    __tablename__ = "impact_analyses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    base_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    current_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    reasoning_mode: Mapped[str] = mapped_column(String(20), default="HEURISTIC", nullable=False)
    total_changed_entities: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_deleted_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_impacted_downstream_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_callers_at_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    repository: Mapped[RepositoryOrm] = relationship(
        "RepositoryOrm",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_impact_analyses_repo_created", "repository_id", "created_at"),
    )
