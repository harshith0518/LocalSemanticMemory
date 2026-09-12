"""Reproducible isolated retrieval experiment; no live model or semantic grading."""

import json
import sys
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.models import Base
from jarvis.policy import LocalIdentity
from jarvis.retrieval import SEARCH_VERSION
from jarvis.services import Service
from jarvis.worker import process_one


def run():
    settings = Settings.from_env()
    settings.require_test_database()  # Before connecting, importing or constructing a double.
    sys.path.insert(0, str(Path("tests").resolve()))
    from memory_double import FixtureExtractor, passage

    engine = make_engine(settings)
    # A namespace cannot isolate owner-wide exclusions or the browser worker's lease.
    service = Service(engine, LocalIdentity(uuid4()), extractor=FixtureExtractor())
    context = service.identity.context("normal")
    namespace = f"s08-eval-{uuid4()}"
    core_bytes = Path("data/synthetic/sample-dictations.jsonl").read_bytes()
    extra_bytes = Path("tests/fixtures/s08-observations.jsonl").read_bytes()
    labels_bytes = Path("eval/fixtures/s08-retrieval.json").read_bytes()
    labels = json.loads(labels_bytes)
    cases = (
        json.loads(Path("eval/fixtures/sample-evaluation-cases.json").read_text())["cases"]
        + labels["cases"]
    )
    projects = ["Atlas", "Orion", "Cedar", "Maple", "Boreal", "Zephyr", "Lyra"]
    distractors = [
        {
            "record_id": f"noise_{i:04}",
            "raw_transcript": (
                f"In the {projects[i % len(projects)]} archive, inventory card {i:04} lists shelf "
                f"{i % 17} and a sealed box. No project schedule or personal preference "
                "is recorded on this card."
            ),
        }
        for i in range(485)
    ]
    policy = service.list_sources(context, {"namespace": namespace}).policy_revision
    service.import_observations(
        context, {"namespace": namespace, "expected_policy_revision": policy}, core_bytes
    )
    service.request_processing(
        context, {"namespace": namespace, "expected_policy_revision": policy}
    )
    for _ in range(8):
        outcome = process_one(service, context, namespace=namespace)
        if not outcome or outcome.get("decision") != "extracted":
            raise RuntimeError("Deterministic preparation failed")
    service.import_observations(
        context, {"namespace": namespace, "expected_policy_revision": policy}, extra_bytes
    )
    service.import_observations(
        context,
        {"namespace": namespace, "expected_policy_revision": policy},
        "\n".join(json.dumps(row) for row in distractors),
    )
    with Session(engine) as session:
        rows = session.scalars(service._namespace_sources(context, namespace)).all()
        sources = {row.source_key.split(":")[-1]: service._source_contract(row) for row in rows}
    assert len(sources) == 500
    for proposal in labels["deterministic_proposals"]:
        source = sources[proposal["record_id"]]
        service.commit_claim(
            context,
            {
                "expected_policy_revision": policy,
                "content": proposal["content"],
                "passages": [passage(source.model_dump(mode="json"))],
            },
        )
    # Mechanical gold-span checks happen before either candidate is evaluated.
    for case in cases:
        for support in case["required_evidence"]:
            source = sources[support["record_id"]]
            original = (
                source.raw_text if support["field"] == "raw_transcript" else source.formatted_text
            )
            assert original and support["quote"] in original
    measurements = []
    for repeat in range(3):
        # Alternate evaluation order; both methods share the frozen original/claim state.
        representations = ["sources", "sources_and_memories"]
        if repeat % 2:
            representations.reverse()
        for representation in representations:
            for case in cases:
                started = perf_counter()
                result = service.search(
                    context,
                    {
                        "namespace": namespace,
                        "query": case["request"],
                        "representation": representation,
                        "history": True,
                        "limit": 5,
                        "max_bytes": 24000,
                    },
                )
                elapsed = (perf_counter() - started) * 1000
                selected = {row["source_key"].split(":")[-1]: row for row in result["sources"]}
                required = case["required_evidence"]
                covered = sum(
                    support["record_id"] in selected
                    and support["quote"]
                    in (
                        selected[support["record_id"]][
                            "raw_text" if support["field"] == "raw_transcript" else "formatted_text"
                        ]
                        or ""
                    )
                    for support in required
                )
                measurements.append(
                    {
                        "repeat": repeat + 1,
                        "representation": representation,
                        "case_id": case["case_id"],
                        "status": result["status"],
                        "required_passages": len(required),
                        "covered_passages": covered,
                        "all_required_found": covered == len(required) if required else None,
                        "selected_records": list(selected),
                        "evidence_bytes": result["evidence_bytes"],
                        "budget_limited": result["budget_limited"],
                        "elapsed_ms": round(elapsed, 3),
                    }
                )
    summary = {}
    for representation in ("sources", "sources_and_memories"):
        rows = [r for r in measurements if r["representation"] == representation]
        answerable = [r for r in rows if r["required_passages"]]
        times = sorted(r["elapsed_ms"] for r in rows)
        summary[representation] = {
            "attempts": len(rows),
            "answerable_attempts": len(answerable),
            "all_evidence_found": sum(r["all_required_found"] for r in answerable),
            "passage_coverage": sum(r["covered_passages"] for r in rows)
            / sum(r["required_passages"] for r in rows),
            "mean_evidence_bytes": round(mean(r["evidence_bytes"] for r in rows), 2),
            "p50_ms": median(times),
            "p95_ms": times[round((len(times) - 1) * 0.95)],
        }
    with engine.connect() as connection:
        indexes = connection.execute(
            text(
                "SELECT indexname, pg_relation_size((schemaname || '.' || indexname)::regclass) "
                "FROM pg_indexes WHERE schemaname='jarvis' AND indexname IN "
                "('sources_search_idx','claims_search_idx') ORDER BY indexname"
            )
        ).all()
        counts = {
            table.name: connection.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }
    engine.dispose()
    return {
        "kind": "isolated_retrieval_diagnostic",
        "owner_isolation": "fresh synthetic owner per run",
        "search_version": SEARCH_VERSION,
        "corpus_records": 500,
        "cases": len(cases),
        "repeats": 3,
        "core_sha256": sha256(core_bytes).hexdigest(),
        "challenge_sha256": sha256(extra_bytes).hexdigest(),
        "labels_sha256": sha256(labels_bytes).hexdigest(),
        "proposal_origin": "explicit_deterministic_fixtures",
        "live_model_calls": 0,
        "limits": {"primary_sources": 5, "evidence_bytes": 24000, "candidates_per_branch": 100},
        "summary": summary,
        "runs": measurements,
        "index_bytes": dict(indexes),
        "database_rows": counts,
        "limitations": [
            "Authored diagnostics and templated distractors, not a blind/generalization benchmark.",
            "Coverage checks exact gold passages, not semantic entailment or answer correctness.",
            "Repeated retrieval uses frozen deterministic claims; not repeated live extraction.",
            "Evidence budgets count serialized UTF-8 bytes, not model tokens.",
            "Dense retrieval, live Kimi answers and S06 all-history answer comparison not run.",
            "Indexes may be warm; this is not a cold-start or general latency benchmark.",
            "Lifecycle correctness is tested separately; this diagnostic scores retrieval only.",
            "Database row and index totals include other retained isolated test owners.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
