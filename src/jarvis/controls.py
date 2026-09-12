"""User-confirmed lifecycle operations under the same guard as workers and replies."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from jarvis.contracts import (
    ClaimContent,
    ClaimWrite,
    Contract,
    ObservationInput,
    Revision,
    SupportingPassage,
    Text,
    parse_contract,
)
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import Identifier
from jarvis.metrics import measured
from jarvis.models import (
    ClaimEvidence,
    ClaimRecord,
    ClaimRelation,
    ControlReceipt,
    Job,
    Passage,
    PassageExclusion,
    Source,
    SourceExclusion,
)


class ControlRequest(Contract):
    operation_id: UUID
    namespace: Identifier
    target_revision_id: UUID
    expected_policy_revision: Revision
    action: Literal["correct", "world_change", "forget"]
    statement: Text | None = None
    replacement: ClaimContent | None = None
    preview_token: str | None = None

    @model_validator(mode="after")
    def explicit_replacement(self):
        if self.action == "forget":
            if self.statement is not None or self.replacement is not None:
                raise ValueError("Forget does not save a new factual assertion")
        elif self.statement is None or self.replacement is None:
            raise ValueError(
                "A correction needs explicit user evidence and a confirmed interpretation"
            )
        return self


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def same_observation(left, right):
    variants = {v for v in (right.raw_text, right.formatted_text) if v}
    return left.source_key == right.source_key or any(
        v in variants for v in (left.raw_text, left.formatted_text) if v
    )


def reject_corrected_relearning(session, context, command, sources):
    """Reject the known revoked interpretation from the same observation or exact copy.

    A fresh assertion can report a later change. This is exact typed equality, not a
    semantic entailment classifier; paraphrased misinterpretations still need evaluation.
    """
    targets = session.scalars(
        select(ClaimRecord)
        .join(ControlReceipt, ControlReceipt.target_revision_id == ClaimRecord.id)
        .where(ControlReceipt.owner_id == context.owner_id, ControlReceipt.action == "correct")
    ).all()
    for target in targets:
        if parse_contract(ClaimContent, target.content) != command.content:
            continue
        originals = session.scalars(
            select(Source).where(
                Source.owner_id == context.owner_id,
                Source.id.in_(
                    select(Passage.source_id)
                    .join(ClaimEvidence, ClaimEvidence.passage_id == Passage.id)
                    .where(ClaimEvidence.claim_revision_id == target.id)
                ),
            )
        ).all()
        if any(same_observation(s, old) for s in sources for old in originals):
            raise ApplicationError(ErrorCode.INVALID_TRANSITION)


def blocked_sources(context):
    """Exact known copies, source revisions and literal excluded support, owner-scoped."""
    original = aliased(Source)
    source_match = (
        select(SourceExclusion.source_id)
        .join(original, original.id == SourceExclusion.source_id)
        .where(
            SourceExclusion.owner_id == context.owner_id,
            or_(
                Source.source_key == original.source_key,
                Source.raw_text == original.raw_text,
                Source.formatted_text == original.raw_text,
                Source.raw_text == original.formatted_text,
                Source.formatted_text == original.formatted_text,
            ),
        )
        .correlate(Source)
        .exists()
    )
    passage_match = (
        select(PassageExclusion.passage_id)
        .join(Passage, Passage.id == PassageExclusion.passage_id)
        .where(
            PassageExclusion.owner_id == context.owner_id,
            or_(
                func.strpos(Source.raw_text, Passage.exact_text) > 0,
                func.strpos(Source.formatted_text, Passage.exact_text) > 0,
            ),
        )
        .correlate(Source)
        .exists()
    )
    legacy = (
        select(Passage.source_id)
        .join(ClaimEvidence, ClaimEvidence.passage_id == Passage.id)
        .join(ClaimRecord, ClaimRecord.id == ClaimEvidence.claim_revision_id)
        .where(
            ClaimRecord.owner_id == context.owner_id,
            ClaimRecord.lifecycle == "excluded",
            ~ClaimRecord.id.in_(
                select(ClaimEvidence.claim_revision_id)
                .join(Passage, Passage.id == ClaimEvidence.passage_id)
                .join(SourceExclusion, SourceExclusion.source_id == Passage.source_id)
                .where(ClaimEvidence.owner_id == context.owner_id)
            ),
        )
    )
    return select(Source.id).where(
        Source.owner_id == context.owner_id, or_(source_match, passage_match, Source.id.in_(legacy))
    )


class ControlOperations:
    def _control_target(self, session, context, command):
        target = session.scalar(
            select(ClaimRecord).where(
                ClaimRecord.id == command.target_revision_id,
                ClaimRecord.owner_id == context.owner_id,
            )
        )
        if target is None:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        latest = session.scalar(
            select(func.max(ClaimRecord.revision)).where(
                ClaimRecord.owner_id == context.owner_id, ClaimRecord.claim_id == target.claim_id
            )
        )
        if target.revision != latest or target.lifecycle != "active":
            raise ApplicationError(ErrorCode.STALE_REVISION)
        contract = self._claim_contract(session, context, target)
        sources = session.scalars(
            select(Source).where(
                Source.owner_id == context.owner_id,
                Source.id.in_({p.source_id for p in contract.passages}),
            )
        ).all()
        if not sources or any(
            not s.source_key.startswith(f"import:{command.namespace}:") for s in sources
        ):
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        self._support(
            session,
            context,
            ClaimWrite(
                expected_policy_revision=command.expected_policy_revision,
                content=contract.content,
                passages=contract.passages,
            ),
        )
        if command.action == "world_change" and any(
            getattr(command.replacement, field) != getattr(contract.content, field)
            for field in ("subject", "predicate", "scope", "attribution")
        ):
            raise ApplicationError(ErrorCode.INVALID_TRANSITION)
        return target, contract, sources

    def _control_preview(self, session, context, command):
        self._policy(session, context, command.expected_policy_revision, lock=True)
        target, contract, sources = self._control_target(session, context, command)
        affected = sources
        if command.action == "forget":
            family_passages = session.scalars(
                select(Passage)
                .join(ClaimEvidence, ClaimEvidence.passage_id == Passage.id)
                .join(ClaimRecord, ClaimRecord.id == ClaimEvidence.claim_revision_id)
                .where(
                    ClaimRecord.owner_id == context.owner_id,
                    ClaimRecord.claim_id == target.claim_id,
                )
            ).all()
            sources = session.scalars(
                select(Source).where(
                    Source.owner_id == context.owner_id,
                    Source.id.in_({p.source_id for p in family_passages}),
                )
            ).all()
            # Exact copies and literal support; no fuzzy entity/semantic identity guesses.
            candidates = session.scalars(
                select(Source).where(Source.owner_id == context.owner_id)
            ).all()
            variants = {v for s in sources for v in (s.raw_text, s.formatted_text) if v}
            keys = {s.source_key for s in sources}
            quotes = {p.exact_text for p in family_passages}
            affected = [
                s
                for s in candidates
                if s.source_key in keys
                or any(
                    v in variants or any(q in v for q in quotes)
                    for v in (s.raw_text, s.formatted_text)
                    if v
                )
            ]
        ids = {s.id for s in affected}
        claims = session.scalars(
            select(ClaimRecord).where(
                ClaimRecord.owner_id == context.owner_id,
                ClaimRecord.id.in_(
                    select(ClaimEvidence.claim_revision_id)
                    .join(Passage, Passage.id == ClaimEvidence.passage_id)
                    .where(ClaimEvidence.owner_id == context.owner_id, Passage.source_id.in_(ids))
                ),
            )
        ).all()
        preview = {
            "action": command.action,
            "policy_revision": command.expected_policy_revision,
            "target": contract.model_dump(mode="json"),
            "sources": [
                self._source_contract(s).model_dump(mode="json")
                for s in sorted(affected, key=lambda s: str(s.id))
            ],
            "affected_revision_ids": sorted(str(c.id) for c in claims),
            "replacement": command.replacement.model_dump(mode="json")
            if command.replacement
            else None,
            "statement": command.statement,
            "history_retained": True,
        }
        preview["preview_token"] = digest(preview)
        return target, contract, affected, claims, preview

    @measured("control_preview")
    def preview_control(self, context, payload):
        self._authorize(context)
        command = parse_contract(ControlRequest, payload)
        with self._session(context, write=True) as session:
            return self._control_preview(session, context, command)[-1]

    @measured("control_commit")
    def apply_control(self, context, payload):
        self._authorize(context)
        command = parse_contract(ControlRequest, payload)
        request_hash = digest(command.model_dump(mode="json"))
        with self._session(context, write=True) as session:
            # Always serialize before the idempotency lookup; replay reports an old receipt,
            # not authorization to read old evidence or reverse a later control.
            from jarvis.models import Policy

            session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            previous = session.get(ControlReceipt, command.operation_id)
            if previous:
                if previous.owner_id != context.owner_id or previous.request_hash != request_hash:
                    raise ApplicationError(ErrorCode.STALE_REVISION)
                return previous.result
            target, contract, sources, claims, preview = self._control_preview(
                session, context, command
            )
            if command.preview_token != preview["preview_token"]:
                raise ApplicationError(ErrorCode.STALE_REVISION)
            policy = self._policy(session, context, command.expected_policy_revision, lock=True)
            policy.revision += 1
            result = {
                "status": "applied",
                "operation_id": str(command.operation_id),
                "action": command.action,
                "policy_revision": policy.revision,
                "target_revision_id": str(target.id),
                "support_source_ids": [str(s.id) for s in sources],
                "history_retained": True,
            }
            receipt = ControlReceipt(
                id=command.operation_id,
                owner_id=context.owner_id,
                target_revision_id=target.id,
                action=command.action,
                request_hash=request_hash,
                result=dict(result),
            )
            session.add(receipt)
            session.flush()
            if command.action == "forget":
                for source in sources:
                    session.execute(
                        insert(SourceExclusion)
                        .values(
                            source_id=source.id,
                            source_revision=source.revision,
                            owner_id=context.owner_id,
                            control_id=receipt.id,
                        )
                        .on_conflict_do_nothing()
                    )
                passage_ids = session.scalars(
                    select(ClaimEvidence.passage_id)
                    .join(ClaimRecord, ClaimRecord.id == ClaimEvidence.claim_revision_id)
                    .where(
                        ClaimEvidence.owner_id == context.owner_id,
                        ClaimRecord.claim_id == target.claim_id,
                    )
                ).all()
                for passage_id in passage_ids:
                    session.execute(
                        insert(PassageExclusion)
                        .values(
                            passage_id=passage_id, owner_id=context.owner_id, control_id=receipt.id
                        )
                        .on_conflict_do_nothing()
                    )
                for claim in claims:
                    claim.lifecycle = "excluded"
                result["excluded_revisions"] = len(claims)
                result["excluded_sources"] = len(sources)
            else:
                observation = ObservationInput(
                    source_key=f"import:{command.namespace}:control-{receipt.id.hex}",
                    kind="user_message",
                    raw_text=command.statement,
                    capture_metadata={
                        "input_kind": "user_control",
                        "confirmed_content": command.replacement.model_dump(mode="json"),
                    },
                )
                [(source, job)] = self._save_sources(session, context, policy, [(observation, 1)])
                # A control is consumed synchronously, never fed back into the extractor queue.
                job.status, job.requested, job.error_code = "cancelled", False, "control_input"
                job.finished_at = session.scalar(select(func.clock_timestamp()))
                passage = SupportingPassage(
                    source_id=source.id,
                    source_revision=1,
                    variant="raw",
                    start=0,
                    end=len(source.raw_text),
                    exact_text=source.raw_text,
                )
                target.lifecycle = "corrected" if command.action == "correct" else "superseded"
                write = ClaimWrite(
                    claim_id=target.claim_id,
                    expected_claim_revision=target.revision,
                    expected_policy_revision=policy.revision,
                    content=command.replacement,
                    passages=(passage,),
                )
                self._support(session, context, write)
                created = self._insert_claim(session, context, write, target.revision + 1)
                session.add(
                    ClaimRelation(
                        from_revision_id=created.id,
                        to_revision_id=target.id,
                        owner_id=context.owner_id,
                        job_id=job.id,
                        kind="corrects" if command.action == "correct" else "supersedes",
                    )
                )
                result.update(
                    replacement_revision_id=str(created.id), replacement_source_id=str(source.id)
                )
            # Fence all in-flight owner packets; harmless pending jobs can be explicitly
            # requested again with the new policy revision, excluded jobs cannot.
            for job in session.scalars(
                select(Job).where(
                    Job.owner_id == context.owner_id, Job.status.in_(["pending", "running"])
                )
            ):
                if job.source_id in {s.id for s in sources} and command.action == "forget":
                    job.status, job.error_code = "cancelled", "excluded_source"
                elif job.status == "running":
                    job.status, job.error_code = "failed", "stale_revision"
                else:
                    job.expected_policy_revision = policy.revision
                    continue
                job.requested, job.lease_token, job.lease_until = False, None, None
                job.finished_at = session.scalar(select(func.clock_timestamp()))
            receipt.result = dict(result)
            session.flush()
            return result

    def _attach_controls(self, session, context, packet):
        """Original-source results always carry explicit later user amendments, in any mode.

        This is canonical control provenance, shared across retrieval representations;
        neither ranking nor an old exact quote can hide a user's explicit correction.
        """
        from jarvis.retrieval import ControlAnnotation, evidence_size

        sources = {s.id: s for s in packet.sources}
        annotations = []
        receipts = session.scalars(
            select(ControlReceipt)
            .where(
                ControlReceipt.owner_id == context.owner_id,
                ControlReceipt.action.in_(["correct", "world_change"]),
            )
            .order_by(ControlReceipt.result["policy_revision"].as_integer())
        ).all()
        for receipt in receipts:
            previous = {UUID(i) for i in receipt.result["support_source_ids"]}
            replacement_id = UUID(receipt.result["replacement_source_id"])
            originals = session.scalars(
                select(Source).where(Source.owner_id == context.owner_id, Source.id.in_(previous))
            ).all()
            copies = {
                s.id for s in sources.values() if any(same_observation(s, old) for old in originals)
            }
            if not (copies or replacement_id in sources):
                continue
            if session.scalar(blocked_sources(context).where(Source.id == replacement_id)):
                continue
            row = session.scalar(
                select(Source).where(
                    Source.id == replacement_id, Source.owner_id == context.owner_id
                )
            )
            if row is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            sources[row.id] = self._source_contract(row)
            annotations.append(
                ControlAnnotation(
                    action=receipt.action,
                    source_id=row.id,
                    prior_source_ids=tuple(sorted(previous | copies)),
                )
            )
        size = evidence_size(sources.values(), packet.memories) + len(
            json.dumps(
                [a.model_dump(mode="json") for a in annotations], separators=(",", ":")
            ).encode("utf-8")
        )
        if annotations and size > packet.request.max_bytes:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        return packet.model_copy(
            update={
                "sources": tuple(sources.values()),
                "controls": tuple(annotations),
                "evidence_bytes": size if annotations else packet.evidence_bytes,
            }
        )
