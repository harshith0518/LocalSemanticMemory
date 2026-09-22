"""Semantic routing contracts with scripted decisions, never live model-quality evidence."""

import json

import pytest
from answer_double import FixtureResponder
from test_auto_answers import request, setup_notes
from test_conversation import message, send
from test_private import snapshot

from jarvis.errors import ApplicationError
from jarvis.services import Service

LONG_CAPITAL = (
    "what is the capital of USA ? I just want to know the city and in which state it is present"
)

ACCOUNTING_TABLES = {"model_calls", "model_budgets", "turn_assessments"}


@pytest.mark.parametrize(
    "question",
    [
        LONG_CAPITAL,
        "what is the capital of USA ?",
        "how many planets are there in the solar system ?",
        "Explain photosynthesis in two sentences.",
        "What does a project manager do? Explain it to me.",
        "What is the US capital?",
        "Tell me a joke.",
    ],
)
def test_general_decision_keeps_no_source_job_or_memory_and_sends_no_notes(engine, question):
    seen = []

    def general(data, result):
        seen.append(data)
        return {"status": "general", "text": "A synthetic public answer.", "citations": []}

    service, context = setup_notes(engine, responder=FixtureResponder(general))
    before = snapshot(engine)
    payload = message(question)
    payload["request"]["namespace"] = "auto"
    receipt = service.save_message(context, payload)
    assert receipt["status"] == "not_saved" and receipt["source_id"] is None
    assert receipt["calls"] == []
    assert receipt["assessment"]["decision"]["route"] == "general"
    assert len(receipt["assessment"]["calls"]) == 1
    assert service.save_message(context, payload) == receipt
    assert service.responder.assessment_calls == 1
    after_capture = snapshot(engine)
    for key in before.keys() - ACCOUNTING_TABLES:
        assert before[key] == after_capture[key]
    assert question not in json.dumps(after_capture["turn_assessments"])

    result = service.ask(context, {**payload["request"], "assessment_id": receipt["assessment_id"]})
    assert result["status"] == "general" and result["evidence_bytes"] == 0
    assert result["retrieval"]["strategy"] == "general_question"
    assert result["retrieval"]["sources_reviewed"] == 0
    assert result["retrieval"]["memories_reviewed"] == 0
    assert "No workspace evidence was sent" in result["notice"]
    assert seen[0]["SOURCES"] == seen[0]["MEMORIES"] == []
    assert seen[0]["GENERAL_KNOWLEDGE_ALLOWED"] is True
    assert result["assessment"] == receipt["assessment"]
    assert len(result["call_ids"]) == 1 and service.responder.assessment_calls == 1
    after = snapshot(engine)
    for key in before.keys() - ACCOUNTING_TABLES:
        assert before[key] == after[key]


@pytest.mark.parametrize(
    "question,reason",
    [
        ("Hypothetically, suppose I prefer coffee. Explain photosynthesis.", "hypothetical"),
        ("For this answer only, use three bullet points. Explain gravity.", "one_off"),
        ("Hello Jarvis, how are you?", "small_talk"),
    ],
)
def test_nonlasting_decisions_skip_persistence_without_relying_on_personal_pronouns(
    engine, question, reason
):
    service, context = setup_notes(engine)
    before = snapshot(engine)
    receipt = service.save_message(context, message(question))
    assert receipt["source_id"] is None and receipt["calls"] == []
    assert receipt["assessment"]["decision"] == {
        "retention": "skip",
        "route": "general",
        "reason": reason,
        "memory_excerpts": [],
    }
    after = snapshot(engine)
    for key in before.keys() - ACCOUNTING_TABLES:
        assert before[key] == after[key]
    assert question not in json.dumps(after["turn_assessments"])


@pytest.mark.parametrize(
    "question",
    ["What is my favourite beverage?", "What is Atlas?", "I just want to know my manager's name"],
)
def test_personal_question_is_transient_but_still_retrieves_workspace_evidence(engine, question):
    service, context = setup_notes(engine)
    payload = message(question)
    payload["request"]["namespace"] = "auto"
    receipt = service.save_message(context, payload)
    assert receipt["source_id"] is None
    assert receipt["assessment"]["decision"]["route"] == "contextual"
    packet = service.prepare_answer(
        context, {**payload["request"], "assessment_id": receipt["assessment_id"]}
    )
    assert packet.evidence.strategy in {"memory_first_ranked", "ranked_sources_and_memories"}
    assert len(packet.evidence.sources) <= 1
    assert all(source.source_key.startswith("import:auto:") for source in packet.evidence.sources)
    assert service.responder.assessment_calls == 1


def test_completed_no_memory_history_is_retained_but_not_auto_evidence(engine):
    from memory_double import FixtureExtractor

    service, context = setup_notes(engine)
    service.extractor = FixtureExtractor(lambda data: {"decision": "no_memory"})
    payload = message("I prefer tea.")
    payload["request"]["namespace"] = "auto"
    receipt = send(service, context, payload)
    assert receipt["decision"] == "no_memory"
    assert len(service.list_sources(context, {"namespace": "auto"}).observations) == 3
    packet = service.prepare_answer(context, request("What is my favourite beverage?"))
    assert not packet.evidence.sources
    assert all(str(s.id) != receipt["source_id"] for s in packet.evidence.sources)
    assert packet.evidence.eligible_sources == 2


def test_invalid_model_output_is_not_reported_as_invalid_user_input(engine):
    service = Service(
        engine,
        responder=FixtureResponder(
            lambda data, result: {"status": "general", "text": "An invented personal fact."}
        ),
    )
    context = service.identity.context("normal")
    with pytest.raises(ApplicationError, match="provider_response_invalid"):
        service.ask(context, request("What is my favourite beverage?"))
    assert service.responder.calls == 2 and service.responder.assessment_calls == 1


@pytest.mark.parametrize(
    "question",
    [
        "I work on Cedar. How many planets are in the solar system?",
        "I prefer tea. What does a project manager do?",
        "What is the capital of USA? Atlas uses PostgreSQL.",
    ],
)
def test_retention_and_answer_route_are_independent_for_fact_plus_public_question(engine, question):
    service, context = setup_notes(
        engine,
        responder=FixtureResponder(
            lambda data, result: {"status": "general", "text": "A public answer.", "citations": []}
        ),
    )
    payload = message(question)
    receipt = service.save_message(context, payload)
    assert receipt["status"] == "pending" and receipt["source_id"] is not None
    decision = receipt["assessment"]["decision"]
    assert decision["retention"] == "candidate" and decision["route"] == "general"
    assert decision["memory_excerpts"] and all(q in question for q in decision["memory_excerpts"])
    source = service.read_source(context, receipt["source_id"])
    assert source.raw_text == question
    result = service.ask(context, {**payload["request"], "assessment_id": receipt["assessment_id"]})
    assert result["status"] == "general" and result["sources"] == []
    assert service.responder.assessment_calls == 1


def mixed_decision(_):
    return {
        "retention": "skip",
        "route": "mixed",
        "reason": "personal_question",
        "memory_excerpts": [],
    }


def test_mixed_answer_keeps_grounded_personal_and_unsourced_general_sections_separate(engine):
    general_text = "A synthetic explanation of caffeine from general knowledge."
    service, context = setup_notes(
        engine,
        responder=FixtureResponder(
            lambda data, result: {**result, "status": "mixed", "general_text": general_text},
            assessment=mixed_decision,
        ),
    )
    result = service.ask(context, request("What is my favourite beverage, and what is caffeine?"))
    assert result["status"] == "mixed" and result["general_text"] == general_text
    assert result["citations"] and result["sources"]
    assert general_text not in result["text"]
    assert result["assessment"]["decision"]["retention"] == "skip"
    assert len(service.list_sources(context, {"namespace": "auto"}).observations) == 2


def test_mixed_route_cannot_replace_missing_personal_knowledge_with_general_output(engine):
    service, context = setup_notes(
        engine,
        responder=FixtureResponder(
            lambda data, result: {"status": "general", "text": "You prefer coffee."},
            assessment=mixed_decision,
        ),
    )
    with pytest.raises(ApplicationError, match="provider_response_invalid"):
        service.ask(context, request("What is my favourite beverage, and what is caffeine?"))
    assert service.responder.calls == 3
