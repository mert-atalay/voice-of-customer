"""Two taggers behind one interface.

KeywordTagger  offline rules. The baseline. Used in the tests and in CI.
ModelTagger    a language model with a strict JSON schema and a hard call budget.

Both get the same input: the public view of an item, which is its id and its text.
The hidden `intended` labels, the location, the date and the star rating are never
passed to a tagger. Stars are held back so text sentiment and stars stay independent.
"""

from __future__ import annotations

import json
import re

from . import taxonomy
from .client import BudgetExceeded, OpenAIChatClient, model_name


def public_chat(chat: dict) -> dict:
    return {"id": chat["id"],
            "turns": [{"role": t["role"], "text": t["text"]} for t in chat["turns"]]}


def public_review(review: dict) -> dict:
    return {"id": review["id"], "text": review["text"]}


# ---------------------------------------------------------------- keyword baseline

TOPIC_WORDS: dict[str, str] = {
    "pricing": r"price|prices|cost|costs|fee|fees|expensive|cheap|cheaper|discount|how much|overpriced|value|rate",
    "trial": r"trial|try|day pass",
    "cancellation": r"cancel|cancelling|cancelled|notice|freeze|pause|on hold|leave",
    "billing": r"charged|charge|payment|payments|refund|refunded|billing|direct debit|money back",
    "schedule_hours": r"open|opens|opening|close|closes|hours|holiday|holidays",
    "classes": r"class|classes|yoga|spin|timetable|instructors?",
    "facilities": r"equipment|machines?|pool|sauna|showers?|lockers?|weights|kit|towels?|childcare|creche|kids|padlock",
    "cleanliness": r"clean|cleaned|cleans|cleanest|cleanliness|dirty|filthy|spotless|hygienic|smells?|wiped?",
    "crowding": r"busy|busier|crowded|overcrowded|packed|queue|queued|queues|quiet|space|peak|rush",
    "staff": r"staff|staffed|front desk|reception|trainers?|coach|coaches|personal training|pt|team",
    "parking": r"parking|park|car park|bike",
}
TOPIC_RE = {t: re.compile(rf"\b(?:{words})\b") for t, words in TOPIC_WORDS.items()}

REQUEST_RE = re.compile(r"\b(i want|id like|i'd like|i would like|can you|please|i need to|need to)\b")
COMPLAINT_RE = re.compile(r"\b(twice|too busy|overcrowded|dirty|not happy|broken|disgusting|"
                          r"not been cleaned|not hygienic|complain|complaint|queued)\b")
PRAISE_RE = re.compile(r"\b(great|brilliant|lovely|love|thanks to|well done|amazing)\b")

FALLBACK_RE = re.compile(r"did not understand|not sure i follow|rephrase|say that another way|"
                         r"what would you like to know")
NO_ANSWER_RE = re.compile(r"do not have|cannot transfer|could not help")
PARTLY_RE = re.compile(r"please check")
REPEAT_RE = re.compile(r"\b(i mean|not what i asked|i asked|again)\b")
HUMAN_RE = re.compile(r"\b(human|person|agent|someone|operator|member of staff|representative)\b")
NEGATIVE_RE = re.compile(r"\b(useless|waste|ridiculous|terrible|not helpful|annoying|awful|"
                         r"rubbish|joke|pathetic)\b")
GAVE_UP_RE = re.compile(r"\b(forget it|never mind|nevermind|nvm|give up|ill just|i'll just)\b")

POSITIVE_WORDS = re.compile(
    r"\b(friendly|helpful|great|good|excellent|clean|cleanest|spotless|love|best|easy|free|new|"
    r"fresh|welcoming|patient|plenty|quiet|bonus|well|simple|correct|quickly|cheap|fair|worth|"
    r"value|lovely|rarely)\b")
NEGATIVE_WORDS = re.compile(
    r"\b(rude|unhelpful|dirty|filthy|disgusting|smells?|broken|old|worn|cold|packed|crowded|"
    r"busy|busier|queue|queues|overpriced|expensive|nightmare|full|cancelled|hard|pain|useless|"
    r"bored|unfriendly|ignore|overflowing|hidden|mistakes|too|waiting|impossible|twice|"
    r"out of order|fault|hassle|nowhere)\b")
NEGATION = re.compile(r"\b(not|never|no|cannot|without)\b|n't")
CLAUSE_SPLIT = re.compile(r"[.;!?]|\bbut\b|\bthough\b|\bhowever\b")


def _topic(text: str) -> str:
    """The topic with the most keyword hits. Ties go to the one mentioned first."""
    best, best_key = "other", (0, 0)
    for topic, pattern in TOPIC_RE.items():
        hits = list(pattern.finditer(text))
        if hits:
            key = (len(hits), -hits[0].start())
            if key > best_key:
                best, best_key = topic, key
    return best


class KeywordTagger:
    name = "keyword"
    model = None
    batch_size = 50

    def tag_chat_batch(self, items: list[dict]) -> list[dict]:
        return [{"id": item["id"], **self.tag_chat(item)} for item in items]

    def tag_review_batch(self, items: list[dict]) -> list[dict]:
        return [{"id": item["id"], **self.tag_review(item)} for item in items]

    def tag_chat(self, chat: dict) -> dict:
        user = [t["text"].lower() for t in chat["turns"] if t["role"] == "user"]
        bot = [t["text"].lower() for t in chat["turns"] if t["role"] == "bot"]
        first, all_user = user[0], " \n ".join(user)
        topic = _topic(all_user)

        if COMPLAINT_RE.search(first):
            intent = "complaint"
        elif PRAISE_RE.search(first):
            intent = "praise"
        elif REQUEST_RE.search(first):
            intent = "request"
        else:
            intent = "question"

        signals = []
        on_topic = sum(1 for text in user if topic != "other" and TOPIC_RE[topic].search(text))
        if on_topic >= 2 or any(REPEAT_RE.search(text) for text in user[1:]):
            signals.append("repeated_question")
        if any(FALLBACK_RE.search(text) for text in bot):
            signals.append("bot_misunderstood")
        if any(HUMAN_RE.search(text) for text in user):
            signals.append("asked_for_human")
        if NEGATIVE_RE.search(all_user):
            signals.append("negative_language")
        gave_up = bool(GAVE_UP_RE.search(all_user))
        if gave_up:
            signals.append("gave_up")

        last_bot = bot[-1] if bot else ""
        if gave_up or FALLBACK_RE.search(last_bot) or NO_ANSWER_RE.search(last_bot):
            answered = "no"
        elif any(PARTLY_RE.search(text) for text in bot):
            answered = "partly"
        else:
            answered = "yes"
        return {"topic": topic, "intent": intent, "answered": answered, "signals": signals}

    def tag_review(self, review: dict) -> dict:
        """Split into clauses; each clause gives its sentiment to the aspects it names."""
        found: dict[str, list[int]] = {}
        for clause in CLAUSE_SPLIT.split(review["text"].lower()):
            aspects = [a for a in taxonomy.ASPECTS if TOPIC_RE[a].search(clause)]
            if not aspects:
                continue
            score = len(POSITIVE_WORDS.findall(clause)) - len(NEGATIVE_WORDS.findall(clause))
            if NEGATION.search(clause):
                score = -score
            for aspect in aspects:
                found.setdefault(aspect, []).append(score)
        out = []
        for aspect, scores in found.items():
            total = sum(scores)
            sentiment = "positive" if total > 0 else "negative" if total < 0 else "neutral"
            out.append({"aspect": aspect, "sentiment": sentiment})
        return {"aspects": out}


# ---------------------------------------------------------------- model

class ModelTagger:
    name = "model"

    def __init__(self, max_calls: int = 30, client: OpenAIChatClient | None = None,
                 model: str | None = None, batch_size: int = 18):
        self.client = client or OpenAIChatClient(max_calls=max_calls)
        self.model = model or model_name()
        self.batch_size = batch_size

    def tag_chat_batch(self, items: list[dict]) -> list[dict]:
        return self._ask(taxonomy.chat_prompt(), items, taxonomy.chat_schema(), "chat_tags")

    def tag_review_batch(self, items: list[dict]) -> list[dict]:
        return self._ask(taxonomy.review_prompt(), items, taxonomy.review_schema(), "review_tags")

    def _ask(self, prompt: str, items: list[dict], schema: dict, name: str) -> list[dict]:
        answer = self.client.complete_json(self.model, prompt, json.dumps(items), schema, name)
        returned = answer.get("items") if isinstance(answer, dict) else None
        return returned if isinstance(returned, list) else []


# ---------------------------------------------------------------- run

def tag_all(tagger, chats: list[dict], reviews: list[dict]) -> dict:
    """Tag everything in batches. Invalid or missing answers are recorded, not repaired.

    If the call budget runs out or the API fails, the run stops and keeps what it has.
    """
    result = {"tagger": tagger.name, "model": tagger.model, "calls": 0,
              "chats": {}, "reviews": {}, "invalid": [], "stopped": None}
    jobs = (
        ("chats", [public_chat(c) for c in chats], tagger.tag_chat_batch, taxonomy.validate_chat),
        ("reviews", [public_review(r) for r in reviews], tagger.tag_review_batch,
         taxonomy.validate_review),
    )
    for kind, items, tag_batch, validate in jobs:
        for start in range(0, len(items), tagger.batch_size):
            batch = items[start:start + tagger.batch_size]
            wanted = {item["id"] for item in batch}
            try:
                answers = tag_batch(batch)
            except (BudgetExceeded, RuntimeError) as error:
                result["stopped"] = str(error)
                break
            result["calls"] = getattr(getattr(tagger, "client", None), "calls", 0)
            for answer in answers:
                item_id = answer.get("id") if isinstance(answer, dict) else None
                if item_id not in wanted or item_id in result[kind]:
                    result["invalid"].append({"kind": kind, "id": item_id,
                                              "problems": ["unknown or repeated id"]})
                    continue
                tags = {k: v for k, v in answer.items() if k != "id"}
                problems = validate(tags)
                if problems:
                    result["invalid"].append({"kind": kind, "id": item_id, "problems": problems})
                else:
                    result[kind][item_id] = tags
            for item_id in sorted(wanted - set(result[kind])):
                if not any(e["id"] == item_id for e in result["invalid"]):
                    result["invalid"].append({"kind": kind, "id": item_id,
                                              "problems": ["no answer returned"]})
        if result["stopped"]:
            break
    return result
