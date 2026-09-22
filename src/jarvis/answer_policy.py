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


def general_knowledge_allowed(question):
    # A missing personal fact cannot be supplied from model training. Conservatively
    # block personal/workspace requests and time-sensitive or high-stakes advice.
    text = re.sub(
        r"^(?:(?:please )?(?:can|could|would) you )?(?:please )?(?:tell|explain to) me\b|"
        r"^i (?:want|would like) to (?:know|understand)\b",
        "",
        question.lower(),
    )
    if is_inventory_question(question):
        return False
    if re.search(r"\b(?:your|the|our)\s+(?:database|db|memory|memories)\b", text):
        return False
    return not re.search(
        r"\b(my|mine|our|ours|we|us|i|me|remember\w*|stored|"
        r"notes|sources|colleague|coworker|team|manager|project|today|currently|latest|"
        r"recent|now|current|news|weather|price|stock|exchange|president|ceo|"
        r"medical|diagnos\w*|dosage|medication|legal|invest\w*)\b",
        text,
    )
