# Substack pipeline

Finds antizionism-related posts on the Substacks in `config/substacks.yaml`, has Claude judge and tag them, and adds the best ones to the site's `data.json`.
Run every task from the repo root with `pixi run <task>`; tasks that call Claude need credentials (prefix with `opclaude` locally).

## All tasks

| Task | Claude | Changes | What it does |
|---|---|---|---|
| `pipeline` | yes | `articles.json`, `processed.json`, `data.json` | Weekly run: classifies new posts from their full text and exports publishable ones. Flags: `--post-url URL` (force-include), `--force` (reclassify those URLs), `--publication-url URL` (one publication). |
| `dry-run` | yes | `output/` only | Classifies a small sample and writes a report, changing nothing else. |
| `retag` | yes | `articles.json` | Re-judges relevance, score and tags for every article from its stored summary. |
| `retag-full-text` | yes | `articles.json` | Same, from the full post (re-fetched), for articles scoring 4+, everything publishable, and anything re-read before. |
| `dedupe` | yes | `articles.json` | Marks posts that repeat another post's argument within the same publication (`duplicate_of`). |
| `fill` | yes | `articles.json` | Tops up tags under 10 resources with held-back articles Claude confirms are on-theme (`published_for_tag`). |
| `export-sync` | no | `data.json` | Removes cards that no longer qualify, refreshes tags and category (News or not), and adds new ones. |
| `export` | no | `data.json` | Only adds newly publishable articles; no removals or re-tagging. |
| `add-resource` | yes | `data.json` | Adds non-Substack pages (`--category essays URL ...`) or re-tags existing entries (`--retag ID ...`). |
| `tag-review` | yes | `articles.json` | Re-checks only the scoped tags; not needed after `retag`. |
| `tag-stats` | no | nothing | Counts the tags Claude suggested beyond the vocabulary, to spot new tag candidates. |
| `pr-body` | no | `output/pr-body.md` | Writes the weekly PR description. |

Tasks that change the same file must not run at the same time.

## Files

- `config/substacks.yaml`: publications to check.
- `config/tags.json`: the tag vocabulary; a tag with a `scope` applies only when that condition holds, and a `manual` tag is never assigned by the pipeline, only by hand in `data.json`.
- `config/settings.py`: every tunable number (score bars, tag targets, limits); each can be overridden by an environment variable.
- `data/articles.json`: every classified post with its summary, tags, relevance and score; the source of truth.
- `data/processed.json`: URLs already seen, so they're never classified twice.

## Weekly run

`.github/workflows/update-substack-posts.yml` runs `pixi run pipeline` every Monday and opens a PR.
It fetches new posts, has Claude judge each from its full text, saves them to `articles.json`, and exports publishable ones to `data.json`.
A post is publishable if it is relevant and scores 5, or was picked by fill, and isn't marked a duplicate; posts added with `--post-url` always are.
Posts Claude tags `news` (mainly reporting events) go to the News category instead, with a lower bar (relevant, score 2 or more); they never count toward fill's tag totals or cap, and the site leaves them out of tag and search results unless the visitor shows them.
Run it by hand from the Actions tab to force-include specific posts or check one publication.

## Clean-up steps (run by hand, in this order)

1. `retag` (Claude): re-judges relevance, score and tags for every article from its stored summary; re-run after changing the scoring rules or `tags.json`.
   `retag-full-text` (Claude) does the same from the full post, re-fetched, for articles scoring 4 or more, everything publishable, and anything re-read before; slower and costlier, but more accurate.
2. `dedupe` (Claude): within each publication, marks posts that repeat another's argument (`duplicate_of`), keeping the most useful.
3. `fill` (Claude): tops up each tag under 10 resources with held-back articles scoring 3 or more, once Claude confirms the tag is central to each (`published_for_tag`), adds nothing from a publication that already has 10 publishable articles (`FILL_MAX_PER_PUBLICATION`), and warns about tags still under 6.
4. `export-sync`: removes Substack cards that no longer qualify, refreshes the tags of the rest, and adds newly qualifying ones; cards deleted by hand stay deleted.

Each step saves as it goes, so an interrupted run can simply be started again.
Review `git diff data.json` before committing.

## Non-Substack resources

`add-resource` (Claude) adds essays, articles and other pages to `data.json`: it fetches each page and writes the description, citation and 1-5 tags, flagging any with fewer than 2 for you to finish.
`pixi run add-resource --category essays URL [URL ...]` adds pages; paywalled or thin pages are skipped and listed, to add by hand.
`pixi run add-resource --retag RESOURCE_ID [...]` re-tags existing entries from their pages, keeping manual tags and leaving their text alone.
