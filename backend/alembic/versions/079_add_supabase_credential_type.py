"""add supabase credential type

Revision ID: 079_add_supabase_credential_type
Revises: 078_merge_s3_dashboard_heads
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "079_add_supabase_credential_type"
down_revision: str | None = "078_merge_s3_dashboard_heads"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credential_type ADD VALUE IF NOT EXISTS 'supabase'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
