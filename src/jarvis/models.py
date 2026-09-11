from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
        UniqueConstraint("owner_id", "source_key", "revision", name="source_observation_revision"),
        UniqueConstraint("id", "owner_id", "revision", name="source_owner_revision"),
        CheckConstraint("revision > 0", name="source_revision_positive"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="source_sha256"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("jarvis.policies.owner_id"))
    source_key: Mapped[str] = mapped_column(String(255))
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
