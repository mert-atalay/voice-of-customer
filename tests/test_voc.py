import json
import re
from pathlib import Path

import pytest

from voc import generate, quality, questions, report, scores, summary, tagger, taxonomy
from voc.__main__ import main
from voc.client import BudgetExceeded, OpenAIChatClient

ROOT = Path(__file__).resolve().parent.parent
CHATS, REVIEWS, SITE = generate.build()


def load(name):
    return json.loads((ROOT / "data" / f"{name}.json").read_text())


def all_text():
    yield from (t["text"] for c in CHATS for t in c["turns"])
    yield from (r["text"] for r in REVIEWS)


class StubTransport:
    """Stands in for the network. Records every request and answers from a function."""

    def __init__(self, answer):
        self.answer, self.requests = answer, []

    def __call__(self, body, headers, timeout):
        self.requests.append({"body": body, "headers": headers})
        items = json.loads(body["messages"][1]["content"])
        return {"choices": [{"message": {"content": json.dumps({"items": self.answer(items)})}}]}


def echo_chat(items):
    return [{"id": i["id"], "topic": "pricing", "intent": "question", "answered": "yes",
             "signals": []} for i in items]


def echo_review(items):
    return [{"id": i["id"], "aspects": [{"aspect": "staff", "sentiment": "positive"}]}
            for i in items]


def stub_tagger(max_calls=30, chat=echo_chat, review=echo_review):
    transport = StubTransport(lambda items: chat(items) if "turns" in items[0] else review(items))
    client = OpenAIChatClient(max_calls=max_calls, api_key="test-key", transport=transport)
    return tagger.ModelTagger(client=client, model="stub-model"), transport


def review(loc, day, stars, **aspects):
    rid = f"x{review.n}"
    review.n += 1
    return ({"id": rid, "location": loc, "date": day, "stars": stars, "text": ""},
            {rid: {"aspects": [{"aspect": a, "sentiment": s} for a, s in aspects.items()]}})


review.n = 0


def review_set(rows):
    reviews, tags = [], {}
    for item, tag in rows:
        reviews.append(item)
        tags.update(tag)
    return reviews, tags


# ---------------------------------------------------------------- generator

def test_generator_is_deterministic():
    assert generate.build() == generate.build()
    assert generate.build(seed=1)[0] != CHATS


def test_committed_data_matches_the_seed():
    assert load("chats") == CHATS
    assert load("reviews") == REVIEWS
    assert load("site_pages") == SITE


def test_data_shape():
    assert len(CHATS) == 150 and len(REVIEWS) == 200
    assert all(2 <= len(c["turns"]) <= 8 for c in CHATS)
    assert all(c["turns"][0]["role"] == "user" for c in CHATS)
    assert {c["location"] for c in CHATS} | {r["location"] for r in REVIEWS} == set(generate.LOCATIONS)
    assert all(1 <= r["stars"] <= 5 for r in REVIEWS)
    assert len({t for t in all_text()}) > 250  # the text is varied, not a handful of templates


def test_intended_labels_fit_the_taxonomy():
    for chat in CHATS:
        labels = {k: v for k, v in chat["intended"].items() if k != "question_id"}
        assert taxonomy.validate_chat(labels) == []
    for item in REVIEWS:
        as_tags = {"aspects": [{"aspect": a, "sentiment": s}
                               for a, s in item["intended"]["aspects"].items()]}
        assert taxonomy.validate_review(as_tags) == []


def test_no_personal_data_patterns():
    patterns = [r"@", r"https?://", r"\d{5,}", r"\d{3}[\s.-]\d{3,4}",
                r"\b(Mr|Mrs|Ms|Dr)\b\.?\s+[A-Z]", r"\bmy name is\b", r"\bI am [A-Z][a-z]+\b"]
    for text in all_text():
        for pattern in patterns:
            assert not re.search(pattern, text), (pattern, text)


def test_site_pages_leave_common_questions_unanswered():
    covered = questions.covered_ids(SITE)
    known = set(questions.WORDING)
    assert covered <= known
    for missing in ("pricing_student", "cancel_notice", "parking_cost", "hours_holiday"):
        assert missing not in covered
    asked = {c["intended"]["question_id"] for c in CHATS
             if c["intended"]["intent"] in questions.BANK_INTENTS}
    assert asked <= known


# ---------------------------------------------------------------- taxonomy

def test_validator_accepts_good_tags():
    assert taxonomy.validate_chat({"topic": "pricing", "intent": "question", "answered": "no",
                                   "signals": ["gave_up"]}) == []
    assert taxonomy.validate_review({"aspects": []}) == []


def test_validator_rejects_bad_chat_tags():
    good = {"topic": "pricing", "intent": "question", "answered": "no", "signals": []}
    assert taxonomy.validate_chat({**good, "topic": "weather"})
    assert taxonomy.validate_chat({**good, "signals": ["angry"]})
    assert taxonomy.validate_chat({**good, "signals": ["gave_up", "gave_up"]})
    assert taxonomy.validate_chat({**good, "mood": "bad"})
    assert taxonomy.validate_chat({k: v for k, v in good.items() if k != "answered"})


def test_validator_rejects_bad_review_tags():
    assert taxonomy.validate_review({"aspects": [{"aspect": "other", "sentiment": "positive"}]})
    assert taxonomy.validate_review({"aspects": [{"aspect": "staff", "sentiment": "great"}]})
    assert taxonomy.validate_review({"aspects": [{"aspect": "staff", "sentiment": "positive"},
                                                 {"aspect": "staff", "sentiment": "negative"}]})
    assert taxonomy.validate_review({"aspects": [], "stars": 5})
    assert taxonomy.validate_review({})


def test_schemas_are_strict_and_built_from_the_taxonomy():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)

    for schema in (taxonomy.chat_schema(), taxonomy.review_schema()):
        for obj in objects(schema):
            assert obj["additionalProperties"] is False
            assert set(obj["required"]) == set(obj["properties"])
    item = taxonomy.chat_schema()["properties"]["items"]["items"]["properties"]
    assert item["topic"]["enum"] == list(taxonomy.TOPICS)
    assert all(topic in taxonomy.chat_prompt() for topic in taxonomy.TOPICS)
    assert all(aspect in taxonomy.review_prompt() for aspect in taxonomy.ASPECTS)


# ---------------------------------------------------------------- keyword tagger

def test_keyword_tagger_reads_a_clear_chat():
    chat = {"id": "t1", "turns": [
        {"role": "user", "text": "how do i cancel my membership"},
        {"role": "bot", "text": "Sorry, I did not understand that. Could you rephrase?"},
        {"role": "user", "text": "no, i mean how can I cancel"},
        {"role": "bot", "text": "I do not have that information."},
        {"role": "user", "text": "this is useless. can i talk to a person"},
        {"role": "user", "text": "forget it"}]}
    tags = tagger.KeywordTagger().tag_chat(chat)
    assert tags["topic"] == "cancellation" and tags["answered"] == "no"
    assert set(tags["signals"]) == set(taxonomy.SIGNALS)
    assert taxonomy.validate_chat(tags) == []


def test_keyword_tagger_reads_a_mixed_review_and_misses_sarcasm():
    kw = tagger.KeywordTagger()
    mixed = kw.tag_review({"id": "t", "text": "The staff are friendly but the car park is always full."})
    assert {a["aspect"]: a["sentiment"] for a in mixed["aspects"]} == {
        "staff": "positive", "parking": "negative"}
    negated = kw.tag_review({"id": "t", "text": "Never crowded when I go."})
    assert negated["aspects"] == [{"aspect": "crowding", "sentiment": "positive"}]
    # The baseline fails honestly on sarcasm. This is the kind of case a model should win.
    sarcasm = kw.tag_review({"id": "t", "text": "Love that it is packed every single evening."})
    assert sarcasm["aspects"] != [{"aspect": "crowding", "sentiment": "negative"}]


def test_keyword_run_tags_everything_validly():
    run = tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS)
    assert len(run["chats"]) == 150 and len(run["reviews"]) == 200
    assert run["invalid"] == [] and run["calls"] == 0 and run["stopped"] is None


def test_committed_keyword_results_match_the_code():
    committed = json.loads((ROOT / "results" / "keyword" / "tags.json").read_text())
    assert committed == tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS)


# ---------------------------------------------------------------- model tagger, stubbed

def test_intended_labels_are_never_sent_to_the_tagger():
    worker, transport = stub_tagger()
    tagger.tag_all(worker, CHATS, REVIEWS)
    sent = [json.loads(r["body"]["messages"][1]["content"]) for r in transport.requests]
    for items in sent:
        for item in items:
            assert set(item) in ({"id", "turns"}, {"id", "text"})
            for turn in item.get("turns", []):
                assert set(turn) == {"role", "text"}
    raw = json.dumps([r["body"] for r in transport.requests])
    assert "intended" not in raw and "question_id" not in raw and '"stars"' not in raw
    assert set(tagger.public_chat(CHATS[0])) == {"id", "turns"}
    assert set(tagger.public_review(REVIEWS[0])) == {"id", "text"}


def test_keyword_tagger_also_gets_only_the_public_view():
    seen = []

    class Spy(tagger.KeywordTagger):
        def tag_chat(self, chat):
            seen.append(set(chat))
            return super().tag_chat(chat)

        def tag_review(self, item):
            seen.append(set(item))
            return super().tag_review(item)

    tagger.tag_all(Spy(), CHATS[:5], REVIEWS[:5])
    assert all(keys in ({"id", "turns"}, {"id", "text"}) for keys in seen)


def test_model_run_fits_the_default_budget():
    worker, transport = stub_tagger()
    run = tagger.tag_all(worker, CHATS, REVIEWS)
    assert run["calls"] == len(transport.requests) == 21
    assert 20 <= run["calls"] <= 25 and run["calls"] <= 30
    assert len(run["chats"]) == 150 and len(run["reviews"]) == 200
    assert all(15 <= len(json.loads(r["body"]["messages"][1]["content"])) <= 20
               for r in transport.requests[:8])


def test_request_uses_a_strict_schema_and_a_header_key():
    worker, transport = stub_tagger()
    tagger.tag_all(worker, CHATS[:3], REVIEWS[:3])
    request = transport.requests[0]
    fmt = request["body"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert request["body"]["model"] == "stub-model"
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert "test-key" not in json.dumps(request["body"])


def test_budget_is_enforced():
    client = OpenAIChatClient(max_calls=2, api_key="k", transport=StubTransport(echo_chat))
    items = [tagger.public_chat(CHATS[0])]
    for _ in range(2):
        client.complete_json("m", "s", json.dumps(items), {}, "n")
    with pytest.raises(BudgetExceeded):
        client.complete_json("m", "s", json.dumps(items), {}, "n")
    assert client.calls == 2 and len(client.transport.requests) == 2


def test_run_stops_at_the_budget_and_keeps_what_it_has():
    worker, transport = stub_tagger(max_calls=3)
    run = tagger.tag_all(worker, CHATS, REVIEWS)
    assert len(transport.requests) == 3 and run["calls"] == 3
    assert len(run["chats"]) == 54 and run["reviews"] == {}
    assert "budget" in run["stopped"]


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIChatClient(max_calls=1)


def test_invalid_and_missing_model_answers_are_recorded_not_used():
    def bad_chat(items):
        out = echo_chat(items)
        out[0]["topic"] = "weather"          # outside the taxonomy
        out[1]["id"] = "c999"                # an id that was not asked about
        return out[:-1]                      # and the last item is missing

    worker, _ = stub_tagger(chat=bad_chat)
    run = tagger.tag_all(worker, CHATS[:18], [])
    assert len(run["chats"]) == 15
    assert len(run["invalid"]) == 4          # bad value, unknown id, and two never answered
    assert all(taxonomy.validate_chat(tags) == [] for tags in run["chats"].values())


# ---------------------------------------------------------------- scores

def test_frustration_known_answers():
    def tags(answered, *signals):
        return {"answered": answered, "signals": list(signals)}

    assert scores.frustration(tags("yes")) == 0
    assert scores.frustration(tags("partly")) == 10
    assert scores.frustration(tags("no", "gave_up")) == 50
    assert scores.frustration(tags("yes", "repeated_question", "bot_misunderstood")) == 35
    assert scores.frustration(tags("no", *taxonomy.SIGNALS)) == 100  # capped


def test_frustration_by_topic():
    chats = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "untagged"}]
    tags = {"a": {"topic": "parking", "answered": "no", "signals": ["gave_up"]},
            "b": {"topic": "parking", "answered": "yes", "signals": []},
            "c": {"topic": "trial", "answered": "partly", "signals": []}}
    out = scores.frustration_by_topic(chats, tags)
    assert out["per_chat"] == {"a": 50, "b": 0, "c": 10}
    parking = out["by_topic"][0]
    assert parking["topic"] == "parking" and parking["mean_frustration"] == 25.0
    assert parking["high_share"] == 0.5 and parking["unanswered_share"] == 0.5
    assert out["mean"] == 20.0


def test_recency_weight_halves_every_half_life():
    assert scores.recency_weight("2026-10-31", "2026-10-31") == 1.0
    assert scores.recency_weight("2026-08-02", "2026-10-31", half_life=90) == pytest.approx(0.5)
    assert scores.recency_weight("2026-05-04", "2026-10-31", half_life=90) == pytest.approx(0.25)


def test_recency_makes_recent_reviews_count_more():
    reviews, tags = review_set([
        review("A", "2026-10-31", 5, cleanliness="positive"),
        review("A", "2026-08-02", 1, cleanliness="negative"),
    ])
    out = scores.location_sentiment(reviews, tags, as_of="2026-10-31", half_life=90,
                                    prior_reviews=0)
    row = out["locations"][0]
    # weights 1 and 0.5: (100 * 1 + 0 * 0.5) / 1.5
    assert row["raw_recent"] == pytest.approx(66.7, abs=0.05)
    assert row["raw_all_time"] == 50.0
    assert row["stars_mean"] == pytest.approx((5 + 0.5) / 1.5, abs=0.01)


def test_shrinkage_known_answer():
    assert scores.shrink(100, 2, 50, 10) == pytest.approx(58.33, abs=0.01)
    assert scores.shrink(100, 0, 50, 10) == 50
    assert scores.shrink(100, 1000, 50, 10) == pytest.approx(99.5, abs=0.01)


def test_small_location_is_pulled_toward_the_chain():
    day = "2026-10-31"
    rows = [review("Big", day, 3, staff="positive") for _ in range(20)]
    rows += [review("Big", day, 3, staff="negative") for _ in range(20)]
    rows += [review("Small", day, 1, staff="negative") for _ in range(2)]
    reviews, tags = review_set(rows)
    out = scores.location_sentiment(reviews, tags, as_of=day, prior_reviews=5)
    big, small = out["locations"]
    chain = 2000 / 42
    assert out["chain_score"] == pytest.approx(chain, abs=0.05)
    assert small["raw_recent"] == 0.0
    assert small["score"] == pytest.approx(5 * chain / 7, abs=0.05)   # (2*0 + 5*chain) / 7
    assert big["score"] == pytest.approx((40 * 50 + 5 * chain) / 45, abs=0.05)
    assert small["aspects"]["staff"]["thin"] and not big["aspects"]["staff"]["thin"]


def test_stars_are_kept_apart_and_disagreement_is_flagged():
    day = "2026-10-31"
    reviews, tags = review_set(
        [review("Generous", day, 5, parking="negative") for _ in range(6)]
        + [review("Plain", day, 3, parking="neutral") for _ in range(6)])
    out = scores.location_sentiment(reviews, tags, as_of=day)
    generous, plain = out["locations"]
    assert generous["stars_100"] == 100.0 and generous["raw_recent"] == 0.0
    assert generous["stars_disagree"] and generous["odd_reviews"] == 6
    assert not plain["stars_disagree"] and plain["stars_minus_text"] == 0.0
    # changing the stars does not move the text score
    for item in reviews:
        item["stars"] = 1
    again = scores.location_sentiment(reviews, tags, as_of=day)
    assert again["locations"][0]["score"] == generous["score"]


def test_review_with_no_aspects_is_not_scored():
    reviews, tags = review_set([review("A", "2026-10-31", 4),
                                review("A", "2026-10-31", 4, staff="positive")])
    row = scores.location_sentiment(reviews, tags, prior_reviews=0)["locations"][0]
    assert row["reviews"] == 2 and row["scored_reviews"] == 1 and row["score"] == 100.0


# ---------------------------------------------------------------- question bank

def test_canonical_question_grouping():
    q = questions.canonical_question
    assert q("pricing", "do students pay less?") == "pricing_student"
    assert q("pricing", "How much is a membership") == "pricing_monthly"
    assert q("cancellation", "can i freeze my membership") == "cancel_freeze"
    assert q("cancellation", "what is the notice period to cancel") == "cancel_notice"
    assert q("cancellation", "how do I cancel") == "cancel_how"
    assert q("parking", "is parking free") == "parking_cost"
    assert q("parking", "where can i park") == "parking_available"
    assert q("billing", "something odd on my account") == "billing_general"


def test_bank_counts_and_gaps():
    def chat(cid, text):
        return {"id": cid, "turns": [{"role": "user", "text": text}]}

    def tag(topic, answered, intent="question"):
        return {"topic": topic, "intent": intent, "answered": answered, "signals": []}

    chats = ([chat(f"s{i}", "is there a student discount") for i in range(4)]
             + [chat(f"m{i}", "how much is a membership") for i in range(5)]
             + [chat("p1", "do students pay less"), chat("x1", "the showers are dirty")])
    tags = {f"s{i}": tag("pricing", "no") for i in range(4)}
    tags.update({f"m{i}": tag("pricing", "yes") for i in range(5)})
    tags["p1"] = tag("pricing", "partly")
    tags["x1"] = tag("cleanliness", "no", intent="complaint")
    frustration = {cid: 40 if cid.startswith("s") else 0 for cid in tags}
    site = {"pages": [{"path": "/membership", "answers": ["pricing_monthly"]}]}
    bank = questions.build_bank(chats, tags, frustration, site)
    rows = {row["id"]: row for row in bank}
    assert set(rows) == {"pricing_student", "pricing_monthly"}      # the complaint stays out
    student = rows["pricing_student"]
    assert student["count"] == 5 and not student["on_site"]
    assert student["unanswered_share"] == 0.9                       # (4 + 0.5) / 5
    assert student["mean_frustration"] == 32.0
    assert rows["pricing_monthly"]["on_site"]
    gaps = questions.content_gaps(bank)
    assert [g["id"] for g in gaps] == ["pricing_student"]
    assert gaps[0]["priority"] == pytest.approx(5 * 0.9 * 1.32, abs=0.05)
    assert questions.content_gaps(bank, min_count=6) == []


def test_content_gaps_on_the_data_are_ranked_and_off_site():
    result = summary.summarise(tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS),
                               CHATS, REVIEWS, SITE)
    gaps = result["content_gaps"]
    covered = questions.covered_ids(SITE)
    assert len(gaps) >= 5
    assert all(g["id"] not in covered and g["count"] >= questions.MIN_COUNT for g in gaps)
    assert [g["priority"] for g in gaps] == sorted((g["priority"] for g in gaps), reverse=True)


# ---------------------------------------------------------------- quality and report

def test_agreement_is_perfect_for_the_intended_labels_and_counts_misses():
    truth = summary.intended_run(CHATS, REVIEWS)
    perfect = quality.agreement(truth, CHATS, REVIEWS)["per_field"]
    for field in ("chat_topic", "chat_intent", "chat_answered", "chat_signals_exact",
                  "review_aspects_found", "review_sentiment", "review_exact"):
        assert perfect[field]["rate"] == 1.0, field
    del truth["chats"]["c001"]
    truth["chats"]["c002"]["topic"] = "other" if CHATS[1]["intended"]["topic"] != "other" else "staff"
    worse = quality.agreement(truth, CHATS, REVIEWS)["per_field"]
    assert worse["chat_topic"]["match"] == 148 and worse["chat_topic"]["total"] == 150
    assert worse["chat_intent"]["match"] == 149


def test_side_by_side_has_one_cell_per_tagger():
    keyword = quality.agreement(tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS),
                                CHATS, REVIEWS)
    worker, _ = stub_tagger()
    model = quality.agreement(tagger.tag_all(worker, CHATS, REVIEWS), CHATS, REVIEWS)
    rows = quality.side_by_side([keyword, model])
    assert len(rows) == len(quality.FIELD_LABELS)
    assert [c["tagger"] for c in rows[0]["cells"]] == ["keyword", "model"]


def test_report_builds_and_contains_key_numbers():
    result = summary.summarise(tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS),
                               CHATS, REVIEWS, SITE)
    html = report.render(result)
    assert "Synthetic data" in html and "<svg" in html
    assert "<script" not in html and "http://" not in html and "https://" not in html
    assert "prefers-color-scheme: dark" in html and 'name="viewport"' in html
    topic = result["agreement"]["per_field"]["chat_topic"]
    assert f'{topic["match"]}/{topic["total"]}' in html
    for row in result["locations"]["locations"]:
        assert row["location"] in html and f'{row["score"]:.1f}' in html
    assert result["content_gaps"][0]["question"] in html
    assert "keyword baseline" in html and "model (" not in html


def test_report_shows_both_taggers_when_given_two_runs():
    result = summary.summarise(tagger.tag_all(tagger.KeywordTagger(), CHATS, REVIEWS),
                               CHATS, REVIEWS, SITE)
    worker, _ = stub_tagger()
    other = quality.agreement(tagger.tag_all(worker, CHATS, REVIEWS), CHATS, REVIEWS)
    html = report.render(result, compare=[other])
    assert "keyword baseline" in html and "model (stub-model)" in html


def test_cli_end_to_end(tmp_path):
    out = tmp_path / "keyword"
    assert main(["tag", "--tagger", "keyword", "--out", str(out)]) == 0
    assert main(["score", "--out", str(out)]) == 0
    assert main(["report", "--out", str(out)]) == 0
    assert (out / "report.html").read_text().startswith("<!doctype html>")
    committed = json.loads((ROOT / "results" / "keyword" / "scores.json").read_text())
    assert json.loads((out / "scores.json").read_text()) == committed
    assert main(["score", "--out", str(tmp_path / "missing")]) == 1
