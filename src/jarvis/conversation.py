"""Preserve user-authored chat messages and learn through the existing guarded worker."""

from typing import Annotated
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from jarvis.answers import AskRequest
from jarvis.contracts import Contract, ObservationInput, parse_contract
from jarvis.controls import blocked_sources
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.extraction import MAX_ATTEMPTS
from jarvis.imports import source_key, validate_json_text
from jarvis.models import Job, ModelCall, Policy, ProcessingReceipt, Source, TurnAssessment
from jarvis.worker import process_one


class ConversationMessage(Contract):
    message_id: UUID
    conversation_id: UUID
    request: AskRequest
    retry_failed: Annotated[bool, Field(strict=True)] = False


class LearningRequest(Contract):
    retry_failed: Annotated[bool, Field(strict=True)] = False


class ConversationOperations:
    def save_message(self, context, payload):
        self._authorize(context)  # Before parsing, persistence or provider access.
        command = parse_contract(ConversationMessage, payload)
        try:
            validate_json_text(command.request.question)
        except (ValueError, UnicodeError):
            raise ApplicationError(ErrorCode.INVALID_INPUT) from None
        if not command.request.question.strip():
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        key = source_key(command.request.namespace, f"chat-{command.message_id}")
        # An exact replay of an already retained turn needs no new model decision.
        with self._session(context) as session:
            existing = session.scalar(
                select(Source).where(Source.owner_id == context.owner_id, Source.source_key == key)
            )
            if existing is not None:
                metadata = existing.capture_metadata or {}
                if (
                    existing.kind != "user_message"
                    or existing.raw_text != command.request.question
                    or metadata.get("conversation_id") != str(command.conversation_id)
                    or (
                        "assessment_request" in metadata
                        and metadata["assessment_request"]
                        != command.request.model_dump(
                            mode="json", exclude={"question", "assessment_id"}
                        )
                    )
                ):
                    raise ApplicationError(ErrorCode.IMPORT_CONFLICT)
                existing_id = existing.id
            else:
                existing_id = None
        if existing_id is not None:
            return self.message_learning(context, existing_id)

        assessment = self.assess_turn(
            context, command.request, command.message_id, retry_failed=command.retry_failed
        )
        if assessment["status"] != "ready" or assessment["decision"]["retention"] == "skip":
            return {
                "source_id": None,
                "status": "not_saved",
                "decision": "no_memory" if assessment["status"] == "ready" else None,
                "revision_ids": [],
                "error_code": assessment["error_code"],
                "attempts": 0,
                "calls": [],
                "assessment_id": assessment["assessment_id"],
                "assessment": assessment,
            }
        request = command.request.model_copy(
            update={"assessment_id": UUID(assessment["assessment_id"])}
        )
        with self._session(context, write=True) as session:
            session.execute(
                insert(Policy).values(owner_id=context.owner_id).on_conflict_do_nothing()
            )
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            decision = self._read_turn_decision(session, context, request)
            if decision.retention != "candidate":
                raise ApplicationError(ErrorCode.INVALID_TRANSITION)
            source = session.scalar(
                select(Source).where(Source.owner_id == context.owner_id, Source.source_key == key)
            )
            if source is not None:
                if (
                    source.kind != "user_message"
                    or source.raw_text != command.request.question
                    or (source.capture_metadata or {}).get("conversation_id")
                    != str(command.conversation_id)
                ):
                    raise ApplicationError(ErrorCode.IMPORT_CONFLICT)
            else:
                # Only earlier USER messages from this collection/conversation can resolve
                # follow-up references. No client-provided history or assistant answers.
                previous = session.scalars(
                    self._namespace_sources(context, command.request.namespace)
                    .where(
                        Source.kind == "user_message",
                        Source.capture_metadata["conversation_id"].astext
                        == str(command.conversation_id),
                        ~Source.id.in_(blocked_sources(context)),
                    )
                    .order_by(Source.imported_at.desc(), Source.id.desc())
                    .limit(6)
                ).all()
                observation = parse_contract(
                    ObservationInput,
                    {
                        "source_key": key,
                        "kind": "user_message",
                        "raw_text": command.request.question,
                        "capture_metadata": {
                            "origin": "ask_jarvis",
                            "conversation_id": str(command.conversation_id),
                            "previous_user_source_ids": [str(s.id) for s in reversed(previous)],
                            "assessment_id": assessment["assessment_id"],
                            "assessment_request": request.model_dump(
                                mode="json", exclude={"question", "assessment_id"}
                            ),
                            "memory_excerpts": list(decision.memory_excerpts),
                        },
                    },
                )
                [(source, _)] = self._save_sources(session, context, policy, [(observation, 1)])
            source_id = source.id
        return self.message_learning(context, source_id)

    def _message_job(self, session, context, source_id):
        pair = session.execute(
            select(Source, Job)
            .join(Job, (Job.source_id == Source.id) & (Job.owner_id == Source.owner_id))
            .where(Source.id == source_id, Source.owner_id == context.owner_id)
        ).one_or_none()
        if (
            pair is None
            or pair[0].kind != "user_message"
            or (pair[0].capture_metadata or {}).get("origin") != "ask_jarvis"
        ):
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        return pair

    def message_learning(self, context, source_id):
        self._authorize(context)
        try:
            source_id = UUID(str(source_id))
        except (ValueError, TypeError):
            raise ApplicationError(ErrorCode.INVALID_INPUT) from None
        with self._session(context) as session:
            source, job = self._message_job(session, context, source_id)
            excluded = bool(session.scalar(blocked_sources(context).where(Source.id == source.id)))
            receipt = session.get(ProcessingReceipt, job.id)
            calls = session.scalars(
                select(ModelCall)
                .where(ModelCall.owner_id == context.owner_id, ModelCall.job_id == job.id)
                .order_by(ModelCall.id)
            ).all()
            # Inspection is historical, not authority to answer or relearn. Keep
            # cancelled sources inspectable after a later control changes policy.
            assessment_id = (source.capture_metadata or {}).get("assessment_id")
            try:
                parsed_id = UUID(str(assessment_id)) if assessment_id else None
            except (ValueError, TypeError):
                parsed_id = None
            record = session.get(TurnAssessment, parsed_id) if parsed_id else None
            assessment = (
                self._assessment_receipt(session, context, record)
                if record is not None and record.owner_id == context.owner_id
                else None
            )
            return {
                "source_id": str(source.id),
                "status": "cancelled" if excluded else job.status,
                "decision": receipt.result["decision"] if receipt and not excluded else None,
                "revision_ids": receipt.result["revision_ids"] if receipt and not excluded else [],
                "error_code": "excluded_source" if excluded else job.error_code,
                "attempts": job.attempts,
                "assessment_id": assessment["assessment_id"] if assessment else None,
                "assessment": assessment,
                "calls": [
                    {
                        "id": str(c.id),
                        "status": c.status,
                        "input_tokens": c.input_tokens,
                        "output_tokens": c.output_tokens,
                        "elapsed_ms": c.elapsed_ms,
                        "error_code": c.error_code,
                    }
                    for c in calls
                ],
            }

    def learn_message(self, context, source_id, payload):
        self._authorize(context)
        command = parse_contract(LearningRequest, payload)
        state = self.message_learning(context, source_id)
        if state["status"] in {"succeeded", "cancelled"}:
            return state
        if state["status"] == "failed" and not command.retry_failed:
            return state
        try:
            self._provider_gate(context)
            with self._session(context, write=True) as session:
                policy = session.scalar(
                    select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
                )
                source, job = self._message_job(session, context, UUID(state["source_id"]))
                self._trial_source(source)
                if job.status == "pending" or (job.status == "failed" and command.retry_failed):
                    if job.attempts >= MAX_ATTEMPTS:
                        raise ApplicationError(ErrorCode.RETRY_LIMIT)
                    job.status, job.requested, job.error_code = "pending", True, None
                    job.expected_policy_revision = policy.revision
            # Scope to this message. Never accidentally drain unrelated imported notes.
            process_one(self, context, source_id=UUID(state["source_id"]))
        except ApplicationError as error:
            state = self.message_learning(context, source_id)
            return {**state, "error_code": error.code.value}
        return self.message_learning(context, source_id)
