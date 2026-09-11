"""Index original observations and claim values without rewriting canonical records."""

import sqlalchemy as sa
from alembic import op

revision = "0004_lexical_retrieval"
down_revision = "0003_memory_processing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "sources_search_idx",
        "sources",
        [
            sa.text(
                "(to_tsvector('english'::regconfig, "
                "raw_text || ' ' || COALESCE(formatted_text, '')) || "
                "to_tsvector('simple'::regconfig, raw_text || ' ' || COALESCE(formatted_text, '')))"
            )
        ],
        schema="jarvis",
        postgresql_using="gin",
    )
    op.create_index(
        "claims_search_idx",
        "claim_revisions",
        [
            sa.text(
                "(jsonb_to_tsvector('english'::regconfig, content, "
                '\'["string","numeric","boolean"]\'::jsonb) || '
                "jsonb_to_tsvector('simple'::regconfig, content, "
                '\'["string","numeric","boolean"]\'::jsonb))'
            )
        ],
        schema="jarvis",
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("claims_search_idx", table_name="claim_revisions", schema="jarvis")
    op.drop_index("sources_search_idx", table_name="sources", schema="jarvis")
