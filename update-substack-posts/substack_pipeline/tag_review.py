"""Re-checks the narrowly scoped tags (those with a "scope" in config/tags.json) on stored articles.

Adds or removes each scoped tag, judging from the article's title, summary and stance. An article is
re-checked whenever any scope's wording changes. Saves after each article, so it resumes if interrupted.
With --only TAG, checks just those tags and leaves every other tag alone, e.g. after adding a new tag.
Run it before the export that publishes the articles: data.json entries aren't updated afterwards.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.tag_review [--only TAG ...]
"""

import argparse
import hashlib
import json
import logging
import sys

from config import settings
from substack_pipeline import state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError, scoped_signature, scoped_tags

log = logging.getLogger(__name__)


def _tag_signature(tag):
    """Changes whenever this one tag's scope wording changes, so --only knows what to re-check."""
    return hashlib.sha1(json.dumps(tag, sort_keys=True).encode()).hexdigest()[:12]


def main(argv=None):
    p = argparse.ArgumentParser(description="Re-check scoped tags on stored articles")
    p.add_argument("--only", nargs="+", metavar="TAG",
                   help="Check only these scoped tags, leaving every other tag unchanged.")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    tags = state.load_tags()
    scoped = scoped_tags(tags)
    if not scoped:
        sys.exit("No tags in config/tags.json have a scope; nothing to review.")
    signature = scoped_signature(tags)

    review = scoped
    if args.only:
        unknown = set(args.only) - {t["id"] for t in scoped}
        if unknown:
            sys.exit(f"Not scoped tags in config/tags.json: {', '.join(sorted(unknown))}")
        review = [t for t in scoped if t["id"] in args.only]
    # Per-tag marks let an --only run resume; a full review sets them too, so --only then skips those articles
    marks = {t["id"]: _tag_signature(t) for t in review}

    articles = state.load_articles()
    if args.only:
        # Articles classified under the current scopes were already judged for these tags
        pending = [a for a in articles if a.get("scoped_tags_reviewed") != signature
                   and any(a.get("scoped_tag_checks", {}).get(k) != v for k, v in marks.items())]
    else:
        pending = [a for a in articles if a.get("scoped_tags_reviewed") != signature]
    log.info("%d of %d articles to review for: %s", len(pending), len(articles), ", ".join(t["id"] for t in review))
    if any(a.get("exported_resources") for a in pending):
        log.warning("Some of these are already in data.json; their entries there won't change")

    classifier = Classifier(tags)
    failed = 0
    over_limit = 0
    for i, article in enumerate(pending, 1):
        try:
            verdicts = classifier.review_scoped_tags(article, review)
        except ClassifyAuthError as exc:
            sys.exit(f"Stopped: {exc}. Articles finished before this point are saved; re-run once fixed.")
        except (ClassifyError, ValueError) as exc:
            log.error("%s: %s", article["url"], exc)
            failed += 1
            continue
        changes = []
        for tag_id, applies in verdicts.items():
            if applies and tag_id not in article["tags"]:
                article["tags"].append(tag_id)
                changes.append(f"+{tag_id}")
            elif not applies and tag_id in article["tags"]:
                article["tags"].remove(tag_id)
                changes.append(f"-{tag_id}")
        over_limit += len(article["tags"]) > settings.MAX_TAGS
        article.setdefault("scoped_tag_checks", {}).update(marks)
        if not args.only:
            article["scoped_tags_reviewed"] = signature
        state.save_articles(articles)
        log.info("[%d/%d] %s %s", i, len(pending), " ".join(changes) or "(no change)", article["title"])
    if over_limit:
        log.warning("%d reviewed articles now have more than %d tags", over_limit, settings.MAX_TAGS)
    log.info("Done; %d failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
