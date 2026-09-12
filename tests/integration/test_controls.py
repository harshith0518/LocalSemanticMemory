import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from answer_double import FixtureResponder
from memory_double import FixtureExtractor
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from jarvis.api import create_app
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.models import ControlReceipt, Job, Source
from jarvis.services import Service
from jarvis.worker import process_one


@pytest.fixture
def controlled(engine):
    service = Service(engine, extractor=FixtureExtractor(), responder=FixtureResponder())
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {"namespace": "controls", "expected_policy_revision": 0},
        Path("data/synthetic/sample-dictations.jsonl").read_bytes(),
    )
    service.request_processing(context, {"namespace": "controls", "expected_policy_revision": 0})
    for _ in range(8):
        assert process_one(service, context)["decision"] == "extracted"
    claim = next(
        m
        for m in service.list_memories(context, {"namespace": "controls"})["memories"]
        if m["content"]["predicate"] == "launch_date"
    )
    return service, context, claim


def command(claim, action="forget", revision=0):
    result = {
        "operation_id": str(uuid4()),
        "namespace": "controls",
        "target_revision_id": claim["id"],
        "expected_policy_revision": revision,
        "action": action,
    }
    if action != "forget":
        replacement = json.loads(json.dumps(claim["content"]))
        replacement["value"]["value"] = "2026-09-23"
        result.update(
            statement="The Atlas launch plan is 23 September 2026.", replacement=replacement
        )
    return result


def apply(service, context, payload):
    preview = service.preview_control(context, payload)
    payload = {**payload, "preview_token": preview["preview_token"]}
    return service.apply_control(context, payload), payload


@pytest.mark.parametrize(
    "action,lifecycle", [("correct", "corrected"), ("world_change", "superseded")]
)
def test_correction_and_world_change_preserve_originals_and_change_search(
    controlled, engine, action, lifecycle
):
    service, context, claim = controlled
    with Session(engine) as session:
        original = {s.id: s.raw_text for s in session.scalars(select(Source))}
    result, payload = apply(service, context, command(claim, action))
    assert result["policy_revision"] == 1
    history = service.memory_history(context, claim["claim_id"])
    assert history["revisions"][-2]["lifecycle"] == lifecycle
    assert history["revisions"][-1]["content"]["value"]["value"] == "2026-09-23"
    searched = service.search(context, {"namespace": "controls", "query": "legal review launch"})
    assert searched["controls"][-1]["action"] == action
    assert any(s["id"] == result["replacement_source_id"] for s in searched["sources"])
    assert service.apply_control(context, payload) == result
    with Session(engine) as session:
        assert original == {
            s.id: s.raw_text for s in session.scalars(select(Source).where(Source.id.in_(original)))
        }
        job = session.scalar(select(Job).where(Job.source_id == result["replacement_source_id"]))
        assert job.status == "cancelled" and job.error_code == "control_input"
        assert len(session.scalars(select(ControlReceipt)).all()) == 1


def test_forget_all_revision_support_and_reimports_cannot_resurrect(controlled, engine):
    service, context, claim = controlled
    rows = [
        json.loads(s)
        for s in Path("data/synthetic/sample-dictations.jsonl").read_text().splitlines()
    ]
    copy = {**rows[2], "record_id": "copy"}
    service.import_observations(
        context, {"namespace": "copies", "expected_policy_revision": 0}, json.dumps(copy)
    )
    preview = service.preview_control(context, command(claim))
    assert {s["source_key"] for s in preview["sources"]} >= {
        "import:controls:dict_0001",
        "import:controls:dict_0003",
        "import:copies:copy",
    }
    result, payload = apply(service, context, command(claim))
    assert result["excluded_sources"] >= 3
    searched = service.search(context, {"namespace": "copies", "query": "Atlas launch"})
    assert searched["status"] == "no_matches"
    # Same words, new namespace and new ID; changed formatted text still shares raw support.
    copy["record_id"], copy["formatted_text"] = "new-copy", "A changed export rendering."
    receipt = service.import_observations(
        context, {"namespace": "reimport", "expected_policy_revision": 1}, json.dumps(copy)
    )
    assert receipt.observations[0].job.status == "cancelled"
    assert (
        service.request_processing(
            context, {"namespace": "reimport", "expected_policy_revision": 1}
        )["requested"]
        == 0
    )
    assert (
        service.search(context, {"namespace": "reimport", "query": "Atlas"})["status"]
        == "no_matches"
    )
    assert (
        service.inspect_source(context, receipt.observations[0].source_id).observation.raw_text
        == copy["raw_transcript"]
    )
    # Source visibility and historical control receipts do not authorize renewed learning.
    with pytest.raises(ApplicationError, match="excluded_source"):
        service.commit_claim(
            context,
            {
                "expected_policy_revision": 1,
                "content": claim["content"],
                "passages": claim["passages"],
            },
        )
    assert service.apply_control(context, payload) == result


def test_literal_excluded_passage_is_blocked_inside_a_modified_export(controlled):
    service, context, claim = controlled
    apply(service, context, command(claim))
    row = {
        "record_id": "modified",
        "raw_transcript": "Extra material. "
        + claim["passages"][0]["exact_text"]
        + " More material.",
    }
    receipt = service.import_observations(
        context, {"namespace": "modified", "expected_policy_revision": 1}, json.dumps(row)
    )
    assert receipt.observations[0].job.status == "cancelled"


def test_forgetting_a_corrected_claim_also_blocks_its_original_support(controlled):
    service, context, claim = controlled
    result, _ = apply(service, context, command(claim, "correct"))
    current = next(
        c
        for c in service.list_memories(context, {"namespace": "controls"})["memories"]
        if c["id"] == result["replacement_revision_id"]
    )
    forgotten, _ = apply(service, context, command(current, revision=1))
    assert forgotten["excluded_sources"] >= 3
    assert all(
        s["source_key"] not in {"import:controls:dict_0001", "import:controls:dict_0003"}
        for s in service.search(context, {"namespace": "controls", "query": "launch"})["sources"]
    )


@pytest.mark.parametrize("fault", ["owner", "policy", "preview", "payload", "world_scope"])
def test_invalid_or_stale_controls_write_nothing(controlled, engine, fault):
    from test_private import snapshot

    service, context, claim = controlled
    payload = command(claim, "world_change")
    preview = service.preview_control(context, payload)
    payload["preview_token"] = preview["preview_token"]
    if fault == "owner":
        payload["target_revision_id"] = str(uuid4())
    elif fault == "policy":
        payload["expected_policy_revision"] = 99
    elif fault == "preview":
        payload["preview_token"] = "wrong"
    elif fault == "payload":
        payload["statement"] = "Unreviewed replacement"
    else:
        payload["replacement"]["scope"]["key"] = "different-project"
    before = snapshot(engine)
    with pytest.raises(ApplicationError):
        service.apply_control(context, payload)
    assert snapshot(engine) == before


def test_new_duplicate_between_preview_and_commit_requires_new_preview(controlled):
    service, context, claim = controlled
    payload = command(claim)
    payload["preview_token"] = service.preview_control(context, payload)["preview_token"]
    service.import_observations(
        context,
        {"namespace": "late-copy", "expected_policy_revision": 0},
        Path("data/synthetic/sample-dictations.jsonl").read_bytes(),
    )
    with pytest.raises(ApplicationError, match="stale_revision"):
        service.apply_control(context, payload)


def test_forget_fences_inflight_worker_and_delayed_answer(controlled, settings):
    service, context, claim = controlled
    # Queue a known duplicate, then pause an actual lease before the control commits.
    row = Path("data/synthetic/sample-dictations.jsonl").read_text().splitlines()[2]
    service.import_observations(
        context, {"namespace": "queued", "expected_policy_revision": 0}, row
    )
    service.request_processing(context, {"namespace": "queued", "expected_policy_revision": 0})
    packet = service.lease_next(context, namespace="queued")
    answer = service.prepare_answer(context, {"namespace": "controls", "question": "Atlas launch"})
    ready, done = Barrier(2, timeout=10), Barrier(2, timeout=10)
    independent = make_engine(settings)

    def control():
        other = Service(independent, extractor=FixtureExtractor())
        ready.wait()
        result, _ = apply(other, context, command(claim))
        done.wait()
        return result

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(control)
            ready.wait()
            done.wait()
            with pytest.raises(ApplicationError, match="stale_revision"):
                service.commit_extraction(context, packet, {"decision": "no_memory"})
            from jarvis.answers import AnswerProposal

            with pytest.raises(ApplicationError, match="stale_revision"):
                service.release_answer(
                    context, answer, AnswerProposal(status="unknown", text="Old answer")
                )
            assert future.result()["policy_revision"] == 1
    finally:
        independent.dispose()


def test_private_controls_refuse_unread_body(controlled):
    service, _, _ = controlled

    async def unread():
        raise AssertionError("Private control body read")
        yield b""

    async def check():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://jarvis.test"
            ) as client,
        ):
            for path in ("/controls/preview", "/controls/apply", "/feedback"):
                result = await client.post(
                    path, content=unread(), headers={"X-Jarvis-Mode": "private"}
                )
                assert result.status_code == 403 and result.headers["Cache-Control"] == "no-store"

    asyncio.run(check())


@pytest.mark.parametrize("operation", ["worker", "reply"])
def test_control_waits_for_worker_commit_or_reply_release(controlled, settings, operation):
    service, context, claim = controlled
    row = Path("data/synthetic/sample-dictations.jsonl").read_text().splitlines()[2]
    service.import_observations(
        context, {"namespace": "queued", "expected_policy_revision": 0}, row
    )
    service.request_processing(context, {"namespace": "queued", "expected_policy_revision": 0})
    worker_packet = service.lease_next(context, namespace="queued")
    answer_packet = service.prepare_answer(
        context, {"namespace": "controls", "question": "Atlas launch"}
    )
    payload = command(claim)
    payload["preview_token"] = service.preview_control(context, payload)["preview_token"]
    writer_engine, controller_engine = make_engine(settings), make_engine(settings)
    locked, release, attempted = (Barrier(2, timeout=10) for _ in range(3))
    first = True

    def after_lock(conn, cursor, statement, *args):
        nonlocal first
        if first and "jarvis.policies" in statement and "FOR UPDATE" in statement:
            first = False
            locked.wait()
            release.wait()

    control_first = True

    def control_listener(conn, cursor, statement, *args):
        nonlocal control_first
        if control_first and "jarvis.policies" in statement and "FOR UPDATE" in statement:
            control_first = False
            attempted.wait()

    event.listen(writer_engine, "after_cursor_execute", after_lock)
    event.listen(controller_engine, "before_cursor_execute", control_listener)

    def write():
        writer = Service(writer_engine, extractor=FixtureExtractor(), responder=FixtureResponder())
        if operation == "worker":
            return writer.commit_extraction(context, worker_packet, {"decision": "no_memory"})
        from jarvis.answers import AnswerProposal

        return writer.release_answer(
            context, answer_packet, AnswerProposal(status="unknown", text="Already released")
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            completed = pool.submit(write)
            locked.wait()
            controller = Service(controller_engine, extractor=FixtureExtractor())
            forgotten = pool.submit(controller.apply_control, context, payload)
            attempted.wait()
            assert not forgotten.done()
            release.wait()
            assert completed.result()
            assert forgotten.result()["policy_revision"] == 1
        assert (
            service.search(context, {"namespace": "queued", "query": "Atlas"})["status"]
            == "no_matches"
        )
    finally:
        event.remove(writer_engine, "after_cursor_execute", after_lock)
        event.remove(controller_engine, "before_cursor_execute", control_listener)
        writer_engine.dispose()
        controller_engine.dispose()


def test_correction_follows_exact_copy_and_rejects_known_wrong_relearning(controlled):
    service, context, claim = controlled
    result, _ = apply(service, context, command(claim, "correct"))
    row = json.loads(Path("data/synthetic/sample-dictations.jsonl").read_text().splitlines()[2])
    receipt = service.import_observations(
        context,
        {"namespace": "copy", "expected_policy_revision": 1},
        json.dumps({**row, "record_id": "renamed"}),
    )
    copied = service.inspect_source(context, receipt.observations[0].source_id).observation
    searched = service.search(context, {"namespace": "copy", "query": "launch"})
    assert searched["controls"][-1]["source_id"] == result["replacement_source_id"]
    answered = service.ask(context, {"namespace": "copy", "question": "launch"})
    assert "23 September 2026" in answered["text"]
    from memory_double import passage

    with pytest.raises(ApplicationError, match="invalid_transition"):
        service.validate_claim(
            context,
            {
                "expected_policy_revision": 1,
                "content": claim["content"],
                "passages": [passage(copied.model_dump(mode="json"))],
            },
        )


def test_only_exact_public_control_content_is_live_eligible(controlled):
    service, context, claim = controlled
    payload = command(claim, "correct")
    payload["statement"] = "The Atlas launch plan is 2026-09-23."
    result, _ = apply(service, context, payload)
    source = service.inspect_source(context, result["replacement_source_id"]).observation
    service._trial_source(source, live=True)
    tampered = source.model_copy(
        update={
            "capture_metadata": {
                "input_kind": "user_control",
                "confirmed_content": {"personal": "not permitted"},
            }
        }
    )
    with pytest.raises(ApplicationError, match="trial_input_denied"):
        service._trial_source(tampered, live=True)
