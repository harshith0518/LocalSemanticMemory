import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import IntegrityError
from test_private import no_store_access, snapshot
from typer.testing import CliRunner

import jarvis.cli as cli_module
from jarvis.api import create_app
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.imports import MAX_IMPORT_BYTES
from jarvis.models import Job, Policy
from jarvis.policy import LocalIdentity
from jarvis.services import Service, content_hash

OPTIONS = {"namespace": "diagnostic-v1", "expected_policy_revision": 0}


@pytest.fixture
def corpus():
    return Path("data/synthetic/sample-dictations.jsonl").read_bytes()


def jsonl(*records):
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records)


def http(service, method, path, payload=None, mode="normal", extra_headers=None):
    async def request():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            return await client.request(
                method,
                path,
                content=payload,
                headers={
                    "X-Jarvis-Mode": mode,
                    **(extra_headers or {}),
                },
            )

    return asyncio.run(request())


def test_diagnostic_import_preserves_pairs_metadata_and_all_labeled_spans(
    service, normal, corpus, engine, claim_content
):
    receipt = service.import_observations(normal, OPTIONS, corpus)
    assert (receipt.created, receipt.unchanged) == (8, 0)
    originals = {row["record_id"]: row for row in map(json.loads, corpus.splitlines())}
    saved = {}
    for item in receipt.observations:
        inspection = service.inspect_source(normal, item.source_id)
        source = inspection.observation
        original = originals[item.record_id]
        assert source.raw_text == original["raw_transcript"]
        assert source.formatted_text == original["formatted_text"]
        assert source.capture_metadata == original["metadata"]
        assert source.content_hash == content_hash(source.raw_text, source.formatted_text)
        assert source.kind == "imported_dictation"
        assert inspection.latest_revision == source.revision == 1
        assert inspection.job == item.job
        assert item.job.status == "pending" and item.job.attempts == 0
        saved[item.record_id] = source
    assert saved["dict_0007"].captured_at is None
    assert saved["dict_0007"].capture_metadata == {}
    assert "fifteen thousand rupees" in saved["dict_0008"].raw_text
    assert "₹50,000" in saved["dict_0008"].formatted_text
    labels = json.loads(Path("eval/fixtures/sample-evaluation-cases.json").read_text())
    assert labels["ingest_into_memory"] is False
    checked = 0
    for case in labels["cases"]:
        for evidence in case["required_evidence"]:
            source = saved[evidence["record_id"]]
            variant = "raw" if evidence["field"] == "raw_transcript" else "formatted"
            value = source.raw_text if variant == "raw" else source.formatted_text
            start = value.index(evidence["quote"])
            # Deterministic structural validation only; this is not a semantic grade.
            service.validate_claim(
                normal,
                {
                    "expected_policy_revision": 0,
                    "content": claim_content,
                    "passages": [
                        {
                            "source_id": source.id,
                            "source_revision": 1,
                            "variant": variant,
                            "start": start,
                            "end": start + len(evidence["quote"]),
                            "exact_text": evidence["quote"],
                        }
                    ],
                },
            )
            checked += 1
    assert checked == 11
    state = snapshot(engine)
    assert len(state["sources"]) == len(state["jobs"]) == 8
    assert state["passages"] == state["claim_revisions"] == []
    for case in labels["cases"]:
        assert case["request"] not in json.dumps(state)


def test_exact_reimport_preserves_every_saved_field_and_never_requeues(
    service, normal, corpus, engine
):
    first = service.import_observations(normal, OPTIONS, corpus)
    with engine.begin() as connection:
        connection.execute(update(Job).values(status="failed", attempts=1))
    before = snapshot(engine)
    # Record/key ordering and JSON encoding do not change identity or metadata meaning.
    reordered = "\ufeff" + "\r\n".join(
        json.dumps(row, sort_keys=True)
        for row in reversed(list(map(json.loads, corpus.splitlines())))
    )
    retry = service.import_observations(normal, OPTIONS, reordered)
    assert (retry.created, retry.unchanged) == (0, 8)
    assert {item.source_id for item in retry.observations} == {
        item.source_id for item in first.observations
    }
    assert all(
        item.job.status == "failed" and item.job.attempts == 1 for item in retry.observations
    )
    assert snapshot(engine) == before


@pytest.mark.parametrize(
    "changed",
    [
        {"raw_transcript": "Changed report"},
        {"formatted_text": None},
        {"metadata": {"app": "Different"}},
        {"metadata": None},
        {"metadata": {"captured_at": "2026-09-02T10:00:00+05:30", "app": "Slack"}},
    ],
)
def test_conflicting_reimport_rolls_back_whole_batch(service, normal, corpus, engine, changed):
    original = json.loads(corpus.splitlines()[0])
    service.import_observations(normal, OPTIONS, jsonl(original))
    before = snapshot(engine)
    new = {**original, "record_id": "new"}
    with pytest.raises(ApplicationError, match="import_conflict"):
        service.import_observations(normal, OPTIONS, jsonl(new, {**original, **changed}))
    assert snapshot(engine) == before


def test_metadata_boolean_and_number_are_not_equal_on_reimport(service, normal):
    original = {"record_id": "arbitrary-id", "raw_transcript": "Report", "metadata": {"flag": True}}
    service.import_observations(normal, OPTIONS, jsonl(original))
    with pytest.raises(ApplicationError, match="import_conflict"):
        service.import_observations(normal, OPTIONS, jsonl({**original, "metadata": {"flag": 1}}))


def test_jsonb_numbers_and_literal_unicode_escape_text_reimport(service, normal):
    record = {
        "record_id": "numeric",
        "raw_transcript": "Literal \\u0000 and separator \u2028 stay text",
        "metadata": {"large": 1e23, "small": 1e-12, "nested": [1.0, True, None]},
    }
    first = service.import_observations(normal, OPTIONS, jsonl(record))
    second = service.import_observations(normal, OPTIONS, jsonl(record))
    assert first.created == second.unchanged == 1
    assert first.observations[0].source_id == second.observations[0].source_id
    assert (
        service.inspect_source(normal, first.observations[0].source_id).observation.raw_text
        == record["raw_transcript"]
    )


def test_unfamiliar_unicode_and_missing_fields_remain_exact_and_distinct(service, normal):
    record = {
        "record_id": "item-1",
        "raw_transcript": "  🙂 Zéphyr / नील: don't run `send mail`; e\u0301\r\n",
        "metadata": None,
    }
    first = service.import_observations(normal, OPTIONS, jsonl(record)).observations[0]
    second = service.import_observations(
        normal, OPTIONS, jsonl({**record, "record_id": "item-2"})
    ).observations[0]
    third = service.import_observations(
        normal, {**OPTIONS, "namespace": "unfamiliar_02"}, jsonl(record)
    ).observations[0]
    assert len({first.source_id, second.source_id, third.source_id}) == 3
    inspected = service.inspect_source(normal, first.source_id).observation
    assert inspected.raw_text == record["raw_transcript"]
    assert inspected.formatted_text is inspected.captured_at is inspected.capture_metadata is None
    assert service.import_observations(normal, OPTIONS, jsonl(record)).unchanged == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"{bad json",
        b"[]",
        b"null",
        b'{"record_id":"a","record_id":"b","raw_transcript":"x"}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"app":1,"app":2}}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"x":NaN}}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"x":1e999}}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"x":"\\u0000"}}',
        b'{"record_id":"a","raw_transcript":"\\ud800"}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"captured_at":17234}}',
        b'{"record_id":"a","raw_transcript":"x","metadata":{"captured_at":"2026-09-01T10:00:00"}}',
        b'{"record_id":"a","raw_transcript":"x","role":"assistant"}',
        b'{"record_id":"a","raw_transcript":"x","owner_id":"someone-else"}',
        b'{"record_id":"a:b","raw_transcript":"x"}',
        b'{"record_id":"a","raw_transcript":"x"}\n' * 2,
        b"x" * (MAX_IMPORT_BYTES + 1),
        "\n".join(json.dumps({"record_id": str(i), "raw_transcript": "x"}) for i in range(1001)),
    ],
)
def test_invalid_imports_fail_before_database_access(service, normal, engine, monkeypatch, payload):
    before = snapshot(engine)
    with (
        no_store_access(engine, monkeypatch),
        pytest.raises(ApplicationError, match="invalid_input"),
    ):
        service.import_observations(normal, OPTIONS, payload)
    assert snapshot(engine) == before


def test_import_namespace_is_reserved_and_policy_must_be_current(
    service, normal, corpus, observation, engine
):
    with pytest.raises(ApplicationError, match="invalid_input"):
        service.save_observation(
            normal,
            {
                "observation": {**observation, "source_key": "import:diagnostic-v1:dict_0001"},
                "expected_policy_revision": 0,
            },
        )
    before = snapshot(engine)
    with pytest.raises(ApplicationError, match="stale_revision"):
        service.import_observations(normal, {**OPTIONS, "expected_policy_revision": 1}, corpus)
    assert snapshot(engine) == before
    service.import_observations(normal, OPTIONS, corpus)
    with engine.begin() as connection:
        connection.execute(update(Policy).values(revision=1))
    before = snapshot(engine)
    with pytest.raises(ApplicationError, match="stale_revision"):
        service.import_observations(normal, OPTIONS, corpus)
    assert service.list_sources(normal, {"namespace": OPTIONS["namespace"]}).policy_revision == 1
    assert snapshot(engine) == before


def test_late_job_failure_rolls_back_sources_and_new_policy(service, normal, corpus, engine):
    before = snapshot(engine)
    attempted = []

    def fail_job(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO jarvis.jobs"):
            attempted.append(True)
            raise IntegrityError("synthetic failure", {}, Exception("SYNTHETIC_PRIVATE_ERROR"))

    event.listen(engine, "before_cursor_execute", fail_job)
    try:
        with pytest.raises(ApplicationError, match="database_unavailable"):
            service.import_observations(normal, OPTIONS, corpus)
    finally:
        event.remove(engine, "before_cursor_execute", fail_job)
    assert attempted == [True]
    assert snapshot(engine) == before


def test_owner_isolation_and_namespace_pagination(service, normal, corpus, engine):
    foreign = Service(engine, LocalIdentity(uuid4()))
    foreign_context = foreign.identity.context("normal")
    foreign_receipt = foreign.import_observations(foreign_context, OPTIONS, corpus)
    with pytest.raises(ApplicationError, match="reference_unavailable"):
        service.inspect_source(normal, foreign_receipt.observations[0].source_id)
    assert service.list_sources(normal, {"namespace": OPTIONS["namespace"]}).observations == ()
    with pytest.raises(ApplicationError, match="reference_unavailable"):
        service.import_observations(foreign_context, OPTIONS, corpus)
    service.import_observations(normal, OPTIONS, corpus)
    seen, after = [], None
    while True:
        page = service.list_sources(
            normal, {"namespace": OPTIONS["namespace"], "limit": 3, "after": after}
        )
        seen.extend(item.id for item in page.observations)
        after = page.next_after
        if after is None:
            break
    assert len(set(seen)) == len(seen) == 8
    assert not set(seen) & {item.source_id for item in foreign_receipt.observations}
    for namespace in ("a_b", "axb"):
        service.import_observations(normal, {**OPTIONS, "namespace": namespace}, corpus)
    assert len(service.list_sources(normal, {"namespace": "a_b"}).observations) == 8


def test_simultaneous_imports_share_receipts_with_separate_postgres_connections(
    settings, engine, corpus
):
    start = Barrier(2, timeout=10)

    def write():
        independent = make_engine(settings)
        try:
            with independent.connect() as connection:
                pid = connection.scalar(text("SELECT pg_backend_pid()"))
                start.wait()
            service = Service(independent)
            return pid, service.import_observations(
                service.identity.context("normal"), OPTIONS, corpus
            )
        finally:
            independent.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: write(), range(2)))
    assert first[0] != second[0]
    assert sorted([first[1].created, second[1].created]) == [0, 8]
    assert [item.source_id for item in first[1].observations] == [
        item.source_id for item in second[1].observations
    ]
    assert [item.job.id for item in first[1].observations] == [
        item.job.id for item in second[1].observations
    ]
    state = snapshot(engine)
    assert len(state["sources"]) == len(state["jobs"]) == 8


def test_api_cli_import_list_inspect_parity_and_safe_failures(service, normal, corpus, engine):
    imported = http(
        service,
        "POST",
        "/sources/import?namespace=diagnostic-v1&expected_policy_revision=0",
        corpus,
        extra_headers={"X-Owner-ID": str(uuid4())},
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 8
    cli = CliRunner().invoke(
        cli_module.app,
        [
            "sources",
            "import",
            "--namespace",
            "diagnostic-v1",
            "--expected-policy-revision",
            "0",
            "--mode",
            "normal",
        ],
        input=corpus,
    )
    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.output)["unchanged"] == 8
    assert json.loads(cli.output) == service.import_observations(
        normal, OPTIONS, corpus
    ).model_dump(mode="json")
    for path, args in [
        ("/sources?namespace=diagnostic-v1", ["list", "--namespace", "diagnostic-v1"]),
        (
            "/sources/" + imported.json()["observations"][0]["source_id"],
            ["inspect", imported.json()["observations"][0]["source_id"]],
        ),
    ]:
        api = http(service, "GET", path)
        cli = CliRunner().invoke(cli_module.app, ["sources", *args, "--mode", "normal"])
        assert api.status_code == 200 and cli.exit_code == 0
        assert api.json() == json.loads(cli.output)
        assert api.headers["Cache-Control"] == "no-store"
        assert api.headers["Content-Type"] == "application/json; charset=utf-8"
    before = snapshot(engine)
    changed = deepcopy(json.loads(corpus.splitlines()[0]))
    changed["raw_transcript"] = "SYNTHETIC_DO_NOT_ECHO"
    conflict = http(
        service,
        "POST",
        "/sources/import?namespace=diagnostic-v1&expected_policy_revision=0",
        jsonl(changed),
    )
    assert conflict.status_code == 409 and conflict.json()["reason"] == "import_conflict"
    assert "SYNTHETIC_DO_NOT_ECHO" not in conflict.text
    assert http(service, "GET", "/sources?namespace=diagnostic-v1", mode="").status_code == 422
    assert http(service, "GET", "/sources/not-an-id").status_code == 422
    assert snapshot(engine) == before


def test_private_import_and_inspection_do_not_read_input_or_saved_state(
    service, normal, corpus, engine, monkeypatch, caplog, capsys
):
    service.import_observations(normal, OPTIONS, corpus)
    before = snapshot(engine)
    reads = []
    sentinel = "SYNTHETIC_PRIVATE_IMPORT_CONTENT"

    async def unread_body():
        reads.append("http_body")
        raise RuntimeError(sentinel)
        yield b""  # Make this an async byte stream; it must never be consumed.

    class UnreadStdin:
        def read(self, *args):
            reads.append("stdin")
            raise RuntimeError(sentinel)

    with caplog.at_level(logging.WARNING), no_store_access(engine, monkeypatch):
        response = http(
            service,
            "POST",
            "/sources/import?namespace=diagnostic-v1&expected_policy_revision=0",
            unread_body(),
            mode="private",
        )
        assert response.status_code == 403
        for path in ("/sources?namespace=diagnostic-v1", "/sources/" + sentinel):
            response = http(service, "GET", path, mode="private")
            assert response.status_code == 403
            assert response.json()["reason"] == "private_operation_denied"
            assert sentinel not in response.text
        for args in (
            ["import", "--namespace", "diagnostic-v1", "--expected-policy-revision", "0"],
            ["list", "--namespace", "diagnostic-v1"],
            ["inspect", sentinel],
        ):
            cli = CliRunner().invoke(
                cli_module.app, ["sources", *args, "--mode", "private"], input=sentinel
            )
            assert cli.exit_code == 1
            assert json.loads(cli.output)["reason"] == "private_operation_denied"
            assert sentinel not in cli.output
        with monkeypatch.context() as patch:
            patch.setattr(cli_module.sys, "stdin", UnreadStdin())
            with pytest.raises(cli_module.typer.Exit):
                cli_module.import_sources(
                    namespace="diagnostic-v1", expected_policy_revision=0, mode="private"
                )
        assert json.loads(capsys.readouterr().out)["reason"] == "private_operation_denied"
    assert reads == [] and caplog.records == []
    assert snapshot(engine) == before


def test_import_guard_holds_until_source_and_job_commit(settings, engine, corpus):
    writer_locked, release_writer, control_attempt = (Barrier(2, timeout=10) for _ in range(3))
    writer_engine, control_engine = make_engine(settings), make_engine(settings)
    service = Service(writer_engine)
    context = service.identity.context("normal")
    # Existing policy row lets the independent controller request the same commit guard.
    with engine.begin() as connection:
        connection.execute(Policy.__table__.insert().values(owner_id=context.owner_id))

    def after_lock(connection, cursor, statement, parameters, execution, many):
        if "jarvis.policies" in statement and "FOR UPDATE" in statement:
            writer_locked.wait()
            release_writer.wait()

    def before_control(connection, cursor, statement, parameters, execution, many):
        if "jarvis.policies" in statement and "FOR UPDATE" in statement:
            control_attempt.wait()

    def control():
        with control_engine.begin() as connection:
            connection.execute(
                select(Policy).where(Policy.owner_id == context.owner_id).with_for_update()
            )
            jobs = connection.execute(select(Job)).mappings().all()
            assert len(jobs) == 8 and all(job["expected_policy_revision"] == 0 for job in jobs)
            connection.execute(
                update(Policy).where(Policy.owner_id == context.owner_id).values(revision=1)
            )

    event.listen(writer_engine, "after_cursor_execute", after_lock)
    event.listen(control_engine, "before_cursor_execute", before_control)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(service.import_observations, context, OPTIONS, corpus)
            writer_locked.wait()
            controller = pool.submit(control)
            control_attempt.wait()
            assert not controller.done()
            release_writer.wait()
            assert writer.result(timeout=10).created == 8
            controller.result(timeout=10)
    finally:
        event.remove(writer_engine, "after_cursor_execute", after_lock)
        event.remove(control_engine, "before_cursor_execute", before_control)
        writer_engine.dispose()
        control_engine.dispose()
    with pytest.raises(ApplicationError, match="stale_revision"):
        Service(engine).import_observations(context, OPTIONS, corpus)
