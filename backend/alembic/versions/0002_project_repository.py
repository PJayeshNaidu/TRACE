"""Project and repository tables.

Revision ID: 0002_project_repository
Revises: 0001_baseline
Create Date: 2026-09-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_project_repository"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create projects and repositories tables."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_name", "projects", ["name"], unique=True)

    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=False),
        sa.Column("default_branch", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="REGISTERED", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_analysis_run_id", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "location", name="uq_project_location"),
    )
    op.create_index("ix_repositories_project_id", "repositories", ["project_id"], unique=False)


def downgrade() -> None:
    """Drop repositories and projects tables."""
    op.drop_index("ix_repositories_project_id", table_name="repositories")
    op.drop_table("repositories")
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
