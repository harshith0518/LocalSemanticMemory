"""Complete, explicit synthetic pipeline. JSONL retains failures; screens are not truth scores."""

import argparse
import json
import resource
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter, sleep

from sqlalchemy import select, text

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.imports import parse_dictations
from jarvis.metrics import capture_timings
from jarvis.models import Job, ModelBudget, Source
from jarvis.providers import BUDGET_KEY, MAX_REQUESTS
from jarvis.services import Service
from jarvis.worker import process_one

SOURCE = Path("data/synthetic/corpus-540.jsonl")
CASES = Path("eval/fixtures/corpus-cases.json")
MANIFEST = Path("eval/fixtures/corpus-manifest.json")


def emit(event, **fields):
    print(
        json.dumps(
            {"event": event, "at": datetime.now(UTC).isoformat(), **fields},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def validate():
    payload = SOURCE.read_bytes()
    parsed = parse_dictations("validation", payload)
    records = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    manifest, cases = json.loads(MANIFEST.read_text()), json.loads(CASES.read_text())["cases"]
    assert len(parsed) == len(records) == manifest["records"] == 540
    assert sha256(payload).hexdigest() == manifest["source_sha256"]
    ids = {r["record_id"]: r for r in records}
    assert len(ids) == len(records)
    assert len({r["raw_transcript"] for r in records}) == len(records)
    assert all(r["raw_transcript"].strip() and r["formatted_text"].strip() for r in records)
    assert all(
        set(r) == {"record_id", "raw_transcript", "formatted_text", "metadata"} for r in records
    )
    assert len({c["case_id"] for c in cases}) == len(cases)
    assert len({c["request"] for c in cases}) == len(cases)
    for case in cases:
        assert 0 < len(case["request"]) <= 512
        for evidence in case["required_evidence"]:
            row = ids[evidence["record_id"]]
            variant = "raw_transcript" if evidence["variant"] == "raw" else "formatted_text"
            assert evidence["exact_text"] in row[variant]
    assert Counter(c["split"] for c in cases)["showcase"] == 30
    assert Counter(c["split"] for c in cases)["held_out"] == 30
    return payload, records, manifest, cases


def screen(case, answer):
    """Conservative mechanical obligations; no LLM judge or claimed semantic entailment."""
    required = {e["record_id"] for e in case["required_evidence"]}
    source_ids = {s["id"]: s["source_key"].split(":")[-1] for s in answer["sources"]}
    retrieved = set(source_ids.values())
    cited = {source_ids.get(p["source_id"]) for p in answer["citations"]}
    text_value = answer["text"].casefold()
    checks = [
        any(term.casefold() in text_value for term in choices) for choices in case["answer_checks"]
    ]
    status_ok = answer["status"] == case["expected_status"]
    retrieval_ok = required <= retrieved
    citations_ok = required <= cited if answer["status"] != "unknown" else True
    if case["category"] == "variant-conflict":
        variants = {(source_ids.get(p["source_id"]), p["variant"]) for p in answer["citations"]}
        citations_ok = all(
            (e["record_id"], e["variant"]) in variants for e in case["required_evidence"]
        )
    return {
        "status_matches": status_ok,
        "required_sources_retrieved": retrieval_ok,
        "required_sources_cited": citations_ok,
        "answer_anchor_checks": checks,
        "passed_screen": status_ok and retrieval_ok and citations_ok and all(checks),
        "semantic_review": (
            "required; these mechanical checks do not establish entailment or quality"
        ),
    }


def storage(engine):
    with engine.connect() as connection:
        return {
            "database_bytes": connection.scalar(
                text("SELECT pg_database_size(current_database())")
            ),
            "relation_bytes": {
                name: connection.scalar(text(f"SELECT pg_total_relation_size('jarvis.{name}')"))
                for name in (
                    "sources",
                    "claim_revisions",
                    "passages",
                    "claim_evidence",
                    "jobs",
                    "model_calls",
                )
            },
            "scope": ("whole DB/relations including other owners, not per-corpus allocation"),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=("validate", "extract", "answers", "all"), default="validate"
    )
    parser.add_argument("--namespace", default="corpus-evaluation")
    parser.add_argument("--max-jobs", type=int, default=540)
    parser.add_argument("--max-new-calls", type=int, default=MAX_REQUESTS)
    parser.add_argument("--case-limit", type=int, default=60)
    parser.add_argument(
        "--split", choices=("showcase", "held_out", "development", "review"), default="review"
    )
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument(
        "--representations", choices=("sources", "sources_and_memories", "both"), default="both"
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--min-call-interval", type=float, default=0)
    parser.add_argument("--deadline-seconds", type=int, default=3600)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--stop-on-provider-failure", action="store_true")
    args = parser.parse_args()
    if (
        not 0 <= args.min_call_interval <= 60
        or not 1 <= args.deadline_seconds <= 7200
        or not 1 <= args.timeout_seconds <= 180
    ):
        parser.error("Invalid pacing or timebox")
    if (
        not 0 <= args.max_jobs <= 540
        or not 1 <= args.max_new_calls <= MAX_REQUESTS
        or args.case_limit < 0
    ):
        parser.error("Invalid bounded work allowance")
    payload, records, manifest, cases = validate()
    emit(
        "corpus_validation",
        records=len(records),
        cases=len(cases),
        splits=manifest["splits"],
        source_sha256=sha256(payload).hexdigest(),
        cases_sha256=sha256(CASES.read_bytes()).hexdigest(),
    )
    if args.stage == "validate":
        return
    engine = make_engine(Settings.from_env())
    service = Service(engine)
    context = service.identity.context("normal")
    started = perf_counter()
    before_calls = service.model_call_report(context)
    with engine.connect() as connection:
        used = (
            connection.scalar(select(ModelBudget.requests).where(ModelBudget.key == BUDGET_KEY))
            or 0
        )
    ceiling = min(
        MAX_REQUESTS,
        service.extractor.max_requests,
        service.responder.max_requests,
        used + args.max_new_calls,
    )
    service.extractor.max_requests = min(service.extractor.max_requests, ceiling)
    service.responder.max_requests = min(service.responder.max_requests, ceiling)
    last_call = [0.0]

    def paced(complete):
        def run(body):
            sleep(max(0, args.min_call_interval - (perf_counter() - last_call[0])))
            last_call[0] = perf_counter()
            return complete(body)

        return run

    for provider in (service.extractor, service.responder):
        provider.complete = paced(provider.complete)
        provider.timeout_seconds = args.timeout_seconds
    before_storage = storage(engine)
    emit(
        "run_start",
        namespace=args.namespace,
        stage=args.stage,
        max_jobs=args.max_jobs,
        effective_lifetime_request_ceiling=ceiling,
        extractor=service.extractor.model,
        responder=service.responder.model,
        repeats=args.repeats,
        learning_prompt="s11-v3-qualified-context",
        evidence_bytes=24000,
        paid_spend_authorized_usd=0,
        actual_provider_bill=None,
        min_call_interval_seconds=args.min_call_interval,
        deadline_seconds=args.deadline_seconds,
        provider_timeout_seconds=args.timeout_seconds,
        limits="Synthetic templates; authored screening labels, no independent semantic judge.",
    )
    attempts, outcomes = [], Counter()
    try:
        if args.stage in {"extract", "all"}:
            service._provider_gate(context)
            page = service.list_sources(context, {"namespace": args.namespace})
            options = {
                "namespace": args.namespace,
                "expected_policy_revision": page.policy_revision,
            }
            receipt = service.import_observations(context, options, payload)
            emit("import", receipt=receipt.model_dump(mode="json"))
            queued = service.request_processing(
                context, {**options, "retry_failed": args.retry_failed}
            )
            emit("queue", result=queued)
            index = -1
            while index + 1 < args.max_jobs:
                if perf_counter() - started >= args.deadline_seconds:
                    emit("deadline_stop", reason="Stop new work and preserve handoff time")
                    break
                with capture_timings() as timings:
                    result = process_one(service, context, namespace=args.namespace)
                if result is None:
                    status = service.processing_status(context, {"namespace": args.namespace})
                    if status["counts"].get("pending", 0) or status["counts"].get("running", 0):
                        sleep(2)  # A different worker or an interrupted lease still owns the guard.
                        continue
                index += 1
                emit("processing_attempt", index=index + 1, result=result, timings=timings)
                if (
                    args.stop_on_provider_failure
                    and result
                    and result.get("reason") == "provider_failed"
                ):
                    emit(
                        "provider_stop",
                        reason="No retry storm after an operational provider failure",
                    )
                    break
                if result:
                    outcomes[result.get("decision", result.get("reason", "failed"))] += 1
                if (
                    (index + 1) % 10 == 0
                    or result is None
                    or (result and result.get("status") == "failed")
                ):
                    status = service.processing_status(context, {"namespace": args.namespace})
                    emit(
                        "progress",
                        attempted=index + 1,
                        counts=status["counts"],
                        decisions=status["decisions"],
                    )
                    if not status["counts"].get("pending", 0) and not status["counts"].get(
                        "running", 0
                    ):
                        break
                if result and result.get("reason") in {"budget_exhausted", "rate_limited"}:
                    break
        if args.stage in {"answers", "all"}:
            selected = [
                c
                for c in cases
                if c["split"] == args.split
                or args.split == "review"
                and c["split"] in {"showcase", "held_out"}
            ][: args.case_limit]
            representations = (
                ["sources", "sources_and_memories"]
                if args.representations == "both"
                else [args.representations]
            )
            exhausted = False
            for repeat in range(1, args.repeats + 1):
                for index, case in enumerate(selected):
                    order = (
                        representations if (index + repeat) % 2 else list(reversed(representations))
                    )
                    for representation in order:
                        item = {
                            "case_id": case["case_id"],
                            "split": case["split"],
                            "category": case["category"],
                            "question": case["request"],
                            "representation": representation,
                            "repeat": repeat,
                        }
                        try:
                            with capture_timings() as timings:
                                answer = service.ask(
                                    context,
                                    {
                                        "namespace": args.namespace,
                                        "question": case["request"],
                                        "representation": representation,
                                    },
                                )
                            item.update(answer=answer, screen=screen(case, answer), timings=timings)
                        except ApplicationError as error:
                            item.update(error=error.code.value, timings=timings)
                            exhausted = error.code.value in {"budget_exhausted", "rate_limited"}
                        attempts.append(item)
                        emit("answer", **item)
                        if exhausted:
                            break
                    if exhausted:
                        break
                if exhausted:
                    break
    except ApplicationError as error:
        emit("failure", reason=error.code.value)
    finally:
        # Every original and its terminal/pending job state remains inspectable, including
        # jobs that failed before any model call. No result silently disappears from totals.
        with service._session(context) as session:
            originals = session.scalars(
                service._namespace_sources(context, args.namespace).order_by(Source.source_key)
            ).all()
            jobs = {
                j.source_id: j
                for j in session.scalars(
                    select(Job).where(
                        Job.owner_id == context.owner_id,
                        Job.source_id.in_([s.id for s in originals]),
                    )
                ).all()
            }
            for original in originals:
                job = jobs.get(original.id)
                emit(
                    "source_state",
                    record_id=original.source_key.split(":")[-1],
                    original=service._source_contract(original).model_dump(mode="json"),
                    job={
                        "id": job.id,
                        "status": job.status,
                        "error": job.error_code,
                        "attempts": job.attempts,
                    }
                    if job
                    else None,
                )
        report = service.processing_report(context, {"namespace": args.namespace})
        emit("memory_state", report=report)
        old_ids = {c["id"] for c in before_calls}
        calls = [c for c in service.model_call_report(context) if c["id"] not in old_ids]
        if args.stage == "extract":
            scoped_jobs = {job.id for job in jobs.values()}
            calls = [call for call in calls if call["job_id"] in scoped_jobs]
        known = [
            c for c in calls if c["input_tokens"] is not None and c["output_tokens"] is not None
        ]
        accounting = {
            "new_requests": len(calls),
            "known_input_tokens": sum(c["input_tokens"] for c in known),
            "known_output_tokens": sum(c["output_tokens"] for c in known),
            "unknown_usage_calls": len(calls) - len(known),
            "accounted_tokens": sum(
                c["input_tokens"] + c["output_tokens"] if c in known else c["reserved_tokens"]
                for c in calls
            ),
            "calls": calls,
            "actual_cost_usd": None,
            "paid_spend_authorized_usd": 0,
        }
        emit("accounting", **accounting)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        emit(
            "summary",
            source_count=len(originals),
            processing=report["processing"],
            extraction_attempt_outcomes=dict(outcomes),
            answer_attempts=len(attempts),
            answer_operational_failures=sum("error" in a for a in attempts),
            answer_screens_passed=sum(
                a.get("screen", {}).get("passed_screen", False) for a in attempts
            ),
            semantic_review="pending; inspect actual answers/memories, not just screen counts",
            elapsed_seconds=round(perf_counter() - started, 3),
            storage_before=before_storage,
            storage_after=storage(engine),
            process_peak_rss_kib=usage.ru_maxrss,
            process_cpu_seconds=usage.ru_utime + usage.ru_stime,
            new_requests=len(calls),
        )
        engine.dispose()


if __name__ == "__main__":
    main()
