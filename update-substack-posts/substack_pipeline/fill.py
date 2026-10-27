"""Tops up thin tags with held-back articles, so each tag has TAG_TARGET_RESOURCES resources on the site.

Counts each tag across data.json's other resources plus the articles already publishable. Scarcest tags
first, each tag below the target gets held-back articles scoring at least TAG_FILL_MIN_SCORE (highest score,
then most central tag, then newest), marked published_for_tag, once Claude confirms the tag is central to
the article. Verdicts are cached in fill_checks (retag clears them); earlier marks are cleared, so it can be
re-run. Warns about tags still under TAG_MIN_RESOURCES.
Run after dedupe and before export --sync.
Run from update-substack-posts/: python -m substack_pipeline.fill
"""

import json
import logging
import sys
from collections import Counter

from config import settings
from substack_pipeline import state
from substack_pipeline.classify import NEWS_TAG, Classifier, ClassifyAuthError, ClassifyError
from substack_pipeline.export import fill_candidate, publishable

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = state.load_articles()
    for a in articles:
        a.pop("published_for_tag", None)
    data = json.loads(settings.RESOURCES_FILE.read_text())
    counts = Counter(t for r in data["resources"] if r["category"] != settings.RESOURCE_CATEGORY_ID for t in r["tags"])
    counts.update(t for a in articles if publishable(a) for t in a["tags"])
    before = Counter(counts)

    pool = [a for a in articles if not publishable(a) and not a.get("duplicate_of") and fill_candidate(a)]
    pool.sort(key=lambda a: a["date"], reverse=True)
    vocab = state.load_tags()
    classifier = Classifier(vocab)
    defs = {t["id"]: t for t in vocab}

    def confirmed(a, tag):
        checks = a.setdefault("fill_checks", {})
        if tag not in checks:
            checks[tag] = classifier.confirm_tag(a, defs[tag])
            state.save_articles(articles)
        return checks[tag]

    # news is a format, not a theme
    tags = [t["id"] for t in vocab if t["id"] != NEWS_TAG]
    for tag in sorted(tags, key=lambda t: counts[t]):
        need = settings.TAG_TARGET_RESOURCES - counts[tag]
        if need <= 0:
            continue
        candidates = sorted((a for a in pool if tag in a["tags"] and not a.get("published_for_tag")),
                            key=lambda a: (-a["relevance_score"], a["tags"].index(tag)))
        for a in candidates:
            if need <= 0:
                break
            try:
                if not confirmed(a, tag):
                    log.info("%s: skip (not central) %s | %s", tag, a["publication"], a["title"])
                    continue
            except ClassifyAuthError as exc:
                sys.exit(f"Stopped: {exc}. Verdicts so far are saved; re-run once fixed.")
            except (ClassifyError, ValueError) as exc:
                log.error("%s: %s", a["url"], exc)
                continue
            a["published_for_tag"] = tag
            counts.update(a["tags"])
            need -= 1
            log.info("%s: + %d %s | %s", tag, a["relevance_score"], a["publication"], a["title"])
    state.save_articles(articles)

    width = max(len(t) for t in tags)
    for tag in sorted(tags, key=lambda t: counts[t]):
        log.info("%s  %3d -> %3d", tag.ljust(width), before[tag], counts[tag])
    short = [f"{t} ({counts[t]})" for t in tags if counts[t] < settings.TAG_MIN_RESOURCES]
    if short:
        log.warning("Still under %d resources: %s", settings.TAG_MIN_RESOURCES, ", ".join(short))
    log.info("Marked %d articles to publish; run export --sync next", sum(bool(a.get("published_for_tag")) for a in articles))


if __name__ == "__main__":
    main()
