"""Add upgrade_plans, upgrade_tasks, and task_dependencies tables for F07 Upgrade Planner.

Revision ID: 0007_upgrade_plans
Revises: 0006_impact_analyses
Create Date: 2026-10-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_upgrade_plans"
down_revision: str | Sequence[str] | None = "0006_impact_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the upgrade_plans, upgrade_tasks, and task_dependencies tables."""
    # 1. upgrade_plans table
    op.create_table(
        "upgrade_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("impact_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("base_commit", sa.String(length=64), nullable=False),
        sa.Column("target_commit", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("reasoning_mode", sa.String(length=20), nullable=False, server_default="HEURISTIC"),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
            name="fk_upgrade_plan_repository",
        ),
        sa.ForeignKeyConstraint(
            ["impact_analysis_id"],
            ["impact_analyses.id"],
            ondelete="CASCADE",
            name="fk_upgrade_plan_impact_analysis",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upgrade_plans_repository_id",
        "upgrade_plans",
        ["repository_id"],
    )
    op.create_index(
        "ix_upgrade_plans_impact_id",
        "upgrade_plans",
        ["impact_analysis_id"],
    )
    op.create_index(
        "ix_upgrade_plans_repo_created",
        "upgrade_plans",
        ["repository_id", "created_at"],
    )

    # 2. upgrade_tasks table
    op.create_table(
        "upgrade_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(length=255), nullable=False),
        sa.Column("component_type", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("expected_changes", sa.Text(), nullable=False, server_default=""),
        sa.Column("required_tests", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("is_circular", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parallel_group_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["upgrade_plans.id"],
            ondelete="CASCADE",
            name="fk_upgrade_task_plan",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upgrade_tasks_plan_step",
        "upgrade_tasks",
        ["plan_id", "step_number"],
    )
    op.create_index(
        "ix_upgrade_tasks_status",
        "upgrade_tasks",
        ["status"],
    )

    # 3. task_dependencies table
    op.create_table(
        "task_dependencies",
        sa.Column("source_task_id", sa.Uuid(), nullable=False),
        sa.Column("target_task_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False, server_default="CALLS"),
        sa.ForeignKeyConstraint(
            ["source_task_id"],
            ["upgrade_tasks.id"],
            ondelete="CASCADE",
            name="fk_task_dep_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_task_id"],
            ["upgrade_tasks.id"],
            ondelete="CASCADE",
            name="fk_task_dep_target",
        ),
        sa.PrimaryKeyConstraint("source_task_id", "target_task_id"),
    )


def downgrade() -> None:
    """Drop the task_dependencies, upgrade_tasks, and upgrade_plans tables."""
    op.drop_table("task_dependencies")
    op.drop_index("ix_upgrade_tasks_status", table_name="upgrade_tasks")
    op.drop_index("ix_upgrade_tasks_plan_step", table_name="upgrade_tasks")
    op.drop_table("upgrade_tasks")
    op.drop_index("ix_upgrade_plans_repo_created", table_name="upgrade_plans")
    op.drop_index("ix_upgrade_plans_impact_id", table_name="upgrade_plans")
    op.drop_index("ix_upgrade_plans_repository_id", table_name="upgrade_plans")
    op.drop_table("upgrade_plans")
