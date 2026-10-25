"""Appends articles from data/articles.json to the site's data.json.

Each article is added once (exported_resources), so an interrupted run exports on the next one
and entries a reviewer deletes stay deleted. A publication without a Substack card gets one,
drafted from its own feed for a reviewer to check.
Run from update-substack-posts/: python -m substack_pipeline.export
"""

import json
import logging
from datetime import date

from config import settings
from substack_pipeline import fetch, state

log = logging.getLogger(__name__)

_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def format_date(iso):
    d = date.fromisoformat(iso)
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def _unique_id(base, taken):
    rid, n = base, 2
    while rid in taken:
        rid, n = f"{base}-{n}", n + 1
    taken.add(rid)
    return rid


def _resource(article, taken):
    # Key order matches the existing entries in data.json, plus date
    return {
        "id": _unique_id("substack-" + article["url"].rstrip("/").rsplit("/", 1)[-1], taken),
        "title": article["title"],
        "category": settings.RESOURCE_CATEGORY_ID,
        "description": article["summary"],
        "tags": article["tags"],
        "reference": f'{article["publication"]}. "{article["title"]}." Substack, {format_date(article["date"])}.',
        "author": article["publication"],
        "url": article["url"],
        "year": int(article["date"][:4]),
        "date": article["date"],  # full date, so the site can sort a Substack's articles newest first
    }


def _substack_card(host, publications, taken):
    """Card for a publication with none yet: title, description and logo from its feed; author from the config."""
    pub = next((p for p in publications if p.url == host), None)
    try:
        feed = fetch.read_feed(host)
    except fetch.FetchError as exc:
        log.warning("%s; drafting its Substack card from the config only", exc)
        feed = None
    title = (feed and feed.title) or (pub and pub.name) or host
    author = (pub and pub.name) or title
    slug = host.split("://", 1)[-1].removesuffix(".substack.com").replace(".", "-")
    return {
        "id": _unique_id(f"substack-{slug}", taken),
        "title": title,
        "category": settings.SUBSTACK_CATEGORY_ID,
        "description": (feed and feed.description) or (pub and pub.description) or "",
        "tags": [],
        "reference": f"{author}. {title} (Substack).",
        "author": author,
        "image": feed.image if feed else None,
        "url": host,
        "year": None,
    }


def publishable(a):
    """Clears the website bar (PUBLISH_RELEVANCE and PUBLISH_MIN_SCORE), or was added by URL."""
    return a["forced"] or (a["relevance"] in settings.PUBLISH_RELEVANCE
                           and a.get("relevance_score", 0) >= settings.PUBLISH_MIN_SCORE)


def export_resources(articles, vocab):
    """Append pending, publishable articles to data.json, adding the category and any missing tags.

    Articles below the bar stay unexported, so loosening the bar later publishes them. Returns the count.
    """
    pending = [a for a in articles if not a.get("exported_resources") and publishable(a)]
    if not pending:
        return 0
    data = json.loads(settings.RESOURCES_FILE.read_text())
    if not any(c["id"] == settings.RESOURCE_CATEGORY_ID for c in data["categories"]):
        data["categories"].append({"id": settings.RESOURCE_CATEGORY_ID, "label": settings.RESOURCE_CATEGORY_LABEL})
    known_tags = {t["id"] for t in data["tags"]}
    labels = {t["id"]: t["label"] for t in vocab}
    taken_ids = {r["id"] for r in data["resources"]}
    urls = {r.get("url") for r in data["resources"]}
    card_hosts = {fetch.base_url(r["url"]) for r in data["resources"]
                  if r["category"] == settings.SUBSTACK_CATEGORY_ID and r.get("url")}
    publications = state.load_publications()
    for article in pending:
        host = fetch.base_url(article["url"])
        if host not in card_hosts:
            card = _substack_card(host, publications, taken_ids)
            data["resources"].append(card)
            card_hosts.add(host)
            log.info("Drafted Substack card %r for %s", card["title"], host)
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
    held = sum(not a.get("exported_resources") for a in articles)
    log.info("Exported %d articles to data.json; %d held back below the publishing bar", added, held)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_export()
