"""Appends articles from data/articles.json to the site's data.json.

Each article is added once (exported_resources), so an interrupted run exports on the next one
and entries a reviewer deletes stay deleted.
Run from update-substack-posts/: python -m substack_pipeline.export
"""

import json
import logging
from datetime import date

from config import settings
from substack_pipeline import state

log = logging.getLogger(__name__)

_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


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


def run_export():
    articles = state.load_articles()
    added = export_resources(articles, state.load_tags())
    state.save_articles(articles)
    log.info("Exported %d articles to data.json", added)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_export()
