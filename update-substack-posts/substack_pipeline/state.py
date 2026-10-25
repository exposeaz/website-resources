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
