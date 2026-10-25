"""Adds relevance_score and the news tag to stored articles that lack a score, from their title, summary and stance.

For articles classified before scoring existed. Saves after each article, so it resumes if interrupted.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.retag
"""

import logging
import sys

from substack_pipeline import state
from substack_pipeline.classify import NEWS_TAG, Classifier, ClassifyAuthError, ClassifyError

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = state.load_articles()
    pending = [a for a in articles if "relevance_score" not in a]
    log.info("%d of %d articles need a score", len(pending), len(articles))
    classifier = Classifier(state.load_tags())
    failed = 0
    for i, article in enumerate(pending, 1):
        try:
            result = classifier.retag(article)
        except ClassifyAuthError as exc:
            sys.exit(f"Stopped: {exc}. Articles finished before this point are saved; re-run once fixed.")
        except (ClassifyError, ValueError) as exc:
            log.error("%s: %s", article["url"], exc)
            failed += 1
            continue
        article["relevance_score"] = result["relevance_score"]
        # news is a format tag, so it may go past MAX_TAGS
        if result["news"] and NEWS_TAG not in article["tags"]:
            article["tags"].append(NEWS_TAG)
        state.save_articles(articles)
        log.info("[%d/%d] score %d%s %s", i, len(pending), result["relevance_score"],
                 " +news" if result["news"] else "", article["title"])
    log.info("Done; %d failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
