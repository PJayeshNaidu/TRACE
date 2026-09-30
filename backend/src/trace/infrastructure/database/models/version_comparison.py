"""SQLAlchemy ORM model for version_comparisons table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.domain.diff import RiskLevel, VersionComparison
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.infrastructure.database.models.repository import RepositoryOrm


class VersionComparisonOrm(Base):
    """Declarative ORM model mapping to 'version_comparisons' table."""

    __tablename__ = "version_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    base_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    base_commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    target_commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    total_files_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_insertions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_symbols_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_breaking_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("ix_version_comparisons_repo_created", "repository_id", "created_at"),
    )

    def to_domain(self) -> VersionComparison:
        """Convert ORM record to immutable VersionComparison domain aggregate."""
        return VersionComparison(
            id=self.id,
            repository_id=self.repository_id,
            base_ref=self.base_ref,
            target_ref=self.target_ref,
            base_commit_hash=self.base_commit_hash,
            target_commit_hash=self.target_commit_hash,
            risk_level=RiskLevel(self.risk_level),
            total_files_changed=self.total_files_changed,
            total_insertions=self.total_insertions,
            total_deletions=self.total_deletions,
            total_symbols_changed=self.total_symbols_changed,
            total_breaking_changes=self.total_breaking_changes,
            created_at=self.created_at,
            file_diffs=(),
            symbol_diffs=(),
            blast_radius=(),
            commit_messages=(),
        )
