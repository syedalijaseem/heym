"""add dashboards

Revision ID: d6d9466252b4
Revises: 076_discord_trigger_credential
Create Date: 2026-06-13 07:49:28.308010

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d6d9466252b4"
down_revision: Union[str, None] = "076_discord_trigger_credential"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workflow.kind — marks hidden dashboard-widget workflows so they are excluded
    # from the normal workflow lists. server_default backfills existing rows.
    op.add_column(
        "workflows",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="workflow"),
    )
    op.create_index(op.f("ix_workflows_kind"), "workflows", ["kind"], unique=False)

    op.create_table(
        "dashboards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dashboards_owner_id"), "dashboards", ["owner_id"], unique=False)

    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dashboard_id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("layout", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("cached_payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cached_workflow_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_dashboard_widgets_dashboard_id"),
        "dashboard_widgets",
        ["dashboard_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dashboard_widgets_workflow_id"),
        "dashboard_widgets",
        ["workflow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dashboard_widgets_workflow_id"), table_name="dashboard_widgets")
    op.drop_index(op.f("ix_dashboard_widgets_dashboard_id"), table_name="dashboard_widgets")
    op.drop_table("dashboard_widgets")
    op.drop_index(op.f("ix_dashboards_owner_id"), table_name="dashboards")
    op.drop_table("dashboards")
    op.drop_index(op.f("ix_workflows_kind"), table_name="workflows")
    op.drop_column("workflows", "kind")
