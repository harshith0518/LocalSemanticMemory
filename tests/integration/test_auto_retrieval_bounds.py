"""Automatic retrieval stays memory-first and bounded; no live model calls here."""

import json
from uuid import uuid4

from memory_double import content, passage
from sqlalchemy import update

from jarvis.models import ClaimRecord
from jarvis.policy import LocalIdentity
from jarvis.retrieval import SearchRequest
from jarvis.services import Service


def import_rows(service, context, namespace, rows):
    service.import_observations(
        context,
        {"namespace": namespace, "expected_policy_revision": 0},
        "\n".join(json.dumps(row) for row in rows),
    )


def source_for(service, context, namespace, record_id):
    summary = next(
        item
        for item in service.list_sources(context, {"namespace": namespace}).observations
        if item.source_key == f"import:{namespace}:{record_id}"
    )
    return service.read_source(context, summary.id)


def remember(service, context, source, predicate, value):
    return service.commit_claim(
        context,
        {
            "expected_policy_revision": 0,
            "content": content(predicate, value, subject="user", scope="preferences"),
            "passages": [passage(source.model_dump(mode="json"))],
        },
    )


def automatic_packet(service, context, namespace, question):
    query = SearchRequest(
        namespace=namespace,
        query=question,
        representation="sources_and_memories",
        limit=12,
        max_bytes=24000,
        memory_eligible_only=True,
    )
    with service._session(context) as session:
        return service._select_auto(session, context, query)


def test_auto_uses_relevant_memory_with_only_its_complete_provenance(engine):
    service = Service(engine)
    context = service.identity.context("normal")
    namespace = "bounded"
    import_rows(
        service,
        context,
        namespace,
        [
            {
                "record_id": "tea-proof",
                "raw_transcript": "At sunrise I reach for a warm cup of fragrant leaves.",
            },
            *[
                {
                    "record_id": f"noise-{index:02}",
                    "raw_transcript": (
                        f"UNRELATED_NOTE_{index:02} records a different archive item."
                    ),
                }
                for index in range(30)
            ],
        ],
    )
    tea = source_for(service, context, namespace, "tea-proof")
    memory = remember(service, context, tea, "beverage", "tea")

    packet = automatic_packet(service, context, namespace, "Which beverage did I say I prefer?")

    assert packet.strategy == "memory_first_ranked"
    assert packet.status == "matched" and packet.has_more
    assert packet.eligible_sources == 31 and packet.eligible_memories == 1
    assert [item.id for item in packet.memories] == [memory.id]
    assert [item.id for item in packet.sources] == [tea.id]
    assert packet.matches[0].via == ("memory",)
    assert "UNRELATED_NOTE" not in packet.model_dump_json()
    assert packet.evidence_bytes <= packet.request.max_bytes


def test_auto_no_lexical_overlap_uses_bounded_structured_memory_fallback(engine):
    service = Service(engine)
    context = service.identity.context("normal")
    namespace = "paraphrase"
    import_rows(
        service,
        context,
        namespace,
        [
            {
                "record_id": "tea-proof",
                "raw_transcript": "At dawn I reach for a warm cup with fragrant leaves.",
            },
            *[
                {
                    "record_id": f"noise-{index:02}",
                    "raw_transcript": f"NOISE_SENTINEL_{index:02} documents a distant survey.",
                }
                for index in range(36)
            ],
        ],
    )
    tea = source_for(service, context, namespace, "tea-proof")
    memory = remember(service, context, tea, "daily_drink", "tea")

    packet = automatic_packet(service, context, namespace, "Which refreshment do I favour?")

    assert packet.strategy == "memory_diversity_fallback"
    assert packet.status == "matched" and packet.has_more
    assert packet.eligible_sources == 37 and packet.eligible_memories == 1
    assert [item.id for item in packet.memories] == [memory.id]
    assert [item.id for item in packet.sources] == [tea.id]
    assert "NOISE_SENTINEL" not in packet.model_dump_json()
    assert packet.evidence_bytes <= packet.request.max_bytes


def test_auto_fallback_never_leaks_foreign_or_excluded_memory_support(engine):
    service = Service(engine)
    context = service.identity.context("normal")
    namespace = "isolation"
    import_rows(
        service,
        context,
        namespace,
        [
            {"record_id": "visible", "raw_transcript": "A warm cup starts my morning."},
            {"record_id": "forgotten", "raw_transcript": "EXCLUDED_SENTINEL is never recallable."},
        ],
    )
    visible = source_for(service, context, namespace, "visible")
    forgotten = source_for(service, context, namespace, "forgotten")
    visible_memory = remember(service, context, visible, "daily_drink", "tea")
    forgotten_memory = remember(service, context, forgotten, "daily_drink", "coffee")
    with engine.begin() as connection:
        connection.execute(
            update(ClaimRecord)
            .where(ClaimRecord.id == forgotten_memory.id)
            .values(lifecycle="excluded")
        )

    other = Service(engine, LocalIdentity(uuid4()))
    other_context = other.identity.context("normal")
    import_rows(
        other,
        other_context,
        namespace,
        [{"record_id": "foreign", "raw_transcript": "FOREIGN_SENTINEL is confidential."}],
    )
    foreign = source_for(other, other_context, namespace, "foreign")
    remember(other, other_context, foreign, "daily_drink", "espresso")

    packet = automatic_packet(service, context, namespace, "Which refreshment do I favour?")

    assert packet.status == "matched"
    assert [item.id for item in packet.memories] == [visible_memory.id]
    assert [item.id for item in packet.sources] == [visible.id]
    serialized = packet.model_dump_json()
    assert "EXCLUDED_SENTINEL" not in serialized
    assert "FOREIGN_SENTINEL" not in serialized
