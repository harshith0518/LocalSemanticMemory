"""Thirty frozen functional cases; provider attempts are scoped to this evaluator instance."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

from corpus import emit, screen, validate

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.metrics import capture_timings
from jarvis.providers import NvidiaResponder
from jarvis.services import Service


class MeasuredResponder:
    def __init__(self, provider):
        self.provider = provider
        self.attempts = []
        self.started = 0.0
        self.reservation = 0

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def prepare(self, packet, *, repair=False):
        if len(self.attempts) >= 40:
            raise ApplicationError(ErrorCode.BUDGET_EXHAUSTED)
        body, self.reservation = self.provider.prepare(packet, repair=repair)
        return body, self.reservation

    def complete(self, body):
        sleep(max(0, 6.1 - (monotonic() - self.started)))
        self.started = monotonic()
        item = {"reserved_tokens": self.reservation, "model": self.provider.model}
        self.attempts.append(item)
        try:
            result = self.provider.complete(body)
            item.update(
                transport_completion=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                elapsed_ms=result.elapsed_ms,
            )
            return result
        except ApplicationError as error:
            item.update(
                transport_completion=False,
                error=error.code.value,
                input_tokens=None,
                output_tokens=None,
                elapsed_ms=round((monotonic() - self.started) * 1000),
            )
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="corpus-540-20260912")
    parser.add_argument(
        "--report",
        choices=("s14-showcase-review.json", "s15-showcase-review.json"),
        default="s15-showcase-review.json",
    )
    args = parser.parse_args()
    _, _, manifest, cases = validate()
    cases = [case for case in cases if case["split"] == "showcase"]
    engine = make_engine(Settings.from_env())
    provider = NvidiaResponder.from_env()
    provider.max_requests = min(1070, provider.max_requests)
    provider.timeout_seconds = 30
    measured = MeasuredResponder(provider)
    service = Service(engine, responder=measured)
    context = service.identity.context("normal")
    started = monotonic()
    report = {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "namespace": args.namespace,
        "model": provider.model,
        "representation": "sources_and_memories",
        "source_sha256": manifest["source_sha256"],
        "planned_cases": 30,
        "repeats": 1,
        "maximum_evaluator_requests": 40,
        "effective_lifetime_request_ceiling": provider.max_requests,
        "timeout_seconds": 30,
        "paid_authorized_usd": 0,
        "actual_cost_usd": None,
        "semantic_review": "pending; anchor/citation screens are not semantic certification",
        "limits": (
            "Functional showcase during ingestion, not a frozen-state A/B benchmark. "
            "Each answer retains its actual released evidence. Collection-wide processing "
            "can change between cases. No prompts or personal data from other callers "
            "are collected."
        ),
        "processing_before": service.processing_status(context, {"namespace": args.namespace}),
        "cases": [],
    }
    try:
        for case in cases:
            first = len(measured.attempts)
            entry = {key: case[key] for key in ("case_id", "title", "category", "request")}
            entry["required_evidence"] = case["required_evidence"]
            try:
                with capture_timings() as timings:
                    answer = service.ask(
                        context,
                        {
                            "namespace": args.namespace,
                            "question": case["request"],
                            "representation": "sources_and_memories",
                        },
                    )
                entry.update(answer=answer, screen=screen(case, answer), timings=timings)
            except ApplicationError as error:
                entry.update(error=error.code.value)
            entry["provider_attempts"] = measured.attempts[first:]
            report["cases"].append(entry)
            emit("showcase_case", **entry)
            if entry.get("error") in {"budget_exhausted", "rate_limited"}:
                break
            if monotonic() - started > 1500:
                report["stop_reason"] = "25-minute showcase timebox"
                break
    finally:
        completed = {case["case_id"] for case in report["cases"]}
        report.update(
            status="completed" if len(completed) == 30 else "partial",
            finished_at=datetime.now(UTC).isoformat(),
            elapsed_seconds=round(monotonic() - started, 3),
            evaluated_cases=len(completed),
            unassessed=[case["case_id"] for case in cases if case["case_id"] not in completed],
            operational_failures=sum("error" in case for case in report["cases"]),
            mechanical_screens_passed=sum(
                case.get("screen", {}).get("passed_screen", False) for case in report["cases"]
            ),
            provider_requests=len(measured.attempts),
            known_input_tokens=sum(call.get("input_tokens") or 0 for call in measured.attempts),
            known_output_tokens=sum(call.get("output_tokens") or 0 for call in measured.attempts),
            unknown_usage_calls=sum(call.get("input_tokens") is None for call in measured.attempts),
            unknown_usage_reserved_tokens=sum(
                call["reserved_tokens"]
                for call in measured.attempts
                if call.get("input_tokens") is None
            ),
            processing_after=service.processing_status(context, {"namespace": args.namespace}),
            storage_trace=service.processing_report(context, {"namespace": args.namespace}),
        )
        (Path("eval/reports") / args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
        emit(
            "showcase_summary",
            **{
                key: value for key, value in report.items() if key not in {"cases", "storage_trace"}
            },
        )
        engine.dispose()


if __name__ == "__main__":
    main()
