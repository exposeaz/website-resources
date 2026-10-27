"""Re-judges relevance, relevance_score and tags on stored articles, from their title, summary and stance.

Re-judges every article not yet judged under the current rules and vocabulary, so re-run it after changing
either. Saves after each article, so it resumes if interrupted.
Run export --sync afterwards to carry the changes into data.json.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.retag
"""

import logging
import sys

from substack_pipeline import state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = state.load_articles()
    classifier = Classifier(state.load_tags())
    pending = [a for a in articles if a.get("retagged") != classifier.retag_signature]
    log.info("%d of %d articles to re-judge", len(pending), len(articles))
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
        old = (article["relevance"], article.get("relevance_score"))
        article["relevance"] = result["relevance"]
        article["relevance_score"] = result["relevance_score"]
        article["tags"] = result["tags"]
        article["retagged"] = classifier.retag_signature
        # Scoped tags were judged in the same call
        article["scoped_tags_reviewed"] = classifier.scoped_signature
        state.save_articles(articles)
        log.info("[%d/%d] %s %s -> %s %d [%s] %s", i, len(pending), *old, result["relevance"],
                 result["relevance_score"], ", ".join(result["tags"]), article["title"])
    log.info("Done; %d failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
