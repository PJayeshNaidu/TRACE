"""Empty baseline migration for TRACE database foundation.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-28 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply baseline schema upgrades (none in Phase 0)."""
    pass


def downgrade() -> None:
    """Revert baseline schema upgrades (none in Phase 0)."""
    pass
