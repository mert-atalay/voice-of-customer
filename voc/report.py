"""One self-contained HTML report. Inline CSS and inline SVG, no scripts, no requests."""

from __future__ import annotations

from html import escape

from . import quality, scores
from .taxonomy import ASPECTS, SIGNALS

CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--line:#e1e0d9;--axis:#c3c2b7;--blue:#2a78d6;--orange:#eb6834;--grey:#c3c2b7;
--banner:#fff4d6;--banner-ink:#4a3a00;
--s0:#f6b99f;--s1:#fbe0d4;--s2:#f0efec;--s3:#cde2fb;--s4:#9ec5f4}
@media (prefers-color-scheme: dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--line:#2c2c2a;--axis:#383835;--blue:#3987e5;--orange:#d95926;
--grey:#52514e;--banner:#3a3000;--banner-ink:#ffe9a8;
--s0:#8a3413;--s1:#55291a;--s2:#383835;--s3:#163a66;--s4:#1c5cab}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1160px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:26px;line-height:1.2;margin:0 0 4px}
h2{font-size:17px;margin:0 0 2px}
p{margin:0 0 10px}
.sub{color:var(--ink2);margin:0 0 14px}
.note{color:var(--ink2);font-size:13px;margin:0 0 12px}
.banner{background:var(--banner);color:var(--banner-ink);border-radius:8px;padding:10px 14px;
margin:0 0 16px;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 16px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:26px;line-height:1.15;font-weight:650}
.tile span{color:var(--ink2);font-size:13px}
.grid{display:grid;grid-template-columns:1fr;gap:16px;margin:0 0 16px}
@media (min-width:900px){.grid{grid-template-columns:1fr 1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;
min-width:0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12.5px;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:0}
svg{display:block;width:100%}
svg text{font:13px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--ink)}
svg text.m{fill:var(--ink2)}
.bar{fill:var(--blue)}.neg{fill:var(--orange)}.neu{fill:var(--grey)}.pos{fill:var(--blue)}
.track{fill:var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--ink2);margin:0 0 8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.heat td.c{text-align:center;padding:6px 4px;border:2px solid var(--surface);min-width:58px;
font-variant-numeric:tabular-nums;border-radius:6px}
.heat td.c small{display:block;color:var(--ink2);font-size:11px;line-height:1.1}
.heat td.thin{outline:1px dashed var(--muted);outline-offset:-4px}
.heat th{white-space:normal;text-align:center;padding:6px 4px;font-size:12px}
.heat th:first-child,.heat td:first-child{text-align:left;white-space:nowrap;padding-right:10px}
.s0{background:var(--s0)}.s1{background:var(--s1)}.s2{background:var(--s2)}
.s3{background:var(--s3)}.s4{background:var(--s4)}
.flag{display:inline-block;border:1px solid var(--axis);border-radius:10px;padding:0 8px;
font-size:12px;white-space:nowrap}
.mini{display:inline-block;vertical-align:middle;width:70px;height:8px;background:var(--line);
border-radius:4px;overflow:hidden;margin-right:8px}
.mini i{display:block;height:8px;background:var(--blue);border-radius:4px}
footer{color:var(--ink2);font-size:13px;margin-top:8px}
"""

ROW = 26  # px per bar row


def _name(key: str) -> str:
    return key.replace("_", " ")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _bars(rows: list[tuple[str, float, str, str]], maximum: float) -> str:
    """Horizontal bars. Each row is (label, value, text after the bar, tooltip)."""
    height = len(rows) * ROW + 4
    parts = [f'<svg height="{height}" role="img">']
    for i, (label, value, after, tip) in enumerate(rows):
        y = i * ROW
        width = max(0.4, 42 * value / maximum) if maximum else 0.4
        parts.append(
            f'<g><title>{escape(tip)}</title>'
            f'<text x="0" y="{y + 17}">{escape(label)}</text>'
            f'<rect class="bar" x="36%" y="{y + 6}" width="{width:.2f}%" height="14" rx="3"/>'
            f'<text class="m" x="{36 + width + 1.2:.2f}%" y="{y + 17}">{escape(after)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _stacked(rows: list[dict]) -> str:
    """Review aspects: mentions split into negative, neutral and positive."""
    maximum = max((r["mentions"] for r in rows), default=1)
    height = len(rows) * ROW + 4
    parts = [f'<svg height="{height}" role="img">']
    for i, row in enumerate(rows):
        y, x = i * ROW, 36.0
        tip = (f'{_name(row["aspect"])}: {row["negative"]} negative, {row["neutral"]} neutral, '
               f'{row["positive"]} positive')
        parts.append(f'<g><title>{escape(tip)}</title>'
                     f'<text x="0" y="{y + 17}">{escape(_name(row["aspect"]))}</text>')
        for key, cls in (("negative", "neg"), ("neutral", "neu"), ("positive", "pos")):
            width = 52 * row[key] / maximum
            if width <= 0:
                continue
            parts.append(f'<rect class="{cls}" x="{x:.2f}%" y="{y + 6}" '
                         f'width="{max(0.1, width - 0.3):.2f}%" height="14" rx="2"/>')
            x += width
        parts.append(f'<text class="m" x="{x + 1.0:.2f}%" y="{y + 17}">{row["mentions"]}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _band(score: float) -> str:
    return "s0" if score < 30 else "s1" if score < 45 else "s2" if score <= 55 else \
        "s3" if score <= 70 else "s4"


def _themes(result: dict) -> str:
    topics = result["themes"]["chat_topics"]
    total = sum(t["count"] for t in topics) or 1
    rows = [(_name(t["topic"]), t["count"], f'{t["count"]}  ({t["count"] / total:.0%})',
             f'{_name(t["topic"])}: {t["count"]} conversations') for t in topics]
    chat = _bars(rows, max((t["count"] for t in topics), default=1))
    intents = ", ".join(f"{n} {_name(k)}" for k, n in result["themes"]["chat_intents"].items())
    return (
        '<div class="grid"><section class="card"><h2>Top themes in chats</h2>'
        f'<p class="note">Conversations by main topic. By intent: {escape(intents)}.</p>{chat}'
        '</section><section class="card"><h2>Top themes in reviews</h2>'
        '<p class="note">Mentions of each aspect, split by the sentiment of the mention.</p>'
        '<div class="legend"><span><i style="background:var(--orange)"></i>negative</span>'
        '<span><i style="background:var(--grey)"></i>neutral</span>'
        '<span><i style="background:var(--blue)"></i>positive</span></div>'
        f'{_stacked(result["themes"]["review_aspects"])}</section></div>')


def _frustration(result: dict) -> str:
    rows = sorted(result["frustration"]["by_topic"],
                  key=lambda r: (-r["mean_frustration"], r["topic"]))
    body = "".join(
        f'<tr><td>{escape(_name(r["topic"]))}</td>'
        f'<td class="n"><span class="mini"><i style="width:{r["mean_frustration"]:.0f}%"></i>'
        f'</span>{r["mean_frustration"]:.0f}</td><td class="n">{r["count"]}</td>'
        f'<td class="n">{_pct(r["high_share"])}</td>'
        f'<td class="n">{_pct(r["unanswered_share"])}</td></tr>' for r in rows)
    return ('<section class="card"><h2>Frustration by topic</h2>'
            '<p class="note">Mean frustration score per conversation, 0 to 100. "High" is the '
            f'share of conversations scoring {scores.HIGH_FRUSTRATION} or more. Topics with few '
            'chats are noisy.</p><div class="scroll"><table><tr><th>Topic</th>'
            '<th class="n">Mean frustration</th><th class="n">Chats</th><th class="n">High</th>'
            f'<th class="n">Unanswered</th></tr>{body}</table></div></section>')


def _gaps(result: dict) -> str:
    gaps = result["content_gaps"]
    top = max((g["priority"] for g in gaps), default=1) or 1
    body = "".join(
        f'<tr><td class="n">{i}</td><td>{escape(g["question"])}<br>'
        f'<span class="note">{escape(_name(g["topic"]))}</span></td>'
        f'<td class="n">{g["count"]}</td><td class="n">{_pct(g["unanswered_share"])}</td>'
        f'<td class="n">{g["mean_frustration"]:.0f}</td>'
        f'<td class="n"><span class="mini"><i style="width:{100 * g["priority"] / top:.0f}%"></i>'
        f'</span>{g["priority"]:.1f}</td></tr>'
        for i, g in enumerate(gaps, 1))
    bank = result["question_bank"]
    asked = sum(r["count"] for r in bank) or 1
    missing = sum(r["count"] for r in bank if not r["on_site"] and not r["general_bucket"])
    return ('<section class="card"><h2>Content gaps</h2>'
            f'<p class="note">Questions people ask the bot that the website does not answer, '
            f'ranked by how often they come up, how badly the bot answers them and how '
            f'frustrated people get. They make up {missing} of the {asked} questions and '
            f'requests in the bank ({missing / asked:.0%}).</p>'
            '<div class="scroll"><table><tr><th class="n">#</th><th>Question</th>'
            '<th class="n">Asked</th><th class="n">Unanswered</th><th class="n">Frustration</th>'
            f'<th class="n">Priority</th></tr>{body}</table></div></section>')


def _locations(result: dict) -> str:
    loc = result["locations"]
    rows = []
    for row in loc["locations"]:
        gap = row["stars_minus_text"]
        if row["stars_disagree"]:
            flag = f'<span class="flag">{"stars higher" if gap > 0 else "stars lower"}</span>'
        else:
            flag = "close"
        rows.append(
            f'<tr><td>{escape(row["location"])}</td><td class="n">{row["reviews"]}</td>'
            f'<td class="n"><span class="mini"><i style="width:{row["score"]:.0f}%"></i></span>'
            f'<b>{row["score"]:.1f}</b></td><td class="n">{row["raw_recent"]:.1f}</td>'
            f'<td class="n">{row["raw_all_time"]:.1f}</td>'
            f'<td class="n">{row["stars_mean"]:.2f}</td><td class="n">{row["stars_100"]:.1f}</td>'
            f'<td class="n">{gap:+.1f}</td><td>{flag}</td></tr>')
    used = [a for a in ASPECTS if any(a in row["aspects"] for row in loc["locations"])]
    head = "".join(f"<th>{escape(_name(a))}</th>" for a in used)
    heat = []
    for row in loc["locations"]:
        cells = []
        for a in used:
            cell = row["aspects"].get(a)
            if not cell:
                cells.append('<td class="c">-</td>')
                continue
            thin = " thin" if cell["thin"] else ""
            cells.append(f'<td class="c {_band(cell["score"])}{thin}">{cell["score"]:.0f}'
                         f'<small>n={cell["mentions"]}</small></td>')
        heat.append(f'<tr><td>{escape(row["location"])}</td>{"".join(cells)}</tr>')
    return (
        '<section class="card" style="margin-bottom:16px"><h2>Sentiment by location</h2>'
        f'<p class="note">Score from review text, 0 to 100. Recent reviews count more '
        f'(half-life {loc["half_life_days"]} days, as of {escape(loc["as_of"])}) and each location '
        f'is pulled toward the chain average of {loc["chain_score"]} as if it had '
        f'{loc["prior_reviews"]} extra average reviews. Stars are not part of the score. '
        f'A location is flagged when stars and text differ by {scores.STAR_GAP_FLAG} points or '
        'more.</p><div class="scroll"><table><tr><th>Location</th><th class="n">Reviews</th>'
        '<th class="n">Sentiment score</th><th class="n">Before shrinkage</th>'
        '<th class="n">No recency weight</th><th class="n">Mean stars</th>'
        '<th class="n">Stars as 0-100</th><th class="n">Stars minus text</th>'
        f'<th>Stars vs text</th></tr>{"".join(rows)}</table></div>'
        '<p class="note" style="margin-top:14px">By aspect. Orange is negative, blue is positive, '
        f'grey is near the middle. A dashed cell has fewer than {scores.THIN_MENTIONS} mentions '
        'and mostly shows the chain average.</p>'
        f'<div class="scroll"><table class="heat"><tr><th>Location</th>{head}</tr>'
        f'{"".join(heat)}</table></div></section>')


def _agreement(result: dict, compare: list[dict]) -> str:
    reports = sorted([result["agreement"], *compare],
                     key=lambda r: (r["tagger"] != "keyword", r["tagger"]))
    names = []
    for report in reports:
        label = "keyword baseline" if report["tagger"] == "keyword" else \
            f'model ({report.get("model") or report["tagger"]})'
        names.append(label)
    head = "".join(f'<th class="n">{escape(n)}</th>' for n in names)
    body = ""
    for row in quality.side_by_side(reports):
        cells = "".join(f'<td class="n">{c["match"]}/{c["total"]} &nbsp;<b>{_pct(c["rate"])}</b></td>'
                        for c in row["cells"])
        body += f'<tr><td>{escape(row["label"])}</td>{cells}</tr>'
    signal_head = "".join(f'<th class="n">{escape(n)}<br>precision / recall</th>' for n in names)
    signal_body = ""
    for name in SIGNALS:
        cells = "".join(f'<td class="n">{_pct(r["signals"][name]["precision"])} / '
                        f'{_pct(r["signals"][name]["recall"])}</td>' for r in reports)
        signal_body += f"<tr><td>{escape(_name(name))}</td>{cells}</tr>"

    ref = result["reference"]
    who = "keyword baseline" if result["tagger"] == "keyword" else "model"
    effect = [("Mean frustration", ref["mean_frustration"]["tagger"],
               ref["mean_frustration"]["intended"]),
              ("Unanswered by the bot", _pct(ref["unanswered_share"]["tagger"]),
               _pct(ref["unanswered_share"]["intended"])),
              ("Chain sentiment", ref["chain_score"]["tagger"], ref["chain_score"]["intended"])]
    effect += [(f'{r["location"]} sentiment', r["tagger"], r["intended"])
               for r in ref["location_scores"]]
    flagged = lambda key: ", ".join(r["location"] for r in ref["location_scores"]  # noqa: E731
                                    if r[key]) or "none"
    effect.append(("Locations flagged for stars vs text", flagged("stars_disagree_tagger"),
                   flagged("stars_disagree_intended")))
    effect.append((f'Top {ref["top_gaps"]["n"]} content gaps shared',
                   f'{ref["top_gaps"]["shared"]} of {ref["top_gaps"]["n"]}', ""))
    effect_body = "".join(f'<tr><td>{escape(str(a))}</td><td class="n">{escape(str(b))}</td>'
                          f'<td class="n">{escape(str(c))}</td></tr>' for a, b, c in effect)
    return (
        '<div class="grid"><section class="card"><h2>Tagger agreement</h2>'
        '<p class="note">Share of items where the tagger gives the label the text was '
        'generated from. An item the tagger failed to tag counts as a miss.</p>'
        f'<div class="scroll"><table><tr><th>Field</th>{head}</tr>{body}</table></div>'
        f'<div class="scroll" style="margin-top:14px"><table><tr><th>Frustration signal</th>'
        f'{signal_head}</tr>{signal_body}</table></div></section>'
        '<section class="card"><h2>What the tagging errors do to the scores</h2>'
        '<p class="note">Each number on this page beside the same number computed from the '
        'intended labels. This is only possible because the data is synthetic.</p>'
        f'<div class="scroll"><table><tr><th>Number</th><th class="n">{escape(who)}</th>'
        f'<th class="n">intended labels</th></tr>{effect_body}</table></div></section></div>')


def render(result: dict, compare: list[dict] | tuple = ()) -> str:
    counts, frustration = result["counts"], result["frustration"]
    tagger = "keyword baseline (offline rules)" if result["tagger"] == "keyword" else \
        f'language model ({result.get("model")})'
    tiles = [
        (counts["chats"], "chatbot conversations"),
        (counts["reviews"], "reviews"),
        (f'{frustration["mean"]:.0f}', "mean frustration, 0 to 100"),
        (_pct(frustration["unanswered_share"]), "conversations the bot left unanswered"),
        (f'{result["locations"]["chain_score"]:.0f}', "chain sentiment, 0 to 100"),
        (len(result["content_gaps"]), "content gaps found"),
    ]
    tile_html = "".join(f'<div class="tile"><b>{escape(str(v))}</b><span>{escape(label)}</span>'
                        '</div>' for v, label in tiles)
    untagged = (counts["chats"] - counts["tagged_chats"]) + (counts["reviews"] - counts["tagged_reviews"])
    missing = f" {untagged} items could not be tagged and are left out of the scores." if untagged else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Voice of customer report (synthetic data)</title>'
        f'<style>{CSS}</style></head><body><main>'
        '<p class="banner">Synthetic data. Harbour Fitness is an invented gym chain, and every '
        'conversation, review and number on this page was generated for this example.</p>'
        '<h1>Voice of customer: Harbour Fitness</h1>'
        f'<p class="sub">What people ask the chatbot, where they get frustrated, and what reviews '
        f'say about each location. Tagged by: {escape(tagger)}.{escape(missing)}</p>'
        f'<div class="tiles">{tile_html}</div>'
        f'{_themes(result)}'
        f'<div class="grid">{_frustration(result)}{_gaps(result)}</div>'
        f'{_locations(result)}'
        f'{_agreement(result, list(compare))}'
        '<footer>The score weights are judgement calls, not fitted to any outcome. '
        'Agreement is measured against the labels the synthetic text was generated from, '
        'which is easier than real text.</footer>'
        '</main></body></html>\n')
