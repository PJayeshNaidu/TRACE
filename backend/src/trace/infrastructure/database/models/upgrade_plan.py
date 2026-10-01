"""SQLAlchemy ORM models for upgrade_plans, upgrade_tasks, and task_dependencies tables."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.infrastructure.database.models.base import Base
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

if TYPE_CHECKING:
    from trace.infrastructure.database.models.impact_analysis import ImpactAnalysisOrm
    from trace.infrastructure.database.models.repository import RepositoryOrm

# Use JSONB for PostgreSQL and JSON for SQLite
JSONType = JSON().with_variant(JSONB, "postgresql")


class UpgradePlanOrm(Base):
    """Declarative ORM model mapping to 'upgrade_plans' table."""

    __tablename__ = "upgrade_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    impact_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("impact_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    base_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    target_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False)
    reasoning_mode: Mapped[str] = mapped_column(String(20), default="HEURISTIC", nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
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
        lazy="selectin",
    )
    impact_analysis: Mapped[ImpactAnalysisOrm] = relationship(
        "ImpactAnalysisOrm",
        lazy="selectin",
    )
    tasks: Mapped[list[UpgradeTaskOrm]] = relationship(
        "UpgradeTaskOrm",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="UpgradeTaskOrm.step_number",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_upgrade_plans_repo_created", "repository_id", "created_at"),)


class UpgradeTaskOrm(Base):
    """Declarative ORM model mapping to 'upgrade_tasks' table."""

    __tablename__ = "upgrade_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upgrade_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    component: Mapped[str] = mapped_column(String(255), nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    expected_changes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    required_tests: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    is_circular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parallel_group_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
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

    plan: Mapped[UpgradePlanOrm] = relationship(
        "UpgradePlanOrm",
        back_populates="tasks",
    )

    __table_args__ = (
        Index("ix_upgrade_tasks_plan_step", "plan_id", "step_number"),
        Index("ix_upgrade_tasks_status", "status"),
    )


class TaskDependencyOrm(Base):
    """Declarative ORM model mapping to 'task_dependencies' table."""

    __tablename__ = "task_dependencies"

    source_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upgrade_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upgrade_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dependency_type: Mapped[str] = mapped_column(String(50), default="CALLS", nullable=False)
