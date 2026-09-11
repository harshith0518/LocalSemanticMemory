import asyncio
import builtins
import io
import json
import logging
import os
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select
from typer.testing import CliRunner

import jarvis.cli as cli_module
from jarvis.api import create_app
from jarvis.contracts import ObservationInput
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.models import Base

SENTINEL = "PRIVATE_SYNTHETIC_INPUT_do_not_persist_27e16b"


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table.name: sorted(
                json.dumps(dict(row), default=str, sort_keys=True)
                for row in connection.execute(select(table)).mappings()
            )
            for table in Base.metadata.sorted_tables
        }


@contextmanager
def no_store_access(engine, monkeypatch):
    attempts = []

    def reject(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Private operation attempted database access")

    original_open, original_os_open = builtins.open, os.open

    def checked_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            attempts.append("file_write")
            raise AssertionError("Private operation attempted a file write")
        return original_open(file, mode, *args, **kwargs)

    def checked_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            attempts.append("file_write")
            raise AssertionError("Private operation attempted a file write")
        return original_os_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(engine, "connect", reject)
        # CLI gets its own service object; route it through the same instrumented engine.
        patch.setattr(cli_module, "make_engine", lambda settings: engine)
        patch.setattr(builtins, "open", checked_open)
        patch.setattr(io, "open", checked_open)
        patch.setattr(os, "open", checked_os_open)
        event.listen(engine, "before_cursor_execute", reject)
        try:
            yield
        finally:
            event.remove(engine, "before_cursor_execute", reject)
    assert attempts == []


def http_request(service, path, payload, mode="private", extra_headers=None):
    async def request():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            return await client.post(
                path, content=payload, headers={"X-Jarvis-Mode": mode, **(extra_headers or {})}
            )

    return asyncio.run(request())


def test_all_saved_operations_reject_private_before_parsing_or_io(
    service, private, engine, monkeypatch
):
    before = snapshot(engine)
    operations = [
        lambda: service.read_probe(private),
        lambda: service.write_probe(private),
        lambda: service.read_source(private, uuid4()),
        lambda: service.read_claim(private, uuid4()),
        lambda: service.save_observation(private, SENTINEL),
        lambda: service.validate_claim(private, SENTINEL),
        lambda: service.commit_claim(private, SENTINEL),
        lambda: service.import_observations(private, SENTINEL, SENTINEL),
        lambda: service.list_sources(private, SENTINEL),
        lambda: service.inspect_source(private, SENTINEL),
    ]
    with no_store_access(engine, monkeypatch):
        for operation in operations:
            with pytest.raises(ApplicationError, match=ErrorCode.PRIVATE_OPERATION.value):
                operation()
    assert snapshot(engine) == before


@pytest.mark.parametrize("payload_kind", ["valid", "malformed_json", "invalid_schema", "oversized"])
def test_private_api_and_cli_never_persist_input_or_activity(
    service, private, observation, engine, monkeypatch, caplog, capsys, payload_kind
):
    observation["raw_text"] = SENTINEL
    payload = json.dumps(observation)
    expected = "valid"
    if payload_kind == "malformed_json":
        payload = '{"raw_text": "' + SENTINEL
        expected = "error"
    elif payload_kind == "invalid_schema":
        payload = json.dumps({**observation, SENTINEL: SENTINEL})
        expected = "error"
    elif payload_kind == "oversized":
        payload = SENTINEL * 30000
        expected = "error"
    before = snapshot(engine)
    with caplog.at_level(logging.WARNING), no_store_access(engine, monkeypatch):
        response = http_request(service, "/contracts/observations/validate", payload)
        assert response.json()["status"] == expected
        assert response.headers["Cache-Control"] == "no-store"
        assert SENTINEL not in response.text
        cli = CliRunner().invoke(
            cli_module.app, ["contracts", "observation", "--mode", "private"], input=payload
        )
        assert cli.exit_code == (0 if expected == "valid" else 1)
        assert json.loads(cli.output)["status"] == expected
        assert SENTINEL not in cli.output
    assert snapshot(engine) == before
    assert caplog.records == []
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("failure", [RuntimeError, TimeoutError])
def test_private_unexpected_failure_has_no_trace_or_logging(
    service, observation, engine, monkeypatch, caplog, failure
):
    before = snapshot(engine)

    def broken(*args, **kwargs):
        raise failure(SENTINEL)

    monkeypatch.setattr(type(service), "validate_observation", broken)
    with caplog.at_level(logging.WARNING), no_store_access(engine, monkeypatch):
        response = http_request(
            service, "/contracts/observations/validate", json.dumps(observation)
        )
        assert response.status_code == 500
        assert response.json()["reason"] == "operation_failed"
        result = CliRunner().invoke(
            cli_module.app,
            ["contracts", "observation", "--mode", "private"],
            input=json.dumps(observation),
        )
        assert result.exit_code == 1
        assert json.loads(result.output)["reason"] == "operation_failed"
        assert SENTINEL not in response.text + result.output
    assert caplog.records == []
    assert snapshot(engine) == before


def test_private_claim_and_probe_adapters_use_same_gate(service, engine, monkeypatch, caplog):
    before = snapshot(engine)
    with no_store_access(engine, monkeypatch):
        response = http_request(service, "/contracts/claims/validate", SENTINEL)
        assert response.status_code == 403
        for args in (["contracts", "claim"], ["probe", "read"], ["probe", "write"]):
            result = CliRunner().invoke(
                cli_module.app, [*args, "--mode", "private"], input=SENTINEL
            )
            assert result.exit_code == 1
            assert json.loads(result.output)["reason"] == "private_operation_denied"
    assert snapshot(engine) == before
    assert caplog.records == []


def test_private_current_context_is_not_backfilled(service, normal, private, observation, engine):
    private_input = {**observation, "raw_text": SENTINEL}
    assert service.validate_observation(private, private_input).raw_text == SENTINEL
    stored = service.save_observation(
        normal, {"observation": observation, "expected_policy_revision": 0}
    )
    assert stored.raw_text == observation["raw_text"]
    assert SENTINEL not in json.dumps(snapshot(engine))
    assert set(vars(service)) == {"engine", "identity", "expected_revision"}


def test_adapter_owner_override_and_mode_fail_closed(service, observation, engine, monkeypatch):
    payload = json.dumps({**observation, "owner_id": str(uuid4())})
    with no_store_access(engine, monkeypatch):
        result = http_request(service, "/contracts/observations/validate", payload, mode="normal")
        assert result.status_code == 422 and result.json()["reason"] == "invalid_input"
        invalid_mode = http_request(service, "/contracts/observations/validate", SENTINEL, mode="")
        assert invalid_mode.status_code == 422 and invalid_mode.json()["reason"] == "invalid_mode"


def test_private_validation_revalidates_instances(
    service, private, observation, engine, monkeypatch
):
    forged = ObservationInput.model_construct(**{**observation, "raw_text": 7})
    with no_store_access(engine, monkeypatch):
        with pytest.raises(ApplicationError, match="invalid_input"):
            service.validate_observation(private, forged)


def test_normal_claim_adapters_validate_without_writing_or_trusting_owner_header(
    service, proposal, engine
):
    before = snapshot(engine)
    response = http_request(
        service,
        "/contracts/claims/validate",
        json.dumps(proposal),
        mode="normal",
        extra_headers={"X-Owner-ID": str(uuid4())},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "valid", "stored": False}
    result = CliRunner().invoke(
        cli_module.app, ["contracts", "claim", "--mode", "normal"], input=json.dumps(proposal)
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == response.json()
    assert snapshot(engine) == before
