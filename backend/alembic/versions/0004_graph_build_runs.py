"""Add graph_build_runs table for F03 Dependency Graph.

Revision ID: 0004_graph_build_runs
Revises: 0003_analysis_runs
Create Date: 2026-09-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_graph_build_runs"
down_revision: str | Sequence[str] | None = "0003_analysis_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the graph_build_runs table."""
    op.create_table(
        "graph_build_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("nodes_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relationships_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], name="fk_gbr_analysis_run"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], name="fk_gbr_repository"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_graph_build_runs_analysis_id",
        "graph_build_runs",
        ["analysis_run_id"],
    )
    op.create_index(
        "idx_graph_build_runs_status",
        "graph_build_runs",
        ["status"],
    )


def downgrade() -> None:
    """Drop the graph_build_runs table."""
    op.drop_index("idx_graph_build_runs_status", table_name="graph_build_runs")
    op.drop_index("idx_graph_build_runs_analysis_id", table_name="graph_build_runs")
    op.drop_table("graph_build_runs")
