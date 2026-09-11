import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from jarvis.api import create_app
from jarvis.cli import app as cli
from jarvis.config import LOCAL_OWNER
from jarvis.db import make_engine
from jarvis.models import Job, Policy, Source
from jarvis.services import PROBE_FORMATTED, PROBE_KEY, PROBE_RAW, Service, content_hash


def counts(engine):
    with Session(engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model)) for model in (Source, Job)
        )


def api_responses(service):
    async def request():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            return await client.get("/ready"), await client.get("/health")

    return asyncio.run(request())


def test_migrations_from_empty_schema_and_repeat_without_drift(engine, migrations):
    migrations(command.downgrade, "base")
    try:
        assert inspect(engine).get_table_names(schema="jarvis") == ["alembic_version"]
        migrations(command.upgrade, "head")
        migrations(command.upgrade, "head")
        migrations(command.check)
        assert set(inspect(engine).get_table_names(schema="jarvis")) == {
            "alembic_version",
            "policies",
            "sources",
            "jobs",
            "passages",
            "claim_revisions",
            "claim_evidence",
        }
    finally:
        migrations(command.upgrade, "head")


def test_api_cli_and_service_report_identical_readiness(service):
    expected = service.ready()
    assert expected["status"] == "ready"
    assert expected["schema"] == "0002_evidence_contracts"
    assert expected["pgvector"] == "0.8.6"
    response, health = api_responses(service)
    assert response.status_code == 200
    assert response.json() == expected
    assert health.json() == {"status": "alive"}
    result = CliRunner().invoke(cli, ["ready"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected


def assert_unready(service, reason):
    expected = {"status": "not_ready", "reason": reason}
    response, health = api_responses(service)
    assert response.status_code == 503
    assert response.json() == expected
    assert health.status_code == 200
    result = CliRunner().invoke(cli, ["ready"])
    assert result.exit_code == 1
    assert json.loads(result.output) == expected


def test_stale_schema_is_unready(service, migrations):
    migrations(command.downgrade, "base")
    try:
        assert_unready(service, "schema_mismatch")
    finally:
        migrations(command.upgrade, "head")


def test_unavailable_database_is_sanitized(settings, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PORT", "1")
    unavailable = make_engine(replace(settings, port=1))
    try:
        assert_unready(Service(unavailable), "database_unavailable")
    finally:
        unavailable.dispose()


def test_pgvector_is_enabled_and_runtime_cannot_change_schema(engine):
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector")) == 0
        assert connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one() == (False, False, False)
    for statement in (
        "CREATE TABLE jarvis.forbidden (id int)",
        "CREATE TABLE public.forbidden (id int)",
        "UPDATE jarvis.alembic_version SET version_num = 'tampered'",
    ):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(statement))


def test_probe_is_atomic_idempotent_and_preserves_unknowns(service, engine):
    saved = service.write_probe()
    assert service.write_probe() == saved
    assert service.read_probe() == saved
    assert counts(engine) == (1, 1)
    source, job = saved["source"], saved["job"]
    assert source["raw_text"] == PROBE_RAW
    assert source["formatted_text"] == PROBE_FORMATTED
    assert source["content_hash"] == content_hash(PROBE_RAW, PROBE_FORMATTED)
    assert source["captured_at"] is None
    assert source["capture_metadata"] is None
    assert source["imported_at"].tzinfo is not None
    assert job["status"] == "pending" and job["attempts"] == 0
    assert job["expected_policy_revision"] == 0 and job["expected_source_revision"] == 1
    assert source["owner_id"] == job["owner_id"] == LOCAL_OWNER


def test_cli_probe_uses_shared_write_and_read(service):
    result = CliRunner().invoke(cli, ["probe", "write"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == json.loads(json.dumps(service.read_probe(), default=str))
    read = CliRunner().invoke(cli, ["probe", "read"])
    assert read.exit_code == 0 and read.output == result.output


def test_job_collision_rolls_back_source_insert(service, engine):
    saved = service.write_probe()
    with engine.begin() as connection:
        connection.execute(update(Source).values(source_key="another-observation"))
    with pytest.raises(IntegrityError):
        service.write_probe()
    assert counts(engine) == (1, 1)
    assert service.read_probe() is None
    with Session(engine) as session:
        assert session.get(Source, saved["source"]["id"]).source_key == "another-observation"


def test_equal_text_is_not_observation_identity(service, engine):
    saved = service.write_probe()["source"]
    with Session(engine) as session, session.begin():
        session.add(
            Source(
                owner_id=LOCAL_OWNER,
                source_key="independent-synthetic-observation",
                raw_text=saved["raw_text"],
                formatted_text=saved["formatted_text"],
                content_hash=saved["content_hash"],
            )
        )
    assert counts(engine) == (2, 1)
    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(
            Source(
                owner_id=LOCAL_OWNER,
                source_key=PROBE_KEY,
                raw_text=PROBE_RAW,
                content_hash=content_hash(PROBE_RAW, None),
            )
        )


@pytest.mark.parametrize("wrong_owner,revision", [(True, 1), (False, 2)])
def test_job_must_match_source_owner_and_revision(service, engine, wrong_owner, revision):
    source = service.write_probe()["source"]
    owner = uuid4() if wrong_owner else LOCAL_OWNER
    if wrong_owner:
        with Session(engine) as session, session.begin():
            session.add(Policy(owner_id=owner))
    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(
            Job(
                owner_id=owner,
                source_id=source["id"],
                idempotency_key="mismatch",
                expected_source_revision=revision,
                expected_policy_revision=0,
            )
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE jarvis.policies SET revision = -1",
        "UPDATE jarvis.sources SET content_hash = 'invalid'",
        "UPDATE jarvis.jobs SET attempts = -1",
        "UPDATE jarvis.jobs SET expected_policy_revision = -1",
        "UPDATE jarvis.jobs SET status = 'invented'",
    ],
)
def test_invalid_record_state_is_rejected(service, engine, statement):
    service.write_probe()
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(statement))


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "development"},
        {"host": "db"},
        {"database": "jarvis"},
        {"user": "jarvis_app"},
        {"port": 5433},
    ],
)
def test_test_guard_rejects_application_or_unknown_targets(settings, override):
    with pytest.raises(ValueError, match="isolated"):
        replace(settings, **override).require_test_database()


def test_test_database_identity_and_network_are_separate(engine):
    import socket

    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database(), current_user")).one() == (
            "jarvis_test",
            "jarvis_test_app",
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM pg_database WHERE datname = 'jarvis'")) == 0
        )
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("db", 5432)


def test_simultaneous_probe_writes_use_separate_connections(settings, engine):
    barrier = Barrier(2, timeout=10)

    def write():
        independent_engine = make_engine(settings)
        try:
            with independent_engine.connect() as connection:
                pid = connection.scalar(text("SELECT pg_backend_pid()"))
                barrier.wait()
            return pid, Service(independent_engine).write_probe()
        finally:
            independent_engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: write(), range(2)))
    assert first[0] != second[0]
    assert first[1] == second[1]
    assert counts(engine) == (1, 1)
