"""add dashboard_widgets.description

Revision ID: d7a1b2c3d4e5
Revises: d6d9466252b4
Create Date: 2026-06-13 09:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7a1b2c3d4e5"
down_revision: Union[str, None] = "d6d9466252b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("dashboard_widgets", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dashboard_widgets", "description")
