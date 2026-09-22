from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Rebuildable expression indexes; canonical records acquire no derived content fields.
SOURCE_SEARCH_SQL = (
    "to_tsvector('english'::regconfig, (raw_text || ' '::text) || "
    "COALESCE(formatted_text, ''::text)) || "
    "to_tsvector('simple'::regconfig, (raw_text || ' '::text) || "
    "COALESCE(formatted_text, ''::text))"
)
CLAIM_SEARCH_SQL = (
    "jsonb_to_tsvector('english'::regconfig, content, "
    '\'["string","numeric","boolean"]\'::jsonb) || '
    'jsonb_to_tsvector(\'simple\'::regconfig, content, \'["string","numeric","boolean"]\'::jsonb)'
)


class Base(DeclarativeBase):
    metadata = MetaData(schema="jarvis")


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (CheckConstraint("revision >= 0", name="policy_revision_nonnegative"),)

    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, server_default="0")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("sources_search_idx", text(SOURCE_SEARCH_SQL), postgresql_using="gin"),
        UniqueConstraint("owner_id", "source_key", "revision", name="source_observation_revision"),
        UniqueConstraint("id", "owner_id", "revision", name="source_owner_revision"),
        CheckConstraint("revision > 0", name="source_revision_positive"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="source_sha256"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    source_key: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(24), server_default="unknown")
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    raw_text: Mapped[str] = mapped_column(Text)
    formatted_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capture_metadata: Mapped[dict | None] = mapped_column(JSONB)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "owner_id", "expected_source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="job_source_owner_revision",
        ),
        UniqueConstraint("owner_id", "idempotency_key", name="job_owner_idempotency"),
        UniqueConstraint("id", "owner_id", name="job_owner"),
        CheckConstraint("attempts >= 0", name="job_attempts_nonnegative"),
        CheckConstraint("expected_policy_revision >= 0", name="job_policy_revision_nonnegative"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="job_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    source_id: Mapped[UUID]
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    expected_source_revision: Mapped[int] = mapped_column(Integer)
    expected_policy_revision: Mapped[int] = mapped_column(Integer)
    requested: Mapped[bool] = mapped_column(Boolean, server_default="false")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "owner_id", "source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="passage_source_owner_revision",
        ),
        UniqueConstraint("id", "owner_id", name="passage_owner"),
        UniqueConstraint(
            "source_id", "source_revision", "variant", "start", "end", name="passage_location"
        ),
        CheckConstraint("variant IN ('raw', 'formatted')", name="passage_variant"),
        CheckConstraint('start >= 0 AND "end" > start', name="passage_offsets"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID]
    source_id: Mapped[UUID]
    source_revision: Mapped[int] = mapped_column(Integer)
    variant: Mapped[str] = mapped_column(String(16))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    exact_text: Mapped[str] = mapped_column(Text)


class ClaimRecord(Base):
    __tablename__ = "claim_revisions"
    __table_args__ = (
        Index("claims_search_idx", text(CLAIM_SEARCH_SQL), postgresql_using="gin"),
        UniqueConstraint("id", "owner_id", name="claim_revision_owner"),
        UniqueConstraint("claim_id", "owner_id", "revision", name="claim_identity_revision"),
        CheckConstraint("revision > 0", name="claim_revision_positive"),
        CheckConstraint("policy_revision >= 0", name="claim_policy_revision_nonnegative"),
        CheckConstraint(
            "lifecycle IN ('active', 'superseded', 'corrected', 'excluded')", name="claim_lifecycle"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    claim_id: Mapped[UUID]
    revision: Mapped[int] = mapped_column(Integer)
    policy_revision: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    lifecycle: Mapped[str] = mapped_column(String(16), server_default="active")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["claim_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="evidence_claim_owner",
        ),
        ForeignKeyConstraint(
            ["passage_id", "owner_id"],
            ["jarvis.passages.id", "jarvis.passages.owner_id"],
            name="evidence_passage_owner",
        ),
        UniqueConstraint("claim_revision_id", "position", name="evidence_position"),
        CheckConstraint("position >= 0", name="evidence_position_nonnegative"),
    )

    claim_revision_id: Mapped[UUID] = mapped_column(primary_key=True)
    passage_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    position: Mapped[int] = mapped_column(Integer)


class ProcessingReceipt(Base):
    __tablename__ = "processing_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="receipt_job_owner",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    lease_token: Mapped[UUID]
    result: Mapped[dict] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClaimRelation(Base):
    __tablename__ = "claim_relations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["from_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="relation_from_owner",
        ),
        ForeignKeyConstraint(
            ["to_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="relation_to_owner",
        ),
        ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="relation_job_owner",
        ),
        CheckConstraint(
            "kind IN ('supports', 'supersedes', 'corrects', 'disputes')", name="relation_kind"
        ),
        CheckConstraint("from_revision_id <> to_revision_id", name="relation_distinct"),
    )
    from_revision_id: Mapped[UUID] = mapped_column(primary_key=True)
    to_revision_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner_id: Mapped[UUID]
    job_id: Mapped[UUID]


class ModelBudget(Base):
    __tablename__ = "model_budgets"
    __table_args__ = (CheckConstraint("requests >= 0 AND tokens >= 0", name="budget_nonnegative"),)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, server_default="0")
    tokens: Mapped[int] = mapped_column(Integer, server_default="0")


class ModelCall(Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="call_owner"),
        ForeignKeyConstraint(
            ["job_id", "owner_id"],
            ["jarvis.jobs.id", "jarvis.jobs.owner_id"],
            name="call_job_owner",
        ),
        CheckConstraint("reserved_tokens > 0", name="call_reservation_positive"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND elapsed_ms >= 0",
            name="call_usage_nonnegative",
        ),
        CheckConstraint("status IN ('reserved', 'succeeded', 'failed')", name="call_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    budget_key: Mapped[str] = mapped_column(ForeignKey("jarvis.model_budgets.key"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    job_id: Mapped[UUID | None]
    lease_token: Mapped[UUID | None]
    request_hash: Mapped[str | None] = mapped_column(String(64))
    policy_revision: Mapped[int | None] = mapped_column(Integer)
    feedback_parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("jarvis.model_calls.id"))
    configured_model: Mapped[str] = mapped_column(String(128))
    returned_model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="reserved")
    error_code: Mapped[str | None] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TurnAssessment(Base):
    """Bounded decision receipt; skipped message text is never retained."""

    __tablename__ = "turn_assessments"
    __table_args__ = (
        UniqueConstraint("owner_id", "message_id", name="assessment_owner_message"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="assessment_request_hash"),
        CheckConstraint("policy_revision >= 0", name="assessment_policy_revision"),
        CheckConstraint("attempts BETWEEN 0 AND 4", name="assessment_attempts"),
        CheckConstraint("status IN ('running', 'ready', 'failed')", name="assessment_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    message_id: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    policy_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    decision: Mapped[dict | None] = mapped_column(JSONB)
    call_ids: Mapped[list] = mapped_column(JSONB, server_default="[]")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ControlReceipt(Base):
    __tablename__ = "control_receipts"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="control_owner"),
        ForeignKeyConstraint(
            ["target_revision_id", "owner_id"],
            ["jarvis.claim_revisions.id", "jarvis.claim_revisions.owner_id"],
            name="control_target_owner",
        ),
        CheckConstraint("action IN ('correct', 'world_change', 'forget')", name="control_action"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="control_request_hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    target_revision_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(16))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceExclusion(Base):
    __tablename__ = "source_exclusions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "owner_id", "source_revision"],
            ["jarvis.sources.id", "jarvis.sources.owner_id", "jarvis.sources.revision"],
            name="exclusion_source_owner_revision",
        ),
        ForeignKeyConstraint(
            ["control_id", "owner_id"],
            ["jarvis.control_receipts.id", "jarvis.control_receipts.owner_id"],
            name="source_exclusion_control_owner",
        ),
    )
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[UUID]
    control_id: Mapped[UUID]


class PassageExclusion(Base):
    __tablename__ = "passage_exclusions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["passage_id", "owner_id"],
            ["jarvis.passages.id", "jarvis.passages.owner_id"],
            name="exclusion_passage_owner",
        ),
        ForeignKeyConstraint(
            ["control_id", "owner_id"],
            ["jarvis.control_receipts.id", "jarvis.control_receipts.owner_id"],
            name="passage_exclusion_control_owner",
        ),
    )
    passage_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    control_id: Mapped[UUID]


class FeedbackReceipt(Base):
    __tablename__ = "feedback_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["call_id", "owner_id"],
            ["jarvis.model_calls.id", "jarvis.model_calls.owner_id"],
            name="feedback_call_owner",
        ),
        CheckConstraint("diagnosis IN ('retrieval', 'generation')", name="feedback_diagnosis"),
        CheckConstraint("status IN ('started', 'succeeded', 'failed')", name="feedback_status"),
    )
    call_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    diagnosis: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="started")
