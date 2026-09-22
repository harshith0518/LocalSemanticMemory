"""Conservative routing hints; they do not certify a model's factual accuracy."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo


def today_in(timezone):
    return datetime.now(ZoneInfo(timezone)).date()


def is_date_question(question):
    # Match a request for the calendar date, not a question about an event today.
    head = re.split(r"[?!;\n]", question.lower(), maxsplit=1)[0].strip()
    return bool(
        re.fullmatch(
            r"(?:please )?(?:what(?:'s| is)|tell me|can you tell me) "
            r"(?:the )?(?:(?:today'?s?|current) date|date today|day (?:is it )?today)",
            head,
        )
    )


def is_inventory_question(question):
    text = question.lower()
    return bool(
        re.search(r"\b(all|everything|whole|so far|summary|overview)\b", text)
        and re.search(r"\b(remember\w*|memor\w*|stored|database|db|notes|sources)\b", text)
    )


def needs_live_information(question):
    text = question.lower()
    return bool(
        re.search(r"\b(today|tomorrow|latest|current|currently|now|live)\b", text)
        and re.search(r"\b(weather|news|price|prices|stock|exchange|president|ceo)\b", text)
    )


def knowledge_question_text(question):
    """Remove request framing, never personal assertions or possessives."""
    return re.sub(
        r"(^|[?!;\n]\s*)(?:(?:please )?(?:can|could|would) you )?(?:please )?"
        r"(?:(?:tell|explain to) me\b|i (?:just )?(?:want|would like) to "
        r"(?:know|understand)\b)",
        r"\1",
        question.lower(),
    ).strip()


def general_question_candidate(question):
    """Conservative question-only fast path; ambiguous/mixed messages keep learning."""
    if not general_knowledge_allowed(question):
        return False
    # A bare identity question can refer to a private entity not learned yet.
    # Keep it on the contextual path instead of silently treating a namesake
    # as public knowledge. This is a conservative routing hint, not an NER model.
    if re.match(r"^(?:who|where)\s+(?:is|are)\b", question.strip(), re.I) or re.match(
        r"^(?:[Ww]hat)\s+is\s+[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*\s*[?.]*$",
        question.strip(),
    ):
        return False
    parts = [p.strip() for p in re.split(r"[?!;\n]", question.lower()) if p.strip()]
    if not parts:
        return False
    head = knowledge_question_text(parts[0])
    if not re.match(r"^(what|which|who|where|when|why|how|explain|define|compare)\b", head):
        return False
    # Extra sentences may contain new facts, even when the first is a question.
    if re.search(r"\.\s+\w|\b(and|but|also)\s+\w+\s+(uses|works|prefers|moved)\b", head):
        return False
    return all(
        re.match(r"^(?:i (?:just )?(?:want|would like) to know|please (?:give|include))\b", p)
        and not re.search(r"\.\s+\w", p)
        for p in parts[1:]
    )


def general_knowledge_allowed(question):
    # A missing personal fact cannot be supplied from model training. Conservatively
    # block personal/workspace requests and time-sensitive or high-stakes advice.
    text = knowledge_question_text(question)
    if is_inventory_question(question):
        return False
    if re.search(r"\b(?:your|the|our)\s+(?:database|db|memory|memories)\b", text):
        return False
    return not re.search(
        r"\b(my|mine|our|ours|we|us|i|me|remember\w*|stored|"
        r"notes|sources|colleague|coworker|team|manager|project|secret|password|"
        r"deadline|launch|today|currently|latest|"
        r"recent|now|current|news|weather|price|stock|exchange|president|ceo|"
        r"medical|diagnos\w*|dosage|medication|legal|invest\w*)\b",
        text,
    )
