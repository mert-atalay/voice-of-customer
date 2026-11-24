"""Command line: python -m voc <generate|tag|score|report>

generate  write the synthetic data to data/ (seeded, no API calls)
tag       tag every conversation and review, write <out>/tags.json
score     scores, question bank and agreement from <out>/tags.json, write <out>/scores.json
report    one HTML file from <out>/scores.json, written to <out>/report.html

Only `tag --tagger model` calls an API. It needs OPENAI_API_KEY and stops at --max-calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import generate, report, summary, tagger

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_data(data_dir: Path = DATA) -> tuple[list[dict], list[dict], dict]:
    return tuple(json.loads((data_dir / f"{name}.json").read_text())
                 for name in ("chats", "reviews", "site_pages"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voc", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["generate", "tag", "score", "report"])
    parser.add_argument("--tagger", choices=["keyword", "model"], default="keyword")
    parser.add_argument("--out", default=str(ROOT / "results" / "keyword"),
                        help="results folder, for example results/keyword or results/model")
    parser.add_argument("--max-calls", type=int, default=30, help="hard limit on API calls")
    parser.add_argument("--html", default=None, help="where to write the report (report only)")
    args = parser.parse_args(argv)
    out = Path(args.out)

    if args.command == "generate":
        n_chats, n_reviews = generate.write(DATA)
        print(f"wrote {n_chats} conversations and {n_reviews} reviews to {DATA} "
              f"(seed {generate.SEED}, all synthetic)")
        return 0

    chats, reviews, site_pages = load_data()
    out.mkdir(parents=True, exist_ok=True)

    if args.command == "tag":
        if args.tagger == "model":
            worker = tagger.ModelTagger(max_calls=args.max_calls)
        else:
            worker = tagger.KeywordTagger()
        run = tagger.tag_all(worker, chats, reviews)
        (out / "tags.json").write_text(json.dumps(run, indent=1) + "\n")
        print(f"tagged {len(run['chats'])}/{len(chats)} conversations and "
              f"{len(run['reviews'])}/{len(reviews)} reviews with the {run['tagger']} tagger, "
              f"{run['calls']} API calls, {len(run['invalid'])} invalid or missing answers")
        if run["stopped"]:
            print(f"stopped early: {run['stopped']}", file=sys.stderr)
            return 1
        return 0

    tags_path = out / "tags.json"
    if not tags_path.exists():
        print(f"{tags_path} not found. Run `python -m voc tag --out {args.out}` first.",
              file=sys.stderr)
        return 1
    result = summary.summarise(json.loads(tags_path.read_text()), chats, reviews, site_pages)
    (out / "scores.json").write_text(json.dumps(result, indent=1) + "\n")

    if args.command == "score":
        print(f"mean frustration {result['frustration']['mean']}, "
              f"chain sentiment {result['locations']['chain_score']}, "
              f"{len(result['content_gaps'])} content gaps")
        print(f"agreement with intended labels ({result['tagger']} tagger):")
        for field, row in result["agreement"]["per_field"].items():
            print(f"  {field:<24} {row['match']}/{row['total']}  {row['rate']:.0%}")
        return 0

    # report: put the baseline and the model side by side when both runs are present
    others = []
    for name in ("keyword", "model"):
        path = out.parent / name / "scores.json"
        if path.exists() and path.resolve() != (out / "scores.json").resolve():
            others.append(json.loads(path.read_text())["agreement"])
    html_path = Path(args.html) if args.html else out / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(report.render(result, compare=others))
    print(f"wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
