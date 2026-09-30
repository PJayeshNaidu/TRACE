"""Analysis runs table.

Revision ID: 0003_analysis_runs
Revises: 0002_project_repository
Create Date: 2026-09-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_analysis_runs"
down_revision: str | Sequence[str] | None = "0002_project_repository"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create analysis_runs table."""
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("target_ref", sa.String(length=100), nullable=True),
        sa.Column("resolved_revision", sa.String(length=40), nullable=True),
        sa.Column("commit_hash", sa.String(length=40), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("total_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("python_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_modules", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_classes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_functions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_relationships", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_diagnostics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_repository_id", "analysis_runs", ["repository_id"], unique=False)
    op.create_index("ix_analysis_runs_project_id", "analysis_runs", ["project_id"], unique=False)
    op.create_index("idx_analysis_runs_status", "analysis_runs", ["status"], unique=False)
    op.create_index(
        "idx_analysis_runs_repo_created",
        "analysis_runs",
        ["repository_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop analysis_runs table."""
    op.drop_index("idx_analysis_runs_repo_created", table_name="analysis_runs")
    op.drop_index("idx_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_project_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_repository_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
