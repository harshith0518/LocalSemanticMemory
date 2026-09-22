"""Bounded synthetic HTTP journeys; automatic screens do not certify semantic quality."""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

MAX_RUN_CALLS = 45
LIFETIME_STOP = 1060
MAX_CASE_CALLS = 6  # Two assessment, two extraction and two answer attempts, including repairs.
MAX_STAGE_CALLS = 2
LONG_CAPITAL = (
    "what is the capital of USA ? I just want to know the city and in which state it is present"
)
TEA_FACT = "I prefer tea only when tired."
FIXED_ERRORS = {
    "invalid_input",
    "invalid_mode",
    "private_operation_denied",
    "reference_unavailable",
    "invalid_passage",
    "ineligible_source",
    "stale_revision",
    "import_conflict",
    "database_unavailable",
    "operation_failed",
    "provider_disabled",
    "provider_failed",
    "rate_limited",
    "provider_response_invalid",
    "trial_input_denied",
    "budget_exhausted",
    "context_limit",
    "invalid_transition",
    "retry_limit_reached",
    "excluded_source",
}


def cases():
    public = {
        "retention": "skip",
        "route": "general",
        "status": "general",
        "source_delta": 0,
        "memory_delta": 0,
    }
    capital = {**public, "answer_terms": ["washington"], "district_explanation": True}
    return [
        {"id": "long-capital-1", "question": LONG_CAPITAL, "expected": capital},
        {"id": "us-capital", "question": "What is the capital of the US?", "expected": capital},
        {
            "id": "photosynthesis-to-me",
            "question": "Explain photosynthesis to me in two sentences.",
            "expected": {**public, "answer_terms": ["light"]},
        },
        {
            "id": "project-manager",
            "question": "What does a project manager do? Explain it to me.",
            "expected": public,
        },
        {"id": "joke", "question": "Tell me a joke.", "expected": public},
        {
            "id": "hypothetical-job",
            "question": "Suppose I worked at Acme. What might a project manager do?",
            "expected": {**public, "reason": "hypothetical"},
        },
        {
            "id": "one-response-style",
            "question": "For this answer only, use three bullet points. Explain gravity.",
            "expected": {**public, "reason": "one_off"},
        },
        {
            "id": "conditional-tea",
            "question": TEA_FACT,
            "expected": {
                **public,
                "retention": "candidate",
                "reason": "useful_assertion",
                "source_delta": 1,
                "memory_delta": None,
                "minimum_memory_delta": 1,
                "learning_decision": "extracted",
                "exact_excerpt": TEA_FACT,
            },
        },
        {
            "id": "personal-recall",
            "question": "What do I prefer to drink, and under what condition?",
            "expected": {
                **public,
                "route": "contextual",
                "status": "answered",
                "answer_terms": ["tea", "tired"],
                "citations": True,
            },
        },
        {
            "id": "same-fact-again",
            "question": TEA_FACT,
            "expected": {
                **public,
                "retention": "candidate",
                "reason": "useful_assertion",
                "source_delta": 1,
                "learning_decision": "duplicate",
                "exact_excerpt": TEA_FACT,
            },
        },
        {
            "id": "mixed-recall-public",
            "question": "What do I prefer to drink, and what is caffeine?",
            "expected": {
                **public,
                "route": "mixed",
                "status": "mixed",
                "answer_terms": ["tea", "tired"],
                "general_terms": ["caffeine"],
                "citations": True,
            },
        },
        {
            "id": "new-project-plus-public",
            "question": "I work on the Cedar prototype. What does a project manager do?",
            "expected": {
                **public,
                "retention": "candidate",
                "source_delta": 1,
                "memory_delta": None,
                "minimum_memory_delta": 1,
                "learning_decision": "extracted",
                "exact_excerpt": "I work on the Cedar prototype.",
            },
        },
        {"id": "long-capital-2-after-facts", "question": LONG_CAPITAL, "expected": capital},
        {"id": "long-capital-3-repeat", "question": LONG_CAPITAL, "expected": capital},
    ]


class EvaluationStop(Exception):
    """Fixed reason only; never echo a network/driver exception or response body."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def safe_calls(items):
    fields = (
        "id",
        "status",
        "model",
        "input_tokens",
        "output_tokens",
        "reserved_tokens",
        "elapsed_ms",
        "error_code",
    )
    return (
        [
            {key: item.get(key) for key in fields if key in item}
            for item in items
            if isinstance(item, dict)
        ]
        if isinstance(items, list)
        else []
    )


def safe_error(data):
    reason = data.get("reason") if isinstance(data, dict) else None
    result = {"status": "error", "reason": reason if reason in FIXED_ERRORS else "http_error"}
    if isinstance(data, dict):
        metrics = data.get("metrics") or {}
        result["calls"] = safe_calls(metrics.get("calls", [])) if isinstance(metrics, dict) else []
    return result


class Client:
    def __init__(self, base_url, pace_seconds=8):
        self.pace_seconds = pace_seconds
        self.last_inference_finished = perf_counter()
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, payload=None):
        if payload is not None:
            sleep(max(0, self.pace_seconds - (perf_counter() - self.last_inference_finished)))
        started = perf_counter()
        headers = {"X-Jarvis-Mode": "normal", "Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=body, headers=headers)
        try:
            try:
                response = self.opener.open(request, timeout=180)
            except HTTPError as error:
                response = error
            with response:
                status = response.code
                timing = response.headers.get("Server-Timing", "")
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise EvaluationStop("response_limit")
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                data = {"status": "error", "reason": "invalid_http_json"}
            if not isinstance(data, dict):
                data = {"status": "error", "reason": "invalid_http_shape"}
            if not 200 <= status < 300:
                data = safe_error(data)
            return {
                "http_status": status,
                "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "server_timing": timing,
                "data": data,
            }
        except (URLError, TimeoutError, OSError):
            return {
                "http_status": None,
                "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "server_timing": "",
                "data": {"status": "error", "reason": "transport_unavailable"},
            }

        finally:
            if payload is not None:
                self.last_inference_finished = perf_counter()


def require_ok(result):
    status = result["http_status"]
    if status is None or not 200 <= status < 300 or result["data"].get("status") == "error":
        raise EvaluationStop("read_only_check_failed")
    return result["data"]


def read_usage(client):
    data = require_ok(client.request("/usage"))
    rows = data.get("models")
    if not isinstance(rows, list) or any(type(row.get("attempts")) is not int for row in rows):
        raise EvaluationStop("invalid_usage_shape")
    return {"attempts": sum(row["attempts"] for row in rows), "models": rows}


def collection_state(client, namespace):
    query = "?" + urlencode({"namespace": namespace, "limit": 50})
    sources = require_ok(client.request("/sources" + query))
    memories = require_ok(client.request("/memories" + query))
    if sources.get("next_after") or memories.get("next_after"):
        raise EvaluationStop("collection_exceeds_bounded_snapshot")
    rows = memories.get("memories")
    observations = sources.get("observations")
    if not isinstance(rows, list) or not isinstance(observations, list):
        raise EvaluationStop("invalid_collection_shape")
    return {"sources": len(observations), "memories": len(rows), "memory_rows": rows}


def guard(usage, initial_attempts, allowance, reserve):
    used = usage["attempts"]
    if used < initial_attempts:
        raise EvaluationStop("usage_counter_decreased")
    if used + reserve > min(initial_attempts + allowance, LIFETIME_STOP):
        raise EvaluationStop("bounded_call_allowance_reached")


def summarize_stage(response, kind):
    data = response["data"]
    common = {key: response[key] for key in ("http_status", "elapsed_ms", "server_timing")}
    if data.get("status") == "error":
        return {**common, **data}
    if kind == "answer":
        keys = (
            "status",
            "text",
            "general_text",
            "notice",
            "basis",
            "model",
            "prompt_version",
            "retrieval",
            "evidence_bytes",
            "call_ids",
            "assessment",
            "policy_revision",
        )
        return {
            **common,
            **{key: data.get(key) for key in keys},
            "citations": data.get("citations", []),
            "calls": safe_calls((data.get("metrics") or {}).get("calls", [])),
        }
    keys = (
        "status",
        "source_id",
        "decision",
        "revision_ids",
        "attempts",
        "error_code",
        "assessment_id",
        "assessment",
    )
    return {
        **common,
        **{key: data.get(key) for key in keys},
        "calls": safe_calls(data.get("calls", [])),
    }


def check_case(case, before, after, capture, learning, answer):
    expected = case["expected"]
    decision = (capture.get("assessment") or {}).get("decision") or {}
    checks = {}

    def equal(name, actual, wanted):
        checks[name] = {"passed": actual == wanted, "expected": wanted, "actual": actual}

    for field in ("retention", "route", "reason"):
        if field in expected:
            equal(field, decision.get(field), expected[field])
    equal("answer_status", answer.get("status"), expected["status"])
    equal("source_delta", after["sources"] - before["sources"], expected["source_delta"])
    memory_delta = after["memories"] - before["memories"]
    if expected["memory_delta"] is not None:
        equal("active_memory_delta", memory_delta, expected["memory_delta"])
    if "minimum_memory_delta" in expected:
        checks["minimum_active_memory_delta"] = {
            "passed": memory_delta >= expected["minimum_memory_delta"],
            "expected_minimum": expected["minimum_memory_delta"],
            "actual": memory_delta,
        }
    if "learning_decision" in expected:
        equal("learning_decision", (learning or {}).get("decision"), expected["learning_decision"])
    if "exact_excerpt" in expected:
        equal(
            "qualifier_preserved_in_selection",
            expected["exact_excerpt"] in decision.get("memory_excerpts", []),
            True,
        )
    if expected["route"] == "general":
        equal(
            "no_workspace_sources_sent", (answer.get("retrieval") or {}).get("sources_reviewed"), 0
        )
        equal(
            "no_workspace_memories_sent",
            (answer.get("retrieval") or {}).get("memories_reviewed"),
            0,
        )
    if expected.get("citations"):
        equal("personal_answer_has_citation", bool(answer.get("citations")), True)
    for field, terms in (
        ("text", expected.get("answer_terms", [])),
        ("general_text", expected.get("general_terms", [])),
    ):
        value = (answer.get(field) or "").casefold()
        for term in terms:
            equal(f"{field}_contains_{term}", term.casefold() in value, True)
    if expected.get("district_explanation"):
        value = (answer.get("text") or "").casefold()
        equal(
            "district_or_nonstate_explanation",
            "district" in value or bool(re.search(r"not.{0,40}state", value)),
            True,
        )
    return checks


def rate_limited(stage):
    assessment = stage.get("assessment") or {}
    return (
        stage.get("http_status") == 429
        or stage.get("reason") == "rate_limited"
        or stage.get("error_code") == "rate_limited"
        or assessment.get("error_code") == "rate_limited"
    )


def operational_failure(item):
    capture = item.get("capture") or {}
    assessment = capture.get("assessment") or {}
    learning = item.get("learning") or {}
    answer = item.get("answer") or {}
    return (
        assessment.get("status") != "ready"
        or bool(capture.get("error_code"))
        or learning.get("status") in {"failed", "pending", "running"}
        or bool(learning.get("error_code"))
        or answer.get("status") in {None, "error", "not_attempted"}
    )


def load_retry_report(path):
    if path.stat().st_size > 4_000_000:
        raise EvaluationStop("retry_report_too_large")
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(report, dict) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", report.get("namespace", "")
    ):
        raise EvaluationStop("invalid_retry_report")
    UUID(report["conversation_id"])
    frozen = {case["id"]: case for case in cases()}
    previous = {}
    for item in report["cases"]:
        identifier = item["id"]
        if identifier in previous or identifier not in frozen:
            raise EvaluationStop("invalid_retry_case")
        if item["question"] != frozen[identifier]["question"]:
            raise EvaluationStop("retry_requires_original_synthetic_questions")
        UUID(item["message_id"])
        previous[identifier] = item
    completed = set(report.get("completed_case_ids", []))
    if not completed.issubset(frozen):
        raise EvaluationStop("invalid_completed_case")
    selected = []
    for case in cases():
        item = previous.get(case["id"])
        if (item is None and case["id"] not in completed) or (
            item is not None and operational_failure(item)
        ):
            selected.append({**case, "previous_attempt": item})
    return report, selected


def resume_failed(client, previous, selected, allowance):
    return run(client, previous["namespace"], allowance, previous=previous, selected=selected)


def run(client, namespace, allowance, *, previous=None, selected=None):
    planned = cases() if selected is None else selected
    report = {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "base_url": client.base_url,
        "namespace": namespace,
        "scope": (
            "Curated synthetic persona facts and public questions only; "
            "no reset, deletion or provider fallback."
        ),
        "planned_cases": len(planned),
        "nominal_model_calls": sum(
            2 + (case["expected"]["retention"] == "candidate") for case in planned
        ),
        "pacing_seconds": getattr(client, "pace_seconds", 8),
        "explicit_retry": previous is not None,
        "maximum_additional_model_calls": allowance,
        "lifetime_stop": LIFETIME_STOP,
        "shared_lifetime_ceiling": 1100,
        "reserved_demo_calls": 30,
        "automatic_checks": (
            "Contract/count/term screens only; not an independent semantic-quality score. "
            "Inspect all answer text, qualifications, citations and learned content."
        ),
        "semantic_review": "pending",
        "cases": [],
        "concurrency_limit": (
            "Run as the only evaluation client. Usage guards include all owner models; unrelated "
            "concurrent calls count conservatively against this run and remain possible "
            "between HTTP requests."
        ),
    }
    try:
        state = collection_state(client, namespace)
        if previous is None and (state["sources"] or state["memories"]):
            raise EvaluationStop("namespace_must_be_fresh")
        initial = read_usage(client)
        report["usage_before"] = initial
        report["collection_before"] = {key: state[key] for key in ("sources", "memories")}
        conversation_id = previous["conversation_id"] if previous else str(uuid4())
        report["conversation_id"] = conversation_id
        if previous:
            report["prior_run"] = {
                key: previous.get(key)
                for key in (
                    "started_at",
                    "finished_at",
                    "status",
                    "stop_reason",
                    "additional_model_calls",
                )
            }
        for case in planned:
            usage = read_usage(client)
            guard(usage, initial["attempts"], allowance, MAX_CASE_CALLS)
            before = state
            item = {
                **case,
                "message_id": (case.get("previous_attempt") or {}).get("message_id", str(uuid4())),
                "usage_before_attempts": usage["attempts"],
                "counts_before": {key: before[key] for key in ("sources", "memories")},
            }
            report["cases"].append(item)
            request = {
                "namespace": namespace,
                "question": case["question"],
                "representation": "auto",
                "timezone": "Asia/Kolkata",
            }
            response = client.request(
                "/conversation/messages",
                {
                    "message_id": item["message_id"],
                    "conversation_id": conversation_id,
                    "request": request,
                    "retry_failed": previous is not None,
                },
            )
            capture = summarize_stage(response, "capture")
            item["capture"] = capture
            if rate_limited(capture):
                raise EvaluationStop("rate_limited_stop_batch")
            if response["http_status"] is None:
                raise EvaluationStop("capture_transport_outcome_unconfirmed")
            learning, answer = None, {"status": "not_attempted"}
            assessment = capture.get("assessment") or {}
            if assessment.get("status") == "ready":
                assessment_id = str(UUID(capture["assessment_id"]))
                request["assessment_id"] = assessment_id
                if capture.get("source_id"):
                    source_id = str(UUID(capture["source_id"]))
                    guard(read_usage(client), initial["attempts"], allowance, MAX_STAGE_CALLS)
                    learning = summarize_stage(
                        client.request(
                            f"/conversation/messages/{source_id}/learn",
                            {"retry_failed": previous is not None},
                        ),
                        "learning",
                    )
                    item["learning"] = learning
                    if rate_limited(learning):
                        raise EvaluationStop("rate_limited_stop_batch")
                guard(read_usage(client), initial["attempts"], allowance, MAX_STAGE_CALLS)
                answer = summarize_stage(client.request("/ask", request), "answer")
            item["answer"] = answer
            if rate_limited(answer):
                raise EvaluationStop("rate_limited_stop_batch")
            state = collection_state(client, namespace)
            item["counts_after"] = {key: state[key] for key in ("sources", "memories")}
            prior = {row["id"] for row in before["memory_rows"]}
            item["new_or_revised_memories"] = [
                row for row in state["memory_rows"] if row["id"] not in prior
            ]
            screen_case = case
            prior_attempt = case.get("previous_attempt") or {}
            if prior_attempt:
                expectations = {**case["expected"]}
                if (prior_attempt.get("capture") or {}).get("source_id"):
                    expectations["source_delta"] = 0
                if (prior_attempt.get("learning") or {}).get("status") == "succeeded":
                    expectations["memory_delta"] = 0
                    expectations.pop("minimum_memory_delta", None)
                item["resume_expected"] = expectations
                screen_case = {**case, "expected": expectations}
            item["checks"] = check_case(screen_case, before, state, capture, learning, answer)
            item["all_automatic_screens_passed"] = all(
                check["passed"] for check in item["checks"].values()
            )
        report["status"] = "completed"
    except EvaluationStop as error:
        report["status"], report["stop_reason"] = "incomplete", error.args[0]
    except (KeyError, TypeError, ValueError):
        report["status"], report["stop_reason"] = "incomplete", "unexpected_application_shape"
    if report["cases"] and "counts_after" not in report["cases"][-1]:
        try:
            state = collection_state(client, namespace)
            report["cases"][-1]["counts_after"] = {
                key: state[key] for key in ("sources", "memories")
            }
        except EvaluationStop:
            report["final_collection_error"] = "read_only_check_failed"
    completed = set(previous.get("completed_case_ids", [])) if previous else set()
    if previous:
        completed.update(item["id"] for item in previous["cases"] if not operational_failure(item))
    completed.update(item["id"] for item in report["cases"] if not operational_failure(item))
    report["completed_case_ids"] = sorted(completed)
    if "usage_before" in report:
        try:
            final_usage = read_usage(client)
            report["usage_after"] = final_usage
            report["additional_model_calls"] = (
                final_usage["attempts"] - report["usage_before"]["attempts"]
            )
        except EvaluationStop:
            report["final_usage_error"] = "read_only_check_failed"
    if "state" in locals():
        report["collection_after"] = {key: state[key] for key in ("sources", "memories")}
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["automatic_screen_failures"] = [
        item["id"]
        for item in report["cases"]
        if not item.get("all_automatic_screens_passed", False)
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument(
        "--namespace",
        default="semantic-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8],
    )
    parser.add_argument("--max-calls", type=int, default=MAX_RUN_CALLS)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--retry-report",
        type=Path,
        help="Explicitly retry failed or unattempted cases from an immutable prior report.",
    )
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=8,
        help="Delay after each inference stage, in evaluator only (default: 8 seconds).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the fixed plan without any HTTP or model requests.",
    )
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        parser.error("Use an HTTP(S) origin without credentials, query parameters or a path")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", args.namespace):
        parser.error("Use a valid fresh namespace of at most 96 characters")
    if not 1 <= args.max_calls <= MAX_RUN_CALLS:
        parser.error("The model-call allowance must be between 1 and 45")
    if args.output and (args.output.exists() or not args.output.parent.is_dir()):
        parser.error(
            "Choose a new output file in an existing directory; reports are never overwritten"
        )
    if not 0 <= args.pace_seconds <= 60:
        parser.error("Pacing must be between zero and 60 seconds")
    previous, selected = None, cases()
    if args.retry_report:
        try:
            previous, selected = load_retry_report(args.retry_report)
        except (OSError, ValueError, KeyError, TypeError, EvaluationStop):
            parser.error(
                "The retry report must contain the original bounded synthetic cases and IDs"
            )
        args.namespace = previous["namespace"]
    if args.dry_run:
        report = {
            "status": "dry_run",
            "namespace": args.namespace,
            "planned_cases": len(selected),
            "maximum_additional_model_calls": args.max_calls,
            "lifetime_stop": LIFETIME_STOP,
            "pacing_seconds": args.pace_seconds,
            "explicit_retry": previous is not None,
            "cases": selected,
        }
    else:
        client = Client(args.base_url, pace_seconds=args.pace_seconds)
        report = (
            resume_failed(client, previous, selected, args.max_calls)
            if previous
            else run(client, args.namespace, args.max_calls)
        )
        if args.retry_report:
            report["retry_report"] = str(args.retry_report)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return (
        0
        if report["status"] in {"dry_run", "completed"}
        and not report.get("automatic_screen_failures")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
