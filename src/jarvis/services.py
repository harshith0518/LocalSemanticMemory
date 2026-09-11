"""Shared operations. Only the fixed synthetic probe can write in S03."""

import hashlib
import json

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jarvis.config import LOCAL_OWNER
from jarvis.models import Job, Policy, Source

PROBE_KEY = "bootstrap:synthetic:v1"
PROBE_RAW = "Synthetic bootstrap observation: the blue box contains seven marbles."
PROBE_FORMATTED = "The blue box contains seven marbles."


def content_hash(raw: str, formatted: str | None) -> str:
    """Unambiguous UTF-8 pair hash, distinct from observation identity."""
    pair = json.dumps([raw, formatted], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(pair.encode("utf-8")).hexdigest()


class Service:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.expected_revision = ScriptDirectory.from_config(
            Config("alembic.ini")
        ).get_current_head()

    def health(self) -> dict:
        return {"status": "alive"}

    def ready(self) -> dict:
        try:
            with self.engine.connect() as connection:
                revisions = connection.scalars(
                    text("SELECT version_num FROM jarvis.alembic_version")
                ).all()
                vector = connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
            if revisions != [self.expected_revision]:
                return {"status": "not_ready", "reason": "schema_mismatch"}
            if not vector:
                return {"status": "not_ready", "reason": "extension_missing"}
            return {"status": "ready", "schema": self.expected_revision, "pgvector": vector}
        except SQLAlchemyError:
            # Never return/log connection strings, SQL values or raw driver errors.
            return {"status": "not_ready", "reason": "database_unavailable"}

    def write_probe(self) -> dict:
        with Session(self.engine) as session, session.begin():
            session.execute(insert(Policy).values(owner_id=LOCAL_OWNER).on_conflict_do_nothing())
            policy = session.scalars(
                select(Policy).where(Policy.owner_id == LOCAL_OWNER).with_for_update()
            ).one()
            existing = self._probe(session)
            if existing is not None:
                return existing
            source = Source(
                owner_id=LOCAL_OWNER,
                source_key=PROBE_KEY,
                raw_text=PROBE_RAW,
                formatted_text=PROBE_FORMATTED,
                content_hash=content_hash(PROBE_RAW, PROBE_FORMATTED),
            )
            session.add(source)
            session.flush()
            session.add(
                Job(
                    owner_id=LOCAL_OWNER,
                    source_id=source.id,
                    idempotency_key=PROBE_KEY,
                    expected_source_revision=source.revision,
                    expected_policy_revision=policy.revision,
                )
            )
            session.flush()
            return self._probe(session)

    def read_probe(self) -> dict | None:
        with Session(self.engine) as session:
            return self._probe(session)

    @staticmethod
    def _probe(session: Session) -> dict | None:
        pair = session.execute(
            select(Source, Job)
            .join(Job, (Job.source_id == Source.id) & (Job.owner_id == Source.owner_id))
            .where(
                Source.owner_id == LOCAL_OWNER,
                Source.source_key == PROBE_KEY,
                Source.revision == 1,
                Job.idempotency_key == PROBE_KEY,
            )
        ).one_or_none()
        if pair is None:
            return None
        source, job = pair
        # Complete persisted source/job state makes replacement checks meaningful.
        return {
            "source": {
                column.name: getattr(source, column.name) for column in Source.__table__.columns
            },
            "job": {column.name: getattr(job, column.name) for column in Job.__table__.columns},
        }
