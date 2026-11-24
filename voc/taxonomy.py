"""The tag schema. One place defines every field and its allowed values.

The prompts and the JSON schemas are built from these lists, so they cannot drift apart.
"""

from __future__ import annotations

TOPICS: dict[str, str] = {
    "pricing": "membership prices, discounts, joining fees",
    "trial": "free trials, day passes, trying the gym before joining",
    "cancellation": "cancelling, notice periods, freezing or pausing a membership",
    "billing": "payments, charges, payment dates, refunds",
    "schedule_hours": "opening hours, holiday hours",
    "classes": "class timetable, booking classes, class levels, instructors' sessions",
    "facilities": "equipment, pool, sauna, showers, lockers, childcare",
    "cleanliness": "how clean the gym, changing rooms and equipment are",
    "crowding": "how busy it is, waiting for equipment, quiet times",
    "staff": "front desk, trainers, personal training, how staff behave",
    "parking": "car park, parking cost, bike racks",
    "other": "anything that fits none of the above",
}
INTENTS: dict[str, str] = {
    "question": "wants information",
    "complaint": "reports a problem or is unhappy with something",
    "praise": "says something positive",
    "request": "wants something done, such as a booking, a freeze or a refund",
}
ANSWERED: dict[str, str] = {
    "yes": "the bot gave the information or help the person wanted",
    "partly": "the bot gave related or general information but not the specific thing",
    "no": "the bot did not answer, or answered something else",
}
SIGNALS: dict[str, str] = {
    "repeated_question": "the person asks the same thing again in other words",
    "bot_misunderstood": "the bot says it did not understand, or answers a different question",
    "asked_for_human": "the person asks for a human, an agent or a member of staff",
    "negative_language": "the person uses annoyed, dismissive or sarcastic language",
    "gave_up": "the person ends the chat without what they wanted",
}
SENTIMENTS = ["negative", "neutral", "positive"]
# Review aspects are the same list as the topics, minus the catch-all.
ASPECTS = [t for t in TOPICS if t != "other"]

CHAT_FIELDS = ["topic", "intent", "answered", "signals"]


def chat_schema() -> dict:
    """JSON schema for one batch of chat tags. Strict: no extra keys anywhere."""
    item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "topic": {"type": "string", "enum": list(TOPICS)},
            "intent": {"type": "string", "enum": list(INTENTS)},
            "answered": {"type": "string", "enum": list(ANSWERED)},
            "signals": {"type": "array", "items": {"type": "string", "enum": list(SIGNALS)}},
        },
        "required": ["id", *CHAT_FIELDS],
    }
    return _batch(item)


def review_schema() -> dict:
    item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "aspects": {"type": "array", "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "aspect": {"type": "string", "enum": ASPECTS},
                    "sentiment": {"type": "string", "enum": SENTIMENTS},
                },
                "required": ["aspect", "sentiment"],
            }},
        },
        "required": ["id", "aspects"],
    }
    return _batch(item)


def _batch(item: dict) -> dict:
    return {"type": "object", "additionalProperties": False,
            "properties": {"items": {"type": "array", "items": item}}, "required": ["items"]}


def _listing(values: dict[str, str]) -> list[str]:
    return [f"  - {name}: {meaning}" for name, meaning in values.items()]


def chat_prompt() -> str:
    lines = [
        "You are tagging chatbot conversations from a gym chain against a fixed taxonomy.",
        "Each conversation has an id and a list of turns between a user and the bot.",
        "Return one item per conversation, with the same id, in the same order.",
        "Judge only the text. Do not guess anything about the person.",
        "",
        "topic: the main thing the user wants. One of:", *_listing(TOPICS),
        "intent: what the user is doing in their first message. One of:", *_listing(INTENTS),
        "answered: did the bot deal with it by the end? One of:", *_listing(ANSWERED),
        "signals: every frustration signal that is present. Empty list if none. Any of:",
        *_listing(SIGNALS),
    ]
    return "\n".join(lines)


def review_prompt() -> str:
    lines = [
        "You are tagging public reviews of a gym chain against a fixed taxonomy.",
        "Each review has an id and a text. Return one item per review, with the same id.",
        "List each aspect the review mentions, once, with the sentiment the reviewer",
        "expresses about that aspect: negative, neutral or positive. Read sarcasm as it is meant.",
        "Leave out aspects the review does not mention. Judge only the text.",
        "",
        "Aspects:", *_listing({a: TOPICS[a] for a in ASPECTS}),
    ]
    return "\n".join(lines)


def validate_chat(tags: dict) -> list[str]:
    """Return a list of problems; empty means the tags fit the taxonomy."""
    problems = []
    if not isinstance(tags, dict):
        return ["not an object"]
    for field, allowed in (("topic", TOPICS), ("intent", INTENTS), ("answered", ANSWERED)):
        if field not in tags:
            problems.append(f"{field}: missing")
        elif tags[field] not in allowed:
            problems.append(f"{field}: value {tags[field]!r} is not allowed")
    signals = tags.get("signals")
    if not isinstance(signals, list):
        problems.append("signals: missing")
    else:
        bad = [s for s in signals if s not in SIGNALS]
        if bad:
            problems.append(f"signals: values {bad!r} are not allowed")
        if len(set(map(str, signals))) != len(signals):
            problems.append("signals: repeated value")
    extra = set(tags) - set(CHAT_FIELDS)
    if extra:
        problems.append(f"unknown fields: {sorted(extra)}")
    return problems


def validate_review(tags: dict) -> list[str]:
    if not isinstance(tags, dict):
        return ["not an object"]
    problems = []
    aspects = tags.get("aspects")
    if not isinstance(aspects, list):
        problems.append("aspects: missing")
        aspects = []
    seen = set()
    for entry in aspects:
        if not isinstance(entry, dict) or set(entry) != {"aspect", "sentiment"}:
            problems.append("aspects: each entry needs exactly aspect and sentiment")
            continue
        if entry["aspect"] not in ASPECTS:
            problems.append(f"aspects: aspect {entry['aspect']!r} is not allowed")
        elif entry["aspect"] in seen:
            problems.append(f"aspects: {entry['aspect']} listed twice")
        seen.add(entry["aspect"])
        if entry["sentiment"] not in SENTIMENTS:
            problems.append(f"aspects: sentiment {entry['sentiment']!r} is not allowed")
    extra = set(tags) - {"aspects"}
    if extra:
        problems.append(f"unknown fields: {sorted(extra)}")
    return problems
