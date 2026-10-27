"""Appends articles from data/articles.json to the site's data.json.

Each article is added once (exported_resources), so an interrupted run exports on the next one
and entries a reviewer deletes stay deleted. A publication without a Substack card gets one,
drafted from its own feed for a reviewer to check.
With --sync, exported articles are first updated after retag or dedupe (see sync_resources).
Run from update-substack-posts/: python -m substack_pipeline.export
"""

import argparse
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


def _auto_tags(article):
    """The article's tags minus manual ones, which the pipeline never publishes."""
    manual = state.manual_tag_ids()
    return [t for t in article["tags"] if t not in manual]


def _resource(article, taken):
    # Key order matches the existing entries in data.json, plus date
    return {
        "id": _unique_id("substack-" + article["url"].rstrip("/").rsplit("/", 1)[-1], taken),
        "title": article["title"],
        "category": settings.RESOURCE_CATEGORY_ID,
        "description": article["summary"],
        "tags": _auto_tags(article),
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


def meets_bar(a):
    """Clears the website bar: PUBLISH_RELEVANCE and PUBLISH_MIN_SCORE."""
    return a["relevance"] in settings.PUBLISH_RELEVANCE and a.get("relevance_score", 0) >= settings.PUBLISH_MIN_SCORE


def fill_candidate(a):
    """Could be published by fill to top up a tag: relevant enough and scoring at least TAG_FILL_MIN_SCORE."""
    return a["relevance"] in settings.PUBLISH_RELEVANCE and a.get("relevance_score", 0) >= settings.TAG_FILL_MIN_SCORE


def publishable(a):
    """Clears the bar or was picked by fill, and isn't marked a duplicate by dedupe; or was added by URL."""
    return a["forced"] or ((meets_bar(a) or bool(a.get("published_for_tag"))) and not a.get("duplicate_of"))


def _add_tag_defs(data, tag_ids, vocab):
    """Add any tag missing from data.json's tag list, labelled from the vocabulary."""
    known = {t["id"] for t in data["tags"]}
    labels = {t["id"]: t["label"] for t in vocab}
    for tag in tag_ids:
        if tag not in known:
            data["tags"].append({"id": tag, "label": labels.get(tag, tag)})
            known.add(tag)


def sync_resources(articles, vocab):
    """Bring exported Substack articles in data.json in line with articles.json.

    Removes entries no longer publishable (and unmarks them, so they're exported again if they later
    clear the bar) and refreshes the rest's tags, keeping any manual tags added by hand (first, so they
    show on cards). Entries a reviewer deleted stay deleted; other fields and other categories are left
    alone. Returns (removed, retagged).
    """
    data = json.loads(settings.RESOURCES_FILE.read_text())
    by_url = {a["url"]: a for a in articles}
    manual = state.manual_tag_ids()
    kept, removed, retagged = [], 0, 0
    for r in data["resources"]:
        a = by_url.get(r.get("url")) if r["category"] == settings.RESOURCE_CATEGORY_ID else None
        if a is None:
            kept.append(r)
        elif not publishable(a):
            a["exported_resources"] = False
            removed += 1
        else:
            tags = [t for t in r["tags"] if t in manual] + _auto_tags(a)
            if r["tags"] != tags:
                r["tags"] = tags
                retagged += 1
            kept.append(r)
    data["resources"] = kept
    _add_tag_defs(data, [t for r in kept for t in r["tags"]], vocab)
    settings.RESOURCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return removed, retagged


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
        _add_tag_defs(data, _auto_tags(article), vocab)
        if article["url"] not in urls:
            data["resources"].append(_resource(article, taken_ids))
            urls.add(article["url"])
        article["exported_resources"] = True
    settings.RESOURCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return len(pending)


def run_export(sync=False):
    articles = state.load_articles()
    vocab = state.load_tags()
    if sync:
        removed, retagged = sync_resources(articles, vocab)
        log.info("Synced data.json: removed %d articles, updated tags on %d", removed, retagged)
    added = export_resources(articles, vocab)
    state.save_articles(articles)
    held = sum(not a.get("exported_resources") for a in articles)
    log.info("Exported %d articles to data.json; %d held back below the publishing bar", added, held)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Export articles from data/articles.json to data.json")
    parser.add_argument("--sync", action="store_true",
                        help="first remove exported articles no longer publishable and refresh exported articles' tags")
    run_export(sync=parser.parse_args().sync)
