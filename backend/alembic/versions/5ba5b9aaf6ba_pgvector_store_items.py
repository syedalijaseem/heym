"""pgvector_store_items

Revision ID: 5ba5b9aaf6ba
Revises: 081_add_workflow_analysis_notes
Create Date: 2026-06-22 12:55:50.484853

"""

from typing import Sequence, Union

from alembic import op

revision: str = "5ba5b9aaf6ba"
down_revision: Union[str, None] = "081_add_workflow_analysis_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_store_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_name TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            source TEXT,
            file_size INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vsi_collection_name ON vector_store_items (collection_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vsi_collection_source "
        "ON vector_store_items (collection_name, source)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vsi_embedding_hnsw "
        "ON vector_store_items USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vector_store_items")
