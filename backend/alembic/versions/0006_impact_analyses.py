"""Add impact_analyses table for F05 Impact Analysis and Risk Evaluation Engine.

Revision ID: 0006_impact_analyses
Revises: 0005_version_comparisons
Create Date: 2026-09-30 15:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_impact_analyses"
down_revision: str | Sequence[str] | None = "0005_version_comparisons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the impact_analyses table."""
    op.create_table(
        "impact_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("base_commit", sa.String(length=64), nullable=False),
        sa.Column("current_commit", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("reasoning_mode", sa.String(length=20), nullable=False, server_default="HEURISTIC"),
        sa.Column("total_changed_entities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_deleted_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_impacted_downstream_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_callers_at_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
            name="fk_impact_analysis_repository",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_impact_analyses_repo_created",
        "impact_analyses",
        ["repository_id", "created_at"],
    )
    op.create_index(
        "ix_impact_analyses_repository_id",
        "impact_analyses",
        ["repository_id"],
    )


def downgrade() -> None:
    """Drop the impact_analyses table."""
    op.drop_index("ix_impact_analyses_repository_id", table_name="impact_analyses")
    op.drop_index("ix_impact_analyses_repo_created", table_name="impact_analyses")
    op.drop_table("impact_analyses")
