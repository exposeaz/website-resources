# Substack pipeline

Finds antizionism-related posts on the Substacks in `config/substacks.yaml`, has Claude judge and tag them, and adds the best ones to the site's `data.json`.
Run every task from the repo root with `pixi run <task>`; tasks that call Claude need credentials (prefix with `opclaude` locally).

## Files

- `config/substacks.yaml`: publications to check.
- `config/tags.json`: the tag vocabulary; a tag with a `scope` applies only when that condition holds.
- `config/settings.py`: every tunable number (score bars, tag targets, limits); each can be overridden by an environment variable.
- `data/articles.json`: every classified post with its summary, tags, relevance and score; the source of truth.
- `data/processed.json`: URLs already seen, so they're never classified twice.

## Weekly run

`.github/workflows/update-substack-posts.yml` runs `pixi run pipeline` every Monday and opens a PR.
It fetches new posts, has Claude judge each from its full text, saves them to `articles.json`, and exports publishable ones to `data.json`.
A post is publishable if it is relevant and scores 5, or was picked by fill, and isn't marked a duplicate; posts added with `--post-url` always are.
Run it by hand from the Actions tab to force-include specific posts or check one publication.

## Clean-up steps (run by hand, in this order)

1. `retag` (Claude): re-judges relevance, score and tags for every article from its stored summary; re-run after changing the scoring rules or `tags.json`.
2. `dedupe` (Claude): within each publication, marks posts that repeat another's argument (`duplicate_of`), keeping the most useful.
3. `fill` (Claude): tops up each tag under 10 resources with held-back articles scoring 3 or more, once Claude confirms the tag is central to each (`published_for_tag`), adds nothing from a publication that already has 10 publishable articles (`FILL_MAX_PER_PUBLICATION`), and warns about tags still under 6.
4. `export-sync`: removes Substack cards that no longer qualify, refreshes the tags of the rest, and adds newly qualifying ones; cards deleted by hand stay deleted.

Each step saves as it goes, so an interrupted run can simply be started again.
Review `git diff data.json` before committing.

## Other tasks

- `dry-run` (Claude): classifies a small sample and writes a report to `output/`, without changing `articles.json` or `data.json`.
- `export`: adds publishable articles to `data.json` without the sync step.
- `tag-stats`: counts the tags Claude suggested beyond the vocabulary, to spot new tag candidates.
- `tag-review`: re-checks only the scoped tags; not needed after `retag`.
- `pr-body`: writes the weekly PR description.
