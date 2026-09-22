"""Shared memory application operations. Adapters and workers own no SQL."""

import json
from datetime import timedelta
from functools import cache
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import case, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import TSVECTOR, insert
from sqlalchemy.orm import aliased

from jarvis.contracts import ClaimWrite, ObservationInput, parse_contract
from jarvis.controls import blocked_sources
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.extraction import (
    LEASE_SECONDS,
    MAX_ATTEMPTS,
    MAX_CONTEXT_CLAIMS,
    PROMPT_VERSION,
    ExtractionPacket,
    MemoryQuery,
    ProcessingRequest,
    messages,
    parse_proposal,
)
from jarvis.imports import parse_dictations, same_json
from jarvis.metrics import measured, stage
from jarvis.models import (
    CLAIM_SEARCH_SQL,
    ClaimEvidence,
    ClaimRecord,
    ClaimRelation,
    Job,
    ModelBudget,
    ModelCall,
    Passage,
    Policy,
    ProcessingReceipt,
    Source,
)
from jarvis.providers import MAX_INPUT_BYTES, MAX_REQUESTS, MAX_TOTAL_TOKENS


@cache
def _synthetic_sources():
    """Only checked-in public fixtures are cached; never a user's saved observations."""
    return (
        tuple(
            parse_dictations("fixture", Path("data/synthetic/sample-dictations.jsonl").read_bytes())
        )
        + tuple(
            parse_contract(ObservationInput, row)
            for row in json.loads(Path("data/synthetic/control-observations.json").read_text())
        )
        + tuple(parse_dictations("fixture", Path("data/synthetic/corpus-540.jsonl").read_bytes()))
    )


class ProcessingOperations:
    """Part of Service; split by responsibility, sharing its policy/session/evidence helpers."""

    def _provider_gate(self, context):
        self._authorize(context)
        if not self.extractor.enabled:
            raise ApplicationError(ErrorCode.PROVIDER_DISABLED)

    def _trial_source(self, source, *, live=None, unfamiliar=None):
        if not (self.extractor.live if live is None else live):
            return  # Only trusted dependency injection in tests; never a request flag.
        approved = (
            self.extractor.unfamiliar_mode or getattr(self.extractor, "unfamiliar_sources", False)
            if unfamiliar is None
            else unfamiliar
        )
        if approved:
            return  # Explicit operator approval, never inferred from source metadata.
        allowed = _synthetic_sources()
        # Compare all original fields, not a caller-supplied namespace/hash/synthetic label.
        fields = ("kind", "raw_text", "formatted_text", "captured_at", "capture_metadata")
        if not any(
            all(same_json(getattr(source, k), getattr(row, k)) for k in fields) for row in allowed
        ):
            raise ApplicationError(ErrorCode.TRIAL_INPUT_DENIED)

    @staticmethod
    def _namespace_sources(context, namespace):
        return select(Source).where(
            Source.owner_id == context.owner_id,
            Source.source_key.startswith(f"import:{namespace}:", autoescape=True),
        )

    @measured("queue")
    def request_processing(self, context, payload):
        self._provider_gate(context)  # Before parsing, source reads, or queue writes.
        command = parse_contract(ProcessingRequest, payload)
        with self._session(context, write=True) as session:
            self._policy(session, context, command.expected_policy_revision, lock=True)
            sources = session.scalars(
                self._namespace_sources(context, command.namespace).where(
                    ~Source.id.in_(blocked_sources(context))
                )
            ).all()
            for source in sources:
                self._trial_source(source)
            jobs = session.scalars(
                select(Job).where(
                    Job.owner_id == context.owner_id,
                    Job.source_id.in_([s.id for s in sources]),
                )
            ).all()
            count = 0
            for job in jobs:
                if job.status == "failed" and command.retry_failed and job.attempts < MAX_ATTEMPTS:
                    job.status = "pending"
                    job.error_code = None
                    job.finished_at = None
                if job.status == "pending" and not job.requested:
                    job.expected_policy_revision = command.expected_policy_revision
                    job.requested = True
                    count += 1
            return {"status": "queued", "requested": count}

    def _active_memories(self, session, context, namespace):
        source_ids = self._namespace_sources(context, namespace).with_only_columns(Source.id)
        ids = (
            select(ClaimEvidence.claim_revision_id)
            .join(Passage, Passage.id == ClaimEvidence.passage_id)
            .where(ClaimEvidence.owner_id == context.owner_id, Passage.source_id.in_(source_ids))
        )
        newer = aliased(ClaimRecord)
        blocked_claims = (
            select(ClaimEvidence.claim_revision_id)
            .join(Passage, Passage.id == ClaimEvidence.passage_id)
            .where(
                ClaimEvidence.owner_id == context.owner_id,
                Passage.source_id.in_(blocked_sources(context)),
            )
        )
        return (
            select(ClaimRecord)
            .where(
                ClaimRecord.owner_id == context.owner_id,
                ClaimRecord.lifecycle == "active",
                ClaimRecord.id.in_(ids),
                ~ClaimRecord.id.in_(blocked_claims),
                ~select(newer.id)
                .where(
                    newer.owner_id == context.owner_id,
                    newer.claim_id == ClaimRecord.claim_id,
                    newer.revision > ClaimRecord.revision,
                )
                .exists(),
            )
            .order_by(ClaimRecord.id)
        )

    def _packet(self, session, context, job):
        source = session.get(Source, job.source_id)
        if source is None or source.owner_id != context.owner_id:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        if session.scalar(blocked_sources(context).where(Source.id == source.id)):
            raise ApplicationError(ErrorCode.EXCLUDED_SOURCE)
        if not source.source_key.startswith("import:"):
            raise ApplicationError(ErrorCode.INELIGIBLE_SOURCE)
        namespace = source.source_key.split(":")[1]
        latest = session.scalar(
            select(func.max(Source.revision)).where(
                Source.owner_id == context.owner_id,
                Source.source_key == source.source_key,
            )
        )
        if latest != job.expected_source_revision or source.revision != latest:
            raise ApplicationError(ErrorCode.STALE_REVISION)
        active = self._active_memories(session, context, namespace)
        count = session.scalar(select(func.count()).select_from(active.order_by(None).subquery()))
        # Small collections retain the original complete-context behavior. At scale use
        # the same lexical machinery as retrieval, with an explicit project-scope boost.
        if count > 16:
            tsquery = self._search_query(
                session, (source.raw_text + " " + (source.formatted_text or ""))[:4096]
            )
            vector = literal_column(f"({CLAIM_SEARCH_SQL})", type_=TSVECTOR())
            scope = ClaimRecord.content["scope"]["key"].astext
            scope_match = (func.length(scope) > 1) & (
                func.strpos(func.lower(source.raw_text), func.lower(scope)) > 0
            )
            active = (
                active.where(vector.op("@@")(tsquery))
                .order_by(None)
                .order_by(
                    scope_match.desc().nulls_last(),
                    func.ts_rank_cd(vector, tsquery, 32).desc(),
                    ClaimRecord.id,
                )
            )
        records = session.scalars(active.limit(min(16, MAX_CONTEXT_CLAIMS))).all()
        claims = tuple(self._claim_contract(session, context, row) for row in records)
        for claim in claims:
            self._support(
                session,
                context,
                ClaimWrite(
                    expected_policy_revision=job.expected_policy_revision,
                    content=claim.content,
                    passages=claim.passages,
                ),
            )
        ids = {source.id} | {p.source_id for claim in claims for p in claim.passages}
        sources = session.scalars(
            select(Source)
            .where(Source.owner_id == context.owner_id, Source.id.in_(ids))
            .order_by(Source.id)
        ).all()
        for item in sources:
            if not item.source_key.startswith(f"import:{namespace}:"):
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            self._trial_source(item)
        packet = ExtractionPacket(
            job_id=job.id,
            lease_token=job.lease_token,
            lease_until=job.lease_until,
            policy_revision=job.expected_policy_revision,
            namespace=namespace,
            source=self._source_contract(source),
            sources=tuple(self._source_contract(s) for s in sources),
            memories=claims,
            context_claim_count=count,
            context_bounded=count > len(claims),
        )
        # Remove whole lowest-ranked memory/support groups, never truncate a passage,
        # a qualifier, the current observation or one of its paired variants.
        while (
            packet.memories
            and len(json.dumps(messages(packet), ensure_ascii=False).encode("utf-8"))
            > MAX_INPUT_BYTES - 1024
        ):
            retained = packet.memories[:-1]
            keep = {source.id} | {p.source_id for c in retained for p in c.passages}
            packet = packet.model_copy(
                update={
                    "memories": retained,
                    "sources": tuple(s for s in packet.sources if s.id in keep),
                    "context_bounded": True,
                }
            )
        return packet

    @measured("lease")
    def lease_next(self, context, *, namespace=None):
        self._provider_gate(context)
        if namespace is not None:
            namespace = parse_contract(MemoryQuery, {"namespace": namespace}).namespace
        with self._session(context, write=True) as session:
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            if policy is None:
                return None
            now = session.scalar(select(func.clock_timestamp()))
            # One active job per owner makes reconciliation serial and reproducible.
            if session.scalar(
                select(Job.id)
                .where(
                    Job.owner_id == context.owner_id,
                    Job.status == "running",
                    Job.lease_until > now,
                )
                .limit(1)
            ):
                return None
            statement = (
                select(Job)
                .join(Source, Source.id == Job.source_id)
                .where(
                    Job.owner_id == context.owner_id,
                    Job.requested.is_(True),
                    or_(
                        Job.status == "pending",
                        (Job.status == "running") & (Job.lease_until <= now),
                    ),
                )
                .order_by(Source.source_key, Source.revision)
                .limit(1)
                .with_for_update(of=Job)
            )
            if namespace is not None:
                statement = statement.where(
                    Source.source_key.startswith(
                        f"import:{namespace}:",
                        autoescape=True,
                    )
                )
            job = session.scalar(statement)
            if job is None:
                return None
            if job.attempts >= MAX_ATTEMPTS or job.expected_policy_revision != policy.revision:
                job.status = "cancelled"
                job.error_code = (
                    ErrorCode.RETRY_LIMIT.value
                    if job.attempts >= MAX_ATTEMPTS
                    else ErrorCode.STALE_REVISION.value
                )
                job.requested = False
                job.finished_at = now
                return None
            job.attempts += 1
            job.status = "running"
            job.lease_token = uuid4()
            job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            job.error_code = None
            session.flush()
            try:
                return self._packet(session, context, job)
            except ApplicationError as error:
                job.status = "failed"
                job.error_code = error.code.value
                job.requested = False
                job.finished_at = now
                return None

    def _check_packet(self, session, context, packet):
        self._policy(session, context, packet.policy_revision, lock=True)
        job = session.scalar(
            select(Job).where(
                Job.id == packet.job_id,
                Job.owner_id == context.owner_id,
            )
        )
        now = session.scalar(select(func.clock_timestamp()))
        if (
            job is None
            or job.status != "running"
            or job.lease_token != packet.lease_token
            or job.lease_until <= now
        ):
            raise ApplicationError(ErrorCode.STALE_REVISION)
        current = self._packet(session, context, job)
        if current != packet:
            raise ApplicationError(ErrorCode.STALE_REVISION)
        return job

    def _validate_extraction(self, session, context, packet, proposal):
        targets = {claim.id: claim for claim in packet.memories}
        source_ids = {source.id for source in packet.sources}
        additions = set()
        for operation in proposal.operations:
            if not any(p.source_id == packet.source.id for p in operation.passages):
                raise ApplicationError(ErrorCode.INVALID_PASSAGE)
            if any(p.source_id not in source_ids for p in operation.passages):
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            target = targets.get(operation.target_revision_id)
            if operation.target_revision_id and target is None:
                raise ApplicationError(ErrorCode.STALE_REVISION)
            content = operation.content or target.content
            if operation.action == "add":
                key = content  # Typed equality also treats 15000 and 15000.0 alike.
                if key in additions:
                    raise ApplicationError(ErrorCode.INVALID_TRANSITION)
                additions.add(key)
            if target and any(
                getattr(content, key) != getattr(target.content, key)
                for key in ("subject", "predicate", "scope", "attribution")
            ):
                raise ApplicationError(ErrorCode.INVALID_TRANSITION)
            if operation.action == "conflict" and content.evidence_status != "disputed":
                raise ApplicationError(ErrorCode.INVALID_TRANSITION)
            self._support(
                session,
                context,
                ClaimWrite(
                    expected_policy_revision=packet.policy_revision,
                    content=content,
                    passages=operation.passages,
                ),
            )

    @measured("memory_commit")
    def commit_extraction(self, context, packet, payload):
        self._authorize(context)
        proposal = parse_proposal(payload)
        with self._session(context, write=True) as session:
            self._policy(session, context, packet.policy_revision, lock=True)
            receipt = session.get(ProcessingReceipt, packet.job_id)
            if receipt is not None:
                if (
                    receipt.owner_id != context.owner_id
                    or receipt.lease_token != packet.lease_token
                ):
                    raise ApplicationError(ErrorCode.STALE_REVISION)
                return receipt.result
            job = self._check_packet(session, context, packet)
            self._validate_extraction(session, context, packet, proposal)
            revisions = []
            for operation in proposal.operations:
                target = (
                    session.get(ClaimRecord, operation.target_revision_id)
                    if operation.target_revision_id
                    else None
                )
                content = operation.content
                passages = operation.passages
                claim_id, revision = None, 1
                if target:
                    previous = self._claim_contract(session, context, target)
                    if operation.action == "support":
                        content = previous.content
                        unique = {p.model_dump_json(): p for p in previous.passages + passages}
                        passages = tuple(unique.values())
                        if passages == previous.passages:
                            continue
                    if operation.action != "conflict":
                        claim_id, revision = target.claim_id, target.revision + 1
                        target.lifecycle = (
                            "corrected" if operation.action == "correct" else "superseded"
                        )
                    else:
                        # Both competing values remain usable only as disputed evidence.
                        disputed = previous.content.model_copy(
                            update={"evidence_status": "disputed"}
                        )
                        old = self._insert_claim(
                            session,
                            context,
                            ClaimWrite(
                                claim_id=target.claim_id,
                                expected_claim_revision=target.revision,
                                expected_policy_revision=packet.policy_revision,
                                content=disputed,
                                passages=previous.passages,
                            ),
                            target.revision + 1,
                        )
                        target.lifecycle = "superseded"
                        revisions.append(str(old.id))
                command = ClaimWrite(
                    claim_id=claim_id,
                    expected_claim_revision=revision - 1,
                    expected_policy_revision=packet.policy_revision,
                    content=content,
                    passages=passages,
                )
                # Never deduplicate independently authored observations just by text.
                existing = next(
                    (
                        c
                        for c in packet.memories
                        if c.content == command.content and set(c.passages) == set(command.passages)
                    ),
                    None,
                )
                if operation.action == "add" and existing:
                    continue
                created = self._insert_claim(session, context, command, revision)
                revisions.append(str(created.id))
                if target:
                    destination = old.id if operation.action == "conflict" else target.id
                    session.add(
                        ClaimRelation(
                            from_revision_id=created.id,
                            to_revision_id=destination,
                            owner_id=context.owner_id,
                            job_id=job.id,
                            kind={
                                "support": "supports",
                                "supersede": "supersedes",
                                "correct": "corrects",
                                "conflict": "disputes",
                            }[operation.action],
                        )
                    )
            result = {
                "decision": proposal.decision,
                "revision_ids": revisions,
                "prompt_version": PROMPT_VERSION,
                "model": self.extractor.model,
            }
            session.add(
                ProcessingReceipt(
                    job_id=job.id,
                    owner_id=context.owner_id,
                    lease_token=packet.lease_token,
                    result=result,
                )
            )
            job.status = "succeeded"
            job.requested = False
            job.finished_at = session.scalar(select(func.clock_timestamp()))
            job.lease_until = None
            session.flush()
            return result

    def fail_processing(self, context, packet, code):
        self._authorize(context)
        code = ErrorCode(code)
        with self._session(context, write=True) as session:
            session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            job = session.get(Job, packet.job_id)
            if (
                job
                and job.owner_id == context.owner_id
                and job.lease_token == packet.lease_token
                and job.status == "running"
            ):
                job.status = "failed"
                job.error_code = code.value
                job.requested = False
                job.lease_until = None
                job.finished_at = session.scalar(select(func.clock_timestamp()))

    @measured("reserve")
    def reserve_call(self, context, packet, reserved_tokens):
        self._provider_gate(context)
        if type(reserved_tokens) is not int or reserved_tokens <= 0:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        with self._session(context, write=True) as session:
            self._check_packet(session, context, packet)
            return self._reserve_provider(
                session,
                context,
                self.extractor,
                reserved_tokens,
                PROMPT_VERSION,
                job_id=packet.job_id,
                lease_token=packet.lease_token,
                policy_revision=packet.policy_revision,
            )

    @staticmethod
    def _reserve_provider(session, context, provider, reserved_tokens, prompt_version, **fields):
        session.execute(
            insert(ModelBudget).values(key=provider.budget_key).on_conflict_do_nothing()
        )
        budget = session.scalar(
            select(ModelBudget).where(ModelBudget.key == provider.budget_key).with_for_update()
        )
        request_limit = min(MAX_REQUESTS, getattr(provider, "max_requests", MAX_REQUESTS))
        token_limit = min(MAX_TOTAL_TOKENS, getattr(provider, "max_total_tokens", MAX_TOTAL_TOKENS))
        if budget.requests >= request_limit or budget.tokens + reserved_tokens > token_limit:
            raise ApplicationError(ErrorCode.BUDGET_EXHAUSTED)
        budget.requests += 1
        budget.tokens += reserved_tokens
        call = ModelCall(
            owner_id=context.owner_id,
            budget_key=budget.key,
            configured_model=provider.model,
            prompt_version=prompt_version,
            reserved_tokens=reserved_tokens,
            **fields,
        )
        session.add(call)
        session.flush()
        return call.id

    def complete_call(self, context, provider, body, call_id):
        self._authorize(context)
        started = perf_counter()
        try:
            with stage("model"):
                completion = provider.complete(body)
        except Exception as error:
            code = error.code if isinstance(error, ApplicationError) else ErrorCode.PROVIDER_FAILED
            self.finish_call(
                context,
                call_id,
                error=code,
                elapsed_ms=max(0, round((perf_counter() - started) * 1000)),
            )
            raise ApplicationError(code) from None
        self.finish_call(context, call_id, completion)
        return completion

    @measured("accounting")
    def finish_call(self, context, call_id, completion=None, error=None, *, elapsed_ms=None):
        self._authorize(context)
        with self._session(context, write=True) as session:
            key = session.scalar(
                select(ModelCall.budget_key).where(
                    ModelCall.id == call_id,
                    ModelCall.owner_id == context.owner_id,
                )
            )
            if key is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            # Fixed lock order: budget before call; no network while either is held.
            budget = session.scalar(
                select(ModelBudget).where(ModelBudget.key == key).with_for_update()
            )
            call = session.scalar(
                select(ModelCall)
                .where(
                    ModelCall.id == call_id,
                    ModelCall.owner_id == context.owner_id,
                    ModelCall.budget_key == key,
                )
                .with_for_update()
            )
            if call is None or budget is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            if call.status != "reserved":
                if error and call.status == "succeeded":
                    # Record a later proposal/commit rejection without charging twice.
                    call.status = "failed"
                    call.error_code = ErrorCode(error).value
                return
            call.status = "failed" if error else "succeeded"
            call.error_code = ErrorCode(error).value if error else None
            if completion:
                used = completion.input_tokens + completion.output_tokens
                budget.tokens += used - call.reserved_tokens
                call.returned_model = completion.model
                call.input_tokens, call.output_tokens = (
                    completion.input_tokens,
                    completion.output_tokens,
                )
                call.elapsed_ms = completion.elapsed_ms
                if used > call.reserved_tokens:
                    # A broken reservation assumption closes the pilot to further calls.
                    budget.requests = MAX_REQUESTS
                    call.status = "failed"
                    call.error_code = ErrorCode.BUDGET_EXHAUSTED.value
            elif elapsed_ms is not None:
                call.elapsed_ms = elapsed_ms
            # Unknown/failed requests keep their full reservation, including across restarts.

    def list_memories(self, context, payload):
        self._authorize(context)
        query = parse_contract(MemoryQuery, payload)
        with self._session(context) as session:
            statement = self._active_memories(session, context, query.namespace)
            if query.after:
                statement = statement.where(ClaimRecord.id > query.after)
            rows = session.scalars(statement.limit(query.limit + 1)).all()
            return {
                "memories": [
                    self._claim_contract(session, context, row).model_dump(mode="json")
                    for row in rows[: query.limit]
                ],
                "next_after": str(rows[query.limit - 1].id) if len(rows) > query.limit else None,
            }

    def memory_history(self, context, claim_id):
        self._authorize(context)
        try:
            claim_id = UUID(str(claim_id))
        except (ValueError, TypeError):
            raise ApplicationError(ErrorCode.INVALID_INPUT) from None
        with self._session(context) as session:
            rows = session.scalars(
                select(ClaimRecord)
                .where(
                    ClaimRecord.owner_id == context.owner_id,
                    ClaimRecord.claim_id == claim_id,
                )
                .order_by(ClaimRecord.revision)
            ).all()
            if not rows:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            relations = session.scalars(
                select(ClaimRelation).where(
                    ClaimRelation.owner_id == context.owner_id,
                    or_(
                        ClaimRelation.from_revision_id.in_([r.id for r in rows]),
                        ClaimRelation.to_revision_id.in_([r.id for r in rows]),
                    ),
                )
            ).all()
            return {
                "revisions": [
                    self._claim_contract(session, context, r).model_dump(mode="json") for r in rows
                ],
                "relations": [
                    {
                        "from_revision_id": str(r.from_revision_id),
                        "to_revision_id": str(r.to_revision_id),
                        "kind": r.kind,
                    }
                    for r in relations
                ],
            }

    def processing_status(self, context, payload):
        self._authorize(context)
        query = parse_contract(MemoryQuery, payload)
        with self._session(context) as session:
            sources = self._namespace_sources(context, query.namespace).with_only_columns(Source.id)
            rows = session.execute(
                select(Job.status, func.count())
                .where(
                    Job.owner_id == context.owner_id,
                    Job.source_id.in_(sources),
                )
                .group_by(Job.status)
            ).all()
            failures = session.execute(
                select(Job.id, Job.error_code)
                .where(
                    Job.owner_id == context.owner_id,
                    Job.source_id.in_(sources),
                    Job.status.in_(["failed", "cancelled"]),
                )
                .order_by(Job.id)
                .limit(20)
            ).all()
            receipts = (
                session.execute(
                    select(ProcessingReceipt.result)
                    .join(Job, Job.id == ProcessingReceipt.job_id)
                    .where(
                        Job.source_id.in_(sources), ProcessingReceipt.owner_id == context.owner_id
                    )
                )
                .scalars()
                .all()
            )
            waiting = session.execute(
                select(
                    Source.id,
                    Source.source_key,
                    Job.status,
                    Job.attempts,
                    Job.error_code,
                )
                .join(Job, Job.source_id == Source.id)
                .where(
                    Source.owner_id == context.owner_id,
                    Job.owner_id == context.owner_id,
                    Source.id.in_(sources),
                    Job.status != "succeeded",
                )
                .order_by(
                    case(
                        (Job.status == "failed", 0),
                        (Job.status == "cancelled", 1),
                        (Job.status == "running", 2),
                        else_=3,
                    ),
                    Source.imported_at.desc(),
                )
                .limit(50)
            ).all()
            return {
                "counts": dict(rows),
                "provider_enabled": self.extractor.enabled,
                "failures": [{"job_id": str(j), "reason": code} for j, code in failures],
                "waiting": [
                    {
                        "source_id": str(source_id),
                        "record_id": source_key.rsplit(":", 1)[1],
                        "status": status,
                        "attempts": attempts,
                        "reason": error_code,
                    }
                    for source_id, source_key, status, attempts, error_code in waiting
                ],
                "decisions": {
                    name: sum(r["decision"] == name for r in receipts)
                    for name in ("extracted", "no_memory", "duplicate", "needs_clarification")
                },
            }

    def inference_status(self, context):
        """Configuration only: no store access, network probe, key or quota disclosure."""
        self._authorize(context)

        def role(provider):
            return {
                "model": provider.model,
                "enabled": provider.enabled,
                "key_configured": bool(provider._key) or not provider.live,
                "unfamiliar_mode": provider.unfamiliar_mode,
                "unfamiliar_questions": getattr(provider, "unfamiliar_questions", False),
                "unfamiliar_sources": getattr(provider, "unfamiliar_sources", False),
                "private_direct": getattr(provider, "private_direct", False),
                "provider": getattr(provider, "provider_name", "test_double"),
            }

        return {
            "extractor": role(self.extractor),
            "responder": role(self.responder),
            "request_ceiling": min(self.extractor.max_requests, self.responder.max_requests),
            "token_ceiling": min(self.extractor.max_total_tokens, self.responder.max_total_tokens),
            "provider_contacted": False,
            "warning": (
                "Hosted inference follows the selected provider's data terms. Google free "
                "inputs/outputs may be used for product improvement and human review. "
                "Free Google/OpenRouter routes accept only operator-approved demo data. "
                "New questions, unfamiliar synthetic sources, and context-free Private chat "
                "each require their own explicit switch. Private chat never reads the database "
                "and its text or reply is not saved by Jarvis."
            ),
        }

    def processing_report(self, context, payload):
        """Synthetic-only evidence export through the shared policy path."""
        self._authorize(context)
        query = parse_contract(MemoryQuery, payload)
        with self._session(context) as session:
            sources = session.scalars(self._namespace_sources(context, query.namespace)).all()
            for source in sources:
                self._trial_source(source)
            jobs = select(Job.id).where(
                Job.owner_id == context.owner_id, Job.source_id.in_([s.id for s in sources])
            )
            calls = session.scalars(
                select(ModelCall)
                .where(
                    ModelCall.owner_id == context.owner_id,
                    ModelCall.job_id.in_(jobs),
                )
                .order_by(ModelCall.recorded_at)
            ).all()
            # Only counters/identifiers and fixed error categories; no raw provider responses.
            accounting = [
                {c.name: getattr(call, c.name) for c in ModelCall.__table__.columns}
                for call in calls
            ]
            revisions = session.scalars(
                self._active_memories(session, context, query.namespace)
            ).all()
            claim_ids = [row.claim_id for row in revisions]
        return {
            "namespace": query.namespace,
            "processing": self.processing_status(context, payload),
            "calls": accounting,
            "memories": [self.memory_history(context, claim_id) for claim_id in claim_ids],
        }

    def model_call_report(self, context):
        """Permitted accounting only: no prompts, answers, reasoning, keys or raw errors."""
        self._authorize(context)
        with self._session(context) as session:
            calls = session.scalars(
                select(ModelCall)
                .where(ModelCall.owner_id == context.owner_id)
                .order_by(ModelCall.recorded_at)
            ).all()
            return [
                {c.name: getattr(row, c.name) for c in ModelCall.__table__.columns} for row in calls
            ]
