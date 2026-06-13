"""merge s3 and dashboard migration heads

Revision ID: 078_merge_s3_dashboard_heads
Revises: 077_add_s3_credential_type, d7a1b2c3d4e5
Create Date: 2026-06-13
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "078_merge_s3_dashboard_heads"
down_revision: tuple[str, str] = ("077_add_s3_credential_type", "d7a1b2c3d4e5")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
