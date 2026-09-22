"""Regression cases derived from observed failures; fixtures are not live quality evidence."""

import json
from datetime import date
from uuid import uuid4

import pytest
from answer_double import FixtureResponder
from memory_double import content, passage
from sqlalchemy import update

from jarvis.answer_policy import general_knowledge_allowed
from jarvis.answers import AnswerProposal, answer_messages
from jarvis.errors import ApplicationError
from jarvis.models import ClaimRecord, Policy
from jarvis.policy import LocalIdentity
from jarvis.services import Service


def setup_notes(engine, rows=None, responder=None):
    service = Service(engine, responder=responder or FixtureResponder())
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {"namespace": "auto", "expected_policy_revision": 0},
        "\n".join(
            json.dumps(row)
            for row in (
                rows
                or [
                    {"record_id": "tea", "raw_transcript": "When I feel good, I want to have tea."},
                    {
                        "record_id": "atlas",
                        "raw_transcript": "Atlas launch is planned for September 21, 2026.",
                    },
                ]
            )
        ),
    )
    return service, context


def request(question, **extra):
    return {"namespace": "auto", "question": question, "representation": "auto", **extra}


def test_public_memory_concept_is_distinct_from_personal_inventory():
    assert general_knowledge_allowed("Explain semantic memory.")
    assert general_knowledge_allowed("Tell me how databases work.")
    assert not general_knowledge_allowed("What are all the things in your memory?")
    assert not general_knowledge_allowed("What is in the database?")


@pytest.mark.parametrize(
    "question",
    [
        "did i mention anything about any beverage ?",
        "what i like to drink ?",
        "do you know any projects mentioned in the data memory ?",
        "what are all the things you have remembered so far?",
    ],
)
def test_complete_small_collection_recovers_zero_lexical_matches(engine, question):
    service, context = setup_notes(engine)
    packet = service.prepare_answer(context, request(question))
    assert len(packet.evidence.sources) == 2
    assert packet.evidence.strategy == "complete_collection"
    assert not packet.evidence.has_more
    answer = service.ask(context, request(question))
    assert answer["status"] == "answered" and len(answer["call_ids"]) == 1
    assert answer["retrieval"]["sources_reviewed"] == 2


def test_auto_reads_current_memories_and_their_exact_support(engine):
    service, context = setup_notes(engine)
    source = service.read_source(
        context, service.list_sources(context, {"namespace": "auto"}).observations[0].id
    )
    service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": content("topic", "launch", subject="Atlas", scope="Atlas"),
            "passages": [passage(source.model_dump(mode="json"))],
        },
    )
    packet = service.prepare_answer(context, request("What have you remembered?"))
    assert len(packet.evidence.memories) == 1
    prompt = json.loads(answer_messages(packet)[1]["content"])
    assert prompt["MEMORIES"] and len(prompt["SOURCES"]) == 2
    assert "Preserve conditions" in answer_messages(packet)[0]["content"]
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.release_answer(
            context,
            service.prepare_answer(context, request("Who is Atlas?")),
            AnswerProposal(status="general", text="Atlas is a mythological person."),
        )


def test_clock_uses_runtime_timezone_without_provider_or_learning(engine, monkeypatch):
    from test_private import snapshot

    service, context = setup_notes(engine)
    monkeypatch.setattr("jarvis.answers.today_in", lambda timezone: date(2026, 9, 22))
    before = snapshot(engine)
    result = service.ask(
        context,
        request("what is the todays date ? just use your knowledge", timezone="Asia/Kolkata"),
    )
    assert result["status"] == "clock" and "22 September 2026" in result["text"]
    assert "Asia/Kolkata" in result["text"] and result["basis"] == "application_clock"
    assert result["model"] is None and result["call_ids"] == []
    assert result["sources"] == [] and service.responder.calls == 0
    assert snapshot(engine) == before
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.ask(context, request("What is today's date?", timezone="Invalid/Timezone"))


def test_current_weather_explains_missing_live_tool_without_guessing(engine):
    service, context = setup_notes(engine)
    answer = service.ask(context, request("What is today's weather in Bengaluru?"))
    assert answer["status"] == "unknown" and answer["call_ids"] == []
    assert "live web search is not connected" in answer["text"]
    assert "cannot establish a current fact" in answer["notice"]


def test_general_answer_is_labelled_without_citations_and_not_learned(engine):
    from test_private import snapshot

    def general(data, result):
        return {
            "status": "general",
            "text": "Photosynthesis converts light energy into chemical energy.",
            "citations": [],
        }

    service, context = setup_notes(engine, responder=FixtureResponder(general))
    before = snapshot(engine)
    result = service.ask(context, request("Explain photosynthesis."))
    assert result["basis"] == "general_knowledge" and not result["citations"]
    assert "not verified by live web search" in result["notice"]
    after = snapshot(engine)
    for key in before.keys() - {"model_calls", "model_budgets"}:
        assert before[key] == after[key]


def test_first_ever_question_can_use_general_knowledge_without_any_import(engine):
    from test_private import snapshot

    def general(data, result):
        return {"status": "general", "text": "A triangle has three sides.", "citations": []}

    service = Service(engine, responder=FixtureResponder(general))
    context = service.identity.context("normal")
    result = service.ask(context, request("How many sides does a triangle have?"))
    assert result["status"] == "general" and result["sources"] == []
    assert result["retrieval"]["sources_reviewed"] == 0
    assert result["retrieval"]["strategy"] == "general_question"
    state = snapshot(engine)
    assert not state["sources"] and not state["jobs"] and not state["claim_revisions"]
    assert len(state["model_calls"]) == 1


@pytest.mark.parametrize(
    "question",
    [
        "What is my favorite beverage?",
        "What is today's weather?",
        "What is the latest share price?",
        "Which projects have I completed?",
        "What medication should I take?",
    ],
)
def test_personal_and_current_facts_cannot_escape_as_general(engine, question):
    service, context = setup_notes(engine)
    packet = service.prepare_answer(context, request(question))
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.release_answer(
            context, packet, AnswerProposal(status="general", text="A made-up fact.")
        )


def test_strict_comparison_still_requires_evidence(engine):
    service, context = setup_notes(engine)
    packet = service.prepare_answer(
        context, request("Explain photosynthesis", representation="sources")
    )
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.release_answer(
            context, packet, AnswerProposal(status="general", text="A public fact.")
        )
    assert service.ask(context, request("quasar", representation="sources"))["status"] == "unknown"
    assert service.responder.calls == 0


def test_large_collection_uses_one_counted_rewrite_and_reveals_partial_coverage(engine):
    rows = [
        {"record_id": f"n-{i}", "raw_transcript": f"Storage entry {i} contains a widget."}
        for i in range(51)
    ]
    rows.append({"record_id": "tea", "raw_transcript": "When I feel good, I want tea."})
    service, context = setup_notes(engine, rows)
    result = service.ask(context, request("did i mention anything about any beverage ?"))
    assert result["retrieval"]["query_expanded"] is True
    assert result["retrieval"]["partial"] is True
    assert any("want tea" in s["raw_text"] for s in result["sources"])
    assert len(result["call_ids"]) == 2
    assert result["retrieval"]["eligible_sources"] == 52
    assert "Only part" in result["notice"]


def test_large_inventory_never_claims_complete_review(engine):
    service, context = setup_notes(
        engine,
        [
            {"record_id": f"n-{i}", "raw_transcript": f"Entry {i}: " + "synthetic text " * 80}
            for i in range(55)
        ],
    )
    packet = service.prepare_answer(context, request("What is the whole data stored in memory?"))
    assert packet.evidence.has_more and len(packet.evidence.sources) < 55
    assert packet.evidence.strategy == "collection_overview"
    assert packet.evidence.evidence_bytes <= 24000


def test_auto_keeps_revision_and_private_gates(engine):
    service, context = setup_notes(engine)
    packet = service.prepare_answer(context, request("Which beverage?"))
    with engine.begin() as connection:
        connection.execute(update(Policy).values(revision=1))
    with pytest.raises(ApplicationError, match="stale_revision"):
        service.release_answer(
            context, packet, AnswerProposal(status="unknown", text="Missing evidence")
        )
    with pytest.raises(ApplicationError, match="private_operation"):
        service.ask(service.identity.context("private"), request("What do you remember?"))


def test_auto_never_loads_another_owner_collection_or_excluded_support(engine):
    service, context = setup_notes(engine)
    for owner, namespace in [
        (service, "elsewhere"),
        (Service(engine, LocalIdentity(uuid4())), "auto"),
    ]:
        owner.import_observations(
            owner.identity.context("normal"),
            {"namespace": namespace, "expected_policy_revision": 0},
            json.dumps({"record_id": "hidden", "raw_transcript": "PRIVATE_FOREIGN_SENTINEL tea"}),
        )
    source = service.read_source(
        context, service.list_sources(context, {"namespace": "auto"}).observations[0].id
    )
    service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": content("topic", "launch", subject="Atlas", scope="Atlas"),
            "passages": [passage(source.model_dump(mode="json"))],
        },
    )
    with engine.begin() as connection:
        connection.execute(update(ClaimRecord).values(lifecycle="excluded"))
    packet = service.prepare_answer(context, request("What are all your memories?"))
    assert len(packet.evidence.sources) == 1
    assert all(s.id != source.id for s in packet.evidence.sources)
    assert "PRIVATE_FOREIGN_SENTINEL" not in packet.model_dump_json()


def test_planner_outage_is_a_service_failure_not_general_fallback(engine):
    service, context = setup_notes(
        engine, [{"record_id": f"n-{i}", "raw_transcript": f"Widget {i}"} for i in range(51)]
    )
    service.responder.complete = lambda body: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(ApplicationError, match="provider_failed"):
        service.ask(context, request("Explain photosynthesis"))
