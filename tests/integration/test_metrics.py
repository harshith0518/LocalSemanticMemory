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
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_private import no_store_access, snapshot
from typer.testing import CliRunner

import jarvis.cli as cli_module
from jarvis.answers import trial_questions
from jarvis.api import create_app
from jarvis.errors import ApplicationError
from jarvis.metrics import capture_timings, stage
from jarvis.models import ModelCall
from jarvis.policy import LocalIdentity
from jarvis.services import Service
from jarvis.worker import process_one


def http_get(service, path, mode="normal"):
    async def run():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            return await client.get(path, headers={"X-Jarvis-Mode": mode})

    return asyncio.run(run())


def test_snapshot_counts_exact_utf8_and_is_read_only_and_owner_scoped(service, normal, engine):
    body = json.dumps(
        {"record_id": "unicode", "raw_transcript": "café ₹七", "formatted_text": "Café ₹七."}
    )
    service.import_observations(
        normal, {"namespace": "metrics", "expected_policy_revision": 0}, body
    )
    other = Service(engine, LocalIdentity(uuid4()))
    other.write_probe()
    before = snapshot(engine)
    with capture_timings() as timings:
        result = service.usage_snapshot(normal)
    assert result["storage"]["source_revisions"] == 1
    assert result["storage"]["source_text_utf8_bytes"] == len("café ₹七Café ₹七.".encode())
    assert result["storage"]["claim_revisions"] == 0
    assert result["models"] == []
    assert result["cost"]["billed_usd"] is None and not result["semantic_quality"]["measured"]
    assert timings["usage_snapshot"]["calls"] == 1
    assert snapshot(engine) == before
    assert (
        other.usage_snapshot(other.identity.context("normal"))["storage"]["source_revisions"] == 1
    )


def test_shared_api_cli_snapshot_and_no_store_headers(service, normal, engine, monkeypatch):
    service.write_probe(normal)
    before = snapshot(engine)
    expected = service.usage_snapshot(normal)
    response = http_get(service, "/usage")
    assert response.status_code == 200 and response.json() == expected
    assert "usage_snapshot;dur=" in response.headers["Server-Timing"]
    assert response.headers["Cache-Control"] == "no-store"
    monkeypatch.setattr(cli_module, "make_engine", lambda settings: engine)
    cli = CliRunner().invoke(cli_module.app, ["usage", "--mode", "normal"])
    assert cli.exit_code == 0 and json.loads(cli.stdout) == expected
    assert snapshot(engine) == before


def test_private_metrics_and_sample_refuse_all_io(service, private, engine, monkeypatch, caplog):
    before = snapshot(engine)
    with no_store_access(engine, monkeypatch), capture_timings() as timings:
        with pytest.raises(ApplicationError):
            service.usage_snapshot(private)
        assert timings == {}
        for path in ("/usage", "/trial/sources"):
            response = http_get(service, path, "private")
            assert response.status_code == 403
            assert "server-timing" not in response.headers
        cli = CliRunner().invoke(cli_module.app, ["usage", "--mode", "private"])
        assert cli.exit_code != 0
    assert not caplog.records
    assert snapshot(engine) == before


def test_public_sample_matches_originals_and_never_imports_itself(service, engine):
    before = snapshot(engine)
    response = http_get(service, "/trial/sources")
    assert response.status_code == 200
    assert response.json()["jsonl"] == Path("data/synthetic/sample-dictations.jsonl").read_text()
    assert len(response.json()["jsonl"].splitlines()) == 8
    assert snapshot(engine) == before


def test_failed_call_latency_keeps_unknown_usage_and_idempotent_reservation(engine):
    service = Service(engine, extractor=FixtureExtractor(), responder=FixtureResponder())
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {"namespace": "usage", "expected_policy_revision": 0},
        Path("data/synthetic/sample-dictations.jsonl").read_bytes(),
    )
    service.request_processing(context, {"namespace": "usage", "expected_policy_revision": 0})
    with capture_timings() as stages:
        assert process_one(service, context)["decision"] == "extracted"
    assert {"lease", "model", "proposal_validation", "memory_commit", "accounting"} <= stages.keys()
    payload = {"namespace": "usage", "question": trial_questions()[0]}
    service.ask(context, payload)

    def broken(body):
        raise TimeoutError("raw provider error must not be retained")

    service.responder.complete = broken
    with capture_timings() as stages, pytest.raises(ApplicationError):
        service.ask(context, payload)
    assert stages["model"]["calls"] == 1
    result = service.usage_snapshot(context)
    answer = next(m for m in result["models"] if m["role"] == "answer")
    assert answer["attempts"] == 2 and answer["failed"] == 1
    assert answer["known_input_tokens"] == 100 and answer["known_output_tokens"] == 50
    assert answer["unknown_usage_calls"] == 1 and answer["timed_calls"] == 2
    with Session(engine) as session:
        failed = session.scalar(select(ModelCall).where(ModelCall.status == "failed"))
        assert failed.elapsed_ms is not None and failed.input_tokens is None
        assert failed.error_code == "provider_failed"
        assert answer["unsettled_reserved_tokens"] == failed.reserved_tokens
        call_id = failed.id
    service.finish_call(context, call_id, error="provider_failed", elapsed_ms=999999)
    assert service.usage_snapshot(context) == result


def test_concurrent_and_nested_timing_scopes_do_not_mix():
    barrier = Barrier(2)

    def run(name):
        with capture_timings() as stages:
            with stage(name):
                barrier.wait(timeout=5)
                with capture_timings(enabled=False):
                    with stage("disabled"):
                        pass
            return stages

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(run, "first"), pool.submit(run, "second")
        assert set(first.result()) == {"first"}
        assert set(second.result()) == {"second"}


def test_api_failed_search_has_fixed_timings_without_query_content(service):
    async def run():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            return await client.post(
                "/search", content=b"SYNTHETIC_INVALID_SECRET", headers={"X-Jarvis-Mode": "normal"}
            )

    response = asyncio.run(run())
    assert response.status_code == 422 and "search;dur=" in response.headers["Server-Timing"]
    assert "SYNTHETIC_INVALID_SECRET" not in str(response.headers) + response.text
