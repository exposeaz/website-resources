"""Local dedupe state and config loading."""

import json
from urllib.parse import urlsplit, urlunsplit

import yaml

from config import settings
from substack_pipeline.fetch import Publication, base_url


def normalize_url(url):
    """Lowercase host; drop query, fragment and trailing slash."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def load_processed():
    if not settings.PROCESSED_FILE.exists():
        return set()
    return set(json.loads(settings.PROCESSED_FILE.read_text()))


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def save_processed(urls):
    _write_json(settings.PROCESSED_FILE, sorted(urls))


def load_articles():
    if not settings.ARTICLES_FILE.exists():
        return []
    return json.loads(settings.ARTICLES_FILE.read_text())


def save_articles(articles):
    _write_json(settings.ARTICLES_FILE, articles)


def merge_articles(existing, new):
    """Append new records; a record for a URL already present (--force) replaces it in place."""
    by_url = {r["url"]: r for r in new}
    merged = [by_url.pop(r["url"], r) for r in existing]
    return merged + [r for r in new if r["url"] in by_url]


def load_tags():
    return json.loads(settings.TAGS_FILE.read_text())


def load_publications():
    """Configured publications, one per distinct URL; shared URLs merge their names and descriptions."""
    merged = {}
    for entry in yaml.safe_load(settings.SUBSTACKS_FILE.read_text()):
        key = base_url(entry["url"])
        desc = (entry.get("description") or "").strip()
        if key in merged:
            pub = merged[key]
            pub.name = f"{pub.name} / {entry['name']}"
            pub.description = " ".join(d for d in (pub.description, desc) if d)
        else:
            merged[key] = Publication(name=entry["name"], url=key, description=desc)
    return list(merged.values())
