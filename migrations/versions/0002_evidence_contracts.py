"""Preserve source provenance and store structurally validated claim evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_evidence_contracts"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy provenance is unknown; never silently relabel existing text as eligible.
    op.add_column(
        "sources",
        sa.Column("kind", sa.String(24), server_default="unknown", nullable=False),
        schema="jarvis",
    )
    op.create_table(
        "passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("variant", sa.String(16), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("exact_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id", "owner_id", "source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="passage_source_owner_revision",
        ),
        sa.UniqueConstraint("id", "owner_id", name="passage_owner"),
        sa.UniqueConstraint(
            "source_id", "source_revision", "variant", "start", "end", name="passage_location"
        ),
        sa.CheckConstraint("variant IN ('raw', 'formatted')", name="passage_variant"),
        sa.CheckConstraint('start >= 0 AND "end" > start', name="passage_offsets"),
        schema="jarvis",
    )
    op.create_table(
        "claim_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("jarvis.policies.owner_id"), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("lifecycle", sa.String(16), server_default="active", nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "owner_id", name="claim_revision_owner"),
        sa.UniqueConstraint("claim_id", "owner_id", "revision", name="claim_identity_revision"),
        sa.CheckConstraint("revision > 0", name="claim_revision_positive"),
        sa.CheckConstraint("policy_revision >= 0", name="claim_policy_revision_nonnegative"),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'superseded', 'corrected', 'excluded')", name="claim_lifecycle"
        ),
        schema="jarvis",
    )
    op.create_table(
        "claim_evidence",
        sa.Column("claim_revision_id", sa.Uuid(), primary_key=True),
        sa.Column("passage_id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="evidence_claim_owner",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id", "owner_id"],
            ["jarvis.passages.id", "jarvis.passages.owner_id"],
            name="evidence_passage_owner",
        ),
        sa.UniqueConstraint("claim_revision_id", "position", name="evidence_position"),
        sa.CheckConstraint("position >= 0", name="evidence_position_nonnegative"),
        schema="jarvis",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON jarvis.passages, jarvis.claim_revisions, jarvis.claim_evidence TO jarvis_runtime"
    )


def downgrade() -> None:
    op.drop_table("claim_evidence", schema="jarvis")
    op.drop_table("claim_revisions", schema="jarvis")
    op.drop_table("passages", schema="jarvis")
    op.drop_column("sources", "kind", schema="jarvis")
