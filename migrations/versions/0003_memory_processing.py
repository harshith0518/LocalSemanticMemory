"""Add bounded memory processing, revision relationships and provider accounting."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_memory_processing"
down_revision = "0002_evidence_contracts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "jobs",
        sa.Column("requested", sa.Boolean(), server_default="false", nullable=False),
        schema="jarvis",
    )
    op.add_column("jobs", sa.Column("lease_token", sa.Uuid(), nullable=True), schema="jarvis")
    op.add_column(
        "jobs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True), schema="jarvis"
    )
    op.add_column(
        "jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), schema="jarvis"
    )
    op.add_column(
        "jobs", sa.Column("error_code", sa.String(length=40), nullable=True), schema="jarvis"
    )
    op.create_unique_constraint("job_owner", "jobs", ["id", "owner_id"], schema="jarvis")
    op.create_table(
        "model_budgets",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("requests >= 0 AND tokens >= 0", name="budget_nonnegative"),
        sa.PrimaryKeyConstraint("key"),
        schema="jarvis",
    )
    op.create_table(
        "claim_relations",
        sa.Column("from_revision_id", sa.Uuid(), nullable=False),
        sa.Column("to_revision_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('supports', 'supersedes', 'corrects', 'disputes')", name="relation_kind"
        ),
        sa.CheckConstraint("from_revision_id <> to_revision_id", name="relation_distinct"),
        sa.ForeignKeyConstraint(
            ["from_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="relation_from_owner",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="relation_job_owner",
        ),
        sa.ForeignKeyConstraint(
            ["to_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="relation_to_owner",
        ),
        sa.PrimaryKeyConstraint("from_revision_id", "to_revision_id", "kind"),
        schema="jarvis",
    )
    op.create_table(
        "model_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("budget_key", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("configured_model", sa.String(length=128), nullable=False),
        sa.Column("returned_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="reserved", nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('reserved', 'succeeded', 'failed')", name="call_status"),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND elapsed_ms >= 0",
            name="call_usage_nonnegative",
        ),
        sa.CheckConstraint("reserved_tokens > 0", name="call_reservation_positive"),
        sa.ForeignKeyConstraint(
            ["budget_key"],
            ["jarvis.model_budgets.key"],
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="call_job_owner",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["jarvis.policies.owner_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="jarvis",
    )
    op.create_table(
        "processing_receipts",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="receipt_job_owner",
        ),
        sa.PrimaryKeyConstraint("job_id"),
        schema="jarvis",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON jarvis.processing_receipts, "
        "jarvis.claim_relations, jarvis.model_calls, jarvis.model_budgets TO jarvis_runtime"
    )


def downgrade():
    op.drop_table("processing_receipts", schema="jarvis")
    op.drop_table("model_calls", schema="jarvis")
    op.drop_table("claim_relations", schema="jarvis")
    op.drop_table("model_budgets", schema="jarvis")
    op.drop_constraint("job_owner", "jobs", schema="jarvis", type_="unique")
    op.drop_column("jobs", "error_code", schema="jarvis")
    op.drop_column("jobs", "finished_at", schema="jarvis")
    op.drop_column("jobs", "lease_until", schema="jarvis")
    op.drop_column("jobs", "lease_token", schema="jarvis")
    op.drop_column("jobs", "requested", schema="jarvis")
