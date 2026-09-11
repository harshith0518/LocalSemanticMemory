import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from memory_double import FixtureExtractor, content, fixture_proposal, operation
from sqlalchemy import event, func, select, text, update
from sqlalchemy.orm import Session

from jarvis.api import create_app
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.extraction import parse_proposal
from jarvis.models import ClaimRecord, Job, ModelBudget, ModelCall, Policy, ProcessingReceipt
from jarvis.providers import Completion, NvidiaExtractor
from jarvis.services import Service
from jarvis.worker import process_one

FIXTURE = Path("data/synthetic/sample-dictations.jsonl")


@pytest.fixture
def memory_service(engine):
    return Service(engine, extractor=FixtureExtractor())


def queue(service, rows=None, namespace="memory"):
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {"namespace": namespace, "expected_policy_revision": 0},
        rows or FIXTURE.read_bytes(),
    )
    service.request_processing(context, {"namespace": namespace, "expected_policy_revision": 0})
    return context


def test_complete_fixture_path_is_atomic_inspectable_and_idempotent(memory_service, engine):
    context = queue(memory_service)
    outcomes = [process_one(memory_service, context) for _ in range(8)]
    assert all(o.get("decision") == "extracted" for o in outcomes), outcomes
    assert process_one(memory_service, context) is None
    page = memory_service.list_memories(context, {"namespace": "memory"})
    memories = page["memories"]
    launch = next(c for c in memories if c["content"]["predicate"] == "launch_date")
    assert launch["content"]["value"]["value"] == "2026-09-21"
    history = memory_service.memory_history(context, launch["claim_id"])
    assert [c["content"]["value"]["value"] for c in history["revisions"]] == [
        "2026-09-18",
        "2026-09-21",
    ]
    assert history["relations"][0]["kind"] == "supersedes"
    owner = next(c for c in memories if c["content"]["predicate"] == "budget_owner")
    assert owner["content"]["evidence_status"] == "tentative"
    assert owner["content"]["condition"] and owner["content"]["time"]["event"] is None
    amounts = [c for c in memories if c["content"]["predicate"] == "spending_limit"]
    assert len(amounts) == 2 and all(c["content"]["evidence_status"] == "disputed" for c in amounts)
    assert len({p["source_id"] for c in amounts for p in c["passages"]}) == 1
    before = memory_service.processing_status(context, {"namespace": "memory"})
    queue(memory_service)
    assert memory_service.processing_status(context, {"namespace": "memory"}) == before
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProcessingReceipt)) == 8
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 8


@pytest.mark.parametrize("decision", ["no_memory", "duplicate", "needs_clarification"])
def test_zero_claim_receipts_are_not_failures(memory_service, engine, decision):
    memory_service.extractor = FixtureExtractor(lambda _: {"decision": decision, "operations": []})
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    assert process_one(memory_service, context)["decision"] == decision
    assert memory_service.list_memories(context, {"namespace": "memory"})["memories"] == []
    assert memory_service.processing_status(context, {"namespace": "memory"})["counts"] == {
        "succeeded": 1
    }


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("span", ErrorCode.INVALID_PASSAGE),
        ("owner", ErrorCode.REFERENCE_UNAVAILABLE),
        ("version", ErrorCode.STALE_REVISION),
        ("variant", ErrorCode.INVALID_PASSAGE),
        ("duplicate", ErrorCode.INVALID_TRANSITION),
    ],
)
def test_invalid_proposal_rolls_back_all_operations(memory_service, engine, mutation, reason):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    packet = memory_service.lease_next(context)
    good = fixture_proposal(
        {"CURRENT_SOURCE": packet.source.model_dump(mode="json"), "MEMORIES": []}
    )
    bad = deepcopy(good["operations"][0])
    bad["content"]["predicate"] = "second_fact"
    if mutation == "span":
        bad["passages"][0]["exact_text"] = "fabricated"
    elif mutation == "owner":
        bad["passages"][0]["source_id"] = str(uuid4())
    elif mutation == "version":
        bad["passages"][0]["source_revision"] = 2
    elif mutation == "variant":
        bad["passages"][0]["variant"] = "formatted"
    else:
        bad = deepcopy(good["operations"][0])
    if mutation == "owner":
        bad["passages"].append(deepcopy(good["operations"][0]["passages"][0]))
    good["operations"].append(bad)
    with pytest.raises(ApplicationError, match=reason.value):
        memory_service.commit_extraction(context, packet, good)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 0
        assert session.scalar(select(func.count()).select_from(ProcessingReceipt)) == 0


def test_receipt_replay_and_expired_worker_fencing(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    old = memory_service.lease_next(context)
    assert memory_service.lease_next(context) is None
    with engine.begin() as connection:
        connection.execute(update(Job).values(lease_until=func.now() - text("interval '1 second'")))
    current = memory_service.lease_next(context)
    proposal = fixture_proposal(
        {"CURRENT_SOURCE": current.source.model_dump(mode="json"), "MEMORIES": []}
    )
    with pytest.raises(ApplicationError, match="stale_revision"):
        memory_service.commit_extraction(context, old, proposal)
    first = memory_service.commit_extraction(context, current, proposal)
    assert memory_service.commit_extraction(context, current, proposal) == first
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 1


def test_policy_change_while_model_runs_rejects_result_without_holding_lock(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    started, release = Barrier(2, timeout=10), Barrier(2, timeout=10)

    def proposal(data):
        started.wait()
        release.wait()
        return fixture_proposal(data)

    memory_service.extractor = FixtureExtractor(proposal)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(process_one, memory_service, context)
        started.wait()
        with engine.begin() as control:
            control.execute(text("SET LOCAL lock_timeout = '2s'"))
            control.execute(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            control.execute(update(Policy).values(revision=1))
        release.wait()
        assert worker.result(timeout=10)["reason"] == "stale_revision"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 0


def test_two_connections_cannot_lease_same_job(memory_service, settings):
    context = queue(memory_service)
    barrier = Barrier(2, timeout=10)

    def lease():
        engine = make_engine(settings)
        try:
            independent = Service(engine, extractor=FixtureExtractor())
            barrier.wait()
            return independent.lease_next(context)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda _: lease(), range(2)))
    assert sum(lease is not None for lease in leases) == 1


def test_failed_unknown_call_keeps_reservation_and_retry_is_bounded(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])

    def fail(_):
        raise RuntimeError("SYNTHETIC_PROVIDER_SECRET")

    memory_service.extractor.complete = fail
    for _ in range(3):
        assert process_one(memory_service, context)["reason"] == "provider_failed"
        memory_service.request_processing(
            context,
            {
                "namespace": "memory",
                "expected_policy_revision": 0,
                "retry_failed": True,
            },
        )
    assert process_one(memory_service, context) is None
    with Session(engine) as session:
        budget = session.get(ModelBudget, "s07-contract-tests")
        assert budget.requests == 3
        assert budget.tokens == session.scalar(select(func.sum(ModelCall.reserved_tokens)))


def test_live_gate_checks_actual_content_before_queue(memory_service, engine):
    context = memory_service.identity.context("normal")
    modified = json.loads(FIXTURE.read_text().splitlines()[0])
    modified["raw_transcript"] += " non-fixture text"
    memory_service.import_observations(
        context, {"namespace": "synthetic", "expected_policy_revision": 0}, json.dumps(modified)
    )
    memory_service.extractor = NvidiaExtractor(approved=True, key="synthetic-test-key")
    with pytest.raises(ApplicationError, match="trial_input_denied"):
        memory_service.request_processing(
            context, {"namespace": "synthetic", "expected_policy_revision": 0}
        )
    with Session(engine) as session:
        assert session.scalar(select(Job.requested)) is False


def test_api_uses_shared_memory_operations(memory_service):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    process_one(memory_service, context)

    async def request():
        app = create_app(memory_service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            page = await client.get("/memories?namespace=memory", headers={"X-Jarvis-Mode": "normal"})
            assert page.json() == memory_service.list_memories(context, {"namespace": "memory"})
            for path in ("/memories?namespace=memory", "/processing?namespace=memory"):
                response = await client.get(path, headers={"X-Jarvis-Mode": "private"})
                assert response.status_code == 403

    asyncio.run(request())


@pytest.mark.parametrize("action", ["support", "supersede", "correct", "conflict"])
def test_reconciliation_preserves_evidence_and_history(memory_service, engine, action):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    process_one(memory_service, context)
    old = memory_service.list_memories(context, {"namespace": "memory"})["memories"][0]
    extra = json.loads(FIXTURE.read_text().splitlines()[0])
    extra["record_id"] = "later"
    extra["raw_transcript"] = "Synthetic later statement: launch on 21 September 2026."
    extra["formatted_text"] = None
    queue(memory_service, json.dumps(extra))
    packet = memory_service.lease_next(context)
    claim = deepcopy(old["content"])
    claim["value"] = {"kind": "date", "value": "2026-09-21"}
    if action == "conflict":
        claim["evidence_status"] = "disputed"
    proposal = {
        "decision": "extracted",
        "operations": [
            operation(
                packet.source.model_dump(mode="json"),
                None if action == "support" else claim,
                action=action,
                target=old["id"],
            )
        ],
    }
    memory_service.commit_extraction(context, packet, proposal)
    history = memory_service.memory_history(context, old["claim_id"])
    assert len(history["revisions"]) == 2
    assert history["revisions"][0]["content"] == old["content"]
    assert history["revisions"][0]["lifecycle"] == (
        "corrected" if action == "correct" else "superseded"
    )
    if action == "support":
        assert len(history["revisions"][1]["passages"]) == 2
        assert history["revisions"][1]["content"] == old["content"]
    if action == "conflict":
        current = memory_service.list_memories(context, {"namespace": "memory"})["memories"]
        assert len(current) == 2
        assert all(c["content"]["evidence_status"] == "disputed" for c in current)


def test_failure_after_first_insert_rolls_back_claims_receipt_and_job(
    memory_service, engine, monkeypatch
):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    packet = memory_service.lease_next(context)
    source = packet.source.model_dump(mode="json")
    proposal = {
        "decision": "extracted",
        "operations": [
            operation(source, content("one", "value")),
            operation(source, content("two", "value")),
        ],
    }
    original = memory_service._insert_claim
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ApplicationError(ErrorCode.OPERATION_FAILED)
        return original(*args)

    monkeypatch.setattr(memory_service, "_insert_claim", fail_second)
    with pytest.raises(ApplicationError, match="operation_failed"):
        memory_service.commit_extraction(context, packet, proposal)
    with Session(engine) as session:
        for model in (ClaimRecord, ProcessingReceipt):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(Job.status)) == "running"
        assert session.scalar(text("SELECT count(*) FROM jarvis.passages")) == 0


def test_new_claim_while_model_runs_invalidates_memory_snapshot(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    packet = memory_service.lease_next(context)
    proposal = fixture_proposal(
        {"CURRENT_SOURCE": packet.source.model_dump(mode="json"), "MEMORIES": []}
    )
    memory_service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": proposal["operations"][0]["content"],
            "passages": proposal["operations"][0]["passages"],
        },
    )
    with pytest.raises(ApplicationError, match="stale_revision"):
        memory_service.commit_extraction(context, packet, proposal)


def test_budget_race_reserves_last_call_only_once(memory_service, settings, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    packet = memory_service.lease_next(context)
    with Session(engine) as session, session.begin():
        session.add(ModelBudget(key="s07-contract-tests", requests=31, tokens=0))
    barrier = Barrier(2, timeout=10)

    def reserve():
        independent = make_engine(settings)
        try:
            service = Service(independent, extractor=FixtureExtractor())
            barrier.wait()
            try:
                return service.reserve_call(context, packet, 1000)
            except ApplicationError as error:
                return error.code
        finally:
            independent.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert results.count(ErrorCode.BUDGET_EXHAUSTED) == 1
    with Session(engine) as session:
        budget = session.get(ModelBudget, "s07-contract-tests")
        assert (budget.requests, budget.tokens) == (32, 1000)


def test_worker_commit_holds_policy_guard_until_receipt_commit(memory_service, settings, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    packet = memory_service.lease_next(context)
    proposal = fixture_proposal(
        {"CURRENT_SOURCE": packet.source.model_dump(mode="json"), "MEMORIES": []}
    )
    locked, release, control_attempt = (Barrier(2, timeout=10) for _ in range(3))
    writer_engine, control_engine = make_engine(settings), make_engine(settings)
    first = True

    def after_lock(*args):
        nonlocal first
        if first and "jarvis.policies" in args[2] and "FOR UPDATE" in args[2]:
            first = False
            locked.wait()
            release.wait()

    def before_control(*args):
        if "jarvis.policies" in args[2] and "FOR UPDATE" in args[2]:
            control_attempt.wait()

    def control():
        with control_engine.begin() as connection:
            connection.execute(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            assert connection.scalar(select(Job.status)) == "succeeded"
            assert connection.scalar(select(func.count()).select_from(ProcessingReceipt)) == 1
            connection.execute(update(Policy).values(revision=1))

    event.listen(writer_engine, "after_cursor_execute", after_lock)
    event.listen(control_engine, "before_cursor_execute", before_control)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(
                Service(writer_engine, extractor=FixtureExtractor()).commit_extraction,
                context,
                packet,
                proposal,
            )
            locked.wait()
            controller = pool.submit(control)
            control_attempt.wait()
            assert not controller.done()
            release.wait()
            assert writer.result(timeout=10)["revision_ids"]
            controller.result(timeout=10)
    finally:
        writer_engine.dispose()
        control_engine.dispose()


def test_one_schema_repair_is_accounted_and_then_stops(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    memory_service.extractor = FixtureExtractor(lambda _: {"invented": "not a proposal"})
    assert process_one(memory_service, context)["reason"] == "invalid_input"
    assert memory_service.extractor.calls == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 2
        assert session.scalar(select(Job.status)) == "failed"


def test_provider_packet_excludes_collection_owner_and_activity_metadata(memory_service):
    context = queue(memory_service)
    packet = memory_service.lease_next(context)
    body, _ = memory_service.extractor.prepare(packet)
    data = json.loads(body["messages"][1]["content"])
    assert "source_key" not in data["CURRENT_SOURCE"]
    assert "owner_id" not in data["CURRENT_SOURCE"]
    assert "imported_at" not in data["CURRENT_SOURCE"]


@pytest.mark.parametrize(
    "payload",
    [
        '{"decision":"no_memory","decision":"duplicate"}',
        '{"decision":"no_memory","operations":NaN}',
    ],
)
def test_ambiguous_or_nonfinite_model_json_is_rejected(payload):
    with pytest.raises(ApplicationError, match="invalid_input"):
        parse_proposal(payload)


def test_bad_usage_closes_budget_without_committing_claims(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    memory_service.extractor.complete = lambda _: Completion(
        '{"decision":"no_memory"}',
        "deterministic-test-double",
        500000,
        500000,
        1,
    )
    assert process_one(memory_service, context)["reason"] == "budget_exhausted"
    with Session(engine) as session:
        budget = session.get(ModelBudget, "s07-contract-tests")
        assert budget.requests == 32 and budget.tokens == 1000000
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 0


def test_token_ceiling_rejects_call_before_transport(memory_service, engine):
    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    with Session(engine) as session, session.begin():
        session.add(ModelBudget(key="s07-contract-tests", requests=0, tokens=499999))
    assert process_one(memory_service, context)["reason"] == "budget_exhausted"
    assert memory_service.extractor.calls == 0
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 0


def test_disabled_processing_does_not_read_store(service, normal, engine, monkeypatch):
    from test_private import no_store_access

    with no_store_access(engine, monkeypatch):
        with pytest.raises(ApplicationError, match="provider_disabled"):
            service.request_processing(normal, "not json")
        with pytest.raises(ApplicationError, match="provider_disabled"):
            process_one(service, normal)


def test_private_processing_http_denies_before_reading_body(
    memory_service, engine, monkeypatch, caplog
):
    from test_private import no_store_access, snapshot

    before = snapshot(engine)

    async def request():
        async def forbidden_body():
            raise AssertionError("Private request body was consumed")
            yield b""  # pragma: no cover

        app = create_app(memory_service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            response = await client.post(
                "/processing", content=forbidden_body(), headers={"X-Jarvis-Mode": "private"}
            )
            assert response.status_code == 403
            assert response.json()["reason"] == "private_operation_denied"

    with no_store_access(engine, monkeypatch):
        asyncio.run(request())
    assert snapshot(engine) == before and not caplog.records


def test_optional_cli_has_shared_queue_and_memory_results(memory_service, monkeypatch):
    from typer.testing import CliRunner

    import jarvis.cli as cli_module

    context = queue(memory_service, FIXTURE.read_text().splitlines()[0])
    monkeypatch.setattr(cli_module, "Service", lambda engine: memory_service)
    command = CliRunner().invoke(
        cli_module.app,
        ["process", "--namespace", "memory", "--expected-policy-revision", "0", "--mode", "normal"],
    )
    assert command.exit_code == 0
    assert json.loads(command.output) == {"status": "queued", "requested": 0}
    process_one(memory_service, context)
    command = CliRunner().invoke(
        cli_module.app, ["memories", "--namespace", "memory", "--mode", "normal"]
    )
    assert command.exit_code == 0
    assert json.loads(command.output) == memory_service.list_memories(
        context, {"namespace": "memory"}
    )


def test_evaluator_processing_does_not_consume_another_collections_jobs(memory_service):
    row = FIXTURE.read_text().splitlines()[0]
    context = queue(memory_service, row, namespace="aaa-other")
    queue(memory_service, row, namespace="zzz-evaluation")
    assert process_one(memory_service, context, namespace="zzz-evaluation")["revision_ids"]
    assert memory_service.processing_status(context, {"namespace": "aaa-other"})["counts"] == {
        "pending": 1
    }


def test_nvidia_adapter_with_mock_transport_accepts_exact_fixtures(memory_service):
    """Exercises the real allowlist and transport contract without a network/model call."""

    def send(request):
        body = json.loads(request.content)
        data = json.loads(body["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "model": NvidiaExtractor.model,
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(fixture_proposal(data)),
                        },
                    }
                ],
            },
        )

    memory_service.extractor = NvidiaExtractor(
        approved=True,
        key="synthetic-test-key",
        transport=httpx.MockTransport(send),
    )
    context = queue(memory_service)
    assert all(process_one(memory_service, context)["revision_ids"] for _ in range(8))
    assert memory_service.processing_status(context, {"namespace": "memory"})["counts"] == {
        "succeeded": 8
    }
