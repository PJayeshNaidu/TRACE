"""Add version_comparisons table for F04 Version and Change Impact Analyzer.

Revision ID: 0005_version_comparisons
Revises: 0004_graph_build_runs
Create Date: 2026-09-29 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_version_comparisons"
down_revision: str | Sequence[str] | None = "0004_graph_build_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the version_comparisons table."""
    op.create_table(
        "version_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("base_ref", sa.String(length=255), nullable=False),
        sa.Column("target_ref", sa.String(length=255), nullable=False),
        sa.Column("base_commit_hash", sa.String(length=40), nullable=False),
        sa.Column("target_commit_hash", sa.String(length=40), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("total_files_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_insertions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_symbols_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_breaking_changes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE", name="fk_vc_repository"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_version_comparisons_repo_created",
        "version_comparisons",
        ["repository_id", "created_at"],
    )


def downgrade() -> None:
    """Drop the version_comparisons table."""
    op.drop_index("ix_version_comparisons_repo_created", table_name="version_comparisons")
    op.drop_table("version_comparisons")
