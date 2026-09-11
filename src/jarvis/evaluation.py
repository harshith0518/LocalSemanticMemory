"""Repeated live extraction evidence, explicitly ungraded until semantic review."""

from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from jarvis.errors import ApplicationError, ErrorCode
from jarvis.worker import process_one


def extraction_pilot(service, *, repeats=3):
    context = service.identity.context("normal")
    service._provider_gate(context)
    if not service.extractor.live or repeats not in {1, 2, 3}:
        raise ApplicationError(ErrorCode.INVALID_INPUT)
    data = Path("data/synthetic/sample-dictations.jsonl").read_bytes()
    run_id = str(uuid4())
    reports = []
    for repeat in range(1, repeats + 1):
        namespace = f"s07-eval-{run_id}-{repeat}"
        page = service.list_sources(context, {"namespace": namespace})
        service.import_observations(
            context,
            {
                "namespace": namespace,
                "expected_policy_revision": page.policy_revision,
            },
            data,
        )
        service.request_processing(
            context,
            {
                "namespace": namespace,
                "expected_policy_revision": page.policy_revision,
            },
        )
        deadline = monotonic() + 1800
        while monotonic() < deadline:
            status = service.processing_status(context, {"namespace": namespace})
            if not status["counts"].get("pending", 0) and not status["counts"].get("running", 0):
                break
            if process_one(service, context, namespace=namespace) is None:
                sleep(1)
        reports.append(service.processing_report(context, {"namespace": namespace}))
        if any(f["reason"] == "budget_exhausted" for f in reports[-1]["processing"]["failures"]):
            break
    return {
        "kind": "live_extraction",
        "status": "ungraded",
        "semantic_review": "pending",
        "run_id": run_id,
        "fixture_sha256": sha256(data).hexdigest(),
        "requested_repeats": repeats,
        "completed_reports": len(reports),
        "runs": reports,
        "limitations": [
            "Processing success is not semantic correctness.",
            "No response-model, retrieval or stronger-extractor comparison.",
        ],
    }
