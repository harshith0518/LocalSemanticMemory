"""Runtime date and a retrieval inventory hint; turn intent is assessed separately."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo


def today_in(timezone):
    return datetime.now(ZoneInfo(timezone)).date()


def is_inventory_question(question):
    text = question.lower()
    return bool(
        re.search(r"\b(all|everything|whole|so far|summary|overview)\b", text)
        and re.search(r"\b(remember\w*|memor\w*|stored|database|db|notes|sources)\b", text)
    )
