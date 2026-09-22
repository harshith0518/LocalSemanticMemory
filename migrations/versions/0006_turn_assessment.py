"""Owned, bounded semantic turn decisions without retaining skipped questions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_turn_assessment"
down_revision = "0005_user_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "turn_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="running", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("decision", postgresql.JSONB(), nullable=True),
        sa.Column("call_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["jarvis.policies.owner_id"]),
        sa.UniqueConstraint("owner_id", "message_id", name="assessment_owner_message"),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="assessment_request_hash"),
        sa.CheckConstraint("policy_revision >= 0", name="assessment_policy_revision"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 4", name="assessment_attempts"),
        sa.CheckConstraint("status IN ('running', 'ready', 'failed')", name="assessment_status"),
        schema="jarvis",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON jarvis.turn_assessments TO jarvis_runtime")


def downgrade():
    op.drop_table("turn_assessments", schema="jarvis")
