"""Transport contract fixture, never live quality or ingested source data."""

import json
import re

from jarvis.providers import Completion, NvidiaResponder


def fixture_assessment(data):
    """Scripted transport decisions; these rules are never application routing."""
    question = data["QUESTION"]
    text = question.lower().strip()
    decision = {
        "retention": "skip",
        "route": "contextual",
        "reason": "personal_question",
        "memory_excerpts": [],
    }
    if "date" in text and ("today" in text or "current date" in text):
        return {**decision, "route": "clock", "reason": "clock"}
    if any(term in text for term in ("weather", "latest share price", "latest news")):
        return {**decision, "route": "live", "reason": "current_information"}
    if any(term in text for term in ("hypothetically", "suppose i", "imagine i")):
        return {**decision, "route": "general", "reason": "hypothetical"}
    if any(term in text for term in ("for this answer only", "just this once", "one-off")):
        return {**decision, "route": "general", "reason": "one_off"}
    if text.startswith(("hello", "hi ", "thanks", "thank you")) or text == "hi":
        return {**decision, "route": "general", "reason": "small_talk"}
    public = any(
        term in text
        for term in (
            "capital of",
            "solar system",
            "planets",
            "photosynthesis",
            "triangle",
            "semantic memory",
            "databases work",
            "project manager",
            "tell me a joke",
            "explain gravity",
            "explain recursion",
            "what is the us",
            "translate",
        )
    )
    personal = any(term in text for term in ("my project's", "my manager", "my capital"))
    if public and not personal:
        decision.update(route="general", reason="general_request")
    # Only scripted assertions used by contract/browser fixtures get retained.
    # Exact quotes keep production validation meaningful, without pretending a
    # deterministic test double establishes the quality of semantic assessment.
    sentences = re.split(r"(?<=[.!?])\s+", question)
    excerpts = [
        sentence
        for sentence in sentences
        if "?" not in sentence
        and (
            re.search(
                r"\b(?:i (?:work|live|prefer)|(?:atlas|cedar|willow) (?:now )?uses)\b",
                sentence,
                re.I,
            )
            or sentence.lower().startswith(
                (
                    "quick atlas update",
                    "mira asked",
                    "the atlas",
                    "if finance signs off",
                    "i sent mira",
                    "for orion",
                    "my favourite beverage is",
                    "my favorite beverage is",
                )
            )
        )
    ]
    if excerpts:
        decision.update(
            retention="candidate", reason="useful_assertion", memory_excerpts=excerpts[:4]
        )
    return decision


class FixtureResponder(NvidiaResponder):
    live = False
    model = "deterministic-answer-double"
    budget_key = "s07-contract-tests"

    def __init__(self, proposal=None, *, private_direct=False, assessment=None):
        super().__init__(approved=True, private_direct=private_direct)
        self.proposal = proposal
        self.calls = 0
        self.assessment = assessment
        self.assessment_calls = 0

    def complete(self, body):
        try:
            data = json.loads(body["messages"][1]["content"])
        except ValueError:
            data = {}
        if data.get("TASK") == "assess_turn":
            self.assessment_calls += 1
            result = (self.assessment or fixture_assessment)(data)
            return Completion(json.dumps(result), self.model, 120, 35, 1)
        self.calls += 1
        if body["max_tokens"] == 2048:
            return Completion(
                json.dumps({"text": "Synthetic context-free answer."}),
                self.model,
                20,
                8,
                1,
            )
        if "SOURCES" not in data:
            return Completion(
                json.dumps({"queries": ["drink beverage tea coffee"]}), self.model, 30, 10, 1
            )
        if not data["SOURCES"]:
            result = {"status": "unknown", "text": "No supported personal fact.", "citations": []}
            if self.proposal:
                result = self.proposal(data, result)
            return Completion(json.dumps(result), self.model, 100, 50, 1)
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
