"""Assess retention and answer needs separately before storing conversation text."""

import json
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from jarvis.contracts import Contract, exact_text, parse_contract
from jarvis.controls import digest
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import reject_constant, unique_object, validate_json_text
from jarvis.metrics import measured, stage
from jarvis.models import ModelCall, Policy, TurnAssessment

ASSESSMENT_VERSION = "turn-assessment-v1"
ASSESSMENT_LEASE_SECONDS = 300
ASSESSMENT_MAX_CALLS = 4
ASSESSMENT_REPAIR = (
    "Return only the schema JSON. Retention and answer route are independent. "
    "Select candidate only for a useful assertion and copy one to four exact, unique, "
    "non-overlapping excerpts from the current question. Skip requires no excerpts. "
    "Use compatible reason and route enum values. Never rewrite or invent quotations."
)


class TurnDecision(Contract):
    retention: Literal["skip", "candidate"]
    route: Literal["general", "contextual", "mixed", "live", "clock", "clarification"]
    reason: Literal[
        "general_request",
        "personal_question",
        "useful_assertion",
        "hypothetical",
        "one_off",
        "small_talk",
        "ambiguous",
        "current_information",
        "clock",
    ]
    memory_excerpts: Annotated[
        tuple[Annotated[str, Field(strict=True, min_length=1, max_length=512)], ...],
        Field(max_length=4),
    ] = ()

    @model_validator(mode="after")
    def coherent_decision(self):
        if self.retention == "candidate":
            if (
                not self.memory_excerpts
                or self.reason != "useful_assertion"
                or self.route in {"clock", "clarification"}
            ):
                raise ValueError("Candidates need useful assertions and exact excerpts")
        elif self.memory_excerpts or self.reason == "useful_assertion":
            raise ValueError("Skipped turns must not select memory excerpts")
        if (self.route == "clock") != (self.reason == "clock"):
            raise ValueError("Clock route and reason must agree")
        if self.reason == "personal_question" and self.route not in {"contextual", "mixed"}:
            raise ValueError("A personal question needs contextual answering")
        if self.reason == "current_information" and self.route != "live":
            raise ValueError("Current information needs live information")
        if (self.reason == "ambiguous") != (self.route == "clarification"):
            raise ValueError("Ambiguous references need clarification")
        for excerpt in self.memory_excerpts:
            exact_text(excerpt)
        return self


def assessment_hash(request):
    return digest(request.model_dump(mode="json", exclude={"assessment_id"}))


def validate_decision(decision, question):
    """A model's selection is usable only if it locates exact current-input text."""
    locations = []
    for excerpt in decision.memory_excerpts:
        start = question.find(excerpt)
        if start < 0 or question.find(excerpt, start + 1) >= 0:
            raise ApplicationError(ErrorCode.PROVIDER_RESPONSE)
        end = start + len(excerpt)
        if any(
            start < previous_end and end > previous_start
            for previous_start, previous_end in locations
        ):
            raise ApplicationError(ErrorCode.PROVIDER_RESPONSE)
        locations.append((start, end))
    return decision


class TurnAssessmentOperations:
    @staticmethod
    def _assessment_receipt(session, context, record):
        calls = session.scalars(
            select(ModelCall).where(
                ModelCall.owner_id == context.owner_id,
                ModelCall.id.in_([UUID(item) for item in record.call_ids]),
            )
        ).all()
        by_id = {str(call.id): call for call in calls}
        return {
            "assessment_id": str(record.id),
            "status": record.status,
            "decision": record.decision if record.status == "ready" else None,
            "error_code": record.error_code,
            "calls": [
                {
                    "id": str(call.id),
                    "status": call.status,
                    "input_tokens": call.input_tokens,
                    "output_tokens": call.output_tokens,
                    "elapsed_ms": call.elapsed_ms,
                    "error_code": call.error_code,
                }
                for item in record.call_ids
                if (call := by_id.get(item)) is not None
            ],
        }

    def _checked_assessment(self, session, context, request):
        self._authorize(context)
        assessment_id = getattr(request, "assessment_id", None)
        record = (
            session.scalar(
                select(TurnAssessment).where(
                    TurnAssessment.id == assessment_id,
                    TurnAssessment.owner_id == context.owner_id,
                )
            )
            if assessment_id is not None
            else None
        )
        if record is None or record.request_hash != assessment_hash(request):
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        self._policy(session, context, record.policy_revision, lock=True)
        if record.status != "ready" or record.decision is None:
            raise ApplicationError(ErrorCode.INVALID_TRANSITION)
        return record

    def _read_turn_decision(self, session, context, request):
        record = self._checked_assessment(session, context, request)
        return validate_decision(parse_contract(TurnDecision, record.decision), request.question)

    def _read_turn_receipt(self, session, context, request):
        return self._assessment_receipt(
            session, context, self._checked_assessment(session, context, request)
        )

    def _assessment_claim(self, context, request, message_id, retry_failed):
        request_hash = assessment_hash(request)
        with self._session(context, write=True) as session:
            session.execute(
                insert(Policy).values(owner_id=context.owner_id).on_conflict_do_nothing()
            )
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            record = session.scalar(
                select(TurnAssessment)
                .where(
                    TurnAssessment.owner_id == context.owner_id,
                    TurnAssessment.message_id == message_id,
                )
                .with_for_update()
            )
            now = session.scalar(select(func.clock_timestamp()))
            if record is not None:
                if record.request_hash != request_hash:
                    raise ApplicationError(ErrorCode.IMPORT_CONFLICT)
                if record.policy_revision != policy.revision:
                    record.status, record.error_code = "failed", ErrorCode.STALE_REVISION.value
                    record.decision, record.lease_until = None, None
                    return None, self._assessment_receipt(session, context, record)
                if (
                    record.status == "ready"
                    or (record.status == "running" and record.lease_until > now)
                    or (record.status == "failed" and not retry_failed)
                ):
                    return None, self._assessment_receipt(session, context, record)
                if record.attempts >= ASSESSMENT_MAX_CALLS:
                    record.status, record.error_code = "failed", ErrorCode.RETRY_LIMIT.value
                    record.lease_until = None
                    return None, self._assessment_receipt(session, context, record)
            else:
                record = TurnAssessment(
                    owner_id=context.owner_id,
                    message_id=message_id,
                    request_hash=request_hash,
                    policy_revision=policy.revision,
                    attempts=0,
                    call_ids=[],
                )
                session.add(record)
            record.status, record.error_code = "running", None
            record.lease_token = uuid4()
            record.lease_until = now + timedelta(seconds=ASSESSMENT_LEASE_SECONDS)
            session.flush()
            return (record.id, record.lease_token), None

    def _reserve_assessment(self, context, assessment_id, lease_token, reservation):
        if type(reservation) is not int or reservation <= 0:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        with self._session(context, write=True) as session:
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            record = session.scalar(
                select(TurnAssessment)
                .where(
                    TurnAssessment.id == assessment_id,
                    TurnAssessment.owner_id == context.owner_id,
                )
                .with_for_update()
            )
            now = session.scalar(select(func.clock_timestamp()))
            if (
                record is None
                or record.status != "running"
                or record.lease_token != lease_token
                or record.lease_until <= now
                or record.policy_revision != policy.revision
            ):
                raise ApplicationError(ErrorCode.STALE_REVISION)
            if record.attempts >= ASSESSMENT_MAX_CALLS:
                raise ApplicationError(ErrorCode.RETRY_LIMIT)
            call_id = self._reserve_provider(
                session,
                context,
                self.responder,
                reservation,
                ASSESSMENT_VERSION,
                request_hash=record.request_hash,
                policy_revision=record.policy_revision,
                lease_token=lease_token,
            )
            record.attempts += 1
            record.call_ids = [*record.call_ids, str(call_id)]
            return call_id

    def _finish_assessment(self, context, assessment_id, lease_token, *, decision=None, error=None):
        with self._session(context, write=True) as session:
            policy = session.scalar(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            record = session.scalar(
                select(TurnAssessment)
                .where(
                    TurnAssessment.id == assessment_id,
                    TurnAssessment.owner_id == context.owner_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
            if record.lease_token == lease_token and record.status == "running":
                now = session.scalar(select(func.clock_timestamp()))
                if record.policy_revision != policy.revision or record.lease_until <= now:
                    error = ErrorCode.STALE_REVISION
                record.status = "failed" if error else "ready"
                record.error_code = error.value if error else None
                record.decision = decision.model_dump(mode="json") if not error else None
                record.lease_until = None
            return self._assessment_receipt(session, context, record)

    @measured("turn_assessment")
    def assess_turn(self, context, request, message_id, *, retry_failed=False):
        self._authorize(context)  # Before parsing, model preparation or persistence.
        from jarvis.answers import AskRequest, trial_questions

        if not isinstance(request, AskRequest) or type(retry_failed) is not bool:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        try:
            message_id = UUID(str(message_id))
            validate_json_text(request.question)
            exact_text(request.question)
        except (TypeError, ValueError, UnicodeError):
            raise ApplicationError(ErrorCode.INVALID_INPUT) from None
        self._answer_gate(context)
        if (
            self.responder.live
            and not self.responder.unfamiliar_mode
            and not getattr(self.responder, "unfamiliar_questions", False)
            and request.question not in trial_questions()
        ):
            raise ApplicationError(ErrorCode.TRIAL_INPUT_DENIED)
        claim, receipt = self._assessment_claim(context, request, message_id, retry_failed)
        if claim is None:
            return receipt
        assessment_id, lease_token = claim
        for repair in (False, ASSESSMENT_REPAIR):
            call_id = None
            try:
                body, reservation = self.responder.prepare_assessment(
                    request.question, repair=repair
                )
                call_id = self._reserve_assessment(context, assessment_id, lease_token, reservation)
                completion = self.complete_call(context, self.responder, body, call_id)
                if completion.input_tokens + completion.output_tokens > reservation:
                    raise ApplicationError(ErrorCode.BUDGET_EXHAUSTED)
                try:
                    with stage("assessment_validation"):
                        data = json.loads(
                            completion.content,
                            object_pairs_hook=unique_object,
                            parse_constant=reject_constant,
                        )
                        decision = validate_decision(
                            parse_contract(TurnDecision, data), request.question
                        )
                except (ApplicationError, ValueError, TypeError):
                    raise ApplicationError(ErrorCode.PROVIDER_RESPONSE) from None
                receipt = self._finish_assessment(
                    context, assessment_id, lease_token, decision=decision
                )
                if receipt["status"] != "ready":
                    self.finish_call(context, call_id, error=ErrorCode.STALE_REVISION)
                    return self._finish_assessment(
                        context, assessment_id, lease_token, error=ErrorCode.STALE_REVISION
                    )
                return receipt
            except Exception as exception:
                error = (
                    exception.code
                    if isinstance(exception, ApplicationError)
                    else ErrorCode.PROVIDER_FAILED
                )
                if call_id is not None:
                    self.finish_call(context, call_id, error=error)
                if error == ErrorCode.PROVIDER_RESPONSE and repair is False:
                    continue
                return self._finish_assessment(context, assessment_id, lease_token, error=error)
