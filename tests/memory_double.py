"""Explicit deterministic proposals for contract/UI checks; never model-quality evidence."""

import json
from pathlib import Path

from jarvis.providers import Completion, NvidiaExtractor


def content(predicate, value, *, subject="Atlas", scope="Atlas", **changes):
    return {
        "subject": {"label": subject},
        "predicate": predicate,
        "value": value if isinstance(value, dict) else {"kind": "text", "value": value},
        "scope": {"kind": "project", "key": scope},
        "attribution": {"label": "user"},
        "evidence_status": "reported",
        "modality": "asserted",
        "negated": False,
        "condition": None,
        "time": {"event": None, "valid_from": None, "valid_to": None},
        **changes,
    }


def passage(source, variant="raw"):
    text = source["raw_text"] if variant == "raw" else source["formatted_text"]
    return {
        "source_id": source["id"],
        "source_revision": source["revision"],
        "variant": variant,
        "start": 0,
        "end": len(text),
        "exact_text": text,
    }


def operation(source, claim, *, action="add", target=None, variant="raw"):
    return {
        "action": action,
        "target_revision_id": target,
        "content": claim,
        "passages": [passage(source, variant)],
    }


def fixture_proposal(data):
    source = data["CURRENT_SOURCE"]
    originals = [
        json.loads(line)
        for line in Path("data/synthetic/sample-dictations.jsonl").read_text().splitlines()
    ]
    record = next(
        (row["record_id"] for row in originals if row["raw_transcript"] == source["raw_text"]), None
    )
    claims = []
    if record == "dict_0001":
        claims = [content("launch_date", {"kind": "date", "value": "2026-09-18"})]
    elif record == "dict_0002":
        claims = [content("update_style", "three bullets and call out blockers", subject="Mira")]
    elif record == "dict_0003":
        target = next(
            (c for c in data["MEMORIES"] if c["content"]["predicate"] == "launch_date"), None
        )
        date = content("launch_date", {"kind": "date", "value": "2026-09-21"})
        ops = [
            operation(
                source,
                date,
                action="supersede" if target else "add",
                target=target["id"] if target else None,
            ),
            operation(source, content("launch_change_reason", "legal review needs more time")),
        ]
        return {"decision": "extracted", "operations": ops}
    elif record == "dict_0004":
        claims = [
            content(
                "budget_owner",
                "Ravi",
                evidence_status="tentative",
                modality="conditional",
                condition="Finance signs off; nobody has confirmed",
            )
        ]
    elif record == "dict_0005":
        claims = [
            content("checklist_sent_to", "Mira; reported sent this morning"),
            content("checklist_review", "pending"),
        ]
    elif record == "dict_0006":
        claims = [
            content("blocker", "legal approval"),
            content("next_step", "ask Legal for its review date"),
        ]
    elif record == "dict_0007":
        claims = [
            content(
                "client_chosen_date",
                {"kind": "date", "value": "2026-09-25"},
                subject="Orion",
                scope="Orion",
            )
        ]
    elif record == "dict_0008":
        return {
            "decision": "extracted",
            "operations": [
                operation(
                    source,
                    content(
                        "spending_limit",
                        {"kind": "quantity", "value": amount, "unit": "INR"},
                        evidence_status="disputed",
                    ),
                    variant=variant,
                )
                for amount, variant in [(15000, "raw"), (50000, "formatted")]
            ],
        }
    return {
        "decision": "extracted" if claims else "no_memory",
        "operations": [operation(source, claim) for claim in claims],
    }


class FixtureExtractor(NvidiaExtractor):
    live = False
    model = "deterministic-test-double"
    budget_key = "s07-contract-tests"

    def __init__(self, proposal=None):
        super().__init__(approved=True)
        self.proposal = proposal
        self.calls = 0

    def complete(self, body):
        self.calls += 1
        data = json.loads(body["messages"][1]["content"])
        proposal = self.proposal(data) if self.proposal else fixture_proposal(data)
        return Completion(json.dumps(proposal), self.model, 100, 100, 1)
