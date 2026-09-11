"""Minimal source, job and policy records; no memory processing yet."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("owner_id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("revision >= 0", name="policy_revision_nonnegative"),
        schema="jarvis",
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("jarvis.policies.owner_id"), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("formatted_text", sa.Text()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("capture_metadata", postgresql.JSONB()),
        sa.UniqueConstraint(
            "owner_id", "source_key", "revision", name="source_observation_revision"
        ),
        sa.UniqueConstraint("id", "owner_id", "revision", name="source_owner_revision"),
        sa.CheckConstraint("revision > 0", name="source_revision_positive"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="source_sha256"),
        schema="jarvis",
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("jarvis.policies.owner_id"), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expected_source_revision", sa.Integer(), nullable=False),
        sa.Column("expected_policy_revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id", "owner_id", "expected_source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="job_source_owner_revision",
        ),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="job_owner_idempotency"),
        sa.CheckConstraint("attempts >= 0", name="job_attempts_nonnegative"),
        sa.CheckConstraint("expected_policy_revision >= 0", name="job_policy_revision_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="job_status",
        ),
        schema="jarvis",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON jarvis.policies, jarvis.sources, jarvis.jobs TO jarvis_runtime"
    )


def downgrade() -> None:
    op.drop_table("jobs", schema="jarvis")
    op.drop_table("sources", schema="jarvis")
    op.drop_table("policies", schema="jarvis")
