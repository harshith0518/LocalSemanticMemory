from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jarvis.contracts import ClaimContent, ClaimWrite, ObservationInput, parse_contract
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.models import ClaimEvidence, ClaimRecord, Job, Passage, Policy, Source
from jarvis.policy import LocalIdentity, RequestContext
from jarvis.services import Service


def expect_error(code):
    return pytest.raises(ApplicationError, match=f"^{code.value}$")


def test_claim_roundtrip_preserves_uncertainty_time_and_pairing(
    service, normal, source, proposal, engine
):
    proposal["passages"].append(
        {
            "source_id": str(source.id),
            "source_revision": 1,
            "variant": "formatted",
            "start": 0,
            "end": len(source.formatted_text),
            "exact_text": source.formatted_text,
        }
    )
    saved = service.commit_claim(normal, proposal)
    assert service.read_claim(normal, saved.id) == saved
    assert saved.content == parse_contract(ClaimContent, proposal["content"])
    assert saved.content.evidence_status == "tentative"
    assert saved.content.modality == "conditional"
    assert saved.content.subject.entity_id is None
    assert saved.content.attribution.entity_id is None
    assert saved.content.time.model_dump() == {"event": None, "valid_from": None, "valid_to": None}
    assert source.captured_at is None and source.capture_metadata is None
    assert saved.recorded_at.tzinfo is not None
    assert saved.lifecycle == "active" and saved.revision == 1
    assert {p.source_id for p in saved.passages} == {source.id}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(Passage)) == 2


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"source_id": str(uuid4())}, ErrorCode.REFERENCE_UNAVAILABLE),
        ({"source_revision": 2}, ErrorCode.STALE_REVISION),
        ({"variant": "formatted"}, ErrorCode.INVALID_PASSAGE),
        ({"variant": "assistant"}, ErrorCode.INVALID_INPUT),
        ({"start": -1}, ErrorCode.INVALID_INPUT),
        ({"end": 0}, ErrorCode.INVALID_INPUT),
        ({"end": 100000}, ErrorCode.INVALID_PASSAGE),
        ({"exact_text": "Unsupported invented launch date"}, ErrorCode.INVALID_PASSAGE),
    ],
)
def test_invalid_passages_do_not_write(service, normal, proposal, engine, changes, code):
    proposal["passages"][0].update(changes)
    with expect_error(code):
        service.commit_claim(normal, proposal)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 0
        assert session.scalar(select(func.count()).select_from(Passage)) == 0


def test_offsets_are_codepoints_not_utf8_bytes(service, normal, source, proposal):
    text_value = "If the budget is approved"
    start = source.raw_text.index(text_value)
    passage = proposal["passages"][0]
    passage.update(start=start, end=start + len(text_value), exact_text=text_value)
    assert service.validate_claim(normal, proposal)
    passage.update(start=len(source.raw_text[:start].encode("utf-8")))
    passage.update(end=passage["start"] + len(text_value))
    with expect_error(ErrorCode.INVALID_PASSAGE):
        service.commit_claim(normal, proposal)


def test_missing_formatted_variant_cannot_be_cited(service, normal, observation, claim_content):
    observation["formatted_text"] = None
    source = service.save_observation(
        normal, {"observation": observation, "expected_policy_revision": 0}
    )
    with expect_error(ErrorCode.INVALID_PASSAGE):
        service.commit_claim(
            normal,
            {
                "expected_policy_revision": 0,
                "content": claim_content,
                "passages": [
                    {
                        "source_id": source.id,
                        "source_revision": 1,
                        "variant": "formatted",
                        "start": 0,
                        "end": 1,
                        "exact_text": "M",
                    }
                ],
            },
        )


def test_cross_owner_sources_claims_and_context_are_rejected(
    service, normal, proposal, source, engine
):
    other = Service(engine, LocalIdentity(uuid4()))
    context = other.identity.context("normal")
    other.write_probe(context)
    with expect_error(ErrorCode.REFERENCE_UNAVAILABLE):
        other.commit_claim(context, proposal)
    with expect_error(ErrorCode.REFERENCE_UNAVAILABLE):
        other.read_source(context, source.id)
    saved = service.commit_claim(normal, proposal)
    with expect_error(ErrorCode.REFERENCE_UNAVAILABLE):
        other.read_claim(context, saved.id)
    forged = RequestContext(context.owner_id, normal.mode)
    with expect_error(ErrorCode.REFERENCE_UNAVAILABLE):
        service.read_source(forged, source.id)


def test_stale_policy_and_source_rechecked_at_commit(
    service, normal, proposal, observation, source, engine
):
    validated = service.validate_claim(normal, proposal)
    newer = service.save_observation(
        normal,
        {
            "observation": {**observation, "raw_text": "A revised synthetic observation."},
            "expected_policy_revision": 0,
            "expected_source_revision": 1,
        },
    )
    assert newer.revision == 2
    assert service.read_source(normal, source.id) == source
    with expect_error(ErrorCode.STALE_REVISION):
        service.commit_claim(normal, validated)
    with engine.begin() as connection:
        connection.execute(update(Policy).values(revision=1))
    with expect_error(ErrorCode.STALE_REVISION):
        service.save_observation(
            normal,
            {
                "observation": observation,
                "expected_policy_revision": 0,
                "expected_source_revision": 2,
            },
        )


def test_claim_append_checks_revision_and_preserves_prior_record(service, normal, proposal):
    first = service.commit_claim(normal, proposal)
    proposal.update(claim_id=str(first.claim_id), expected_claim_revision=1)
    second = service.commit_claim(normal, proposal)
    assert second.claim_id == first.claim_id and second.revision == 2
    assert service.read_claim(normal, first.id) == first
    with expect_error(ErrorCode.STALE_REVISION):
        service.commit_claim(normal, proposal)


def test_late_evidence_failure_rolls_back_whole_claim(service, normal, proposal, engine):
    # Simulate corrupt pre-existing derived state: a conflicting location with wrong text.
    reference = parse_contract(ClaimWrite, proposal).passages[0]
    with Session(engine) as session, session.begin():
        session.add(
            Passage(
                owner_id=normal.owner_id,
                **{**reference.model_dump(), "exact_text": "Corrupt synthetic derived text"},
            )
        )
    with expect_error(ErrorCode.INVALID_PASSAGE):
        service.commit_claim(normal, proposal)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ClaimRecord)) == 0
        assert session.scalar(select(func.count()).select_from(ClaimEvidence)) == 0


def test_new_migration_preserves_s03_records(engine, migrations):
    migrations(command.downgrade, "0001_bootstrap")
    owner, source_id, job_id = uuid4(), uuid4(), uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO jarvis.policies(owner_id) VALUES (:owner)"), {"owner": owner}
            )
            connection.execute(
                text(
                    "INSERT INTO jarvis.sources(id, owner_id, source_key, raw_text, content_hash) "
                    "VALUES (:id, :owner, 's03:legacy', 'Synthetic legacy source', :hash)"
                ),
                {"id": source_id, "owner": owner, "hash": "a" * 64},
            )
            connection.execute(
                text(
                    "INSERT INTO jarvis.jobs(id, owner_id, source_id, idempotency_key, "
                    "expected_source_revision, expected_policy_revision) "
                    "VALUES (:id, :owner, :source, 's03:legacy', 1, 0)"
                ),
                {"id": job_id, "owner": owner, "source": source_id},
            )
            before = connection.execute(text("SELECT * FROM jarvis.sources")).mappings().one()
            job_before = connection.execute(text("SELECT * FROM jarvis.jobs")).mappings().one()
        migrations(command.upgrade, "head")
        with engine.connect() as connection:
            after = connection.execute(text("SELECT * FROM jarvis.sources")).mappings().one()
            assert {key: after[key] for key in before} == dict(before)
            assert after["kind"] == "unknown"
            assert (
                connection.execute(text("SELECT * FROM jarvis.jobs")).mappings().one() == job_before
            )
        migrations(command.check)
    finally:
        migrations(command.upgrade, "head")


@pytest.mark.parametrize(
    "override",
    [
        {"kind": "assistant_reply"},
        {"owner_id": str(uuid4())},
        {"revision": True},
        {"captured_at": "2026-09-11T12:00:00"},
        {"captured_at": 0},
        {"raw_text": "\ud800"},
    ],
)
def test_observation_contract_rejects_ineligible_or_invented_metadata(observation, override):
    observation.update(override)
    with expect_error(ErrorCode.INVALID_INPUT):
        parse_contract(ObservationInput, observation)


@pytest.mark.parametrize(
    "override",
    [
        {"scope": {"kind": "project"}},
        {"scope": {"kind": "global", "key": "Atlas"}},
        {"evidence_status": "verified"},
        {"evidence_status": "reported"},
        {"condition": None},
        {"negated": "false"},
        {"subject": {"label": "Atlas", "entity_id": str(uuid4())}},
        {"time": {"event": {"precision": "instant", "value": 0}}},
        {"time": {"event": {"precision": "instant", "value": "2026-09-11T12:00:00"}}},
        {"time": {"event": {"precision": "date", "value": "2026-09-11T00:00:00Z"}}},
        {
            "time": {
                "valid_from": {"precision": "date", "value": "2026-09-12"},
                "valid_to": {"precision": "date", "value": "2026-09-11"},
            }
        },
    ],
)
def test_claim_contract_rejects_meaning_losing_inputs(claim_content, override):
    claim_content.update(override)
    with expect_error(ErrorCode.INVALID_INPUT):
        parse_contract(ClaimContent, claim_content)


def test_typed_quantity_negation_and_dates_roundtrip(service, normal, proposal, observation):
    observation.update(
        source_key="s04:synthetic:quantity",
        raw_text=(
            "On 2026-09-11 Mira said: if the budget is approved, Atlas might not cost INR 4500.25."
        ),
        formatted_text=None,
    )
    source = service.save_observation(
        normal, {"observation": observation, "expected_policy_revision": 0}
    )
    proposal["passages"] = [
        {
            "source_id": str(source.id),
            "source_revision": 1,
            "variant": "raw",
            "start": 0,
            "end": len(source.raw_text),
            "exact_text": source.raw_text,
        }
    ]
    proposal["content"].update(
        predicate="possible_cost",
        value={"kind": "quantity", "value": "4500.25", "unit": "INR"},
        negated=True,
        time={"event": {"precision": "date", "value": "2026-09-11"}},
    )
    saved = service.commit_claim(normal, proposal)
    assert saved.content.value.value == Decimal("4500.25")
    assert saved.content.value.unit == "INR" and saved.content.negated is True
    assert saved.content.time.event.precision == "date"
    assert saved.content.time.valid_from is None


def test_unknown_provenance_is_not_eligible(service, normal, proposal, engine):
    with engine.begin() as connection:
        connection.execute(update(Source).values(kind="unknown"))
    with expect_error(ErrorCode.INELIGIBLE_SOURCE):
        service.commit_claim(normal, proposal)


def test_database_evidence_links_cannot_cross_owners(service, normal, proposal, engine):
    first = service.commit_claim(normal, proposal)
    other_owner = uuid4()
    with Session(engine) as session, session.begin():
        session.add(Policy(owner_id=other_owner))
        session.flush()
        other_claim = ClaimRecord(
            owner_id=other_owner,
            claim_id=uuid4(),
            revision=1,
            policy_revision=0,
            content=first.content.model_dump(mode="json"),
        )
        session.add(other_claim)
        session.flush()
        other_id = other_claim.id
    with engine.connect() as connection:
        passage_id = connection.scalar(select(Passage.id))
    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(
            ClaimEvidence(
                claim_revision_id=other_id, passage_id=passage_id, owner_id=other_owner, position=0
            )
        )


def test_constructed_invalid_model_does_not_bypass_validation(service, normal, proposal):
    validated = parse_contract(ClaimWrite, proposal)
    forged = validated.model_copy(update={"expected_policy_revision": -1})
    with expect_error(ErrorCode.INVALID_INPUT):
        service.commit_claim(normal, forged)
