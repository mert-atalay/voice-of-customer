"""The question bank: what people actually ask, grouped into canonical questions.

Grouping is rule based. A conversation's topic tag picks the group of candidates, and
the first candidate whose key phrase appears in the user's words wins. Anything else
lands in a general bucket for that topic. The content gaps list ranks questions that
are asked often, answered badly by the bot, and missing from the website.
"""

from __future__ import annotations

from collections import defaultdict

# Only conversations with these intents enter the bank.
BANK_INTENTS = ("question", "request")
MIN_COUNT = 3                 # a question asked fewer times than this is not ranked as a gap
PARTLY_COUNTS_AS = 0.5        # a partly answered chat counts as half unanswered

# id, topic, canonical wording, key phrases. Order matters: specific questions come first.
CANONICAL: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("pricing_student", "pricing", "Is there a student discount?", ("student",)),
    ("pricing_family", "pricing", "How much is the family plan?", ("family", "partner", "kids")),
    ("pricing_joining_fee", "pricing", "Is there a joining fee?",
     ("joining fee", "sign up fee", "admin fee", "upfront")),
    ("pricing_monthly", "pricing", "How much is a membership?",
     ("how much", "price", "cost", "month", "charge")),
    ("trial_book", "trial", "How do I book a trial?", ("book", "sign up", "start", "arrange")),
    ("trial_free", "trial", "Is there a free trial?", ("trial", "try", "day pass")),
    ("cancel_freeze", "cancellation", "Can I freeze my membership?",
     ("freeze", "pause", "on hold")),
    ("cancel_notice", "cancellation", "How much notice do I need to give to cancel?",
     ("notice", "in advance", "how long", "when does it stop")),
    ("cancel_how", "cancellation", "How do I cancel?", ("cancel", "leave", "end my")),
    ("billing_refund", "billing", "How do I get a refund?", ("refund", "money back")),
    ("billing_date", "billing", "When is payment taken, and can I change the date?",
     ("payment date", "take payment", "what day", "which date", "direct debit")),
    ("hours_holiday", "schedule_hours", "What are the holiday opening hours?",
     ("holiday", "christmas", "new year")),
    ("hours_opening", "schedule_hours", "What are the opening hours?",
     ("open", "close", "hours", "what time")),
    ("classes_beginner", "classes", "Are there classes for beginners?",
     ("beginner", "never done", "new to", "intro", "easy")),
    ("classes_book", "classes", "How do I book a class?", ("book", "reserve")),
    ("classes_timetable", "classes", "What classes are on, and when?",
     ("timetable", "schedule", "what classes", "when is", "is there a")),
    ("facilities_childcare", "facilities", "Is there childcare?",
     ("childcare", "creche", "kids", "children")),
    ("facilities_pool", "facilities", "Is there a pool or sauna?", ("pool", "sauna", "steam")),
    ("facilities_lockers", "facilities", "Are there lockers, showers and towels?",
     ("locker", "shower", "towel", "padlock")),
    ("crowding_quiet", "crowding", "When is the gym quiet?",
     ("quiet", "busy", "crowded", "rush", "peak")),
    ("parking_cost", "parking", "Is parking free?", ("free", "pay", "how much", "cost")),
    ("parking_available", "parking", "Is there parking?", ("parking", "park", "bike")),
    ("staff_pt", "staff", "Do you offer personal training?",
     ("personal train", "pt session", "trainer", "coach")),
    ("other_guest", "other", "Can I bring a guest?", ("guest", "friend", "bring", "come with")),
    ("other_lost", "other", "Where is lost property?", ("lost", "left my")),
]
WORDING = {qid: wording for qid, _, wording, _ in CANONICAL}


def general_wording(topic: str) -> str:
    if topic == "other":
        return "Questions that fit no group"
    return f"Other {topic.replace('_', ' ')} questions"


def covered_ids(site_pages: dict) -> set[str]:
    return {qid for page in site_pages["pages"] for qid in page["answers"]}


def canonical_question(topic: str, user_text: str) -> str:
    """Map one conversation to a canonical question id, or to `<topic>_general`."""
    text = user_text.lower()
    for qid, q_topic, _, phrases in CANONICAL:
        if q_topic == topic and any(phrase in text for phrase in phrases):
            return qid
    return f"{topic}_general"


def assign(chats: list[dict], chat_tags: dict) -> dict[str, str]:
    """Canonical question id for every tagged conversation that is a question or request."""
    out = {}
    for chat in chats:
        tags = chat_tags.get(chat["id"])
        if not tags or tags["intent"] not in BANK_INTENTS:
            continue
        user_text = " ".join(t["text"] for t in chat["turns"] if t["role"] == "user")
        out[chat["id"]] = canonical_question(tags["topic"], user_text)
    return out


def build_bank(chats: list[dict], chat_tags: dict, frustration: dict[str, int],
               site_pages: dict) -> list[dict]:
    """One row per canonical question, most asked first."""
    on_site = covered_ids(site_pages)
    groups: dict[str, list[str]] = defaultdict(list)
    for chat_id, qid in assign(chats, chat_tags).items():
        groups[qid].append(chat_id)
    rows = []
    for qid, ids in groups.items():
        n = len(ids)
        answered = [chat_tags[i]["answered"] for i in ids]
        unanswered = (answered.count("no") + PARTLY_COUNTS_AS * answered.count("partly")) / n
        topic = chat_tags[ids[0]]["topic"]
        rows.append({
            "id": qid,
            "topic": topic,
            "question": WORDING.get(qid, general_wording(topic)),
            "count": n,
            "unanswered_share": round(unanswered, 3),
            "mean_frustration": round(sum(frustration[i] for i in ids) / n, 1),
            "on_site": qid in on_site,
            "general_bucket": qid not in WORDING,
        })
    rows.sort(key=lambda row: (-row["count"], row["id"]))
    return rows


def priority(row: dict) -> float:
    """How much a missing answer costs: how often, how badly answered, how frustrating.

    count x unanswered share x (1 + mean frustration / 100). A judgement call, like the
    score weights. It only orders the list.
    """
    return round(row["count"] * row["unanswered_share"] * (1 + row["mean_frustration"] / 100), 1)


def content_gaps(bank: list[dict], min_count: int = MIN_COUNT) -> list[dict]:
    """Questions the site does not answer, ranked. General buckets are left out."""
    gaps = [dict(row, priority=priority(row)) for row in bank
            if not row["on_site"] and not row["general_bucket"] and row["count"] >= min_count]
    gaps.sort(key=lambda row: (-row["priority"], row["id"]))
    return gaps
