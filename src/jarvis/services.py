"""One policy and transaction path for adapters and future worker operations."""

import hashlib
import json
from contextlib import contextmanager
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jarvis.contracts import (
    ClaimRevision,
    ClaimWrite,
    ObservationInput,
    ObservationWrite,
    SourceObservation,
    SupportingPassage,
    parse_contract,
)
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import (
    IMPORT_PREFIX,
    ImportItem,
    ImportOptions,
    ImportReceipt,
    JobState,
    SourceInspection,
    SourceLookup,
    SourcePage,
    SourceQuery,
    SourceSummary,
    parse_dictations,
    same_json,
    source_key,
)
from jarvis.models import ClaimEvidence, ClaimRecord, Job, Passage, Policy, Source
from jarvis.policy import LocalIdentity, Mode, RequestContext

PROBE_KEY = "bootstrap:synthetic:v1"
PROBE_RAW = "Synthetic bootstrap observation: the blue box contains seven marbles."
PROBE_FORMATTED = "The blue box contains seven marbles."


def content_hash(raw: str, formatted: str | None) -> str:
    """Unambiguous UTF-8 pair hash, distinct from observation identity."""
    pair = json.dumps([raw, formatted], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(pair.encode("utf-8")).hexdigest()


class Service:
    def __init__(self, engine: Engine, identity: LocalIdentity | None = None):
        self.engine = engine
        self.identity = identity or LocalIdentity()
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

    def write_probe(self, context: RequestContext | None = None) -> dict:
        context = context or self.identity.context(Mode.NORMAL)
        self._authorize(context)
        with Session(self.engine) as session, session.begin():
            session.execute(
                insert(Policy).values(owner_id=context.owner_id).on_conflict_do_nothing()
            )
            policy = session.scalars(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            ).one()
            existing = self._probe(session, context)
            if existing is not None:
                return existing
            source = Source(
                owner_id=context.owner_id,
                source_key=PROBE_KEY,
                kind="synthetic",
                raw_text=PROBE_RAW,
                formatted_text=PROBE_FORMATTED,
                content_hash=content_hash(PROBE_RAW, PROBE_FORMATTED),
            )
            session.add(source)
            session.flush()
            session.add(
                Job(
                    owner_id=context.owner_id,
                    source_id=source.id,
                    idempotency_key=PROBE_KEY,
                    expected_source_revision=source.revision,
                    expected_policy_revision=policy.revision,
                )
            )
            session.flush()
            return self._probe(session, context)

    def read_probe(self, context: RequestContext | None = None) -> dict | None:
        context = context or self.identity.context(Mode.NORMAL)
        self._authorize(context)
        with Session(self.engine) as session:
            return self._probe(session, context)

    @staticmethod
    def _probe(session: Session, context: RequestContext) -> dict | None:
        pair = session.execute(
            select(Source, Job)
            .join(Job, (Job.source_id == Source.id) & (Job.owner_id == Source.owner_id))
            .where(
                Source.owner_id == context.owner_id,
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

    def _authorize(self, context: RequestContext, *, saved: bool = True) -> None:
        if not isinstance(context, RequestContext) or context.owner_id != self.identity.owner_id:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        if not isinstance(context.mode, Mode):
            raise ApplicationError(ErrorCode.INVALID_MODE)
        if saved:
            context.require_saved_access()

    @contextmanager
    def _session(self, context: RequestContext, *, write: bool = False):
        self._authorize(context)  # Must precede session creation, even for failed inputs.
        try:
            with Session(self.engine) as session:
                if write:
                    with session.begin():
                        yield session
                else:
                    yield session
        except SQLAlchemyError:
            raise ApplicationError(ErrorCode.DATABASE_UNAVAILABLE) from None

    def validate_observation(self, context: RequestContext, payload: object) -> ObservationInput:
        self._authorize(context, saved=False)
        # Pure current-input validation: no retained context, telemetry, file or DB access.
        return parse_contract(ObservationInput, payload)

    @staticmethod
    def _source_contract(source: Source) -> SourceObservation:
        return SourceObservation.model_validate(
            {column.name: getattr(source, column.name) for column in Source.__table__.columns}
        )

    def read_source(self, context: RequestContext, source_id: UUID) -> SourceObservation:
        with self._session(context) as session:
            source = session.scalar(
                select(Source).where(Source.id == source_id, Source.owner_id == context.owner_id)
            )
            if source is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            return self._source_contract(source)

    @staticmethod
    def _policy(session: Session, context: RequestContext, expected: int, *, lock: bool) -> Policy:
        query = select(Policy).where(Policy.owner_id == context.owner_id)
        policy = session.scalar(query.with_for_update() if lock else query)
        if policy is None or policy.revision != expected:
            raise ApplicationError(ErrorCode.STALE_REVISION)
        return policy

    def save_observation(self, context: RequestContext, payload: object) -> SourceObservation:
        self._authorize(context)
        command = parse_contract(ObservationWrite, payload)
        data = command.observation
        if data.source_key.startswith(IMPORT_PREFIX):
            # Import identity is immutable; generic writes cannot bypass conflict detection.
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        with self._session(context, write=True) as session:
            session.execute(
                insert(Policy).values(owner_id=context.owner_id).on_conflict_do_nothing()
            )
            policy = self._policy(session, context, command.expected_policy_revision, lock=True)
            latest = session.scalar(
                select(Source)
                .where(Source.owner_id == context.owner_id, Source.source_key == data.source_key)
                .order_by(Source.revision.desc())
                .limit(1)
            )
            current = latest.revision if latest is not None else 0
            if command.expected_source_revision != current:
                raise ApplicationError(ErrorCode.STALE_REVISION)
            [(source, _)] = self._save_sources(session, context, policy, [(data, current + 1)])
            return self._source_contract(source)

    @staticmethod
    def _save_sources(
        session: Session,
        context: RequestContext,
        policy: Policy,
        observations: list[tuple[ObservationInput, int]],
    ) -> list[tuple[Source, Job]]:
        sources = [
            Source(
                owner_id=context.owner_id,
                revision=revision,
                content_hash=content_hash(data.raw_text, data.formatted_text),
                **data.model_dump(),
            )
            for data, revision in observations
        ]
        session.add_all(sources)
        session.flush()
        jobs = [
            Job(
                owner_id=context.owner_id,
                source_id=source.id,
                idempotency_key=f"source:{source.id}",
                expected_source_revision=source.revision,
                expected_policy_revision=policy.revision,
            )
            for source in sources
        ]
        session.add_all(jobs)
        session.flush()
        return list(zip(sources, jobs, strict=True))

    @staticmethod
    def _job_contract(job: Job) -> JobState:
        return JobState.model_validate({name: getattr(job, name) for name in JobState.model_fields})

    def import_observations(
        self, context: RequestContext, options: object, payload: str | bytes
    ) -> ImportReceipt:
        self._authorize(context)  # Before parsing content or connecting, including failure paths.
        command = parse_contract(ImportOptions, options)
        data = parse_dictations(command.namespace, payload)
        with self._session(context, write=True) as session:
            session.execute(
                insert(Policy).values(owner_id=context.owner_id).on_conflict_do_nothing()
            )
            policy = self._policy(session, context, command.expected_policy_revision, lock=True)
            existing = {
                source.source_key: (source, job)
                for source, job in session.execute(
                    select(Source, Job)
                    .outerjoin(
                        Job,
                        (Job.source_id == Source.id)
                        & (Job.owner_id == Source.owner_id)
                        & (Job.idempotency_key == func.concat("source:", Source.id)),
                    )
                    .where(
                        Source.owner_id == context.owner_id,
                        Source.source_key.in_([item.source_key for item in data]),
                    )
                    .distinct(Source.source_key)
                    .order_by(Source.source_key, Source.revision.desc())
                )
            }
            for item in data:
                if pair := existing.get(item.source_key):
                    source, job = pair
                    if not all(
                        same_json(getattr(source, field), value)
                        for field, value in item.model_dump().items()
                    ):
                        raise ApplicationError(ErrorCode.IMPORT_CONFLICT)
                    if job is None:
                        raise ApplicationError(ErrorCode.OPERATION_FAILED)
            created = self._save_sources(
                session,
                context,
                policy,
                [(item, 1) for item in data if item.source_key not in existing],
            )
            pairs = {**existing, **{source.source_key: (source, job) for source, job in created}}
            return ImportReceipt(
                namespace=command.namespace,
                policy_revision=policy.revision,
                created=len(created),
                unchanged=len(existing),
                observations=tuple(
                    ImportItem(
                        record_id=item.source_key.rsplit(":", 1)[1],
                        source_id=pairs[item.source_key][0].id,
                        revision=pairs[item.source_key][0].revision,
                        job=self._job_contract(pairs[item.source_key][1]),
                        outcome="unchanged" if item.source_key in existing else "created",
                    )
                    for item in data
                ),
            )

    def list_sources(self, context: RequestContext, payload: object) -> SourcePage:
        self._authorize(context)
        query = parse_contract(SourceQuery, payload)
        with self._session(context) as session:
            policy = session.get(Policy, context.owner_id)
            statement = select(
                *(getattr(Source, name) for name in SourceSummary.model_fields)
            ).where(
                Source.owner_id == context.owner_id,
                Source.source_key.startswith(f"{IMPORT_PREFIX}{query.namespace}:", autoescape=True),
            )
            if query.after is not None:
                statement = statement.where(
                    Source.source_key > source_key(query.namespace, query.after)
                )
            rows = (
                session.execute(
                    statement.distinct(Source.source_key)
                    .order_by(Source.source_key, Source.revision.desc())
                    .limit(query.limit + 1)
                )
                .mappings()
                .all()
            )
            return SourcePage(
                namespace=query.namespace,
                policy_revision=policy.revision if policy else 0,
                observations=tuple(
                    SourceSummary.model_validate(row) for row in rows[: query.limit]
                ),
                next_after=rows[query.limit - 1]["source_key"].rsplit(":", 1)[1]
                if len(rows) > query.limit
                else None,
            )

    def inspect_source(self, context: RequestContext, source_id: UUID | str) -> SourceInspection:
        self._authorize(context)
        source_id = parse_contract(SourceLookup, {"source_id": source_id}).source_id
        with self._session(context) as session:
            source = session.scalar(
                select(Source).where(Source.id == source_id, Source.owner_id == context.owner_id)
            )
            if source is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            latest = session.scalar(
                select(func.max(Source.revision)).where(
                    Source.owner_id == context.owner_id, Source.source_key == source.source_key
                )
            )
            job = session.scalar(
                select(Job).where(
                    Job.owner_id == context.owner_id,
                    Job.source_id == source.id,
                    Job.idempotency_key == f"source:{source.id}",
                )
            )
            return SourceInspection(
                observation=self._source_contract(source),
                latest_revision=latest,
                job=self._job_contract(job) if job else None,
            )

    @staticmethod
    def _support(session: Session, context: RequestContext, command: ClaimWrite) -> None:
        sources = {
            source.id: source
            for source in session.scalars(
                select(Source).where(
                    Source.owner_id == context.owner_id,
                    Source.id.in_({passage.source_id for passage in command.passages}),
                )
            )
        }
        latest = dict(
            session.execute(
                select(Source.source_key, func.max(Source.revision))
                .where(
                    Source.owner_id == context.owner_id,
                    Source.source_key.in_({source.source_key for source in sources.values()}),
                )
                .group_by(Source.source_key)
            ).all()
        )
        for passage in command.passages:
            source = sources.get(passage.source_id)
            if source is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            if (
                source.revision != passage.source_revision
                or source.revision != latest[source.source_key]
            ):
                raise ApplicationError(ErrorCode.STALE_REVISION)
            if source.kind not in {"user_message", "imported_dictation", "synthetic"}:
                raise ApplicationError(ErrorCode.INELIGIBLE_SOURCE)
            variant = source.raw_text if passage.variant == "raw" else source.formatted_text
            if (
                variant is None
                or passage.end > len(variant)
                or variant[passage.start : passage.end] != passage.exact_text
            ):
                raise ApplicationError(ErrorCode.INVALID_PASSAGE)

    @staticmethod
    def _claim_revision(session: Session, context: RequestContext, command: ClaimWrite) -> int:
        if command.claim_id is None:
            return 1
        current = session.scalar(
            select(func.max(ClaimRecord.revision)).where(
                ClaimRecord.owner_id == context.owner_id, ClaimRecord.claim_id == command.claim_id
            )
        )
        if current is None:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        if current != command.expected_claim_revision:
            raise ApplicationError(ErrorCode.STALE_REVISION)
        return current + 1

    def validate_claim(self, context: RequestContext, payload: object) -> ClaimWrite:
        self._authorize(context)
        command = parse_contract(ClaimWrite, payload)
        with self._session(context) as session:
            self._policy(session, context, command.expected_policy_revision, lock=False)
            self._support(session, context, command)
            self._claim_revision(session, context, command)
        # A validation receipt is NOT permission to commit without fresh checks.
        return command

    def commit_claim(self, context: RequestContext, payload: object) -> ClaimRevision:
        self._authorize(context)
        command = parse_contract(ClaimWrite, payload)
        with self._session(context, write=True) as session:
            self._policy(session, context, command.expected_policy_revision, lock=True)
            self._support(session, context, command)
            revision = self._claim_revision(session, context, command)
            record = ClaimRecord(
                owner_id=context.owner_id,
                claim_id=command.claim_id or uuid4(),
                revision=revision,
                policy_revision=command.expected_policy_revision,
                content=command.content.model_dump(mode="json"),
            )
            session.add(record)
            session.flush()
            for position, reference in enumerate(command.passages):
                passage_id = session.scalar(
                    insert(Passage)
                    .values(id=uuid4(), owner_id=context.owner_id, **reference.model_dump())
                    .on_conflict_do_nothing(constraint="passage_location")
                    .returning(Passage.id)
                )
                if passage_id is None:
                    passage_id = session.scalar(
                        select(Passage.id).where(
                            Passage.owner_id == context.owner_id,
                            Passage.source_id == reference.source_id,
                            Passage.source_revision == reference.source_revision,
                            Passage.variant == reference.variant,
                            Passage.start == reference.start,
                            Passage.end == reference.end,
                            Passage.exact_text == reference.exact_text,
                        )
                    )
                    if passage_id is None:
                        raise ApplicationError(ErrorCode.INVALID_PASSAGE)
                session.add(
                    ClaimEvidence(
                        claim_revision_id=record.id,
                        passage_id=passage_id,
                        owner_id=context.owner_id,
                        position=position,
                    )
                )
            session.flush()
            return self._claim_contract(session, context, record)

    @staticmethod
    def _claim_contract(
        session: Session, context: RequestContext, record: ClaimRecord
    ) -> ClaimRevision:
        passages = session.scalars(
            select(Passage)
            .join(
                ClaimEvidence,
                (ClaimEvidence.passage_id == Passage.id)
                & (ClaimEvidence.owner_id == Passage.owner_id),
            )
            .where(
                ClaimEvidence.claim_revision_id == record.id,
                ClaimEvidence.owner_id == context.owner_id,
            )
            .order_by(ClaimEvidence.position)
        ).all()
        return ClaimRevision(
            **{
                column.name: getattr(record, column.name)
                for column in ClaimRecord.__table__.columns
            },
            passages=tuple(
                SupportingPassage(
                    source_id=p.source_id,
                    source_revision=p.source_revision,
                    variant=p.variant,
                    start=p.start,
                    end=p.end,
                    exact_text=p.exact_text,
                )
                for p in passages
            ),
        )

    def read_claim(self, context: RequestContext, revision_id: UUID) -> ClaimRevision:
        with self._session(context) as session:
            record = session.scalar(
                select(ClaimRecord).where(
                    ClaimRecord.id == revision_id, ClaimRecord.owner_id == context.owner_id
                )
            )
            if record is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            return self._claim_contract(session, context, record)
