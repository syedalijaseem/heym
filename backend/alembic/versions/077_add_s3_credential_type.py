"""add s3 credential type

Revision ID: 077_add_s3_credential_type
Revises: 076_discord_trigger_credential
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "077_add_s3_credential_type"
down_revision: str | None = "076_discord_trigger_credential"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credential_type ADD VALUE IF NOT EXISTS 's3'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
