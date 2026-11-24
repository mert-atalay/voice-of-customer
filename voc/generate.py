"""Seeded generator for the synthetic data. Nothing here comes from a real business.

It writes three files:

  data/chats.json       chatbot conversations with a hidden `intended` label block
  data/reviews.json     reviews with a star rating and a hidden `intended` label block
  data/site_pages.json  which questions the invented website already answers

Text is composed from phrase fragments. Some of it is made hard on purpose: typos,
asides about another topic, sarcasm, negation, and complaints with no obvious keyword.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261124
N_CHATS = 150
LOCATIONS = ["Northgate", "Eastfield", "Quayside", "Millbrook"]
REVIEW_COUNTS = {"Northgate": 72, "Eastfield": 64, "Quayside": 50, "Millbrook": 14}
CHAT_START, CHAT_END = date(2026, 8, 1), date(2026, 10, 31)
REVIEW_START, REVIEW_END = date(2026, 2, 1), date(2026, 10, 31)

# ---------------------------------------------------------------- chats

# id: (topic, intent, weight, on_site, user phrasings, a good bot answer)
QUESTIONS: dict[str, tuple] = {
    "pricing_monthly": ("pricing", "question", 10, True, [
        "how much is a membership", "What does it cost per month?", "whats the monthly price",
        "How much do you charge a month?", "price for a standard membership?",
        "hi, what are your prices"],
        "Standard membership is 34 a month. Prices for every plan are on the Membership page."),
    "pricing_student": ("pricing", "question", 8, False, [
        "do you have a student discount", "Is there a student rate?",
        "any discount for students?", "student price??", "im a student, is it cheaper",
        "Do students pay less?"],
        "Yes. Students pay 22 a month with a valid student card."),
    "pricing_family": ("pricing", "question", 4, True, [
        "how much is the family plan", "Is there a family membership and what does it cost?",
        "price for me and my partner and two kids?", "family price?"],
        "The family plan is 59 a month. It covers two adults and children under 16."),
    "pricing_joining_fee": ("pricing", "question", 4, True, [
        "is there a joining fee", "Do I pay anything upfront?", "any sign up fee?",
        "is there an admin fee when you join"],
        "There is no joining fee at the moment. You only pay the monthly price."),
    "trial_free": ("trial", "question", 9, True, [
        "is there a free trial", "Can I try the gym before joining?", "do you do a day pass",
        "can i try it out first", "Do you offer a trial?", "free trial??"],
        "Yes. Every club offers a free three-day trial. You can start one from the Trial page."),
    "trial_book": ("trial", "request", 5, True, [
        "I want to book a trial", "id like to sign up for the free trial",
        "can you book me a trial for saturday", "How do I start a trial?",
        "need to arrange a trial session"],
        "You can book a trial on the Trial page. Pick your club and a start day."),
    "cancel_how": ("cancellation", "question", 9, True, [
        "how do i cancel", "How can I cancel my membership?", "where do I go to cancel",
        "whats the process to end my membership", "How do I leave the gym?",
        "i need to cancel, how"],
        "You can cancel in the member area under Account, or in person at your club."),
    "cancel_notice": ("cancellation", "question", 8, False, [
        "how much notice do i need to give to cancel", "What is the notice period?",
        "if i cancel today when does it stop", "how long before I can leave after cancelling",
        "Is there a notice period for cancelling?", "do i have to cancel in advance"],
        "The notice period is one full calendar month."),
    "cancel_freeze": ("cancellation", "request", 7, False, [
        "i want to pause my membership for 2 months", "Can I freeze my membership?",
        "need to freeze my account, im injured", "can you put my membership on hold",
        "How do I put my membership on hold while I travel?", "freeze membership pls"],
        "You can freeze a membership for up to three months. It is set up at your club."),
    "billing_double": ("billing", "complaint", 5, False, [
        "i was charged twice this month", "You took two payments from me in October.",
        "why have i been charged twice", "double payment on my account, not happy",
        "my statement shows the membership twice"],
        "Sorry about that. A double charge is refunded automatically within five working days."),
    "billing_date": ("billing", "question", 4, True, [
        "when do you take payment", "What day does the payment come out?",
        "can i change my payment date", "which date is the direct debit taken"],
        "Payment is taken on the first of each month. You can change the date in the member area."),
    "billing_refund": ("billing", "request", 4, False, [
        "i want a refund for last month", "How do I get my money back?",
        "please refund the payment from last week", "can i get a refund, i didnt use it at all"],
        "Refund requests go to your club. They reply within five working days."),
    "hours_opening": ("schedule_hours", "question", 9, True, [
        "what are your opening hours", "What time do you open?", "when do you close tonight",
        "are you open on sundays", "opening hours?", "what time does the gym close on saturday",
        "when do you shut on sundays"],
        "All clubs are open 6am to 10pm on weekdays and 8am to 8pm at weekends."),
    "hours_holiday": ("schedule_hours", "question", 7, False, [
        "are you open on the bank holiday", "What are the holiday opening hours?",
        "hours over christmas?", "are you open new years day",
        "Is the gym open on public holidays?", "holiday hours"],
        "On public holidays all clubs open 9am to 5pm."),
    "classes_timetable": ("classes", "question", 7, True, [
        "what classes do you have", "When is the yoga class?", "where can i see the timetable",
        "is there a spin class on weekday evenings", "class schedule please",
        "What classes are on this week?"],
        "The class timetable for each club is on the Classes page. It is updated every Friday."),
    "classes_book": ("classes", "question", 5, True, [
        "how do i book a class", "Do I need to reserve a place in classes?",
        "how far ahead can i book spin", "can i book classes online"],
        "You can book classes up to seven days ahead on the Classes page or in the member area."),
    "classes_beginner": ("classes", "question", 4, True, [
        "are there classes for beginners", "I have never done a class, which one should I pick?",
        "im new to this, any easy classes", "do you run intro classes"],
        "Yes. Classes marked Intro on the timetable are for beginners."),
    "facilities_pool": ("facilities", "question", 5, True, [
        "do you have a pool", "Is there a sauna?", "which clubs have a swimming pool",
        "sauna or steam room?"],
        "Quayside and Northgate have a pool and sauna. Eastfield and Millbrook do not."),
    "facilities_lockers": ("facilities", "question", 4, True, [
        "are there lockers", "Do I need to bring my own padlock?", "do you provide towels",
        "are there showers"],
        "Lockers and showers are free in every club. Bring your own padlock and towel."),
    "facilities_childcare": ("facilities", "question", 6, False, [
        "do you have childcare", "Is there a creche?", "can i bring my kids while i train",
        "is there somewhere for children during classes", "any childcare at the gym?"],
        "Northgate has a supervised kids' room on weekday mornings."),
    "crowding_quiet": ("crowding", "question", 8, False, [
        "when is the gym quiet", "What are the quiet times?", "how busy is it at 6pm",
        "when is it least crowded", "best time to come to avoid the rush?",
        "is it busy on weekday mornings"],
        "Clubs are usually quietest between 1pm and 4pm on weekdays."),
    "crowding_complaint": ("crowding", "complaint", 3, False, [
        "its far too busy in the evenings, i cant get on anything",
        "The gym is overcrowded after work. Something needs to change.",
        "queued 15 minutes for a bench yesterday"],
        "Sorry to hear that. I have noted it for the club team."),
    "cleanliness_complaint": ("cleanliness", "complaint", 3, False, [
        "the changing rooms were dirty this morning", "Showers have not been cleaned in days.",
        "there is never any spray to wipe the machines, its not hygienic"],
        "Sorry to hear that. I have noted it for the club team."),
    "parking_available": ("parking", "question", 6, True, [
        "is there parking", "Do you have a car park?", "where can i park",
        "is there somewhere to lock a bike", "parking at the gym?"],
        "Every club has a car park. Bike racks are by the entrance."),
    "parking_cost": ("parking", "question", 6, False, [
        "is parking free", "Do members pay for parking?", "how much is parking",
        "do i have to pay to park", "is the car park free for members"],
        "Parking is free for members for up to three hours."),
    "staff_pt": ("staff", "question", 5, True, [
        "do you offer personal training", "Can I get a personal trainer?",
        "how do i book a pt session", "is there a coach who can show me the machines"],
        "Yes. Personal training can be booked on the Coaching page."),
    "staff_praise": ("staff", "praise", 2, False, [
        "just wanted to say the morning team are great",
        "The trainer who ran my induction was brilliant, please pass on my thanks.",
        "your front desk staff are lovely"],
        "Thank you. I will pass that on to the team."),
    "other_guest": ("other", "question", 6, False, [
        "can i bring a friend", "Do you do guest passes?", "can my sister come with me once",
        "am i allowed to bring a guest", "bring a friend for free?"],
        "Members can bring one guest a month for free."),
    "other_lost": ("other", "request", 2, False, [
        "i left my water bottle yesterday, do you have lost property",
        "I lost my headphones at the gym. Can you check?"],
        "Lost property is kept at each club for 30 days."),
}

PARTIAL = {
    "pricing": "Our prices are on the Membership page. For discounts please check with your club.",
    "trial": "We offer trials at every club. Please check the Trial page for details.",
    "cancellation": "Membership changes are handled in the member area. For details please check with your club.",
    "billing": "Billing is handled by your club. Please check with them.",
    "schedule_hours": "Our usual opening hours are on the Clubs page. Some days differ, so please check with your club.",
    "classes": "We run classes every day. Please check the Classes page.",
    "facilities": "Facilities differ by club. Please check the Clubs page.",
    "cleanliness": "Thanks for telling us. Please check with your club so they can look at it.",
    "crowding": "Busy times differ by club. Please check with your club.",
    "staff": "Our team can help with that. Please check with your club.",
    "parking": "Most clubs have parking nearby. Please check with your club for details.",
    "other": "Your club can help with that. Please check with them.",
}
FALLBACK = [
    "Sorry, I did not understand that. Could you rephrase?",
    "I am not sure I follow. Can you say that another way?",
    "I can help with memberships, classes and opening hours. What would you like to know?",
]
NO_ANSWER = ["Sorry, I do not have an answer for that.", "I do not have that information."]
NO_DETAIL = "I do not have that detail. Your club can confirm it."
NO_HUMAN = "I cannot transfer this chat. The front desk can help during opening hours."
CLOSING = ["You are welcome. Anything else?", "Happy to help."]
SORRY = "Sorry I could not help more."

THANKS = ["thanks", "ok thank you", "perfect thx", "great, thanks!", "cheers", "ok", "got it, thanks"]
# Said after a good answer. They contain words a keyword rule reads as frustration.
FALSE_ALARMS = ["never mind, found it on the page too. thanks",
                "ok ill just book online then, thanks",
                "a person at the desk told me something different but ok, thanks",
                "not useless after all :) thanks",
                "oh i asked the wrong thing but that helps anyway"]
REPHRASE_PREFIX = ["", "", "no, i mean ", "thats not what i asked. ", "again: ", "no. "]
FOLLOW_UP = ["ok but that doesnt answer it", "yes but what about my question",
             "that is quite general", "so is that a yes or a no"]
HUMAN = ["can i talk to a person", "is there a human i can speak to", "real person please",
         "agent", "get me someone from the front desk", "Can I speak to a member of staff?",
         "is anyone actually there"]
# The second half has no obvious negative word.
NEGATIVE = ["this is useless", "what a waste of time", "ridiculous", "this bot is terrible",
            "not helpful at all", "this is so annoying",
            "great, very helpful.", "wow thanks for nothing", "brilliant. really.",
            "ok so you dont know anything", "ugh"]
GAVE_UP = ["forget it", "never mind", "nvm", "ill just call the gym", "i give up",
           "whatever, ill ask at the desk", "ok I'll figure it out myself", "thanks anyway"]
ASIDES = [("parking", " btw the car park was full last time"),
          ("classes", " my friend says the classes are good"),
          ("pricing", " i saw the price went up"),
          ("staff", " the front desk was closed when i came by"),
          ("crowding", " it was really busy when i visited")]


def messy(rng: random.Random, text: str) -> str:
    """Make a message look typed in a hurry: lower case, lost punctuation, a swapped letter."""
    if rng.random() < 0.3:
        text = text.lower()
    if rng.random() < 0.2:
        text = text.replace("'", "")
    if rng.random() < 0.3:
        text = text.rstrip("?.")
    if rng.random() < 0.15:
        words = text.split(" ")
        long = [i for i, w in enumerate(words) if len(w) >= 6 and w.isalpha()]
        if long:
            i = rng.choice(long)
            k = rng.randrange(1, len(words[i]) - 2)
            w = words[i]
            words[i] = w[:k] + w[k + 1] + w[k] + w[k + 2:]
            text = " ".join(words)
    return text


def _day(rng: random.Random, start: date, end: date) -> str:
    return (start + timedelta(days=rng.randrange((end - start).days + 1))).isoformat()


def _outcome(rng: random.Random, intent: str, on_site: bool) -> str:
    if intent == "praise":
        return "yes"
    if intent == "complaint":
        weights = [20, 50, 30]
    elif on_site:
        weights = [72, 17, 11]
    else:
        weights = [10, 35, 55]
    return rng.choices(["yes", "partly", "no"], weights)[0]


def _wrong_answer(rng: random.Random, topic: str) -> str:
    others = [q for q in QUESTIONS.values() if q[0] != topic and q[1] != "praise"]
    return rng.choice(others)[5]


def make_chat(rng: random.Random, index: int) -> dict:
    ids = list(QUESTIONS)
    qid = rng.choices(ids, [QUESTIONS[i][2] for i in ids])[0]
    topic, intent, _, on_site, asks, answer = QUESTIONS[qid]
    outcome = _outcome(rng, intent, on_site)
    turns: list[dict] = []
    signals: set[str] = set()

    def user(text: str) -> None:
        turns.append({"role": "user", "text": messy(rng, text)})

    def bot(text: str) -> None:
        turns.append({"role": "bot", "text": text})

    def miss() -> None:
        """The bot fails: a fallback line or a confident answer to something else."""
        bot(rng.choice(FALLBACK) if rng.random() < 0.55 else _wrong_answer(rng, topic))
        signals.add("bot_misunderstood")

    def rephrase(first: str) -> None:
        other = rng.choice([a for a in asks if a != first] or asks)
        user(rng.choice(REPHRASE_PREFIX) + other)
        signals.add("repeated_question")

    def tail(p_human: float, p_negative: float, p_gave_up: float) -> None:
        if rng.random() < p_human and len(turns) <= 6:
            user(rng.choice(HUMAN))
            bot(NO_HUMAN)
            signals.add("asked_for_human")
        if rng.random() < p_negative and len(turns) <= 7:
            user(rng.choice(NEGATIVE))
            signals.add("negative_language")
        if rng.random() < p_gave_up and len(turns) <= 7:
            user(rng.choice(GAVE_UP))
            signals.add("gave_up")
            if len(turns) <= 7 and rng.random() < 0.3:
                bot(SORRY)

    first = rng.choice(asks)
    aside = rng.choice(ASIDES)
    opening = first
    if intent != "praise" and aside[0] != topic and rng.random() < 0.12:
        opening = first.rstrip("?.") + "." + aside[1]
    user(opening)

    if outcome == "yes":
        if intent != "praise" and rng.random() < 0.2:
            miss()
            rephrase(first)
        bot(answer)
        if rng.random() < 0.6:
            user(rng.choice(FALSE_ALARMS) if rng.random() < 0.2 else rng.choice(THANKS))
            if rng.random() < 0.5:
                bot(rng.choice(CLOSING))
    elif outcome == "partly":
        bot(PARTIAL[topic])
        if rng.random() < 0.7:
            if rng.random() < 0.5:
                rephrase(first)
            else:
                user(rng.choice(FOLLOW_UP))
            bot(NO_DETAIL)
            tail(0.25, 0.3, 0.3)
        elif rng.random() < 0.4:
            user(rng.choice(["ok", "right ok", "hm ok"]))
    else:
        if rng.random() < 0.7:
            miss()
        else:
            bot(rng.choice(NO_ANSWER))
        if rng.random() < 0.75:
            rephrase(first)
            if rng.random() < 0.6:
                miss()
            else:
                bot(rng.choice(NO_ANSWER))
        tail(0.4, 0.45, 0.5)

    assert 2 <= len(turns) <= 8
    return {
        "id": f"c{index:03d}",
        "location": rng.choices(LOCATIONS, [35, 30, 25, 10])[0],
        "date": _day(rng, CHAT_START, CHAT_END),
        "turns": turns,
        "intended": {"question_id": qid, "topic": topic, "intent": intent,
                     "answered": outcome, "signals": sorted(signals)},
    }


# ---------------------------------------------------------------- reviews

# aspect: (weight, chance of positive, positive, negative, neutral fragments)
FRAGMENTS: dict[str, tuple] = {
    "staff": (16, 0.75, [
        "the staff are friendly and remember you", "front desk team are always helpful",
        "the trainers actually know what they are doing", "staff were welcoming from day one",
        "great coaches, really patient with beginners"], [
        "the front desk staff are rude", "staff spend more time on their phones than helping",
        "trainers ignore you unless you pay for sessions",
        "reception was unhelpful when I had a problem", "staff seem bored and unfriendly"], [
        "staff are there if you need them", "front desk is staffed most of the day"]),
    "cleanliness": (14, 0.6, [
        "the place is spotless", "changing rooms are always clean",
        "everything gets wiped down regularly", "very clean and it smells fresh",
        "cleanest gym I have used"], [
        "the changing rooms are dirty", "the changing area is filthy and it smells",
        "sweat left on the benches and nobody cleans it", "bins overflowing in the changing room",
        "the toilets were disgusting on my last visit"], [
        "cleanliness is about what you would expect", "cleaners come round in the afternoon"]),
    "crowding": (13, 0.35, [
        "never too busy when I go", "plenty of space even at peak time",
        "it is quiet in the mornings which I like", "I rarely have to wait for anything"], [
        "it is packed after work", "way too crowded in the evenings",
        "you have to queue for everything", "too many people and not enough room",
        "so busy at 6pm that I gave up and left"], [
        "it gets busy at the usual times", "busier in January like everywhere"]),
    "facilities": (13, 0.65, [
        "the equipment is new and well kept", "great range of machines and free weights",
        "the pool and sauna are a real bonus", "lockers and showers are good",
        "loads of kit, never short of dumbbells"], [
        "half the machines are broken", "the equipment is old and worn out",
        "showers are cold more often than not", "lockers are broken and too small",
        "the sauna has been out of order for weeks"], [
        "equipment is standard, nothing special",
        "it has the usual machines and a small free weights area"]),
    "classes": (12, 0.75, [
        "the classes are excellent", "spin class is the best part of my week",
        "great variety of classes and good instructors", "yoga classes are well run",
        "the class timetable has something every evening"], [
        "classes are always fully booked", "classes get cancelled at short notice",
        "the class timetable keeps changing", "the class instructors just go through the motions",
        "impossible to book a class unless you do it a week ahead"], [
        "classes are the usual mix", "there are classes most days"]),
    "pricing": (10, 0.5, [
        "good value for the price", "the membership is cheap for what you get",
        "fair price and no hidden fees", "worth the monthly fee"], [
        "it is overpriced", "the price went up twice this year",
        "too expensive for what it is", "hidden fees on top of the membership price"], [
        "prices are about the same as other gyms nearby", "membership price is average"]),
    "parking": (8, 0.4, [
        "parking is easy and free", "big car park right outside",
        "I always find a parking space", "plenty of bike racks and parking"], [
        "parking is a nightmare", "the car park is always full",
        "you have to pay for parking on top of membership", "nowhere to park after 5pm"], [
        "parking is on the street behind the building", "there is a small car park"]),
    "cancellation": (5, 0.25, [
        "cancelling was simple, no fuss",
        "they let me freeze my membership without any hassle"], [
        "cancelling is made as hard as possible", "it took three attempts to cancel my membership",
        "they would not let me cancel without a month of notice nobody mentioned",
        "trying to freeze my membership was a pain"], [
        "you need to give a month of notice to cancel"]),
    "billing": (4, 0.2, [
        "billing has always been correct", "they refunded a wrong charge quickly"], [
        "I was charged twice and it took weeks to fix", "they kept taking payments after I left",
        "billing mistakes every few months", "still waiting for my refund"], [
        "payment comes out on the first of the month"]),
    "schedule_hours": (3, 0.6, [
        "opening hours are great, open early and late", "love that it opens at 6am"], [
        "it closes too early at weekends", "the holiday opening hours were useless"], [
        "it is open until 10pm on weekdays"]),
    "trial": (2, 0.7, [
        "the free trial made it easy to decide", "did the trial and signed up the same week"], [
        "the free trial came with a hard sell", "the trial was not really free"], [
        "I joined after the three-day trial"]),
}

# Fragments a keyword rule is likely to get wrong: sarcasm, negation, no obvious keyword.
TRICKY: list[tuple[str, str, str]] = [
    ("crowding", "negative", "love waiting twenty minutes for a squat rack"),
    ("crowding", "negative", "I now go at 5am just to get a bench"),
    ("crowding", "negative", "good luck finding a free treadmill after work"),
    ("crowding", "positive", "never crowded when I go"),
    ("crowding", "positive", "no queues, ever"),
    ("cleanliness", "negative", "the changing room floor could do with meeting a mop"),
    ("cleanliness", "negative", "great if you enjoy other people's sweat on the benches"),
    ("cleanliness", "negative", "not clean, simple as that"),
    ("cleanliness", "positive", "not a speck of dust anywhere"),
    ("staff", "positive", "cannot fault the staff"),
    ("staff", "positive", "nothing is too much trouble for the front desk"),
    ("staff", "negative", "the front desk greeting is a grunt, if you are lucky"),
    ("parking", "negative", "parking is fun if you like circling for half an hour"),
    ("pricing", "negative", "amazing how the price finds a way to go up every few months"),
    ("pricing", "positive", "not expensive at all for what you get"),
    ("facilities", "negative", "the sauna works about as often as a solar eclipse"),
    ("cancellation", "positive", "they cancelled my membership the same day I asked"),
    ("billing", "negative", "my bank statement shows two payments for one month, again"),
    ("classes", "negative", "the spin class would be lovely if it ever ran"),
]

OPENERS = ["Been a member for about a year.", "Joined in the spring.",
           "Switched from another gym.", "I go three times a week.", "Member since last winter.",
           "First gym I have stuck with."]
CLOSERS = {"positive": ["Would recommend.", "Happy here.", "Glad I joined."],
           "negative": ["Not renewing.", "Looking elsewhere.", "Would not recommend."],
           "mixed": ["Could be better.", "Three stars from me.", "Mixed feelings."]}
VALUE = {"negative": 0.0, "neutral": 0.5, "positive": 1.0}


def _positive_chance(aspect: str, location: str, day: str) -> float:
    """Each location has a planted profile, so the report has something to find."""
    base = FRAGMENTS[aspect][1]
    if location == "Northgate" and aspect == "crowding":
        return 0.12
    if location == "Eastfield" and aspect == "cleanliness":
        # Cleaning was poor until mid August, then fixed. Recency weighting should show it.
        return 0.12 if day < "2026-08-15" else 0.85
    if location == "Quayside":
        return {"parking": 0.08, "facilities": 0.9}.get(aspect, base)
    if location == "Millbrook":
        return {"staff": 0.92, "classes": 0.88}.get(aspect, base)
    return base


def _aspect_weight(aspect: str, location: str) -> float:
    weight = FRAGMENTS[aspect][0]
    boost = {("Northgate", "crowding"): 1.8, ("Eastfield", "cleanliness"): 1.8,
             ("Quayside", "parking"): 2.2, ("Quayside", "facilities"): 1.4}
    return weight * boost.get((location, aspect), 1.0)


def _sentence(text: str) -> str:
    return text[0].upper() + text[1:]


def make_review(rng: random.Random, index: int, location: str) -> dict:
    day = _day(rng, REVIEW_START, REVIEW_END)
    count = rng.choices([1, 2, 3], [35, 45, 20])[0]
    aspects: list[str] = []
    pool = list(FRAGMENTS)
    while len(aspects) < count:
        pick = rng.choices(pool, [_aspect_weight(a, location) for a in pool])[0]
        pool.remove(pick)
        aspects.append(pick)

    parts: list[tuple[str, str, str]] = []
    for aspect in aspects:
        tricky = [t for t in TRICKY if t[0] == aspect]
        if tricky and rng.random() < 0.14:
            parts.append(rng.choice(tricky))
            continue
        roll = rng.random()
        if roll < 0.12:
            sentiment = "neutral"
        else:
            good = rng.random() < _positive_chance(aspect, location, day)
            sentiment = "positive" if good else "negative"
        options = FRAGMENTS[aspect][{"positive": 2, "negative": 3, "neutral": 4}[sentiment]]
        parts.append((aspect, sentiment, rng.choice(options)))

    text = _sentence(parts[0][2])
    for previous, part in zip(parts, parts[1:]):
        opposite = {previous[1], part[1]} == {"positive", "negative"}
        if opposite:
            joiner = rng.choice([" but ", ". However ", ", though ", ". On the other hand "])
        else:
            joiner = rng.choice([" and ", ". ", ". Also "])
        text += joiner + (_sentence(part[2]) if joiner.endswith(". ") else part[2])
    text += "."

    mean = sum(VALUE[p[1]] for p in parts) / len(parts)
    kind = "positive" if mean > 0.7 else "negative" if mean < 0.3 else "mixed"
    if rng.random() < 0.3:
        text = rng.choice(OPENERS) + " " + text
    if rng.random() < 0.35:
        text += " " + rng.choice(CLOSERS[kind])
    if rng.random() < 0.25:
        text = messy(rng, text)

    # Stars follow the text loosely. Quayside reviewers are generous with stars, and a few
    # reviews anywhere give stars that do not match what they wrote.
    stars = 1 + 4 * mean + rng.gauss(0, 0.6) + (1.2 if location == "Quayside" else 0.0)
    if rng.random() < 0.05:
        stars = rng.choice([1, 5])
    stars = max(1, min(5, round(stars)))
    return {
        "id": f"r{index:03d}",
        "location": location,
        "date": day,
        "stars": stars,
        "text": text,
        "intended": {"aspects": {p[0]: p[1] for p in parts}},
    }


# ---------------------------------------------------------------- site pages

SITE_PAGES = [
    ("/membership", "Membership and prices"),
    ("/trial", "Free trial"),
    ("/help/cancel", "How to cancel"),
    ("/help/payments", "Payments"),
    ("/clubs", "Clubs, opening hours and facilities"),
    ("/classes", "Classes and timetable"),
    ("/coaching", "Personal training"),
]
PAGE_OF = {
    "pricing_monthly": "/membership", "pricing_family": "/membership",
    "pricing_joining_fee": "/membership", "trial_free": "/trial", "trial_book": "/trial",
    "cancel_how": "/help/cancel", "billing_date": "/help/payments",
    "hours_opening": "/clubs", "facilities_pool": "/clubs", "facilities_lockers": "/clubs",
    "parking_available": "/clubs", "classes_timetable": "/classes", "classes_book": "/classes",
    "classes_beginner": "/classes", "staff_pt": "/coaching",
}


def site_pages() -> dict:
    return {
        "note": "Synthetic. Which canonical questions the invented website already answers.",
        "pages": [{"path": path, "title": title,
                   "answers": [q for q, p in PAGE_OF.items() if p == path]}
                  for path, title in SITE_PAGES],
    }


# ---------------------------------------------------------------- build

def build(seed: int = SEED) -> tuple[list[dict], list[dict], dict]:
    rng = random.Random(seed)
    chats = [make_chat(rng, i + 1) for i in range(N_CHATS)]
    places = [loc for loc, n in REVIEW_COUNTS.items() for _ in range(n)]
    rng.shuffle(places)
    reviews = [make_review(rng, i + 1, loc) for i, loc in enumerate(places)]
    return chats, reviews, site_pages()


def write(data_dir: Path, seed: int = SEED) -> tuple[int, int]:
    chats, reviews, pages = build(seed)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (("chats", chats), ("reviews", reviews), ("site_pages", pages)):
        (data_dir / f"{name}.json").write_text(json.dumps(payload, indent=1) + "\n")
    return len(chats), len(reviews)
