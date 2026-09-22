"""Real-PostgreSQL assessment lifecycle checks with a transport double, not quality scores."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from jarvis.answers import AskRequest
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.models import ClaimRecord, Job, ModelBudget, Policy, Source, TurnAssessment
from jarvis.policy import LocalIdentity
from jarvis.providers import Completion
from jarvis.services import Service

SKIP = {
    "retention": "skip",
    "route": "general",
    "reason": "general_request",
    "memory_excerpts": [],
}


class AssessmentResponder:
    enabled, live = True, False
    model, budget_key = "assessment-contract-double", "assessment-contract-budget"

    def __init__(self, proposal=None):
        self.proposal = proposal or SKIP
        self.calls, self.repairs, self.questions = 0, [], []

    def prepare_assessment(self, question, *, repair=False):
        self.questions.append(question)
        self.repairs.append(repair)
        return {"question": question}, 1000

    def complete(self, body):
        self.calls += 1
        result = self.proposal(body) if callable(self.proposal) else self.proposal
        if isinstance(result, Exception):
            raise result
        return Completion(
            result if isinstance(result, str) else json.dumps(result), self.model, 30, 20, 1
        )


def setup(engine, proposal=None):
    responder = AssessmentResponder(proposal)
    service = Service(engine, responder=responder)
    context = service.identity.context("normal")
    request = AskRequest(
        namespace="assessment-test", question="What is a planet?", representation="auto"
    )
    return service, context, request, responder


def assert_no_memory_writes(engine):
    with Session(engine) as session:
        assert [
            session.scalar(select(func.count()).select_from(model))
            for model in (Source, Job, ClaimRecord)
        ] == [0, 0, 0]


def test_ready_decision_is_reusable_without_retaining_question(engine):
    service, context, request, responder = setup(engine)
    message_id = uuid4()
    first = service.assess_turn(context, request, message_id)
    again = service.assess_turn(context, request, message_id)
    assert first == again
    assert first["status"] == "ready" and first["decision"] == SKIP
    assert responder.calls == 1
    assert first["calls"][0]["input_tokens"] == 30
    with Session(engine) as session:
        record = session.get(TurnAssessment, UUID(first["assessment_id"]))
        retained = {
            column.name: getattr(record, column.name) for column in record.__table__.columns
        }
        assert request.question not in json.dumps(retained, default=str)
        assert record.attempts == 1
        attached = request.model_copy(update={"assessment_id": record.id})
        assert service._read_turn_decision(session, context, attached).retention == "skip"
        assert service._read_turn_receipt(session, context, attached) == first
    assert_no_memory_writes(engine)


@pytest.mark.parametrize("route", ["general", "contextual", "mixed", "live"])
def test_retention_and_answer_route_are_independent(engine, route):
    excerpt = "I prefer tea."
    proposed = {
        "retention": "candidate",
        "route": route,
        "reason": "useful_assertion",
        "memory_excerpts": [excerpt],
    }
    service, context, request, responder = setup(engine, proposed)
    request = request.model_copy(update={"question": excerpt + " What is caffeine?"})
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "ready" and result["decision"] == proposed
    assert responder.questions == [request.question]
    assert_no_memory_writes(engine)  # Assessment only selects; capture remains separate.


@pytest.mark.parametrize(
    "proposal",
    [
        "not json",
        {**SKIP, "memory_excerpts": ["What is a planet?"]},
        {
            "retention": "candidate",
            "route": "general",
            "reason": "useful_assertion",
            "memory_excerpts": ["invented"],
        },
        {
            "retention": "candidate",
            "route": "general",
            "reason": "useful_assertion",
            "memory_excerpts": ["tea"],
        },
        {
            "retention": "candidate",
            "route": "general",
            "reason": "useful_assertion",
            "memory_excerpts": ["I prefer tea", "prefer tea"],
        },
        {**SKIP, "route": "clock"},
        {**SKIP, "unexpected": "not allowed"},
    ],
)
def test_invalid_or_ambiguous_selection_repairs_once_and_stores_no_sources(engine, proposal):
    service, context, request, responder = setup(engine, proposal)
    request = request.model_copy(update={"question": "I prefer tea. I drink tea."})
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "failed"
    assert result["error_code"] == ErrorCode.PROVIDER_RESPONSE.value
    assert result["decision"] is None
    assert responder.calls == 2 and responder.repairs[0] is False
    assert isinstance(responder.repairs[1], str)
    assert len(result["calls"]) == 2
    assert all(call["status"] == "failed" for call in result["calls"])
    assert_no_memory_writes(engine)


def test_one_structural_repair_can_recover_without_duplicate_usage(engine):
    service, context, request, responder = setup(engine)
    responder.proposal = lambda _: "not JSON" if responder.calls == 1 else SKIP
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "ready"
    assert [call["status"] for call in result["calls"]] == ["failed", "succeeded"]
    with Session(engine) as session:
        budget = session.get(ModelBudget, responder.budget_key)
        assert (budget.requests, budget.tokens) == (2, 100)


def test_failures_require_explicit_retry_and_preserve_four_call_ceiling(engine):
    service, context, request, responder = setup(engine, "broken")
    message_id = uuid4()
    first = service.assess_turn(context, request, message_id)
    assert service.assess_turn(context, request, message_id) == first
    second = service.assess_turn(context, request, message_id, retry_failed=True)
    assert len(second["calls"]) == 4
    last = service.assess_turn(context, request, message_id, retry_failed=True)
    assert last["error_code"] == ErrorCode.RETRY_LIMIT.value
    assert responder.calls == 4
    assert_no_memory_writes(engine)


def test_network_failure_does_not_blindly_retry_or_save(engine):
    service, context, request, responder = setup(engine, TimeoutError())
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "failed" and result["error_code"] == "provider_failed"
    assert responder.calls == 1
    with Session(engine) as session:
        assert session.get(ModelBudget, responder.budget_key).tokens == 1000
    assert_no_memory_writes(engine)


def test_broken_usage_reservation_prevents_ready_decision(engine):
    service, context, request, responder = setup(engine)
    responder.complete = lambda body: Completion(json.dumps(SKIP), responder.model, 1000, 1, 1)
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "failed" and result["error_code"] == "budget_exhausted"
    assert result["calls"][0]["status"] == "failed"
    assert result["decision"] is None
    assert_no_memory_writes(engine)


def test_concurrent_duplicate_uses_live_lease_and_one_model_call(engine):
    entered, release = Event(), Event()

    def blocked(_):
        entered.set()
        assert release.wait(10)
        return SKIP

    service, context, request, responder = setup(engine, blocked)
    message_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.assess_turn, context, request, message_id)
        assert entered.wait(10)
        try:
            running = service.assess_turn(context, request, message_id)
            assert running["status"] == "running" and responder.calls == 1
        finally:
            release.set()
        result = first.result(timeout=10)
    assert result["status"] == "ready" and responder.calls == 1
    assert service.assess_turn(context, request, message_id) == result


def test_expired_lease_reclaims_without_reusing_stale_completion(engine):
    entered, release = Event(), Event()

    def blocked_once(_):
        if responder.calls == 1:
            entered.set()
            assert release.wait(10)
            return {**SKIP, "reason": "small_talk"}
        return SKIP

    service, context, request, responder = setup(engine, blocked_once)
    message_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.assess_turn, context, request, message_id)
        assert entered.wait(10)
        try:
            with engine.begin() as connection:
                connection.execute(
                    update(TurnAssessment).values(
                        lease_until=func.clock_timestamp() - timedelta(seconds=1)
                    )
                )
            result = service.assess_turn(context, request, message_id)
            assert result["status"] == "ready" and result["decision"] == SKIP
        finally:
            release.set()
        first.result(timeout=10)
    assert service.assess_turn(context, request, message_id)["decision"] == SKIP
    assert responder.calls == 2


def test_request_and_owner_binding_reject_substitution(engine):
    service, context, request, responder = setup(engine)
    message_id = uuid4()
    receipt = service.assess_turn(context, request, message_id)
    altered = request.model_copy(update={"question": "I prefer coffee."})
    with pytest.raises(ApplicationError, match="import_conflict"):
        service.assess_turn(context, altered, message_id)
    attached = request.model_copy(update={"assessment_id": UUID(receipt["assessment_id"])})
    other = Service(engine, identity=LocalIdentity(uuid4()), responder=responder)
    with Session(engine) as session, pytest.raises(ApplicationError, match="reference_unavailable"):
        other._read_turn_decision(session, other.identity.context("normal"), attached)
    with Session(engine) as session, pytest.raises(ApplicationError, match="reference_unavailable"):
        service._read_turn_decision(
            session, context, attached.model_copy(update={"namespace": "elsewhere"})
        )


def test_policy_change_during_model_call_prevents_ready_commit(engine):
    def revoke(_):
        with engine.begin() as connection:
            connection.execute(update(Policy).values(revision=Policy.revision + 1))
        return SKIP

    service, context, request, responder = setup(engine, revoke)
    result = service.assess_turn(context, request, uuid4())
    assert result["status"] == "failed" and result["error_code"] == "stale_revision"
    assert result["calls"][0]["status"] == "failed"
    assert_no_memory_writes(engine)


def test_ready_decision_cannot_be_reused_after_policy_change(engine):
    service, context, request, responder = setup(engine)
    message_id = uuid4()
    receipt = service.assess_turn(context, request, message_id)
    with engine.begin() as connection:
        connection.execute(update(Policy).values(revision=Policy.revision + 1))
    attached = request.model_copy(update={"assessment_id": UUID(receipt["assessment_id"])})
    with Session(engine) as session, pytest.raises(ApplicationError, match="stale_revision"):
        service._read_turn_decision(session, context, attached)
    result = service.assess_turn(context, request, message_id, retry_failed=True)
    assert result["status"] == "failed" and result["error_code"] == "stale_revision"
    assert responder.calls == 1


def test_private_rejection_precedes_parsing_provider_and_database(engine, monkeypatch):
    service, context, request, responder = setup(engine)

    def denied(*args, **kwargs):
        raise AssertionError("Private assessment accessed a forbidden dependency")

    monkeypatch.setattr(engine, "connect", denied)
    monkeypatch.setattr(responder, "prepare_assessment", denied)
    with pytest.raises(ApplicationError, match="private_operation_denied"):
        service.assess_turn(service.identity.context("private"), object(), object())
