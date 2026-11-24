"""Everything the report needs, computed from one tagging run."""

from __future__ import annotations

from collections import Counter

from . import quality, questions, scores
from .taxonomy import ASPECTS, SENTIMENTS


def themes(tag_run: dict) -> dict:
    topics = Counter(tags["topic"] for tags in tag_run["chats"].values())
    intents = Counter(tags["intent"] for tags in tag_run["chats"].values())
    mentions = {a: Counter() for a in ASPECTS}
    for tags in tag_run["reviews"].values():
        for entry in tags["aspects"]:
            mentions[entry["aspect"]][entry["sentiment"]] += 1
    aspects = [{"aspect": a, "mentions": sum(c.values()), **{s: c[s] for s in SENTIMENTS}}
               for a, c in mentions.items() if c]
    aspects.sort(key=lambda row: (-row["mentions"], row["aspect"]))
    return {
        "chat_topics": [{"topic": t, "count": n} for t, n in
                        sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))],
        "chat_intents": dict(sorted(intents.items(), key=lambda kv: (-kv[1], kv[0]))),
        "review_aspects": aspects,
    }


def intended_run(chats: list[dict], reviews: list[dict]) -> dict:
    """The intended labels in the shape of a tagging run. Only used as a reference."""
    return {
        "tagger": "intended",
        "model": None,
        "chats": {c["id"]: {k: v for k, v in c["intended"].items() if k != "question_id"}
                  for c in chats},
        "reviews": {r["id"]: {"aspects": [{"aspect": a, "sentiment": s}
                                          for a, s in r["intended"]["aspects"].items()]}
                    for r in reviews},
        "invalid": [],
    }


def reference(tag_run: dict, result: dict, chats: list[dict], reviews: list[dict],
              site_pages: dict) -> dict:
    """What the tagger's errors do to the numbers: each score beside the same score
    computed from the intended labels."""
    truth = intended_run(chats, reviews)
    t_frustration = scores.frustration_by_topic(chats, truth["chats"])
    t_locations = scores.location_sentiment(reviews, truth["reviews"])
    t_bank = questions.build_bank(chats, truth["chats"], t_frustration["per_chat"], site_pages)
    t_gaps = [g["id"] for g in questions.content_gaps(t_bank)]
    gaps = [g["id"] for g in result["content_gaps"]]
    top = 5
    return {
        "mean_frustration": {"tagger": result["frustration"]["mean"],
                             "intended": t_frustration["mean"]},
        "unanswered_share": {"tagger": result["frustration"]["unanswered_share"],
                             "intended": t_frustration["unanswered_share"]},
        "chain_score": {"tagger": result["locations"]["chain_score"],
                        "intended": t_locations["chain_score"]},
        "location_scores": [
            {"location": a["location"], "tagger": a["score"], "intended": b["score"],
             "stars_disagree_tagger": a["stars_disagree"],
             "stars_disagree_intended": b["stars_disagree"]}
            for a, b in zip(result["locations"]["locations"], t_locations["locations"])],
        "top_gaps": {"n": top, "tagger": gaps[:top], "intended": t_gaps[:top],
                     "shared": len(set(gaps[:top]) & set(t_gaps[:top]))},
    }


def summarise(tag_run: dict, chats: list[dict], reviews: list[dict], site_pages: dict) -> dict:
    frustration = scores.frustration_by_topic(chats, tag_run["chats"])
    bank = questions.build_bank(chats, tag_run["chats"], frustration["per_chat"], site_pages)
    result = {
        "synthetic": True,
        "tagger": tag_run["tagger"],
        "model": tag_run.get("model"),
        "counts": {"chats": len(chats), "reviews": len(reviews),
                   "tagged_chats": len(tag_run["chats"]),
                   "tagged_reviews": len(tag_run["reviews"]),
                   "invalid": len(tag_run.get("invalid", []))},
        "themes": themes(tag_run),
        "frustration": frustration,
        "locations": scores.location_sentiment(reviews, tag_run["reviews"]),
        "question_bank": bank,
        "content_gaps": questions.content_gaps(bank),
        "agreement": quality.agreement(tag_run, chats, reviews),
    }
    result["reference"] = reference(tag_run, result, chats, reviews, site_pages)
    return result
