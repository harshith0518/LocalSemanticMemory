"""Real PostgreSQL contract checks; deterministic proposals are not model-quality evidence."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from answer_double import FixtureResponder
from memory_double import FixtureExtractor, content, operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_private import no_store_access, snapshot

from jarvis.api import create_app
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.models import Job, Source
from jarvis.policy import LocalIdentity
from jarvis.services import Service


def message(text="Atlas uses PostgreSQL. What database does Atlas use?", **changes):
    return {
        "message_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "request": {"namespace": "chat", "question": text, "representation": "auto"},
        **changes,
    }


def reconcile(data):
    source = data["CURRENT_SOURCE"]
    text = source["raw_text"]
    if "uses" not in text and "now uses" not in text:
        return {"decision": "no_memory", "operations": []}
    value = "SQLite" if "SQLite" in text else "PostgreSQL"
    target = next((m for m in data["MEMORIES"] if m["content"]["predicate"] == "database"), None)
    if target and target["content"]["value"]["value"] == value:
        return {"decision": "duplicate", "operations": []}
    proposed = operation(
        source,
        content("database", value),
        action="supersede" if target else "add",
        target=target["id"] if target else None,
    )
    if excerpts := data.get("MEMORY_CANDIDATES"):
        proposed["passages"][0].update(
            start=text.index(excerpts[0]),
            end=text.index(excerpts[0]) + len(excerpts[0]),
            exact_text=excerpts[0],
        )
    return {
        "decision": "extracted",
        "operations": [proposed],
    }


@pytest.fixture
def chat(engine):
    service = Service(engine, extractor=FixtureExtractor(reconcile), responder=FixtureResponder())
    return service, service.identity.context("normal")


def send(service, context, payload):
    saved = service.save_message(context, payload)
    payload["request"]["assessment_id"] = saved["assessment_id"]
    if saved["source_id"] is None:
        return saved
    return service.learn_message(context, saved["source_id"], {})


def test_chat_preserves_exact_user_message_learns_and_answers_without_saving_reply(chat, engine):
    service, context = chat
    payload = message()
    saved = send(service, context, payload)
    assert saved["status"] == "succeeded" and saved["decision"] == "extracted"
    assert len(saved["calls"]) == 1 and saved["calls"][0]["input_tokens"] == 100
    answer = service.ask(context, payload["request"])
    assert answer["status"] == "answered"
    with Session(engine) as session:
        sources = session.scalars(select(Source)).all()
        assert len(sources) == 1
        assert sources[0].raw_text == payload["request"]["question"]
        assert sources[0].kind == "user_message" and sources[0].formatted_text is None
    replay = send(service, context, payload)
    assert replay == saved and service.extractor.calls == 1


def test_same_message_id_cannot_change_text_or_conversation(chat):
    service, context = chat
    payload = message()
    service.save_message(context, payload)
    for changed in (
        {**payload, "request": {**payload["request"], "question": "Different words"}},
        {**payload, "conversation_id": str(uuid4())},
    ):
        with pytest.raises(ApplicationError, match="import_conflict"):
            service.save_message(context, changed)


def test_repeat_stays_as_source_without_memory_duplication_and_update_keeps_history(chat):
    service, context = chat
    payload = message()
    first = send(service, context, payload)
    repeated = send(service, context, {**payload, "message_id": str(uuid4())})
    assert repeated["decision"] == "duplicate" and repeated["revision_ids"] == []
    changed = send(
        service,
        context,
        message("Atlas now uses SQLite.", conversation_id=payload["conversation_id"]),
    )
    assert changed["decision"] == "extracted"
    memories = service.list_memories(context, {"namespace": "chat"})["memories"]
    assert len(memories) == 1 and memories[0]["content"]["value"]["value"] == "SQLite"
    history = service.memory_history(context, memories[0]["claim_id"])
    assert [r["content"]["value"]["value"] for r in history["revisions"]] == [
        "PostgreSQL",
        "SQLite",
    ]
    assert history["revisions"][0]["id"] == first["revision_ids"][0]
    assert len(service.list_sources(context, {"namespace": "chat"}).observations) == 3


def test_personal_question_is_transient_without_source_job_or_memory(chat, engine):
    service, context = chat
    result = send(service, context, message("What is Atlas's secret access code?"))
    assert result["decision"] == "no_memory" and result["status"] == "not_saved"
    assert result["source_id"] is None and result["calls"] == []
    assert result["assessment"]["decision"]["route"] == "contextual"
    assert service.list_sources(context, {"namespace": "chat"}).observations == ()
    assert service.list_memories(context, {"namespace": "chat"})["memories"] == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_context_is_bounded_to_previous_user_messages_in_same_conversation_and_collection(chat):
    service, context = chat
    conversation_id = str(uuid4())
    previous = [
        service.save_message(
            context,
            message(f"Atlas uses PostgreSQL for component {i}.", conversation_id=conversation_id),
        )
        for i in range(8)
    ]
    service.save_message(context, message("Atlas uses PostgreSQL elsewhere."))
    other_collection = message("Atlas uses SQLite elsewhere.", conversation_id=conversation_id)
    other_collection["request"]["namespace"] = "elsewhere"
    service.save_message(context, other_collection)
    seen = []
    service.extractor = FixtureExtractor(
        lambda data: seen.append(data) or {"decision": "no_memory"}
    )
    send(service, context, message("Atlas now uses SQLite.", conversation_id=conversation_id))
    assert [s["id"] for s in seen[0]["RECENT_USER_MESSAGES"]] == [
        s["source_id"] for s in previous[-6:]
    ]
    assert all(
        s["raw_text"].startswith("Atlas uses PostgreSQL for component") for s in seen[0]["SOURCES"]
    )


def test_selected_learning_leaves_unrelated_queued_imports_alone(chat, engine):
    service, context = chat
    service.import_observations(
        context,
        {"namespace": "aaa", "expected_policy_revision": 0},
        json.dumps({"record_id": "old", "raw_transcript": "Unrelated note."}),
    )
    service.request_processing(context, {"namespace": "aaa", "expected_policy_revision": 0})
    assert send(service, context, message())["decision"] == "extracted"
    with Session(engine) as session:
        job = session.scalar(
            select(Job)
            .join(Source, Source.id == Job.source_id)
            .where(Source.source_key == "import:aaa:old")
        )
        assert job.status == "pending" and job.attempts == 0


def test_learning_outage_preserves_message_and_does_not_block_answer_or_silently_retry(chat):
    service, context = chat

    def fail(_):
        raise RuntimeError("Provider secret must not escape")

    service.extractor.complete = fail
    payload = message()
    result = send(service, context, payload)
    assert result["status"] == "failed" and result["error_code"] == "provider_failed"
    assert service.ask(context, payload["request"])["status"] == "answered"
    assert send(service, context, payload)["attempts"] == 1
    for attempt in (2, 3):
        assert (
            service.learn_message(context, result["source_id"], {"retry_failed": True})["attempts"]
            == attempt
        )
    assert (
        service.learn_message(context, result["source_id"], {"retry_failed": True})["attempts"] == 3
    )
    assert len(service.list_sources(context, {"namespace": "chat"}).observations) == 1


def test_answer_failure_does_not_undo_saved_and_learned_message(chat):
    service, context = chat
    payload = message()
    saved = send(service, context, payload)
    service.responder.complete = lambda _: (_ for _ in ()).throw(RuntimeError("outage"))
    with pytest.raises(ApplicationError, match="provider_failed"):
        service.ask(context, payload["request"])
    assert service.message_learning(context, saved["source_id"])["decision"] == "extracted"


def test_other_owner_and_private_cannot_read_or_learn_message(chat, engine, monkeypatch):
    service, context = chat
    saved = service.save_message(context, message())
    other = Service(engine, identity=LocalIdentity(owner_id=uuid4()), extractor=FixtureExtractor())
    with pytest.raises(ApplicationError, match="reference_unavailable"):
        other.learn_message(other.identity.context("normal"), saved["source_id"], {})
    private = service.identity.context("private")
    before = snapshot(engine)
    with no_store_access(engine, monkeypatch):
        for operation_call in (
            lambda: service.save_message(private, "invalid"),
            lambda: service.learn_message(private, "invalid", "invalid"),
            lambda: service.message_learning(private, "invalid"),
        ):
            with pytest.raises(ApplicationError, match="private_operation_denied"):
                operation_call()
    assert snapshot(engine) == before


def test_concurrent_capture_has_one_original_and_job(chat, settings, engine):
    _, context = chat
    payload = message()
    start = Barrier(2, timeout=10)

    def capture():
        connection = make_engine(settings)
        try:
            service = Service(
                connection, extractor=FixtureExtractor(), responder=FixtureResponder()
            )
            start.wait()
            return service.save_message(context, payload)
        finally:
            connection.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: capture(), range(2)))
    source_ids = {r["source_id"] for r in results if r["source_id"] is not None}
    assert len(source_ids) == 1
    # The request that observes a running assessment may return before its peer
    # finishes. An explicit replay converges on the one retained source/job.
    assert chat[0].save_message(context, payload)["source_id"] in source_ids
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_forgotten_message_and_exact_repetition_cannot_be_relearned(chat):
    service, context = chat
    payload = message()
    saved = send(service, context, payload)
    claim = service.list_memories(context, {"namespace": "chat"})["memories"][0]
    command = {
        "operation_id": str(uuid4()),
        "namespace": "chat",
        "target_revision_id": claim["id"],
        "expected_policy_revision": 0,
        "action": "forget",
    }
    preview = service.preview_control(context, command)
    service.apply_control(context, {**command, "preview_token": preview["preview_token"]})
    assert (
        service.learn_message(context, saved["source_id"], {"retry_failed": True})["status"]
        == "cancelled"
    )
    assert send(service, context, {**payload, "message_id": str(uuid4())})["status"] == "cancelled"
    assert service.extractor.calls == 1


def test_api_preserves_and_learns_with_private_denial_before_body(chat):
    service, _ = chat

    async def check():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            response = await client.post(
                "/conversation/messages", headers={"X-Jarvis-Mode": "normal"}, json=message()
            )
            assert response.status_code == 200
            source_id = response.json()["source_id"]
            learned = await client.post(
                f"/conversation/messages/{source_id}/learn",
                headers={"X-Jarvis-Mode": "normal"},
                json={},
            )
            assert learned.json()["decision"] == "extracted"
            for url in ("/conversation/messages", f"/conversation/messages/{source_id}/learn"):
                response = await client.post(
                    url, headers={"X-Jarvis-Mode": "private"}, content=b"invalid"
                )
                assert response.status_code == 403

    asyncio.run(check())


@pytest.mark.parametrize("text", [" ", "bad\0text", "\ud800"])
def test_invalid_chat_text_never_persists(chat, engine, text):
    service, context = chat
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.save_message(context, message(text))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_repair_receives_structural_feedback_and_memory_examples_omit_offsets(chat):
    service, context = chat
    send(service, context, message())
    original = service.extractor.complete
    bodies = []

    def complete(body):
        bodies.append(body)
        data = json.loads(body["messages"][1]["content"])
        assert "start" not in data["MEMORIES"][0]["passages"][0]
        result = original(body)
        if len(bodies) == 1:
            from dataclasses import replace

            proposal = json.loads(result.content)
            proposal["operations"][0]["content"]["condition"] = "for the prototype"
            return replace(result, content=json.dumps(proposal))
        return result

    service.extractor.complete = complete
    result = send(service, context, message("Atlas now uses SQLite."))
    assert result["decision"] == "extracted" and len(result["calls"]) == 2
    repair = bodies[1]["messages"][0]["content"]
    assert "Schema fields to recheck" in repair and "value_error" in repair


def test_learning_only_accepts_current_passages_selected_for_memory(chat):
    service, context = chat
    payload = message("Atlas uses PostgreSQL. What is its secret launch code?")

    def quote_question(data):
        source = data["CURRENT_SOURCE"]
        text = source["raw_text"]
        selected = data["MEMORY_CANDIDATES"]
        assert selected == ["Atlas uses PostgreSQL."]
        proposed = operation(source, content("launch_code", "invented"))
        excerpt = "What is its secret launch code?"
        proposed["passages"][0].update(start=text.index(excerpt), end=len(text), exact_text=excerpt)
        return {"decision": "extracted", "operations": [proposed]}

    service.extractor = FixtureExtractor(quote_question)
    result = send(service, context, payload)
    assert result["status"] == "failed" and result["error_code"] == "invalid_passage"
    assert len(result["calls"]) == 2  # One bounded repair; no invalid fact is committed.
    assert service.list_memories(context, {"namespace": "chat"})["memories"] == []


def test_selected_assertion_keeps_source_original_but_memory_quotes_only_eligible_text(chat):
    service, context = chat
    payload = message()
    result = send(service, context, payload)
    assert result["decision"] == "extracted"
    source = service.read_source(context, result["source_id"])
    assert source.raw_text == payload["request"]["question"]
    memory = service.list_memories(context, {"namespace": "chat"})["memories"][0]
    assert memory["passages"][0]["exact_text"] == "Atlas uses PostgreSQL."
