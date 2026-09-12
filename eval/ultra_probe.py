"""Explicit, capped provider diagnostic. Does not change running application selection."""

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from live import RecordedProvider, emit
from sqlalchemy import select

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError
from jarvis.models import ModelBudget
from jarvis.providers import BUDGET_KEY, MODEL, FreeChatProvider, NvidiaExtractor, NvidiaResponder
from jarvis.services import Service
from jarvis.worker import process_one

ULTRA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


class UltraExtractor(NvidiaExtractor):
    """Evaluation-only model; same prompt, transport and limits as Lightning."""

    model = ULTRA_MODEL


class UltraResponder(UltraExtractor):
    def prepare(self, packet, *, repair=False):
        # Use Lightning's exact answer settings without widening the app selector.
        reference = NvidiaResponder(model=MODEL, approved=self.enabled)
        body, reservation = reference.prepare(packet, repair=repair)
        body["model"] = self.model
        return body, reservation


def budget_snapshot(engine):
    with engine.connect() as connection:
        row = connection.execute(
            select(ModelBudget.requests, ModelBudget.tokens).where(ModelBudget.key == BUDGET_KEY)
        ).first()
    return (
        {"requests": row[0], "accounted_tokens": row[1]}
        if row
        else {
            "requests": 0,
            "accounted_tokens": 0,
        }
    )


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approved-ultra-comparison", "--approved-comparison", action="store_true", required=True
    )
    parser.add_argument("--provider", choices=("ultra", "google", "openrouter"), default="ultra")
    parser.add_argument("--max-new-calls", type=int, choices=range(1, 21), default=10)
    args = parser.parse_args()
    if args.provider == "ultra":
        key = os.environ.get("NEMOTRON_550B_API_KEY", "")
        if os.environ.get("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED") != "true" or not key:
            emit("blocked", reason="synthetic_approval_or_ultra_key_missing", calls_made=0)
            return 1
        extractor = UltraExtractor(approved=True, key=key, unfamiliar=False)
        responder = UltraResponder(approved=True, key=key, unfamiliar=False)
    else:
        os.environ["JARVIS_INFERENCE_PROVIDER"] = args.provider
        extractor = FreeChatProvider.from_env(role="extractor")
        responder = FreeChatProvider.from_env(role="responder")
        if not extractor.enabled or not extractor._key:
            emit("blocked", reason="free_synthetic_approval_or_key_missing", calls_made=0)
            return 1
    engine = make_engine(Settings.from_env())
    before = budget_snapshot(engine)
    ceiling = min(
        extractor.max_requests, responder.max_requests, before["requests"] + args.max_new_calls
    )
    extractor.max_requests = responder.max_requests = ceiling
    service = Service(
        engine,
        extractor=RecordedProvider(extractor, "extractor"),
        responder=RecordedProvider(responder, "responder"),
    )
    context = service.identity.context("normal")
    namespace = args.provider + "-probe-" + uuid4().hex
    fixture = Path("data/synthetic/sample-dictations.jsonl").read_bytes()
    cases = json.loads(Path("eval/fixtures/sample-evaluation-cases.json").read_text())["cases"]
    before_ids = {call["id"] for call in service.model_call_report(context)}
    emit(
        "start",
        namespace=namespace,
        model=extractor.model,
        provider=args.provider,
        source_sha256=sha256(fixture).hexdigest(),
        max_new_calls=args.max_new_calls,
        effective_lifetime_request_ceiling=ceiling,
        before=before,
        settings={
            "temperature": 0,
            "max_output_tokens": 4096,
            "thinking": "low" if args.provider == "google" else False,
            "timeout_seconds": extractor.timeout_seconds,
        },
        application_model_changed=False,
        semantic_review="pending; single-run diagnostic, not a benchmark",
    )
    try:
        page = service.list_sources(context, {"namespace": namespace})
        options = {"namespace": namespace, "expected_policy_revision": page.policy_revision}
        imported = service.import_observations(context, options, fixture)
        emit("import", namespace=namespace, result=imported)
        for case in cases:
            if args.provider == "ultra" and case["case_id"] not in {
                "change_with_original_source",
                "grounded_personalized_draft",
            }:
                continue
            if budget_snapshot(engine)["requests"] >= ceiling:
                emit("not_assessed", case_id=case["case_id"], reason="comparison_call_cap")
                continue
            try:
                result = service.ask(
                    context,
                    {
                        "namespace": namespace,
                        "question": case["request"],
                        "representation": "history",
                    },
                )
                emit("answer", case_id=case["case_id"], result=result)
            except ApplicationError as error:
                emit(
                    "answer",
                    case_id=case["case_id"],
                    error=error.code.value,
                    http_status=getattr(responder, "last_http_status", None),
                )
                if args.provider != "ultra" and error.code.value in {
                    "rate_limited",
                    "provider_failed",
                }:
                    emit("stopped", reason="provider_unavailable_no_retry_storm")
                    return 1
        service.request_processing(context, options)
        for index in range(8):
            if budget_snapshot(engine)["requests"] >= ceiling:
                emit("not_assessed", remaining_jobs=8 - index, reason="comparison_call_cap")
                break
            outcome = process_one(service, context, namespace=namespace)
            emit("extraction", ordinal=index + 1, outcome=outcome)
            if outcome is None or outcome.get("reason") in {"budget_exhausted", "rate_limited"}:
                break
        emit("memory_state", report=service.processing_report(context, {"namespace": namespace}))
    except ApplicationError as error:
        emit("failure", reason=error.code.value)
        return 1
    finally:
        calls = [
            call for call in service.model_call_report(context) if call["id"] not in before_ids
        ]
        emit("accounting", calls=calls, before=before, after=budget_snapshot(engine))
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
