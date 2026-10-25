"""CLI entry point. Run from update-substack-posts/: python -m substack_pipeline --help"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone

from config import settings
from substack_pipeline import export, fetch, state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError

log = logging.getLogger("substack_pipeline")


@dataclass
class Candidate:
    url: str
    published: date | None
    publication: fetch.Publication
    forced: bool = False


def _split_urls(values):
    return [u.strip() for v in values or [] for u in v.split(",") if u.strip()]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="substack_pipeline")
    p.add_argument("--dry-run", action="store_true",
                   help=f"Classify the {settings.DRY_RUN_SAMPLE_SIZE} most recent feed posts "
                        "(ignoring START_DATE) and write local output only.")
    p.add_argument("--sample", type=int, default=None,
                   help="Override the dry-run sample size.")
    p.add_argument("--post-url", action="append",
                   help="Specific post(s) to force-include; repeatable or comma-separated.")
    p.add_argument("--publication-url",
                   help="Run only one publication, e.g. name.substack.com or "
                        "https://name.substack.com, or a name exactly as in config/substacks.yaml. "
                        "Substacks not in the config also work (not added to it).")
    p.add_argument("--force", action="store_true",
                   help="With --post-url: reclassify posts even if already processed.")
    return p.parse_args(argv)


def _record_error(errors, label, url, exc):
    """Not-public sources are an expected skip (warning); anything else is an error."""
    not_public = isinstance(exc, fetch.NotPublicError)
    (log.warning if not_public else log.error)("%s: %s", label, exc)
    errors.append({"url": url, "error": str(exc), "kind": "not_public" if not_public else "error"})


def _resolve_publication(url_or_name, configured):
    """Configured publication matching this name or host, else name/description from its feed.

    An unreadable feed falls back to the host as the name, with no description.
    """
    for pub in configured:
        if pub.name.lower() == url_or_name.strip().lower():
            return pub
    key = fetch.base_url(url_or_name if "://" in url_or_name else f"https://{url_or_name}")
    for pub in configured:
        if pub.url == key:
            return pub
    try:
        feed = fetch.read_feed(key)
        title, description = feed.title, feed.description
    except fetch.FetchError as exc:
        log.warning("%s; using %s as the publication name", exc, key)
        title, description = "", ""
    return fetch.Publication(name=title or key, url=key, description=description)


def _publication_entries(pub, args):
    """(url, date) entries for one publication.

    Dry run: every feed item.
    Otherwise: posts on or after START_DATE.
    An unreadable feed falls back to the JSON archive in every mode.
    """
    try:
        feed = fetch.read_feed(pub.url)
        description, entries = feed.description, feed.entries
    except fetch.NotPublicError:
        raise
    except fetch.FetchError as exc:
        log.warning("%s: %s; using the JSON archive instead", pub.name, exc)
        description, entries = "", None
    if not pub.description and description:
        pub.description = description
        log.info("%s: using feed description: %s", pub.name, description)
    if args.dry_run:
        if entries is None:
            entries = fetch.archive_entries(pub.url, limit=args.sample or settings.DRY_RUN_SAMPLE_SIZE)
        return entries
    # The feed holds only recent items; page the archive when it may not reach START_DATE
    oldest = min((d for _, d in entries or [] if d), default=None)
    if entries is None or (entries and oldest and oldest >= settings.START_DATE):
        entries = fetch.archive_entries(pub.url, since=settings.START_DATE)
    return [(u, d) for u, d in entries if d and d >= settings.START_DATE]


def gather_candidates(args, processed, errors):
    configured = state.load_publications()
    post_urls = _split_urls(args.post_url)
    candidates = []

    for url in post_urls:
        if state.normalize_url(url) in processed and not args.force:
            log.info("Already processed, skipping (use --force to reclassify): %s", url)
            continue
        try:
            candidates.append(Candidate(url, None, _resolve_publication(url, configured), forced=True))
        except fetch.FetchError as exc:
            _record_error(errors, url, url, exc)

    if args.publication_url:
        pubs = [_resolve_publication(args.publication_url, configured)]
        log.info("Publication: %s (%s)", pubs[0].name, pubs[0].url)
    elif post_urls:
        pubs = []
    else:
        pubs = configured

    seen = {state.normalize_url(c.url) for c in candidates}
    for pub in pubs:
        try:
            entries = _publication_entries(pub, args)
        except (fetch.FetchError, ValueError) as exc:
            _record_error(errors, pub.name, pub.url, exc)
            continue
        for url, published in entries:
            key = state.normalize_url(url)
            if key in processed or key in seen:
                continue
            seen.add(key)
            candidates.append(Candidate(url, published, pub))

    if args.dry_run:
        size = args.sample or settings.DRY_RUN_SAMPLE_SIZE
        forced = [c for c in candidates if c.forced]
        rest = sorted((c for c in candidates if not c.forced),
                      key=lambda c: c.published or date.min, reverse=True)
        candidates = forced + rest[: max(size - len(forced), 0)]
    return candidates


def _skipped(post, reason):
    return {
        "publication": post.publication,
        "title": post.title,
        "url": state.normalize_url(post.url),
        "word_count": post.word_count,
        "paywalled": post.paywalled,
        "reason": reason,
    }


class StateRecorder:
    """Saves processed.json and articles.json after every post, so an interrupted run resumes."""

    def __init__(self, processed):
        self.processed = processed
        self.articles = state.load_articles()
        self.added = 0

    def __call__(self, record=None, skipped=None):
        if skipped:
            self.processed.add(skipped["url"])
        if record:
            self.processed.add(record["url"])
            if record["relevance"] != "not_relevant" or record["forced"]:
                self.articles = state.merge_articles(self.articles, [record])
                self.added += 1
            state.save_articles(self.articles)
        state.save_processed(self.processed)


def process(candidates, classifier, errors, on_done=None):
    """Classified records, plus posts skipped as too short, too thin, or roundups/announcements.

    --post-url posts are never skipped. on_done(record=..., skipped=...) runs after each post.
    """
    records, skipped = [], []
    on_done = on_done or (lambda **_: None)
    for i, cand in enumerate(candidates, 1):
        log.info("[%d/%d] %s", i, len(candidates), cand.url)
        try:
            post = fetch.fetch_post(cand.url, cand.publication)
            if not cand.forced and post.word_count is not None and post.word_count < settings.MIN_WORD_COUNT:
                log.info("Skipping, %d words < MIN_WORD_COUNT", post.word_count)
                skipped.append(_skipped(post, f"under {settings.MIN_WORD_COUNT} words ({post.word_count})"))
                on_done(skipped=skipped[-1])
                continue
            result = classifier.classify(post)
        except (fetch.FetchError, ClassifyError, ValueError) as exc:
            _record_error(errors, cand.url, cand.url, exc)
            continue
        if not cand.forced:
            # A paywalled preview always looks thin; its word count (full post) already passed the floor
            reason = ("too thin to be a resource" if result["too_thin"] and not post.paywalled
                      else "roundup or announcement" if result["roundup"] else None)
            if reason:
                log.info("Skipping, %s", reason)
                skipped.append(_skipped(post, reason))
                on_done(skipped=skipped[-1])
                continue
        records.append({
            "publication": post.publication,
            "title": post.title,
            "url": state.normalize_url(post.url),
            "date": (post.published or cand.published or date.today()).isoformat(),
            "summary": result["summary"],
            "tags": result["tags"],
            "suggested_tags": result["suggested_tags"],
            "stance": result["stance"],
            "paywalled": post.paywalled,
            "word_count": post.word_count,
            "relevance": result["relevance"],
            "relevance_reason": result["relevance_reason"],
            "relevance_score": result["relevance_score"],
            "scoped_tags_reviewed": classifier.scoped_signature,
            "too_thin": result["too_thin"],
            "roundup": result["roundup"],
            "forced": cand.forced,
        })
        on_done(record=records[-1])
    return records, skipped


def run_report(title, records, skipped, errors):
    groups = {"relevant": [], "unsure": [], "not_relevant": []}
    for r in records:
        groups[r["relevance"]].append(r)
    lines = [f"# {title}", "",
             f"Classified {len(records)} posts: " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()),
             ""]
    for label, items in groups.items():
        lines += [f"## {label} ({len(items)})", ""]
        for r in items:
            flags = [f for f, on in (("paywalled", r["paywalled"]), ("too thin", r["too_thin"]), ("roundup", r["roundup"]),
                                     ("forced", r["forced"])) if on]
            lines += [
                f"### {r['title']}" + (f" [{', '.join(flags)}]" if flags else ""),
                f"{r['publication']} · {r['date']} · {r['url']}",
                "",
            ]
            # Reason only where a human needs to judge: unsure, or forced despite a not-relevant verdict
            if r["relevance"] == "unsure" or (r["forced"] and r["relevance"] == "not_relevant"):
                lines.append(f"- Reason: {r['relevance_reason']}")
            lines += [
                f"- Summary: {r['summary']}",
                f"- Stance: {r['stance']}",
                f"- Tags: {', '.join(r['tags']) or '(none)'}",
                f"- Suggested tags: {', '.join(r['suggested_tags']) or '(none)'}",
                "",
            ]
    if skipped:
        lines += [f"## Skipped ({len(skipped)})", ""]
        lines += [f"- {s['title']} ({s['publication']}): {s['reason']} · {s['url']}" for s in skipped] + [""]
    for kind, heading in (("not_public", "Not publicly readable"), ("error", "Errors")):
        items = [e for e in errors if e["kind"] == kind]
        if items:
            lines += [f"## {heading} ({len(items)})", ""] + [f"- {e['url']}: {e['error']}" for e in items] + [""]
    return "\n".join(lines)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    if args.force and not args.post_url:
        sys.exit("--force only applies with --post-url")

    errors = []
    processed = state.load_processed()
    candidates = gather_candidates(args, processed, errors)
    log.info("%d posts to classify", len(candidates))
    # Errors aren't recorded, so those posts are retried next run
    recorder = None if args.dry_run else StateRecorder(processed)
    try:
        records, skipped = process(candidates, Classifier(state.load_tags()), errors, on_done=recorder)
    except ClassifyAuthError as exc:
        sys.exit(f"Stopped: {exc}. Posts finished before this point are saved; re-run once fixed.")
    if recorder:
        log.info("Recorded %d processed URLs; added %d articles", len(records) + len(skipped), recorder.added)
        export.run_export()

    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # One file per day and kind; a later run the same day overwrites it
    stem = f"{datetime.now(timezone.utc):%Y-%m-%d}-{'dry-run' if args.dry_run else 'run'}"
    json_path = settings.OUTPUT_DIR / f"{stem}.json"
    md_path = settings.OUTPUT_DIR / f"{stem}.md"
    json_path.write_text(json.dumps({"records": records, "skipped": skipped, "errors": errors}, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(run_report("Dry run" if args.dry_run else "Run", records, skipped, errors))
    log.info("Wrote %s and %s", json_path, md_path)


if __name__ == "__main__":
    main()
