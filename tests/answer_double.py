"""Transport contract fixture, never live quality or ingested source data."""

import json

from jarvis.providers import Completion, NvidiaResponder


class FixtureResponder(NvidiaResponder):
    live = False
    model = "deterministic-answer-double"
    budget_key = "s07-contract-tests"

    def __init__(self, proposal=None, *, private_direct=False):
        super().__init__(approved=True, private_direct=private_direct)
        self.proposal = proposal
        self.calls = 0

    def complete(self, body):
        self.calls += 1
        if body["max_tokens"] == 2048:
            return Completion(
                json.dumps({"text": "Synthetic context-free answer."}),
                self.model,
                20,
                8,
                1,
            )
        data = json.loads(body["messages"][1]["content"])
        source = data["SOURCES"][0]
        if data["USER_AMENDMENTS"]:
            latest = data["USER_AMENDMENTS"][-1]["source_id"]
            source = next(s for s in data["SOURCES"] if s["id"] == latest)
        result = {
            "status": "answered",
            "text": "Synthetic contract answer. " + source["raw_text"],
            "citations": [
                {
                    "source_id": source["id"],
                    "source_revision": source["revision"],
                    "variant": "raw",
                    "start": 0,
                    "end": len(source["raw_text"]),
                    "exact_text": source["raw_text"],
                }
            ],
        }
        if self.proposal:
            result = self.proposal(data, result)
        return Completion(json.dumps(result), self.model, 100, 50, 1)
