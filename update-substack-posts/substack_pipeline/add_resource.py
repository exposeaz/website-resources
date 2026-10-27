"""Adds non-Substack resources (essays, articles, books' pages) to data.json, or re-tags existing ones.

Fetches each page, has Claude write the description, reference and 2-5 tags from its text, and adds the
entry after the last one in its category. Pages that are paywalled or too thin are skipped and listed, to
add by hand. With --retag, replaces an existing entry's tags (keeping manual ones) and leaves its text alone.
Run from update-substack-posts/:
  python -m substack_pipeline.add_resource --category essays URL [URL ...]
  python -m substack_pipeline.add_resource --retag RESOURCE_ID [RESOURCE_ID ...]
"""

import argparse
import json
import logging
import re
import sys

from bs4 import BeautifulSoup

from config import settings
from substack_pipeline import fetch, state
from substack_pipeline.classify import NEWS_TAG, Classifier, ClassifyAuthError, ClassifyError, _clean_tags, _vocab_line
from substack_pipeline.export import _add_tag_defs, _unique_id

log = logging.getLogger(__name__)

# The library wants at least this many; fewer is flagged for a human rather than padded by Claude
MIN_TAGS = 2


def _page(url):
    """(text, metadata hints) for a web page."""
    soup = BeautifulSoup(fetch._get(url).text, "html.parser")
    meta = {}
    for key in ("og:title", "og:site_name", "author", "article:author", "article:published_time", "citation_title",
                "citation_author", "citation_journal_title", "citation_publication_date", "citation_volume"):
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            meta[key] = tag["content"].strip()
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    return fetch.html_to_text(str(body))[: settings.MAX_TEXT_CHARS], meta


def _system(tags, examples):
    vocab = "\n".join(_vocab_line(t) for t in tags)
    refs = "\n".join(f"- {r}" for r in examples)
    return f"""You catalogue resources for a nonprofit's library on antizionism.
Judge only from the page text given.

incomplete: true if the text is a paywall, login page, teaser or otherwise too partial to describe the piece; then leave the other text fields empty.

title, author, publication: as given by the piece (author as "First Last"; several joined with "and").
year: publication year, or null if not stated.

description: 1 to 2 sentences on what the piece argues, traces or reports, starting with a verb (e.g. "Argues that...", "Traces..."). Neutral wording; do not evaluate it or mention paywalls.

reference: a citation in the library's style, like these:
{refs}

tags: 1 to {settings.MAX_TAGS} IDs from this vocabulary, most central first. Tag only themes the piece as a whole is about or develops at some length; a theme mentioned in a sentence or an aside does not count. Fewer, accurate tags are better than more, weaker ones; don't add a tag just to reach a count. A tag with an "only when" note applies only when that note is true.
{vocab}"""


def _schema(tags):
    s = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "incomplete": {"type": "boolean"}, "title": s, "author": s, "publication": s,
            "year": {"anyOf": [{"type": "integer"}, {"type": "null"}]}, "description": s, "reference": s,
            "tags": {"type": "array", "items": {"type": "string", "enum": [t["id"] for t in tags]}},
        },
        "required": ["incomplete", "title", "author", "publication", "year", "description", "reference", "tags"],
        "additionalProperties": False,
    }


def _slug(author, title):
    last = (author.split(" and ")[0].split(",")[0].split() or ["resource"])[-1]
    words = re.findall(r"[a-z0-9]+", f"{last} {title}".lower())
    return "-".join(words[:6])


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data = json.loads(settings.RESOURCES_FILE.read_text())
    curated = [c["id"] for c in data["categories"]
               if c["id"] not in (settings.RESOURCE_CATEGORY_ID, settings.SUBSTACK_CATEGORY_ID)]
    p = argparse.ArgumentParser(description="Add or re-tag non-Substack resources in data.json")
    p.add_argument("urls", nargs="*", help="pages to add")
    p.add_argument("--category", choices=curated, help="category for the pages added")
    p.add_argument("--retag", nargs="+", metavar="RESOURCE_ID", help="re-tag these existing entries from their pages")
    args = p.parse_args()
    if bool(args.urls) == bool(args.retag) or (args.urls and not args.category):
        p.error("give URLs with --category, or --retag with resource IDs")

    # news is a format, not a theme; manual tags are never assigned here
    tags = [t for t in state.load_tags() if t["id"] != NEWS_TAG]
    classifier = Classifier(tags)
    manual = state.manual_tag_ids()
    known_urls = {state.normalize_url(r["url"]) for r in data["resources"] if r.get("url")}
    by_id = {r["id"]: r for r in data["resources"]}
    category = args.category or (by_id[args.retag[0]]["category"] if args.retag[0] in by_id else curated[0])
    examples = [r["reference"] for r in data["resources"] if r["category"] == category and r.get("reference")][-3:]
    system, schema = _system(tags, examples), _schema(tags)

    jobs = [(u, None) for u in args.urls]
    jobs += [(by_id[i].get("url"), by_id[i]) if i in by_id else (None, i) for i in args.retag or []]
    skipped, taken = [], {r["id"] for r in data["resources"]}
    for url, existing in jobs:
        if url is None:
            skipped.append(f"{existing if isinstance(existing, str) else existing['id']}: no such resource or no URL")
            continue
        if existing is None and state.normalize_url(url) in known_urls:
            skipped.append(f"{url}: already in data.json")
            continue
        try:
            text, meta = _page(url)
            if len(text.split()) < settings.MIN_WORD_COUNT:
                raise ValueError(f"only {len(text.split())} words of readable text")
            user = f"URL: {url}\nPage metadata: {json.dumps(meta, ensure_ascii=False)}\n\n<page>\n{text}\n</page>"
            result = classifier._call(system, user, schema, settings.MAX_OUTPUT_TOKENS)
        except ClassifyAuthError as exc:
            sys.exit(f"Stopped: {exc}. Entries added before this point are saved; re-run once fixed.")
        except (fetch.FetchError, ClassifyError, ValueError) as exc:
            skipped.append(f"{url}: {exc}")
            continue
        if result["incomplete"]:
            skipped.append(f"{url}: paywalled or partial text")
            continue
        new_tags = _clean_tags(result["tags"], tags)
        if len(new_tags) < MIN_TAGS:
            log.warning("%s: only %d tag(s); add more by hand", url, len(new_tags))
        if existing:
            existing["tags"] = [t for t in existing["tags"] if t in manual] + new_tags
            log.info("Re-tagged %s: %s", existing["id"], ", ".join(existing["tags"]))
        else:
            entry = {
                "id": _unique_id(_slug(result["author"], result["title"]), taken),
                "title": result["title"], "category": category, "description": result["description"],
                "tags": new_tags, "reference": result["reference"], "author": result["author"], "url": url,
                "year": result["year"],
            }
            last = max((i for i, r in enumerate(data["resources"]) if r["category"] == category), default=-1)
            data["resources"].insert(last + 1, entry)
            known_urls.add(state.normalize_url(url))
            log.info("Added %s [%s]: %s", entry["id"], ", ".join(new_tags), entry["description"])
        _add_tag_defs(data, new_tags, tags)
        settings.RESOURCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    if skipped:
        log.warning("Not added; do these by hand:\n  %s", "\n  ".join(skipped))
    log.info("Review with: git diff data.json")


if __name__ == "__main__":
    main()
