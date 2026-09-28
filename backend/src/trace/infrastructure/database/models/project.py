"""SQLAlchemy ORM model for projects table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from trace.domain.project import Project
    from trace.infrastructure.database.models.repository import RepositoryOrm


class ProjectOrm(Base):
    """Declarative ORM model mapping to 'projects' relational table."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
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

    repositories: Mapped[list[RepositoryOrm]] = relationship(
        "RepositoryOrm",
        back_populates="project",
    )

    def to_domain(self) -> Project:
        from trace.domain.project import Project, ProjectStatus

        return Project(
            id=self.id,
            name=self.name,
            description=self.description,
            status=ProjectStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
