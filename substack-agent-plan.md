# Build: Substack → antizionism resource library pipeline

## Goal
Build a Python pipeline that lives in **https://github.com/exposeaz/website-resources** (in its own subdirectory, `update-substack-posts/`, so it doesn't clutter the repo) and regularly:
1. Checks a fixed set of Substacks for posts published after `START_DATE`, skipping posts already processed. An option should be present to check all posts across the entire substack's lifetime.
2. Uses Claude to decide whether each post is relevant, even loosely, to antizionism. Only relevant posts are kept. If it is unsure, it should be kept for manual review. For each kept post, it generates a short summary, tags from a controlled vocabulary, suggested new tags, and a stance phrase.
3. Opens PRs with the new items to two repos:
   - **website-resources** (this same repo): append entries to the `data.json` under the category "Substack articles" (which should be created if it doesn't exist)
   - **https://github.com/exposeaz/azaryah**: update the AI prompt markdown file that the chatbot uses (details below). The prompt file to write is present in `lambda/azaryah-ws-default/prompts/substack-posts.md`. Keep the edit to only new additions


## No hardcoded parameters
Every number and tunable parameter lives in one constants/config module (e.g. `config/settings.py`, overridable by env vars where sensible). Nothing numeric or tunable should be inlined in logic or prompts; prompt text should interpolate the constants. Starting values:

| Constant | Default |
|---|---|
| `START_DATE` | `2026-10-11` |
| `MODEL` | `claude-sonnet-5-5` |
| `MAX_OUTPUT_TOKENS` | 600 |
| `MIN_TAGS` | 1 |
| `MAX_TAGS` | 5 |
| `MAX_SUGGESTED_TAGS` | 5 |
| `SUMMARY_MIN_SENTENCES` / `SUMMARY_MAX_SENTENCES` | 1 / 2 |
| `MAX_TEXT_CHARS` | 20000 |
| `REQUEST_DELAY_SECONDS` | 1 |
| `ARCHIVE_PAGE_SIZE` | 50 |
| `MAX_RETRIES` / `RETRY_BACKOFF_SECONDS` | 3 / 5 |
| `DRY_RUN_SAMPLE_SIZE` | 25 |

Paths, repo names, file paths and the Repo B header sentence also go in config.

## Sources
Put these in `config/substacks.yaml` (name, URL, description). Pass the description to Claude as context when classifying that publication's posts. Each URL is fetched once even if multiple names share it.

- Movement Against Antizionism: https://movementagainstantizionism.substack.com
- Institute for Critical Study of Antizionism (ICSA): https://icsa.substack.com. Scholarly institute founded by Andrew Pessin; research, journal, and courses on antizionism's history and ideology.
- Andrew Pessin: https://andrewpessin.substack.com. Philosophy professor, ICSA founder; weekly commentary on campus antisemitism/antizionism.
- Adam Louis-Klein: https://adamlouisklein.substack.com. Anthropologist, founder of Movement Against Antizionism; Jewish identity and critiques of antizionist ideological frameworks.
- Naya Lekht: https://nayalekht.substack.com. PhD in Russian literature (Soviet antizionism), co-founder of Stop Antizionism; politics, education, history.
- Joshua Dabelstein: https://fornormalpeople.substack.com. Sydney-based, heads Movement Against Antizionism AU; "For Normal People," exclusively about antizionism.
- Samuel J. Hyde: https://sjhyde.substack.com. South Africa-born Israeli cultural analyst; argues antizionism should be studied as its own field.
- Jonah Platt: https://jonahplatt.substack.com. "Being Jewish with Jonah Platt"; interviews on Jewish identity and antizionism, mainstream/entertainment-adjacent.
- Izabella Tabarovsky: https://newrefuseniks.substack.com. Scholar of Soviet antizionism, author of *Be a Refusenik*; links Soviet Jewish dissent to today's campus antizionism.
- Kevin Deutsch: https://kevindeutsch.substack.com. Journalist, founder of "After October 7" media watchdog; tracks antizionist activity in politics and media.
- Jennifer Kogan / Levari: https://jenniferkogan.substack.com. Clinical social worker; "Jewish Fierce Compassion" analyzes antizionism through a psychological-abuse framework. Levari (trauma-informed education on antizionism) publishes through this same Substack.
- Kile B. Jones: https://kilejones.substack.com. Former antizionist; "Inverted World" deconstructs antizionist language and lexicon.
- ESK: https://thegoldenpill.substack.com. "The Golden Pill"; pushing back on antisemitism/antizionism as an information war; Jewish identity, antizionist rhetoric, media narratives about Israel.
- Einat Wilf: https://einatwilf.substack.com. Former Israeli MK; antizionism and Palestinianism.
- David Christopher Kaufman: https://davidkaufman.substack.com. "COUNTERINTUITIVE"; antizionism.
- Sarah Ettedgui: https://sarahettedgui.substack.com. Mizrahi/Sephardic lawyer; antizionism in society.
- Whole Story Institute: https://ghrosenb.substack.com. "Combating Anti-Zionism Through Education in History, Politics and Law"; regional history.
- Moral Clarity: https://moralclarity.substack.com. Description: pull the publication's own name and description from its about page or feed metadata, and show it to me for confirmation.

## Manual input
Besides the scheduled run over the configured publications, support ad hoc input via CLI flags and matching `workflow_dispatch` inputs (so I can trigger them from the GitHub Actions UI):
- `--post-url <url>` (repeatable or comma-separated): process specific Substack posts. These are **force-included**: skip the relevance gate (still record `relevance_reason`, and warn in the PR body if the model judged it not relevant), ignore `START_DATE`, and still generate summary, tags, suggested_tags and stance. Dedupe still applies.
- `--publication-url <url>`: run the normal pipeline (relevance gate, `START_DATE`, dedupe) for one publication that isn't in `config/substacks.yaml`, without adding it to the config.
- Manual runs go through the same PR flow as scheduled ones.

## Fetching
- Use each publication's `/feed` RSS for recent posts. For the initial backfill to `START_DATE`, use the public JSON endpoints (`/api/v1/archive` or `/api/v1/posts?limit=&offset=`, paged by `ARCHIVE_PAGE_SIZE`) and `/api/v1/posts/{slug}` for full content. These are unofficial: handle failures gracefully, retry per `MAX_RETRIES`, and wait `REQUEST_DELAY_SECONDS` between requests.
- Paid posts only expose a preview. Classify from what's available and record `paywalled: true`. Never try to get around the paywall.
- Strip HTML to text and truncate to `MAX_TEXT_CHARS`.

## Classification (one Claude call per post, forced tool use)
Tool schema fields (array bounds come from the constants):
- `is_relevant` (bool): Is the post substantively about antizionism (its ideology, rhetoric, history, institutions, or responses to it)? Passing mentions don't count.
- `relevance_reason` (string, one sentence): for auditing.
- `tags` (array, enum of the vocabulary IDs below, `MIN_TAGS`–`MAX_TAGS` items).
- `suggested_tags` (array of strings, max `MAX_SUGGESTED_TAGS`): themes not covered by the vocabulary. Empty if none; never repeats vocabulary tags.
- `stance` (string): short phrase describing the author's position, e.g. "critical of X," "news report, no clear position."
- `summary` (string, `SUMMARY_MIN_SENTENCES`–`SUMMARY_MAX_SENTENCES` sentences): what the author argues or reports, attributed to the author ("The author argues…"). Neutral wording; don't evaluate the argument.

Controlled vocabulary (`config/tags.json`):
```json
[
  {"id": "antizionism", "label": "Antizionism"},
  {"id": "soviet-antizionism", "label": "Soviet antizionism"},
  {"id": "antizionism-academy", "label": "Antizionism in the academy"},
  {"id": "antizionism-medicine", "label": "Antizionism in medicine"},
  {"id": "antizionism-arts", "label": "Antizionism in the arts"},
  {"id": "antizionism-progressive", "label": "Antizionism in progressive spaces"},
  {"id": "oct7", "label": "October 7th"},
  {"id": "genocide-libel", "label": "Genocide libel"},
  {"id": "campus", "label": "Campuses"},
  {"id": "islamism", "label": "Islamism"},
  {"id": "arab-supremacy", "label": "Arab supremacy"},
  {"id": "poland-1968", "label": "Poland 1968 purges"},
  {"id": "colonizer-libel", "label": "Colonizer libel"},
  {"id": "apartheid-libel", "label": "Apartheid libel"},
  {"id": "bds", "label": "BDS and Boycotts"},
  {"id": "advocacy", "label": "Advocacy"},
  {"id": "media-commentary", "label": "Media bias"},
  {"id": "legal-public-affairs", "label": "Legal & Public-Affairs Commentary"},
  {"id": "data-research", "label": "Data & Research"}
]
```
After each call, validate that tags are a subset of the vocabulary and drop any that aren't.

## State & outputs (in website-resources)
- `update-substack-posts/data/processed.json`: every URL seen (relevant or not), so it's never reclassified.
- `update-substack-posts/data/articles.json`: full records for relevant posts (publication, title, URL, date, summary, tags, suggested_tags, stance, paywalled, relevance_reason).
- A script that prints suggested_tags frequency across all records, so I can review candidates for the vocabulary.
- Dedupe by normalized post URL (lowercase host, strip query string and trailing slash) against local state only.
- State files live on main in website-resources and are updated as part of the pipeline's PR to that repo (including URLs judged not relevant). If a pipeline PR is still open when a run starts, add to that PR's branch instead of opening a new one.

## Azaryah prompt file format
At the top of the section, add exactly this sentence (stored in config):

> These are specific Substack articles on relevant topics that can be recommended to users:

Below it, a markdown table with columns **Substack | Title | Link | Description** (no tags). Append new rows only. Escape `|` and strip newlines in titles and descriptions. If the file has other content, put this section at the end and update it in place on later runs.

## PRs (handled by the workflow, not Python)
- The Python pipeline only reads inputs and writes updated files (the resources JSON, state files, the azaryah prompt file, and a PR-body markdown file). It does no git operations and makes no GitHub API calls.
- The workflow checks out both repos (azaryah into a subdirectory via `actions/checkout` with `repository: exposeaz/azaryah` and the fine-grained token), runs the pipeline against those working trees, then opens PRs with `peter-evans/create-pull-request` (pinned version):
  - website-resources: `GITHUB_TOKEN`
  - azaryah: the fine-grained token
- Use a fixed branch name per repo (in workflow env), so a still-open PR gets updated instead of duplicated. The action handles this natively.
- If the pipeline produced no changes, no PR is created.
- One PR per target repo per run, only when there are new items. If a pipeline PR from an earlier run is still open, add to that PR's branch instead of opening another. The PR body lists the new articles with each one's relevance_reason, so I can review before merging.

## Automation
- GitHub Actions workflow in website-resources on a weekly cron (schedule in the workflow file, not buried in code), plus `workflow_dispatch`.
- PRs to website-resources: use the built-in `GITHUB_TOKEN` with `contents: write` and `pull-requests: write` permissions. Tell me if I need to enable "Allow GitHub Actions to create and approve pull requests" in the repo settings. Note: PRs opened with `GITHUB_TOKEN` don't trigger other workflows; if website-resources has CI that must run on these PRs, use the token below for this repo too and tell me.
- PRs to azaryah: `GITHUB_TOKEN` can't reach other repos, so use a fine-grained personal access token (or GitHub App) scoped to exposeaz/azaryah only, with contents and pull-request write access, stored as a secret. Tell me exactly what to create and what to name the secret.
- `ANTHROPIC_API_KEY` as a repo secret.
- Use a `concurrency` group so two runs never overlap.

## Build order
1. Fetch and classify with a `--dry-run` flag that writes local output only. Run it on `DRY_RUN_SAMPLE_SIZE` recent posts and show me the results (especially the relevant/not-relevant split and the summaries) before going further.
2. Backfill to `START_DATE`.
3. Add PR creation; test against both repos with a single item.
4. Add the scheduled workflow.
