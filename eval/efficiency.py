"""Isolated synthetic workflow measurements. Model doubles are NOT a quality benchmark."""

import argparse
import json
import os
import resource
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from uuid import uuid4

from sqlalchemy import text

from jarvis.answers import trial_questions
from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.metrics import capture_timings
from jarvis.policy import LocalIdentity
from jarvis.services import Service
from jarvis.worker import process_one


def physical_storage(engine):
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
            SELECT relname AS relation,
                   pg_table_size(relid) AS table_bytes,
                   pg_indexes_size(relid) AS index_bytes,
                   pg_total_relation_size(relid) AS total_bytes
            FROM pg_catalog.pg_statio_user_tables
            WHERE schemaname = 'jarvis' ORDER BY relname
        """)
            )
            .mappings()
            .all()
        )
        return {
            "database_bytes": connection.scalar(
                text("SELECT pg_database_size(current_database())")
            ),
            "relations": [dict(row) for row in rows],
        }


def run():
    # Validate before importing doubles, connecting, reading sources or writing an artifact.
    settings = Settings.from_env()
    settings.require_test_database()
    from tests.answer_double import FixtureResponder
    from tests.memory_double import FixtureExtractor

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = make_engine(settings)
    service = Service(
        engine, LocalIdentity(uuid4()), extractor=FixtureExtractor(), responder=FixtureResponder()
    )
    context = service.identity.context("normal")
    fixture = Path("data/synthetic/sample-dictations.jsonl").read_bytes()
    namespace = "s10-efficiency"
    records = []

    def measure(name, operation):
        started, cpu = perf_counter(), process_time()
        with capture_timings() as stages:
            result = operation()
        records.append(
            {
                "operation": name,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "process_cpu_ms": round((process_time() - cpu) * 1000, 3),
                "process_rss_bytes_after": int(Path("/proc/self/statm").read_text().split()[1])
                * os.sysconf("SC_PAGE_SIZE"),
                "process_peak_rss_bytes_so_far": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * 1024,
                "stages": stages,
            }
        )
        return result

    try:
        if service.ready()["status"] != "ready":
            raise RuntimeError("Run the isolated migrations/tests first")
        before = physical_storage(engine)
        empty = service.usage_snapshot(context)
        measure(
            "import_8",
            lambda: service.import_observations(
                context, {"namespace": namespace, "expected_policy_revision": 0}, fixture
            ),
        )
        measure(
            "queue",
            lambda: service.request_processing(
                context, {"namespace": namespace, "expected_policy_revision": 0}
            ),
        )
        outcomes = [
            measure("process_one", lambda: process_one(service, context, namespace=namespace))
            for _ in range(8)
        ]
        searches = []
        for representation in ("sources", "sources_and_memories"):
            for _ in range(3):
                result = measure(
                    "search_" + representation,
                    lambda representation=representation: service.search(
                        context,
                        {
                            "namespace": namespace,
                            "query": "Atlas launch date",
                            "representation": representation,
                        },
                    ),
                )
                searches.append(
                    {
                        "representation": representation,
                        "matches": len(result["matches"]),
                        "evidence_bytes": result["evidence_bytes"],
                    }
                )
        answer = measure(
            "ask_contract_double",
            lambda: service.ask(
                context, {"namespace": namespace, "question": trial_questions()[0]}
            ),
        )
        after = physical_storage(engine)
        report = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "kind": "isolated_postgresql_application_measurement_with_model_doubles",
            "semantic_accuracy_measured": False,
            "limitations": [
                "Provider token counts and provider latency in doubles are fixture constants.",
                "Wall time/CPU/RSS measure the evaluator process, not API or remote model RAM.",
                "Peak RSS is cumulative; CPU excludes PostgreSQL and remote inference.",
                "Physical allocation covers the isolated DB, including preexisting test state.",
                "Payload bytes, allocated disk and resident memory are different quantities.",
                "Stage timings include nested work and must not be summed as disjoint phases.",
                "No labeled semantic grades, compression gains or measured billing are claimed.",
            ],
            "source_sha256": sha256(fixture).hexdigest(),
            "implementation_sha256": {
                str(path): sha256(path.read_bytes()).hexdigest()
                for path in sorted(Path("src").rglob("*"))
                if path.is_file()
            },
            "owner_before": empty,
            "owner_after": service.usage_snapshot(context),
            "physical_before": before,
            "physical_after": after,
            "database_growth_bytes": after["database_bytes"] - before["database_bytes"],
            "operations": records,
            "searches": searches,
            "processing_decisions": [
                result.get("decision", result.get("status")) for result in outcomes
            ],
            "answer_status": answer["status"],
            "citation_count": len(answer["citations"]),
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(args.output),
                    "operations": len(records),
                    "answer_status": answer["status"],
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    run()
