"""Regression contracts for public questions, selective storage and actual context."""

import pytest
from answer_double import FixtureResponder
from test_auto_answers import request, setup_notes
from test_conversation import message, send
from test_private import snapshot

from jarvis.answer_policy import general_knowledge_allowed, general_question_candidate
from jarvis.errors import ApplicationError
from jarvis.services import Service

LONG_CAPITAL = (
    "what is the capital of USA ? I just want to know the city and in which state it is present"
)


@pytest.mark.parametrize(
    "question",
    [
        LONG_CAPITAL,
        "what is the capital of USA ?",
        "how many planets are there in the solar system ?",
        "Explain photosynthesis in two sentences.",
    ],
)
def test_public_question_keeps_no_source_job_or_memory_and_sends_no_notes(engine, question):
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
    assert service.save_message(context, payload) == receipt
    assert snapshot(engine) == before
    result = service.ask(context, payload["request"])
    assert result["status"] == "general" and result["evidence_bytes"] == 0
    assert result["retrieval"]["strategy"] == "general_question"
    assert result["retrieval"]["sources_reviewed"] == 0
    assert result["retrieval"]["memories_reviewed"] == 0
    assert "No workspace evidence was sent" in result["notice"]
    assert seen[0]["SOURCES"] == seen[0]["MEMORIES"] == []
    assert seen[0]["GENERAL_KNOWLEDGE_ALLOWED"] is True
    after = snapshot(engine)
    for key in before.keys() - {"model_calls", "model_budgets"}:
        assert before[key] == after[key]


@pytest.mark.parametrize(
    "question",
    [
        "What is my favourite beverage?",
        "What is the capital? I just want to know my project's location.",
        "I work at a space company. How many planets are there?",
        "What is the capital? Atlas uses PostgreSQL.",
        "What is the capital? I live in Seattle.",
        "What is Atlas's secret access code?",
    ],
)
def test_personal_mixed_or_ambiguous_messages_do_not_take_public_fast_path(question):
    assert not general_question_candidate(question)


def test_request_framing_does_not_disable_public_knowledge_or_erase_personal_context():
    assert general_knowledge_allowed(LONG_CAPITAL)
    assert general_knowledge_allowed("I just want to know what the capital of USA is")
    assert not general_knowledge_allowed("I just want to know my manager's name")


def test_question_only_history_is_retained_but_not_auto_evidence(engine):
    from memory_double import FixtureExtractor

    service, context = setup_notes(engine)
    service.extractor = FixtureExtractor(lambda data: {"decision": "no_memory"})
    payload = message("What is my favourite beverage?")
    payload["request"]["namespace"] = "auto"
    receipt = send(service, context, payload)
    assert receipt["decision"] == "no_memory"
    assert len(service.list_sources(context, {"namespace": "auto"}).observations) == 3
    packet = service.prepare_answer(context, request("What is my favourite beverage?"))
    assert len(packet.evidence.sources) == 2
    assert all(str(s.id) != receipt["source_id"] for s in packet.evidence.sources)
    assert packet.evidence.eligible_sources == 2


def test_workspace_name_without_extraction_still_uses_original_evidence(engine):
    service, context = setup_notes(engine)
    payload = message("What is Atlas?")
    payload["request"]["namespace"] = "auto"
    receipt = service.save_message(context, payload)
    assert receipt["source_id"] is not None
    packet = service.prepare_answer(context, payload["request"])
    assert packet.evidence.strategy == "complete_collection"
    assert any("Atlas launch" in s.raw_text for s in packet.evidence.sources)


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
    assert service.responder.calls == 2


def test_mixed_assertion_is_still_saved_even_with_a_general_question(engine):
    service, context = setup_notes(engine)
    payload = message("I work on Cedar. How many planets are in the solar system?")
    receipt = service.save_message(context, payload)
    assert receipt["status"] == "pending" and receipt["source_id"] is not None
    source = service.read_source(context, receipt["source_id"])
    assert source.raw_text == payload["request"]["question"]
