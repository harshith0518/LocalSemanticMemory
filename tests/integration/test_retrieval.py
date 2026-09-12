import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from memory_double import FixtureExtractor, content, passage
from sqlalchemy import select, update
from typer.testing import CliRunner

import jarvis.cli as cli_module
from jarvis.api import create_app
from jarvis.errors import ApplicationError
from jarvis.models import ClaimRecord, Policy, Source
from jarvis.policy import LocalIdentity
from jarvis.retrieval import evidence_size, fuse_rankings
from jarvis.services import Service
from jarvis.worker import process_one

FIXTURE = Path("data/synthetic/sample-dictations.jsonl")


def imported(service, rows=None, namespace="search"):
    context = service.identity.context("normal")
    service.import_observations(
        context,
        {
            "namespace": namespace,
            "expected_policy_revision": 0,
        },
        rows if rows is not None else FIXTURE.read_bytes(),
    )
    return context


def records(result):
    return {s["source_key"].split(":")[-1] for s in result["sources"]}


@pytest.fixture
def processed(engine):
    service = Service(engine, extractor=FixtureExtractor())
    context = imported(service)
    service.request_processing(context, {"namespace": "search", "expected_policy_revision": 0})
    for _ in range(8):
        assert process_one(service, context)["decision"] == "extracted"
    return service, context


def test_sources_search_without_processing_preserves_pairs_and_leaves_no_activity(service, engine):
    from test_private import snapshot

    context = imported(service)
    before = snapshot(engine)
    result = service.search(context, {"namespace": "search", "query": "spending limit"})
    assert result["status"] == "matched"
    assert records(result) == {"dict_0008"}
    assert len(result["matches"]) == 1
    assert "fifteen thousand" in result["sources"][0]["raw_text"]
    assert "50,000" in result["sources"][0]["formatted_text"]
    assert result["memories"] == []
    assert snapshot(engine) == before


def test_retrieval_keeps_conditions_scope_and_unknown_times(processed):
    service, context = processed
    result = service.search(
        context,
        {
            "namespace": "search",
            "query": "Ravi",
            "representation": "sources_and_memories",
        },
    )
    assert records(result) == {"dict_0004"}
    claim = result["memories"][0]["content"]
    assert claim["condition"] and claim["evidence_status"] == "tentative"
    assert claim["modality"] == "conditional" and claim["scope"]["key"] == "Atlas"
    assert claim["time"]["event"] is None


def test_history_is_explicit_and_never_relabels_prior_claim_current(processed):
    service, context = processed
    query = {
        "namespace": "search",
        "query": "Atlas launch",
        "representation": "sources_and_memories",
    }
    current = service.search(context, query)
    assert all(m["lifecycle"] == "active" for m in current["memories"])
    history = service.search(context, {**query, "history": True})
    old = [m for m in history["memories"] if m["lifecycle"] == "superseded"]
    assert len(old) == 1 and old[0]["content"]["value"]["value"] == "2026-09-18"


def test_memory_terms_can_find_original_and_source_details_remain_searchable(service):
    context = imported(
        service,
        json.dumps(
            {"record_id": "one", "raw_transcript": "My car is electric. Its paint code is Z19."}
        ),
    )
    source = service.read_source(
        context, service.list_sources(context, {"namespace": "search"}).observations[0].id
    )
    service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": content("vehicle", "electric", subject="user", scope="transport"),
            "passages": [passage(source.model_dump(mode="json"))],
        },
    )
    query = {"namespace": "search", "query": "vehicle"}
    assert service.search(context, query)["status"] == "no_matches"
    enriched = service.search(context, {**query, "representation": "sources_and_memories"})
    assert records(enriched) == {"one"} and enriched["matches"][0]["via"] == ["memory"]
    assert records(
        service.search(context, {**query, "query": "Z19", "representation": "sources_and_memories"})
    ) == {"one"}


def test_ownership_namespace_and_provenance_filter_before_limit(service, engine):
    context = imported(service)
    other = Service(engine, LocalIdentity(uuid4()))
    imported(other, json.dumps({"record_id": "secret", "raw_transcript": "Ravi Ravi Ravi"}))
    imported(
        service, json.dumps({"record_id": "elsewhere", "raw_transcript": "Ravi Ravi Ravi"}), "other"
    )
    result = service.search(context, {"namespace": "search", "query": "Ravi", "limit": 1})
    assert records(result) == {"dict_0004"}
    with engine.begin() as connection:
        connection.execute(
            update(Source).where(Source.owner_id == context.owner_id).values(kind="unknown")
        )
    assert (
        service.search(context, {"namespace": "search", "query": "Ravi"})["status"] == "no_matches"
    )


def test_excluded_support_blocks_original_fallback_and_claims(processed, engine):
    service, context = processed
    with engine.begin() as connection:
        connection.execute(
            update(ClaimRecord)
            .where(ClaimRecord.content["predicate"].astext == "budget_owner")
            .values(lifecycle="excluded")
        )
    for representation in ("sources", "sources_and_memories"):
        assert (
            service.search(
                context,
                {
                    "namespace": "search",
                    "query": "Ravi",
                    "representation": representation,
                    "history": True,
                },
            )["status"]
            == "no_matches"
        )


def test_capture_filter_preserves_unknown_and_never_uses_mentioned_date(service):
    context = imported(service)
    query = {"namespace": "search", "query": "Orion", "captured_from": "2030-01-01T00:00:00Z"}
    result = service.search(context, query)
    assert records(result) == {"dict_0007"} and result["sources"][0]["captured_at"] is None
    assert service.search(context, {**query, "include_undated": False})["status"] == "no_matches"


@pytest.mark.parametrize(
    "query",
    ["running", "नमस्ते", "May", "O'Reilly", "blue -green", "' ); DROP TABLE jarvis.sources; --"],
)
def test_unicode_inflections_and_punctuation_are_data(service, query):
    context = imported(
        service,
        json.dumps(
            {
                "record_id": "one",
                "raw_transcript": (
                    "May runs. नमस्ते दुनिया. O'Reilly paints blue and green. DROP TABLE is text."
                ),
            }
        ),
    )
    result = service.search(context, {"namespace": "search", "query": query})
    assert records(result) == {"one"}


def test_budget_keeps_complete_records_and_reports_overflow(service):
    context = imported(
        service, json.dumps({"record_id": "one", "raw_transcript": "budget " + "x" * 4000})
    )
    query = {"namespace": "search", "query": "budget", "max_bytes": 1024}
    small = service.search(context, query)
    assert small["status"] == "evidence_budget_exceeded" and small["sources"] == []
    packet = service.prepare_search(context, {**query, "max_bytes": 8000})
    assert packet.evidence_bytes == evidence_size(packet.sources, packet.memories)
    assert len(packet.sources[0].raw_text) == 4007


@pytest.mark.parametrize("mutation", ["policy", "source", "claim", "exclusion", "new_source"])
def test_prepared_results_rechecked_before_release(processed, engine, mutation):
    service, context = processed
    packet = service.prepare_search(
        context, {"namespace": "search", "query": "Ravi", "representation": "sources_and_memories"}
    )
    with engine.begin() as connection:
        if mutation == "policy":
            connection.execute(update(Policy).values(revision=1))
        elif mutation == "source":
            connection.execute(
                update(Source)
                .where(Source.id == packet.sources[0].id)
                .values(raw_text="Changed source")
            )
        elif mutation in {"claim", "exclusion"}:
            connection.execute(
                update(ClaimRecord)
                .where(ClaimRecord.id == packet.memories[0].id)
                .values(lifecycle="corrected" if mutation == "claim" else "excluded")
            )
    if mutation == "new_source":
        imported(
            service,
            json.dumps({"record_id": "new", "raw_transcript": "Ravi is a different person here."}),
        )
    released = []
    with pytest.raises(ApplicationError):
        service.release_search(context, packet, released.append)
    assert released == []


@pytest.mark.parametrize("change", ["policy", "exclusion"])
def test_policy_commit_between_selection_and_release_is_rejected(processed, engine, change):
    service, context = processed
    barrier = Barrier(2)

    def search():
        packet = service.prepare_search(context, {"namespace": "search", "query": "Ravi"})
        barrier.wait(timeout=5)
        barrier.wait(timeout=5)
        with pytest.raises(ApplicationError, match="stale_revision"):
            service.release_search(context, packet)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(search)
        barrier.wait(timeout=5)
        with engine.begin() as connection:
            connection.execute(select(Policy).with_for_update())
            if change == "policy":
                connection.execute(update(Policy).values(revision=1))
            else:
                connection.execute(
                    update(ClaimRecord)
                    .where(ClaimRecord.content["predicate"].astext == "budget_owner")
                    .values(lifecycle="excluded")
                )
        barrier.wait(timeout=5)
        future.result(timeout=10)


@pytest.mark.parametrize("immediate", [False, True])
def test_release_guard_precedes_competing_policy_write(processed, engine, immediate):
    service, context = processed
    packet = service.prepare_search(context, {"namespace": "search", "query": "Ravi"})
    barrier = Barrier(2)

    def render(result):
        barrier.wait(timeout=5)
        barrier.wait(timeout=5)
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        if immediate:
            future = pool.submit(service.search, context, packet.request, render)
        else:
            future = pool.submit(service.release_search, context, packet, render)
        barrier.wait(timeout=5)
        with engine.begin() as connection:
            assert (
                connection.execute(select(Policy).with_for_update(skip_locked=True)).first() is None
            )
        barrier.wait(timeout=5)
        assert future.result(timeout=10)["status"] == "matched"
    with engine.begin() as connection:
        connection.execute(update(Policy).values(revision=1))


def test_api_cli_share_search_and_private_refuses_body(service, engine, monkeypatch):
    context = imported(service)
    query = {"namespace": "search", "query": "Orion"}
    expected = service.search(context, query)

    async def check():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            result = await client.post("/search", json=query, headers={"X-Jarvis-Mode": "normal"})
            assert result.json() == expected and result.headers["Cache-Control"] == "no-store"

            async def unread():
                raise AssertionError("Private body was read")
                yield b""

            private = await client.post(
                "/search", content=unread(), headers={"X-Jarvis-Mode": "private"}
            )
            assert private.status_code == 403

    asyncio.run(check())
    monkeypatch.setattr(cli_module, "make_engine", lambda _: engine)
    result = CliRunner().invoke(
        cli_module.app, ["search", "--mode", "normal"], input=json.dumps(query)
    )
    assert result.exit_code == 0 and json.loads(result.stdout) == expected


def test_query_validation_and_empty_search(service):
    context = service.identity.context("normal")
    for query in ("", "  ", "x" * 513):
        with pytest.raises(ApplicationError, match="invalid_input"):
            service.search(context, {"namespace": "search", "query": query})
    assert (
        service.search(context, {"namespace": "search", "query": "???"})["status"] == "no_matches"
    )


def test_rrf_deduplicates_each_branch_without_dropping_union_candidates():
    assert fuse_rankings(["a", "a", "b"], ["c", "b"]) == {"a": 1 / 61, "b": 2 / 62, "c": 1 / 61}


def test_all_supporting_sources_travel_with_selected_claim(service):
    context = imported(
        service,
        "\n".join(
            json.dumps(row)
            for row in [
                {"record_id": "a", "raw_transcript": "I drive an electric car."},
                {"record_id": "b", "raw_transcript": "The same car takes me to work."},
            ]
        ),
    )
    sources = [
        service.read_source(context, row.id)
        for row in service.list_sources(context, {"namespace": "search"}).observations
    ]
    service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": content("commuting", "electric vehicle"),
            "passages": [passage(source.model_dump(mode="json")) for source in sources],
        },
    )
    result = service.search(
        context,
        {
            "namespace": "search",
            "query": "commuting",
            "representation": "sources_and_memories",
            "limit": 1,
        },
    )
    assert len(result["matches"]) == 1 and records(result) == {"a", "b"}
    assert len(result["memories"][0]["passages"]) == 2


def test_database_failure_is_not_no_matching_evidence(service, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("", {}, Exception("unpublished driver details"))

    monkeypatch.setattr(service.engine, "connect", unavailable)
    with pytest.raises(ApplicationError, match="database_unavailable"):
        service.search(service.identity.context("normal"), {"namespace": "search", "query": "Ravi"})


def test_fusion_preserves_unextracted_original_context(processed):
    service, context = processed
    imported(
        service,
        json.dumps(
            {
                "record_id": "visitor",
                "raw_transcript": (
                    "The Ravi mentioned in the Cedar note is a visitor. "
                    "I do not know whether he is the Ravi discussed for the Atlas budget."
                ),
            }
        ),
    )
    query = {
        "namespace": "search",
        "query": "Is the visitor Ravi the confirmed Atlas budget owner?",
    }
    original = service.search(context, query)
    combined = service.search(context, {**query, "representation": "sources_and_memories"})
    assert original["matches"][0]["source_id"] == combined["matches"][0]["source_id"]
    assert {"visitor", "dict_0004"}.issubset(records(combined))


def test_index_migration_preserves_all_canonical_rows_and_results(
    processed, engine, migrations, migration_engine
):
    from alembic import command
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect
    from test_private import snapshot

    service, context = processed
    query = {"namespace": "search", "query": "Ravi", "representation": "sources_and_memories"}
    before, result = snapshot(engine), service.search(context, query)
    revision = (
        ScriptDirectory.from_config(Config("alembic.ini"))
        .get_revision("0004_lexical_retrieval")
        .module
    )

    def indexes(action):
        with migration_engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                getattr(revision, action)()

    indexes("downgrade")
    try:
        assert "sources_search_idx" not in {
            i["name"] for i in inspect(engine).get_indexes("sources", schema="jarvis")
        }
        assert snapshot(engine) == before
        assert service.search(context, query) == result
    finally:
        indexes("upgrade")
    migrations(command.check)
    assert snapshot(engine) == before
    assert service.search(context, query) == result
