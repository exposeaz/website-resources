"""Writes articles from data/articles.json into the site's data.json and azaryah's prompt file.

data.json is append-only: each article is added once (exported_resources), so entries a reviewer deletes
stay deleted. The azaryah table is rebuilt as the top-scoring articles (in_azaryah); rows a reviewer
deletes are marked azaryah_excluded and never return.
Run from update-substack-posts/: python -m substack_pipeline.export
"""

import json
import logging
import re
from datetime import date

from config import settings
from substack_pipeline import state

log = logging.getLogger(__name__)

_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
_AZARYAH_TABLE_HEAD = ["| Substack | Title | Link | Description |", "| --- | --- | --- | --- |"]


def format_date(iso):
    d = date.fromisoformat(iso)
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def _resource_id(url, taken):
    base = "substack-" + url.rstrip("/").rsplit("/", 1)[-1]
    rid, n = base, 2
    while rid in taken:
        rid, n = f"{base}-{n}", n + 1
    taken.add(rid)
    return rid


def _resource(article, taken):
    # Key order matches the existing entries in data.json
    return {
        "id": _resource_id(article["url"], taken),
        "title": article["title"],
        "category": settings.RESOURCE_CATEGORY_ID,
        "description": article["summary"],
        "tags": article["tags"],
        "reference": f'{article["publication"]}. "{article["title"]}." Substack, {format_date(article["date"])}.',
        "author": article["publication"],
        "url": article["url"],
        "year": int(article["date"][:4]),
    }


def export_resources(articles, vocab):
    """Append pending articles to data.json, adding the category and any missing tags. Returns the count."""
    pending = [a for a in articles if not a.get("exported_resources")]
    if not pending:
        return 0
    data = json.loads(settings.RESOURCES_FILE.read_text())
    if not any(c["id"] == settings.RESOURCE_CATEGORY_ID for c in data["categories"]):
        data["categories"].append({"id": settings.RESOURCE_CATEGORY_ID, "label": settings.RESOURCE_CATEGORY_LABEL})
    known_tags = {t["id"] for t in data["tags"]}
    labels = {t["id"]: t["label"] for t in vocab}
    taken_ids = {r["id"] for r in data["resources"]}
    urls = {r.get("url") for r in data["resources"]}
    for article in pending:
        for tag in article["tags"]:
            if tag not in known_tags:
                data["tags"].append({"id": tag, "label": labels.get(tag, tag)})
                known_tags.add(tag)
        if article["url"] not in urls:
            data["resources"].append(_resource(article, taken_ids))
            urls.add(article["url"])
        article["exported_resources"] = True
    settings.RESOURCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return len(pending)


def _cell(text):
    """Single line, with pipes escaped so they don't break the markdown table."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _row(a):
    return f"| {_cell(a['publication'])} | {_cell(a['title'])} | {a['url']} | {_cell(a['summary'])} |"


def _row_url(row):
    cells = re.split(r"(?<!\\)\|", row)
    return cells[3].strip() if len(cells) > 4 else None


def _rank_key(a):
    return (a.get("relevance_score", 0), a["date"])


def export_azaryah(articles):
    """Rebuild the azaryah table as the top AZARYAH_MAX_ROWS eligible articles by relevance_score.

    Returns (added, dropped) articles, or None if azaryah isn't checked out.
    """
    if not settings.AZARYAH_DIR.is_dir():
        log.warning("azaryah not found at %s (set AZARYAH_DIR); skipping its prompt file", settings.AZARYAH_DIR)
        return None
    path = settings.AZARYAH_PROMPT_FILE
    lines = path.read_text().splitlines() if path.exists() else []

    # Locate the section: header, blank lines, then table lines
    start = lines.index(settings.AZARYAH_HEADER) if settings.AZARYAH_HEADER in lines else None
    end = start
    current_rows = []
    if start is not None:
        end = start + 1
        while end < len(lines) and not lines[end].strip():
            end += 1
        while end < len(lines) and lines[end].startswith("|"):
            end += 1
        current_rows = [l for l in lines[start + 1:end] if l.startswith("|")][len(_AZARYAH_TABLE_HEAD):]
    current_urls = {_row_url(r) for r in current_rows}

    # Rows we placed that are gone were deleted by a reviewer. If none of ours remain,
    # the table was never merged (e.g. a closed PR), so nothing counts as deleted.
    ours = [a for a in articles if a.get("in_azaryah")]
    if any(a["url"] in current_urls for a in ours):
        for a in ours:
            if a["url"] not in current_urls:
                a["azaryah_excluded"] = True

    eligible = [a for a in articles
                if (a["relevance"] in settings.AZARYAH_RELEVANCE or a["forced"]) and not a.get("azaryah_excluded")]
    chosen = sorted(eligible, key=_rank_key, reverse=True)[: settings.AZARYAH_MAX_ROWS]
    chosen_urls = {a["url"] for a in chosen}
    added = [a for a in chosen if a["url"] not in current_urls]
    dropped = [a for a in ours if a["url"] in current_urls and a["url"] not in chosen_urls]
    for a in articles:
        a["in_azaryah"] = a["url"] in chosen_urls

    # Rows added by hand (not from articles.json) are kept
    known = {a["url"] for a in articles}
    manual = [r for r in current_rows if _row_url(r) not in known]
    section = [settings.AZARYAH_HEADER, "", *_AZARYAH_TABLE_HEAD, *manual, *(_row(a) for a in chosen)]
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += section
    else:
        lines[start:end] = section
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return added, dropped


def _azaryah_pr_body(added, dropped, total):
    lines = ["Automated update from `update-substack-posts` in exposeaz/website-resources.", "",
             f"The Substack table lists the top {total} articles by relevance score "
             f"(newest first on ties). This run added {len(added)} and dropped {len(dropped)}.",
             "Delete any row you don't want before merging; deleted rows are not re-added.", ""]
    for heading, items in (("Added", added), ("Dropped (outranked)", dropped)):
        if items:
            lines += [f"### {heading} ({len(items)})", ""]
            lines += [f"- [{a['title']}]({a['url']}) — {a['publication']}, score {a.get('relevance_score', '?')}"
                      for a in items]
            lines.append("")
    body = "\n".join(lines)
    return body[: settings.PR_BODY_MAX_CHARS]


def run_export():
    articles = state.load_articles()
    to_site = export_resources(articles, state.load_tags())
    changes = export_azaryah(articles)
    state.save_articles(articles)
    log.info("Exported %d articles to data.json", to_site)
    if changes is not None:
        added, dropped = changes
        total = sum(a.get("in_azaryah", False) for a in articles)
        settings.AZARYAH_PR_BODY_FILE.parent.mkdir(parents=True, exist_ok=True)
        settings.AZARYAH_PR_BODY_FILE.write_text(_azaryah_pr_body(added, dropped, total))
        log.info("Azaryah table: %d rows (%d added, %d dropped)", total, len(added), len(dropped))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_export()
