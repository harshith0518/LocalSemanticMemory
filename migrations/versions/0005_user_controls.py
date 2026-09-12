"""Owned control receipts and persistent source/passage exclusions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_user_controls"
down_revision = "0004_lexical_retrieval"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_calls", sa.Column("request_hash", sa.String(64), nullable=True), schema="jarvis"
    )
    op.add_column(
        "model_calls", sa.Column("policy_revision", sa.Integer(), nullable=True), schema="jarvis"
    )
    op.add_column(
        "model_calls", sa.Column("feedback_parent_id", sa.Uuid(), nullable=True), schema="jarvis"
    )
    op.create_unique_constraint("call_owner", "model_calls", ["id", "owner_id"], schema="jarvis")
    op.create_foreign_key(
        "call_feedback_parent",
        "model_calls",
        "model_calls",
        ["feedback_parent_id"],
        ["id"],
        source_schema="jarvis",
        referent_schema="jarvis",
    )
    op.create_table(
        "feedback_receipts",
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("diagnosis", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="started", nullable=False),
        sa.PrimaryKeyConstraint("call_id"),
        sa.ForeignKeyConstraint(
            ["call_id", "owner_id"],
            ["jarvis.model_calls.id", "jarvis.model_calls.owner_id"],
            name="feedback_call_owner",
        ),
        sa.CheckConstraint("diagnosis IN ('retrieval', 'generation')", name="feedback_diagnosis"),
        sa.CheckConstraint("status IN ('started', 'succeeded', 'failed')", name="feedback_status"),
        schema="jarvis",
    )
    op.create_table(
        "control_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("target_revision_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="control_owner"),
        sa.ForeignKeyConstraint(["owner_id"], ["jarvis.policies.owner_id"]),
        sa.ForeignKeyConstraint(
            ["target_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="control_target_owner",
        ),
        sa.CheckConstraint(
            "action IN ('correct', 'world_change', 'forget')", name="control_action"
        ),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="control_request_hash"),
        schema="jarvis",
    )
    op.create_table(
        "source_exclusions",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("control_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
        sa.ForeignKeyConstraint(
            ["source_id", "owner_id", "source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="exclusion_source_owner_revision",
        ),
        sa.ForeignKeyConstraint(
            ["control_id", "owner_id"],
            ["jarvis.control_receipts.id", "jarvis.control_receipts.owner_id"],
            name="source_exclusion_control_owner",
        ),
        schema="jarvis",
    )
    op.create_table(
        "passage_exclusions",
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("control_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("passage_id"),
        sa.ForeignKeyConstraint(
            ["passage_id", "owner_id"],
            ["jarvis.passages.id", "jarvis.passages.owner_id"],
            name="exclusion_passage_owner",
        ),
        sa.ForeignKeyConstraint(
            ["control_id", "owner_id"],
            ["jarvis.control_receipts.id", "jarvis.control_receipts.owner_id"],
            name="passage_exclusion_control_owner",
        ),
        schema="jarvis",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON jarvis.control_receipts, "
        "jarvis.source_exclusions, jarvis.passage_exclusions, jarvis.feedback_receipts TO jarvis_runtime"
    )


def downgrade():
    op.drop_table("feedback_receipts", schema="jarvis")
    op.drop_constraint("call_feedback_parent", "model_calls", schema="jarvis", type_="foreignkey")
    op.drop_constraint("call_owner", "model_calls", schema="jarvis", type_="unique")
    op.drop_column("model_calls", "feedback_parent_id", schema="jarvis")
    op.drop_column("model_calls", "policy_revision", schema="jarvis")
    op.drop_column("model_calls", "request_hash", schema="jarvis")
    op.drop_table("passage_exclusions", schema="jarvis")
    op.drop_table("source_exclusions", schema="jarvis")
    op.drop_table("control_receipts", schema="jarvis")
