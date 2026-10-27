"""Marks near-duplicate articles within each publication, so only the most useful of each group is published.

Considers articles fill could publish (not --post-url ones), one Claude call per publication.
A dropped article gets duplicate_of (the kept article's URL) and duplicate_reason; each publication's
earlier marks are replaced when its call succeeds, so it can be re-run.
Run after retag and before fill.
Don't run it while the pipeline is running: both write data/articles.json.
Run from update-substack-posts/: python -m substack_pipeline.dedupe
"""

import logging
import sys
from collections import defaultdict

from substack_pipeline import state
from substack_pipeline.classify import Classifier, ClassifyAuthError, ClassifyError
from substack_pipeline.export import fill_candidate

log = logging.getLogger(__name__)


def _valid_groups(groups, n):
    """Groups with in-range numbers, each article in at most one group, and at least one dropped."""
    used = set()
    for g in groups:
        drop = [j for j in dict.fromkeys(g["drop"]) if 0 <= j < n and j != g["keep"] and j not in used]
        if not 0 <= g["keep"] < n or g["keep"] in used or not drop:
            log.warning("Ignoring invalid group %s", g)
            continue
        used.update([g["keep"], *drop])
        yield g["keep"], drop, g["reason"]


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = state.load_articles()
    by_pub = defaultdict(list)
    for a in articles:
        if not a["forced"] and fill_candidate(a):
            by_pub[a["publication"]].append(a)
    classifier = Classifier(state.load_tags())
    failed = 0
    for pub, items in sorted(by_pub.items()):
        if len(items) < 2:
            continue
        items.sort(key=lambda a: a["date"])
        try:
            groups = classifier.group_duplicates(items)
        except ClassifyAuthError as exc:
            sys.exit(f"Stopped: {exc}. Publications finished before this point are saved; re-run once fixed.")
        except (ClassifyError, ValueError) as exc:
            log.error("%s: %s", pub, exc)
            failed += 1
            continue
        for a in items:
            a.pop("duplicate_of", None)
            a.pop("duplicate_reason", None)
        dropped = 0
        for keep, drop, reason in _valid_groups(groups, len(items)):
            # Never drop a post for a lower-scoring one, which may not be published
            group = [keep, *drop]
            best = max(group, key=lambda i: items[i]["relevance_score"])
            if items[best]["relevance_score"] > items[keep]["relevance_score"]:
                keep, drop = best, [i for i in group if i != best]
            log.info("%s: keep %r, drop %s (%s)", pub, items[keep]["title"],
                     ", ".join(repr(items[j]["title"]) for j in drop), reason)
            for j in drop:
                items[j]["duplicate_of"] = items[keep]["url"]
                items[j]["duplicate_reason"] = reason
            dropped += len(drop)
        state.save_articles(articles)
        log.info("%s: %d of %d marked as duplicates", pub, dropped, len(items))
    log.info("Done; %d publications failed (re-run to retry them)", failed)


if __name__ == "__main__":
    main()
