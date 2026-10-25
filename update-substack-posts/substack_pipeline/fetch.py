"""Reads posts from Substack's public RSS feed and unofficial JSON endpoints.

Paywalled posts only ever use the preview Substack serves publicly.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from config import settings

log = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_XML_INVALID_CHARS = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class Post:
    publication: str
    publication_description: str
    title: str
    url: str
    published: date
    text: str
    paywalled: bool
    word_count: int | None = None  # full post; None if unknown (paywalled, no API count)


@dataclass
class Feed:
    title: str
    description: str
    image: str | None
    entries: list  # (url, published date), newest first


@dataclass
class Publication:
    name: str
    url: str
    description: str


class FetchError(Exception):
    pass


class NotPublicError(FetchError):
    """Publication or post has no public content, e.g. a subscriber-only Substack."""


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
                final = urlsplit(resp.url)
                # Subdomains without a publication redirect to the author's profile page
                if final.netloc == "substack.com" and final.path.startswith("/@"):
                    raise NotPublicError(f"not publicly readable ({url} redirects to profile {resp.url}; "
                                         "likely subscriber-only)")
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
    return "\n".join(line for line in lines if line)


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return parsedate_to_datetime(value).date()


_feed_results = {}


def read_feed(pub_url):
    """The publication's feed (a Feed).

    Results and failures are cached so a feed is requested at most once per run.
    """
    if pub_url not in _feed_results:
        try:
            _feed_results[pub_url] = (_read_feed(pub_url), None)
        except FetchError as exc:
            _feed_results[pub_url] = (None, exc)
    result, exc = _feed_results[pub_url]
    if exc:
        raise exc
    return result


def _read_feed(pub_url):
    url = f"{base_url(pub_url)}/feed"
    # Control characters are invalid in XML and break parsing; feedparser tolerates other malformed XML
    feed = feedparser.parse(_XML_INVALID_CHARS.sub(b"", _get(url).content))
    if not feed.version or (feed.bozo and not feed.entries):
        raise FetchError(f"{url}: not a readable feed ({feed.get('bozo_exception', 'unrecognized format')})")
    entries = []
    for item in feed.entries:
        link = (item.get("link") or "").strip()
        published = item.get("published_parsed")
        if link:
            entries.append((link, date(*published[:3]) if published else None))
    return Feed(
        title=" ".join((feed.feed.get("title") or "").split()),
        description=" ".join((feed.feed.get("description") or "").split()),
        image=(feed.feed.get("image") or {}).get("href"),
        entries=entries,
    )


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
    word_count = data.get("wordcount")
    if word_count is None and not paywalled:
        word_count = len(text.split())
    return Post(
        publication=publication.name,
        publication_description=publication.description,
        title=(data.get("title") or "").strip(),
        url=data.get("canonical_url") or url,
        published=_parse_date(data.get("post_date")),
        text=text[: settings.MAX_TEXT_CHARS],
        paywalled=paywalled,
        word_count=word_count,
    )
