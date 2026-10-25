"""Reads posts from Substack's public RSS feed and unofficial JSON endpoints.

Paywalled posts only ever use the preview Substack serves publicly.
"""

import functools
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from config import settings

log = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class Post:
    publication: str
    publication_description: str
    title: str
    url: str
    published: date
    text: str
    paywalled: bool


@dataclass
class Publication:
    name: str
    url: str
    description: str


class FetchError(Exception):
    pass


_session = requests.Session()
_session.headers["User-Agent"] = settings.USER_AGENT


def _get(url, params=None):
    """GET with a polite delay before every request and retries on transient failures."""
    for attempt in range(1, settings.MAX_RETRIES + 1):
        time.sleep(settings.REQUEST_DELAY_SECONDS)
        try:
            resp = _session.get(url, params=params, timeout=settings.REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            err = str(exc)
        else:
            if resp.ok:
                return resp
            if resp.status_code not in _RETRY_STATUSES:
                raise FetchError(f"{url}: HTTP {resp.status_code}")
            err = f"HTTP {resp.status_code}"
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                time.sleep(int(retry_after))
        if attempt < settings.MAX_RETRIES:
            log.warning("%s: %s (attempt %d/%d)", url, err, attempt, settings.MAX_RETRIES)
            time.sleep(settings.RETRY_BACKOFF_SECONDS * attempt)
    raise FetchError(f"{url}: {err} after {settings.MAX_RETRIES} attempts")


def base_url(url):
    parts = urlsplit(url)
    return f"{parts.scheme or 'https'}://{parts.netloc.lower()}"


def slug_from_url(url):
    path = urlsplit(url).path.rstrip("/").split("/")
    if len(path) >= 3 and path[-2] == "p":
        return path[-1]
    raise FetchError(f"Not a Substack post URL: {url}")


def html_to_text(html):
    text = BeautifulSoup(html or "", "html.parser").get_text("\n")
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)[: settings.MAX_TEXT_CHARS]


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return parsedate_to_datetime(value).date()


@functools.cache
def read_feed(pub_url):
    """Channel title, channel description and (url, published date) items, newest first.

    Cached so a publication resolved from its feed isn't fetched twice in one run.
    """
    channel = ET.fromstring(_get(f"{base_url(pub_url)}/feed").content).find("channel")
    entries = []
    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        if link:
            entries.append((link, _parse_date(item.findtext("pubDate"))))
    title = channel.findtext("title", "").strip()
    return title, channel.findtext("description", "").strip(), entries


def archive_entries(pub_url, since=None, limit=None):
    """(url, published date) from the JSON archive, newest first.

    Stops before `since` or after `limit` entries, whichever comes first.
    """
    entries = []
    offset = 0
    while limit is None or len(entries) < limit:
        page_size = settings.ARCHIVE_PAGE_SIZE if limit is None else min(settings.ARCHIVE_PAGE_SIZE, limit - len(entries))
        page = _get(
            f"{base_url(pub_url)}/api/v1/archive",
            params={"sort": "new", "offset": offset, "limit": page_size},
        ).json()
        if not page:
            return entries
        for post in page:
            published = _parse_date(post.get("post_date"))
            if since and published and published < since:
                return entries
            url = post.get("canonical_url")
            if url:
                entries.append((url, published))
        offset += len(page)
    return entries[:limit]


def fetch_post(url, publication):
    """Full post (or the public preview, for paid posts) via the JSON post endpoint."""
    data = _get(f"{base_url(url)}/api/v1/posts/{slug_from_url(url)}").json()
    paywalled = data.get("audience") not in (None, "everyone")
    html = data.get("body_html") or data.get("truncated_body_text") or ""
    text = html_to_text(html) or html_to_text(data.get("description") or data.get("subtitle"))
    return Post(
        publication=publication.name,
        publication_description=publication.description,
        title=(data.get("title") or "").strip(),
        url=data.get("canonical_url") or url,
        published=_parse_date(data.get("post_date")),
        text=text,
        paywalled=paywalled,
    )
