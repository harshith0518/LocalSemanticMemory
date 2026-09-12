"""Explicit synthetic-only live evidence. JSONL output retains failures; grades are separate."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from uuid import uuid4

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.providers import NvidiaExtractor, NvidiaResponder
from jarvis.services import Service
from jarvis.worker import process_one

OUTPUT_LOCK = Lock()


def emit(event, **fields):
    with OUTPUT_LOCK:
        print(
            json.dumps(
                {"event": event, "at": datetime.now(UTC).isoformat(), **fields},
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )


class RecordedProvider:
    """Used only by this explicitly invoked fixture evaluator, never by the running app."""

    def __init__(self, provider, role):
        self.provider, self.role = provider, role

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, body):
        completion = self.provider.complete(body)
        data = json.loads(body["messages"][1]["content"])
        emit(
            "completion",
            role=self.role,
            model=completion.model,
            source_id=data.get("CURRENT_SOURCE", {}).get("id"),
            question=data.get("QUESTION"),
            content=completion.content,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            elapsed_ms=completion.elapsed_ms,
        )
        return completion


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke", "extraction", "answers"), required=True)
    parser.add_argument("--namespace")
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    engine = make_engine(Settings.from_env())
    service = Service(
        engine,
        extractor=RecordedProvider(NvidiaExtractor.from_env(), "extractor"),
        responder=RecordedProvider(NvidiaResponder.from_env(), "responder"),
    )
    context = service.identity.context("normal")
    fixture = Path("data/synthetic/sample-dictations.jsonl").read_bytes()
    cases = json.loads(Path("eval/fixtures/sample-evaluation-cases.json").read_text())["cases"]
    namespace = args.namespace or "live-" + uuid4().hex
    emit(
        "start",
        stage=args.stage,
        namespace=namespace,
        repeats=args.repeats,
        source_sha256=sha256(fixture).hexdigest(),
        semantic_review="pending",
        inference_concurrency=2 if args.stage == "answers" else 1,
        evidence_allowance="24000 UTF-8 bytes; conservative, not tokenizer measurement",
    )
    try:
        if args.stage in {"smoke", "extraction"}:
            service._provider_gate(context)
            for repeat in range(1, (1 if args.stage == "smoke" else args.repeats) + 1):
                collection = namespace if repeat == 1 else f"{namespace}-{repeat}"
                page = service.list_sources(context, {"namespace": collection})
                options = {
                    "namespace": collection,
                    "expected_policy_revision": page.policy_revision,
                }
                service.import_observations(context, options, fixture)
                service.request_processing(context, options)
                for _ in range(1 if args.stage == "smoke" else 8):
                    outcome = process_one(service, context, namespace=collection)
                    emit("extraction", namespace=collection, repeat=repeat, outcome=outcome)
                    if outcome is None or outcome.get("reason") == "budget_exhausted":
                        break
                emit(
                    "extraction_report",
                    repeat=repeat,
                    report=service.processing_report(context, {"namespace": collection}),
                )
        if args.stage in {"smoke", "answers"}:
            if args.stage == "answers" and not args.namespace:
                raise ValueError("Answer comparison requires the frozen live-extraction namespace")
            work = [
                (repeat, case, representation)
                for repeat in range(1, (1 if args.stage == "smoke" else args.repeats) + 1)
                for index, case in enumerate(cases[:1] if args.stage == "smoke" else cases)
                for representation in (
                    ["history"]
                    if args.stage == "smoke"
                    else (
                        ["history", "sources", "sources_and_memories"]
                        if (index + repeat) % 2
                        else ["sources_and_memories", "sources", "history"]
                    )
                )
            ]

            def answer(item):
                repeat, case, representation = item
                try:
                    result = service.ask(
                        context,
                        {
                            "namespace": namespace,
                            "question": case["request"],
                            "representation": representation,
                        },
                    )
                    emit(
                        "answer",
                        repeat=repeat,
                        case_id=case["case_id"],
                        representation=representation,
                        result=result,
                    )
                except ApplicationError as error:
                    emit(
                        "answer",
                        repeat=repeat,
                        case_id=case["case_id"],
                        representation=representation,
                        error=error.code.value,
                    )

            with ThreadPoolExecutor(max_workers=2 if args.stage == "answers" else 1) as pool:
                list(pool.map(answer, work))
    except ApplicationError as error:
        emit("failure", reason=error.code.value)
    finally:
        emit("accounting", calls=service.model_call_report(context), semantic_review="pending")
        engine.dispose()


if __name__ == "__main__":
    run()
