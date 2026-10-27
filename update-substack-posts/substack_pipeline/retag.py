"""Re-judges relevance, relevance_score and tags on stored articles.

By default judges from each article's title, summary and stance, for every article not yet judged under the
current rules and vocabulary, so re-run it after changing either.
With --full-text, re-fetches and re-reads the full post (the weekly run's prompt) for articles scoring
FULL_TEXT_MIN_SCORE or more and everything publishable; summaries are kept.
Saves after each article, so it resumes if interrupted.
Then run dedupe, fill and export --sync to carry the changes into data.json.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.retag [--full-text]
"""

import argparse
import hashlib
import json
import logging
import sys

from config import settings
from substack_pipeline import fetch, state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError
from substack_pipeline.export import publishable

log = logging.getLogger(__name__)


def _publication(article, configured):
    host = fetch.base_url(article["url"])
    return next((p for p in configured if p.url == host),
                fetch.Publication(name=article["publication"], url=host, description=""))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Re-judge relevance, score and tags on stored articles")
    p.add_argument("--full-text", action="store_true",
                   help=f"re-read full posts for articles scoring {settings.FULL_TEXT_MIN_SCORE}+ or publishable")
    full_text = p.parse_args().full_text

    articles = state.load_articles()
    classifier = Classifier(state.load_tags())
    if full_text:
        # Changes whenever the full-text prompt or vocabulary change
        signature = hashlib.sha1((classifier.system + json.dumps(classifier.schema, sort_keys=True)).encode()).hexdigest()[:12]
        targets = [a for a in articles
                   if a.get("relevance_score", 0) >= settings.FULL_TEXT_MIN_SCORE or publishable(a)]
        pending = [a for a in targets if a.get("reread") != signature]
        configured = state.load_publications()
    else:
        signature = classifier.retag_signature
        pending = [a for a in articles if a.get("retagged") != signature]
    log.info("%d of %d articles to re-judge%s", len(pending), len(articles), " from full text" if full_text else "")

    failed = 0
    for i, article in enumerate(pending, 1):
        try:
            if full_text:
                result = classifier.classify(fetch.fetch_post(article["url"], _publication(article, configured)))
            else:
                result = classifier.retag(article)
        except ClassifyAuthError as exc:
            sys.exit(f"Stopped: {exc}. Articles finished before this point are saved; re-run once fixed.")
        except (fetch.FetchError, ClassifyError, ValueError) as exc:
            log.error("%s: %s", article["url"], exc)
            failed += 1
            continue
        old = (article["relevance"], article.get("relevance_score"))
        article["relevance"] = result["relevance"]
        article["relevance_score"] = result["relevance_score"]
        article["tags"] = result["tags"]
        article.pop("fill_checks", None)  # fill's verdicts were on the old tags
        article["reread" if full_text else "retagged"] = signature
        # Scoped tags were judged in the same call
        article["scoped_tags_reviewed"] = classifier.scoped_signature
        state.save_articles(articles)
        log.info("[%d/%d] %s %s -> %s %d [%s] %s", i, len(pending), *old, result["relevance"],
                 result["relevance_score"], ", ".join(result["tags"]), article["title"])
    log.info("Done; %d failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
