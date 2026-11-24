"""Two scores built from the tags.

Frustration score per conversation, 0 to 100.
Sentiment score per location, 0 to 100, with recency weighting and shrinkage.

Every number in the constants below is a judgement call. None of them is fitted to
an outcome such as churn or complaints. Change them and the scores change.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .taxonomy import ASPECTS

# --- Frustration. Points are added and the total is capped at 100.
SIGNAL_POINTS = {
    "repeated_question": 20,   # had to ask again
    "bot_misunderstood": 15,   # the bot's fault, but the person may not mind once
    "asked_for_human": 25,     # has stopped trusting the bot
    "negative_language": 20,   # says so
    "gave_up": 25,             # left without the answer
}
ANSWERED_POINTS = {"yes": 0, "partly": 10, "no": 25}
HIGH_FRUSTRATION = 50          # conversations at or above this are counted as "high"

# --- Location sentiment.
SENTIMENT_VALUE = {"negative": 0.0, "neutral": 50.0, "positive": 100.0}
HALF_LIFE_DAYS = 90            # a review this old counts half as much as one from today
PRIOR_REVIEWS = 5              # pull toward the chain average as if 5 average reviews were added
THIN_MENTIONS = 5              # an aspect with fewer mentions than this is flagged as thin
STAR_GAP_FLAG = 15             # points of gap between stars and text before a location is flagged


def frustration(tags: dict) -> int:
    """Score one tagged conversation."""
    points = ANSWERED_POINTS[tags["answered"]]
    points += sum(SIGNAL_POINTS[s] for s in set(tags["signals"]))
    return min(100, points)


def frustration_by_topic(chats: list[dict], chat_tags: dict) -> dict:
    """Per conversation scores, plus the mean and the unanswered share for each topic."""
    per_chat = {c["id"]: frustration(chat_tags[c["id"]]) for c in chats if c["id"] in chat_tags}
    groups: dict[str, list[str]] = defaultdict(list)
    for chat_id in per_chat:
        groups[chat_tags[chat_id]["topic"]].append(chat_id)
    by_topic = []
    for topic, ids in groups.items():
        by_topic.append({
            "topic": topic,
            "count": len(ids),
            "mean_frustration": round(sum(per_chat[i] for i in ids) / len(ids), 1),
            "high_share": round(sum(per_chat[i] >= HIGH_FRUSTRATION for i in ids) / len(ids), 3),
            "unanswered_share": round(
                sum(chat_tags[i]["answered"] == "no" for i in ids) / len(ids), 3),
        })
    by_topic.sort(key=lambda row: (-row["count"], row["topic"]))
    scores = list(per_chat.values())
    return {
        "per_chat": per_chat,
        "by_topic": by_topic,
        "mean": round(sum(scores) / len(scores), 1) if scores else None,
        "high_share": round(sum(s >= HIGH_FRUSTRATION for s in scores) / len(scores), 3)
        if scores else None,
        "unanswered_share": round(
            sum(chat_tags[i]["answered"] == "no" for i in per_chat) / len(per_chat), 3)
        if per_chat else None,
    }


def recency_weight(review_date: str, as_of: str, half_life: float = HALF_LIFE_DAYS) -> float:
    age = max(0, (date.fromisoformat(as_of) - date.fromisoformat(review_date)).days)
    return 0.5 ** (age / half_life)


def shrink(value: float, weight: float, prior: float, prior_weight: float = PRIOR_REVIEWS) -> float:
    """Weighted average of a group's own value and the prior. Little data, more prior."""
    return (weight * value + prior_weight * prior) / (weight + prior_weight)


def review_score(tags: dict) -> float | None:
    """Mean sentiment of the aspects a review mentions. None if it mentions none."""
    values = [SENTIMENT_VALUE[a["sentiment"]] for a in tags["aspects"]]
    return sum(values) / len(values) if values else None


def _wmean(pairs: list[tuple[float, float]]) -> float | None:
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else None


def location_sentiment(reviews: list[dict], review_tags: dict, as_of: str | None = None,
                       half_life: float = HALF_LIFE_DAYS,
                       prior_reviews: float = PRIOR_REVIEWS) -> dict:
    """Sentiment per location from review text, with stars kept beside it, not inside it."""
    if as_of is None:
        as_of = max(r["date"] for r in reviews)
    text: dict[str, list] = defaultdict(list)       # location -> (score, weight)
    stars: dict[str, list] = defaultdict(list)      # location -> (stars, weight)
    aspect: dict[tuple, list] = defaultdict(list)   # (location, aspect) -> (value, weight)
    plain: dict[str, list] = defaultdict(list)      # location -> unweighted scores
    odd: dict[str, int] = defaultdict(int)          # reviews whose stars and text disagree
    counts: dict[str, int] = defaultdict(int)
    for review in reviews:
        loc = review["location"]
        counts[loc] += 1
        weight = recency_weight(review["date"], as_of, half_life)
        stars[loc].append((review["stars"], weight))
        tags = review_tags.get(review["id"])
        score = review_score(tags) if tags else None
        if score is None:
            continue
        text[loc].append((score, weight))
        plain[loc].append(score)
        if (review["stars"] >= 4 and score < 40) or (review["stars"] <= 2 and score > 60):
            odd[loc] += 1
        for entry in tags["aspects"]:
            aspect[(loc, entry["aspect"])].append((SENTIMENT_VALUE[entry["sentiment"]], weight))

    chain = _wmean([p for pairs in text.values() for p in pairs])
    chain_aspect = {a: _wmean([p for (_, name), pairs in aspect.items() if name == a
                               for p in pairs]) for a in ASPECTS}
    locations = []
    for loc in sorted(counts):
        pairs = text.get(loc, [])
        weight = sum(w for _, w in pairs)
        raw = _wmean(pairs)
        score = shrink(raw, weight, chain, prior_reviews) if raw is not None else chain
        stars_mean = _wmean(stars[loc])
        stars_100 = (stars_mean - 1) / 4 * 100
        gap = stars_100 - raw if raw is not None else None
        aspects = {}
        for name in ASPECTS:
            a_pairs = aspect.get((loc, name), [])
            if not a_pairs:
                continue
            a_raw = _wmean(a_pairs)
            aspects[name] = {
                "mentions": len(a_pairs),
                "raw": round(a_raw, 1),
                "score": round(shrink(a_raw, sum(w for _, w in a_pairs), chain_aspect[name],
                                      prior_reviews), 1),
                "thin": len(a_pairs) < THIN_MENTIONS,
            }
        locations.append({
            "location": loc,
            "reviews": counts[loc],
            "scored_reviews": len(pairs),
            "effective_reviews": round(weight, 1),
            "score": round(score, 1) if score is not None else None,
            "raw_recent": round(raw, 1) if raw is not None else None,
            "raw_all_time": round(sum(plain[loc]) / len(plain[loc]), 1) if plain[loc] else None,
            "stars_mean": round(stars_mean, 2),
            "stars_100": round(stars_100, 1),
            "stars_minus_text": round(gap, 1) if gap is not None else None,
            "stars_disagree": gap is not None and abs(gap) >= STAR_GAP_FLAG,
            "odd_reviews": odd[loc],
            "aspects": aspects,
        })
    return {
        "as_of": as_of,
        "half_life_days": half_life,
        "prior_reviews": prior_reviews,
        "chain_score": round(chain, 1) if chain is not None else None,
        "chain_aspects": {a: round(v, 1) for a, v in chain_aspect.items() if v is not None},
        "locations": locations,
    }
