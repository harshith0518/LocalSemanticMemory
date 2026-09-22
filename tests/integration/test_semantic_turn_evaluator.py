"""Evaluator safety contracts: no model call is needed to check its hard boundaries."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location("semantic_turns", Path("eval/semantic_turns.py"))
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


@pytest.mark.parametrize(
    "used,initial,allowance,reserve",
    [(1032, 988, 45, 2), (1055, 1020, 45, 6), (987, 988, 45, 2)],
)
def test_evaluator_preserves_run_and_lifetime_allowances(used, initial, allowance, reserve):
    with pytest.raises(evaluator.EvaluationStop):
        evaluator.guard({"attempts": used}, initial, allowance, reserve)


def test_evaluator_allows_only_calls_fitting_both_bounds():
    evaluator.guard({"attempts": 1031}, 988, 45, 2)
    evaluator.guard({"attempts": 1058}, 1030, 45, 2)


def test_budget_stop_happens_before_capture_or_provider_calls():
    class AlmostExhaustedClient:
        base_url = "http://127.0.0.1:18000"

        def request(self, path, payload=None):
            assert payload is None, "Budget boundary must precede every mutation"
            if path.startswith("/sources"):
                data = {"observations": [], "next_after": None}
            elif path.startswith("/memories"):
                data = {"memories": [], "next_after": None}
            elif path == "/usage":
                data = {"models": [{"attempts": 1059}]}
            else:
                raise AssertionError("Unexpected endpoint")
            return {"http_status": 200, "data": data}

    report = evaluator.run(AlmostExhaustedClient(), "fresh-synthetic", 45)
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "bounded_call_allowance_reached"
    assert report["cases"] == [] and report["additional_model_calls"] == 0


def test_transport_error_report_does_not_copy_raw_error_details():
    result = evaluator.safe_error(
        {
            "reason": "SYNTHETIC_SECRET_RESPONSE",
            "detail": "SYNTHETIC_SECRET_RESPONSE",
            "metrics": {"calls": [{"status": "failed", "elapsed_ms": 10, "raw": "SECRET"}]},
        }
    )
    assert result == {
        "status": "error",
        "reason": "http_error",
        "calls": [{"status": "failed", "elapsed_ms": 10}],
    }


class ScriptedClient:
    base_url = "http://127.0.0.1:18000"

    def __init__(self, limited=False):
        self.limited = limited
        self.posts = []
        self.assessment_id = str(uuid4())

    def request(self, path, payload=None):
        if path.startswith("/sources"):
            data = {"observations": [], "next_after": None}
        elif path.startswith("/memories"):
            data = {"memories": [], "next_after": None}
        elif path == "/usage":
            data = {"models": [{"attempts": 1000 + len(self.posts)}]}
        else:
            self.posts.append((path, payload))
            if path == "/conversation/messages":
                data = {
                    "status": "not_saved",
                    "source_id": None,
                    "assessment_id": self.assessment_id,
                    "assessment": {
                        "status": "failed" if self.limited else "ready",
                        "error_code": "rate_limited" if self.limited else None,
                        "decision": {"retention": "skip", "route": "general"},
                    },
                }
            else:
                assert path == "/ask"
                data = {
                    "status": "general",
                    "text": "Washington, D.C. is a federal district.",
                    "retrieval": {"sources_reviewed": 0, "memories_reviewed": 0},
                }
        return {"http_status": 200, "data": data, "elapsed_ms": 1, "server_timing": ""}


def test_rate_limit_stops_batch_immediately_and_keeps_failed_attempt():
    client = ScriptedClient(limited=True)
    report = evaluator.run(client, "fresh", 45)
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "rate_limited_stop_batch"
    assert len(client.posts) == 1
    assert report["cases"][0]["capture"]["assessment"]["error_code"] == "rate_limited"
    assert report["completed_case_ids"] == []


def test_explicit_retry_preserves_ids_and_never_repeats_completed_cases(tmp_path):
    previous = {"namespace": "original-synthetic", "conversation_id": str(uuid4()), "cases": []}
    for case in evaluator.cases():
        previous["cases"].append(
            {
                **case,
                "message_id": str(uuid4()),
                "capture": {"assessment": {"status": "ready"}},
                "answer": {"status": "general"},
            }
        )
    previous["cases"][0]["answer"] = {"status": "error", "reason": "provider_failed"}
    path = tmp_path / "original.json"
    path.write_text(json.dumps(previous))
    immutable = path.read_bytes()
    prior, selected = evaluator.load_retry_report(path)
    assert [case["id"] for case in selected] == ["long-capital-1"]
    client = ScriptedClient()
    report = evaluator.resume_failed(client, prior, selected, 45)
    assert report["status"] == "completed"
    assert report["namespace"] == previous["namespace"]
    capture = client.posts[0][1]
    assert capture["message_id"] == previous["cases"][0]["message_id"]
    assert capture["conversation_id"] == previous["conversation_id"]
    assert capture["retry_failed"] is True
    assert client.posts[1][1]["assessment_id"] == client.assessment_id
    assert report["cases"][0]["previous_attempt"]["answer"]["reason"] == "provider_failed"
    assert path.read_bytes() == immutable
    next_path = tmp_path / "retry.json"
    next_path.write_text(json.dumps(report))
    assert evaluator.load_retry_report(next_path)[1] == []


def test_retry_rejects_unapproved_changed_question(tmp_path):
    report = {
        "namespace": "synthetic",
        "conversation_id": str(uuid4()),
        "cases": [
            {
                "id": "long-capital-1",
                "message_id": str(uuid4()),
                "question": "not a frozen case",
            }
        ],
    }
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(report))
    with pytest.raises(evaluator.EvaluationStop):
        evaluator.load_retry_report(path)


def test_pacing_applies_to_inference_only(monkeypatch):
    waits = []
    monkeypatch.setattr(evaluator, "perf_counter", lambda: 0)
    monkeypatch.setattr(evaluator, "sleep", waits.append)

    class Response:
        code, headers = 200, {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"{}"

    client = evaluator.Client("http://127.0.0.1:18000")
    monkeypatch.setattr(client.opener, "open", lambda *args, **kwargs: Response())
    client.request("/usage")
    client.request("/conversation/messages", {})
    client.request("/ask", {})
    assert waits == [8, 8]
