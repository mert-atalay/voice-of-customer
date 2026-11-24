"""Does a tagger recover what each text was written to say?

Every synthetic conversation and review carries the labels it was generated from.
Agreement is the share of items where the tagger gives the same label. An item the
tagger failed to tag counts as a miss, so a tagger cannot look better by skipping.
"""

from __future__ import annotations

from . import questions
from .taxonomy import SIGNALS

# field -> how it is read in the tables
FIELD_LABELS = {
    "chat_topic": "Chat: topic",
    "chat_intent": "Chat: intent",
    "chat_answered": "Chat: answered",
    "chat_signals_exact": "Chat: all frustration signals exactly right",
    "chat_frustration_band": "Chat: frustration score within 10 points",
    "chat_question": "Chat: canonical question",
    "review_aspects_found": "Review: intended aspects found",
    "review_aspects_extra": "Review: tagged aspects that were intended",
    "review_sentiment": "Review: sentiment right on aspects found",
    "review_exact": "Review: whole review exactly right",
}


def _row() -> dict:
    return {"match": 0, "total": 0}


def _finish(rows: dict) -> dict:
    for row in rows.values():
        row["rate"] = round(row["match"] / row["total"], 3) if row["total"] else None
    return rows


def agreement(tag_run: dict, chats: list[dict], reviews: list[dict]) -> dict:
    from .scores import frustration  # local import keeps module load order simple

    fields = {name: _row() for name in FIELD_LABELS}
    signals = {name: {"tp": 0, "fp": 0, "fn": 0} for name in SIGNALS}
    assigned = questions.assign(chats, tag_run["chats"])

    for chat in chats:
        want, got = chat["intended"], tag_run["chats"].get(chat["id"])
        for field in ("topic", "intent", "answered"):
            row = fields[f"chat_{field}"]
            row["total"] += 1
            row["match"] += bool(got and got[field] == want[field])
        got_signals = set(got["signals"]) if got else set()
        row = fields["chat_signals_exact"]
        row["total"] += 1
        row["match"] += bool(got and got_signals == set(want["signals"]))
        for name in SIGNALS:
            if name in got_signals and name in want["signals"]:
                signals[name]["tp"] += 1
            elif name in got_signals:
                signals[name]["fp"] += 1
            elif name in want["signals"]:
                signals[name]["fn"] += 1
        row = fields["chat_frustration_band"]
        row["total"] += 1
        row["match"] += bool(got and abs(frustration(got) - frustration(want)) <= 10)
        if want["intent"] in questions.BANK_INTENTS:
            row = fields["chat_question"]
            row["total"] += 1
            row["match"] += assigned.get(chat["id"]) == want["question_id"]

    for review in reviews:
        want = review["intended"]["aspects"]
        tags = tag_run["reviews"].get(review["id"])
        got = {a["aspect"]: a["sentiment"] for a in tags["aspects"]} if tags else {}
        fields["review_aspects_found"]["total"] += len(want)
        fields["review_aspects_found"]["match"] += len(set(want) & set(got))
        fields["review_aspects_extra"]["total"] += len(got)
        fields["review_aspects_extra"]["match"] += len(set(want) & set(got))
        shared = set(want) & set(got)
        fields["review_sentiment"]["total"] += len(shared)
        fields["review_sentiment"]["match"] += sum(want[a] == got[a] for a in shared)
        fields["review_exact"]["total"] += 1
        fields["review_exact"]["match"] += bool(tags) and got == want

    for row in signals.values():
        found, wanted = row["tp"] + row["fp"], row["tp"] + row["fn"]
        row["precision"] = round(row["tp"] / found, 3) if found else None
        row["recall"] = round(row["tp"] / wanted, 3) if wanted else None
    return {
        "tagger": tag_run["tagger"],
        "model": tag_run.get("model"),
        "tagged_chats": len(tag_run["chats"]),
        "tagged_reviews": len(tag_run["reviews"]),
        "invalid": len(tag_run.get("invalid", [])),
        "per_field": _finish(fields),
        "signals": signals,
    }


def side_by_side(reports: list[dict]) -> list[dict]:
    """One row per field, one cell per tagger, for the comparison table."""
    rows = []
    for field, label in FIELD_LABELS.items():
        row = {"field": field, "label": label, "cells": []}
        for report in reports:
            cell = report["per_field"][field]
            row["cells"].append({"tagger": report["tagger"], **cell})
        rows.append(row)
    return rows
