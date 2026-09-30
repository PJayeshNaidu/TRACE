"""SQLAlchemy ORM model for repositories table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.domain.repository import Repository
    from trace.infrastructure.database.models.project import ProjectOrm


class RepositoryOrm(Base):
    """Declarative ORM model mapping to 'repositories' relational table."""

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="REGISTERED", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
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

    project: Mapped[ProjectOrm] = relationship(
        "ProjectOrm",
        back_populates="repositories",
    )

    __table_args__ = (UniqueConstraint("project_id", "location", name="uq_project_location"),)

    def to_domain(self) -> Repository:
        from trace.domain.repository import Repository, RepositoryStatus, RepositoryType

        return Repository(
            id=self.id,
            project_id=self.project_id,
            type=RepositoryType(self.type),
            location=self.location,
            default_branch=self.default_branch,
            status=RepositoryStatus(self.status),
            last_error=self.last_error,
            last_validated_at=self.last_validated_at,
            last_analysis_run_id=self.last_analysis_run_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
