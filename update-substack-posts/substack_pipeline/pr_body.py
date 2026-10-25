"""Writes the website-resources PR description: articles in data/articles.json that aren't on the base branch yet.

Run from update-substack-posts/: python -m substack_pipeline.pr_body --base <base articles.json>
"""

import argparse
import json
from pathlib import Path

from config import settings
from substack_pipeline import state
from substack_pipeline.export import format_date


def _entry(a, with_reason):
    score = f", score {a['relevance_score']}" if "relevance_score" in a else ""
    lines = [f"- [{a['title']}]({a['url']}) — {a['publication']}, {format_date(a['date'])}{score}",
             f"  - Summary: {a['summary']}"]
    if with_reason:
        lines.append(f"  - Reason: {a['relevance_reason']}")
    return lines


def build_body(new, new_cards=()):
    forced = [a for a in new if a["forced"]]
    unsure = [a for a in new if not a["forced"] and a["relevance"] == "unsure"]
    relevant = [a for a in new if not a["forced"] and a["relevance"] == "relevant"]
    lines = ["Automated update from `update-substack-posts`.", "",
             f"{len(new)} new articles: {len(relevant)} relevant, {len(unsure)} unsure, {len(forced)} added by URL.",
             "Before merging, remove any entry you don't want from `data.json`; removed entries are not re-added.", ""]
    if new_cards:
        lines += [f"### New Substack cards ({len(new_cards)}): please check the wording", ""]
        for c in new_cards:
            lines += [f"- [{c['title']}]({c['url']}) by {c['author']}", f"  - Description: {c['description'] or '(none)'}"]
        lines.append("")
    if any(a["relevance"] == "not_relevant" for a in forced):
        lines += ["**Warning:** some articles added by URL were judged not relevant; see their reasons below.", ""]
    # Reasons only where a human needs to judge
    sections = [
        ("Unsure: please review", unsure, True),
        ("Added by URL", forced, False),
        ("Relevant", relevant, False),
    ]
    for heading, items, with_reason in sections:
        if items:
            lines += [f"### {heading} ({len(items)})", ""]
            for a in items:
                lines += _entry(a, with_reason or (a["forced"] and a["relevance"] == "not_relevant"))
            lines.append("")
    body = "\n".join(lines)
    if len(body) > settings.PR_BODY_MAX_CHARS:
        note = "\n\n_List truncated; see `update-substack-posts/data/articles.json` in this PR for every article._\n"
        body = body[: settings.PR_BODY_MAX_CHARS - len(note)].rsplit("\n- ", 1)[0] + note
    return body


def main(argv=None):
    p = argparse.ArgumentParser(prog="substack_pipeline.pr_body")
    p.add_argument("--base", type=Path, help="articles.json from the base branch; omit to list every article")
    p.add_argument("--base-resources", type=Path, help="data.json from the base branch, to list new Substack cards")
    args = p.parse_args(argv)
    base = json.loads(args.base.read_text()) if args.base and args.base.exists() else []
    base_urls = {a["url"] for a in base}
    new = [a for a in state.load_articles() if a["url"] not in base_urls]
    new_cards = []
    if args.base_resources and args.base_resources.exists():
        base_ids = {r["id"] for r in json.loads(args.base_resources.read_text())["resources"]}
        new_cards = [r for r in json.loads(settings.RESOURCES_FILE.read_text())["resources"]
                     if r["category"] == settings.SUBSTACK_CATEGORY_ID and r["id"] not in base_ids]
    settings.PR_BODY_FILE.parent.mkdir(parents=True, exist_ok=True)
    settings.PR_BODY_FILE.write_text(build_body(new, new_cards))
    print(f"Wrote {settings.PR_BODY_FILE} ({len(new)} new articles)")


if __name__ == "__main__":
    main()
