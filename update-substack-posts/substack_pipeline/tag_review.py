"""Re-checks the narrowly scoped tags (those with a "scope" in config/tags.json) on stored articles.

Adds or removes each scoped tag, judging from the article's title, summary and stance. An article is
re-checked whenever any scope's wording changes. Saves after each article, so it resumes if interrupted.
Run it before the export that publishes the articles: data.json entries aren't updated afterwards.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.tag_review
"""

import logging
import sys

from substack_pipeline import state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError, scoped_signature, scoped_tags

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    tags = state.load_tags()
    scoped = scoped_tags(tags)
    if not scoped:
        sys.exit("No tags in config/tags.json have a scope; nothing to review.")
    signature = scoped_signature(tags)

    articles = state.load_articles()
    pending = [a for a in articles if a.get("scoped_tags_reviewed") != signature]
    log.info("%d of %d articles to review for: %s", len(pending), len(articles), ", ".join(t["id"] for t in scoped))
    if any(a.get("exported_resources") for a in pending):
        log.warning("Some of these are already in data.json; their entries there won't change")

    classifier = Classifier(tags)
    failed = 0
    for i, article in enumerate(pending, 1):
        try:
            verdicts = classifier.review_scoped_tags(article, scoped)
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
        article["scoped_tags_reviewed"] = signature
        state.save_articles(articles)
        log.info("[%d/%d] %s %s", i, len(pending), " ".join(changes) or "(no change)", article["title"])
    log.info("Done; %d failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
