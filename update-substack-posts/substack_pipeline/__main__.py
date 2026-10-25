"""CLI entry point. Run from update-substack-posts/: python -m substack_pipeline --help"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone

from config import settings
from substack_pipeline import fetch, state
from substack_pipeline.classify import Classifier, ClassifyError

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
    p.add_argument("--all-posts", action="store_true",
                   help=f"Ignore START_DATE and read each publication's {settings.ALL_POSTS_LIMIT} most recent "
                        "posts (ALL_POSTS_LIMIT).")
    p.add_argument("--no-limit", action="store_true",
                   help="With --all-posts: read each publication's entire archive.")
    p.add_argument("--post-url", action="append",
                   help="Specific post(s) to force-include; repeatable or comma-separated.")
    p.add_argument("--publication-url",
                   help="Run only one publication, e.g. name.substack.com or "
                        "https://name.substack.com, or a name exactly as in config/substacks.yaml. "
                        "Substacks not in the config also work (not added to it).")
    p.add_argument("--force", action="store_true",
                   help="With --post-url: reclassify posts even if already processed.")
    return p.parse_args(argv)


def _resolve_publication(url_or_name, configured):
    """Configured publication matching this name or host, else name/description from its feed.

    An unreadable feed falls back to the host as the name, with no description.
    """
    for pub in configured:
        if pub.name.lower() == url_or_name.strip().lower():
            return pub
    full = url_or_name if "://" in url_or_name else f"https://{url_or_name}"
    key = fetch.base_url(full)
    if full.rstrip("/") != key:
        log.info("Using publication %s (only the host of %s is used)", key, url_or_name)
    for pub in configured:
        if pub.url == key:
            return pub
    try:
        title, description, _ = fetch.read_feed(key)
    except fetch.FetchError as exc:
        log.warning("%s; using %s as the publication name", exc, key)
        title, description = "", ""
    return fetch.Publication(name=title or key, url=key, description=description)


def _publication_entries(pub, args):
    """(url, date) entries for one publication.

    Dry run: every feed item. --all-posts: archive, capped by ALL_POSTS_LIMIT unless --no-limit.
    Otherwise: posts on or after START_DATE.
    An unreadable feed falls back to the JSON archive in every mode.
    """
    try:
        _, description, entries = fetch.read_feed(pub.url)
    except fetch.FetchError as exc:
        log.warning("%s: %s; using the JSON archive instead", pub.name, exc)
        description, entries = "", None
    if not pub.description and description:
        pub.description = description
        log.info("%s: using feed description: %s", pub.name, description)
    if args.all_posts:
        limit = None if args.no_limit or settings.ALL_POSTS_LIMIT <= 0 else settings.ALL_POSTS_LIMIT
        return fetch.archive_entries(pub.url, limit=limit)
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
            errors.append({"url": url, "error": str(exc)})

    if args.publication_url:
        pubs = [_resolve_publication(args.publication_url, configured)]
    elif post_urls:
        pubs = []
    else:
        pubs = configured

    seen = {state.normalize_url(c.url) for c in candidates}
    for pub in pubs:
        try:
            entries = _publication_entries(pub, args)
        except (fetch.FetchError, ValueError) as exc:
            log.error("%s: %s", pub.name, exc)
            errors.append({"url": pub.url, "error": str(exc)})
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
        "reason": reason,
    }


def process(candidates, classifier, errors):
    """Classified records, plus posts skipped as too short or as roundups/announcements.

    --post-url posts are never skipped.
    """
    records, skipped = [], []
    for i, cand in enumerate(candidates, 1):
        log.info("[%d/%d] %s", i, len(candidates), cand.url)
        try:
            post = fetch.fetch_post(cand.url, cand.publication)
            if not cand.forced and post.word_count is not None and post.word_count < settings.MIN_WORD_COUNT:
                log.info("Skipping, %d words < MIN_WORD_COUNT", post.word_count)
                skipped.append(_skipped(post, f"under {settings.MIN_WORD_COUNT} words ({post.word_count})"))
                continue
            result = classifier.classify(post)
        except (fetch.FetchError, ClassifyError, ValueError) as exc:
            log.error("%s: %s", cand.url, exc)
            errors.append({"url": cand.url, "error": str(exc)})
            continue
        if result["roundup"] and not cand.forced:
            log.info("Skipping, roundup or announcement")
            skipped.append(_skipped(post, "roundup or announcement"))
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
            "roundup": result["roundup"],
            "forced": cand.forced,
        })
    return records, skipped


def dry_run_report(records, skipped, errors):
    groups = {"relevant": [], "unsure": [], "not_relevant": []}
    for r in records:
        groups[r["relevance"]].append(r)
    lines = ["# Dry run", "",
             f"Classified {len(records)} posts: " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()),
             ""]
    for label, items in groups.items():
        lines += [f"## {label} ({len(items)})", ""]
        for r in items:
            flags = [f for f, on in (("paywalled", r["paywalled"]), ("roundup", r["roundup"]),
                                     ("forced", r["forced"])) if on]
            lines += [
                f"### {r['title']}" + (f" [{', '.join(flags)}]" if flags else ""),
                f"{r['publication']} · {r['date']} · {r['url']}",
                "",
                f"- Reason: {r['relevance_reason']}",
                f"- Summary: {r['summary']}",
                f"- Stance: {r['stance']}",
                f"- Tags: {', '.join(r['tags']) or '(none)'}",
                f"- Suggested tags: {', '.join(r['suggested_tags']) or '(none)'}",
                "",
            ]
    if skipped:
        lines += [f"## Skipped ({len(skipped)})", ""]
        lines += [f"- {s['title']} ({s['publication']}): {s['reason']} · {s['url']}" for s in skipped] + [""]
    if errors:
        lines += [f"## Errors ({len(errors)})", ""] + [f"- {e['url']}: {e['error']}" for e in errors] + [""]
    return "\n".join(lines)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    if args.force and not args.post_url:
        sys.exit("--force only applies with --post-url")
    if args.no_limit and not args.all_posts:
        sys.exit("--no-limit only applies with --all-posts")
    if not args.dry_run:
        sys.exit("Only --dry-run is implemented so far (build step 1).")

    errors = []
    candidates = gather_candidates(args, state.load_processed(), errors)
    log.info("%d posts to classify", len(candidates))
    records, skipped = process(candidates, Classifier(state.load_tags()), errors)

    settings.DRY_RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = settings.DRY_RUN_OUTPUT_DIR / f"dry-run-{stamp}.json"
    md_path = settings.DRY_RUN_OUTPUT_DIR / f"dry-run-{stamp}.md"
    json_path.write_text(json.dumps({"records": records, "skipped": skipped, "errors": errors}, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(dry_run_report(records, skipped, errors))
    log.info("Wrote %s and %s", json_path, md_path)


if __name__ == "__main__":
    main()
