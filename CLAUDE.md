# CLAUDE.md — website-resources

Context for Claude Code sessions working in this repo. Read this before making changes.


## First and foremost, Coding rules and expectations. These are the most important.

- ALWAYS assume we are having a design discussion UNLESS I explicitly give you permission to write code.
- Do NOT run `git add`, `git commit`, `git push`, `git revert`, `git checkout` or any other git write commands without explicit permission. The human must approve all git operations.
- Do NOT create, read, or modify `.env` files or any file containing credentials, tokens, or secrets.
- You MAY fetch public URLs (documentation, reference pages) using the WebFetch tool to help answer questions or research tools.
- Do NOT make API calls that send credentials, tokens, or user data to external services.
- Do NOT use `curl` or `wget` from the shell — use the WebFetch tool instead, which is sandboxed and auditable.
- Do NOT install system-level packages or modify system configuration.
- Do NOT rewrite, condense, or rephrase user-facing copy (help text, labels, instructions) during code cleanup or simplification — only change markup and structure.
- When adding text to markdown files, write only one sentence per line to make diff review easier. 
- Do NOT implement code changes without explicit permission.
- NEVER DELETE OR MODIFY .env files
- When the user asks a question about existing code or design ("why is X here?", "do we need Y?", "should this be Z?"), treat it as a discussion prompt — explain the reasoning and ask for direction before making any changes. Only modify code after the user has explicitly agreed on a course of action.
- Assume when the user asks to discuss an idea, they are looking to explore different angles, pros, and cons. They do not only want validation. If it is a good idea, say so and why. If there are drawbacks, say so and why. Do not invent good or bad qualities where there are none. 
- When you have made changes, stop and describe what you changed and why so the human can review.
- If you are unsure whether an action is allowed, ask rather than proceeding.
- Keep changes small and incremental. Prefer multiple small steps over one large batch of changes.
- When writing scripts that interact with a third party API, ensure that the code treats the API with respect with regard to rate limits. 

## What this repo is

Source for a filterable, searchable resource-library widget embedded on a nonprofit's Squarespace site (an antizionism-education advocacy org). The widget lets visitors browse educational resources (books, scholarly articles, essays, legal commentary, organizations, letters, declarations) by category, filter by cross-cutting tags, and free-text search — all client-side, no backend.

## How it's deployed (this is the part that's easy to get wrong)

This repo is **not** deployed via GitHub Pages, a build step, or any framework. It's served as-is, directly from GitHub, via **jsDelivr's free CDN** (`cdn.jsdelivr.net/gh/exposeaz/website-resources@main/<file>`), which mirrors any public GitHub repo automatically with zero configuration.

A tiny, permanent snippet is pasted once into a Squarespace Code Block on the live site:

```html
<div id="ean-resources-root"></div>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/ean-resources.css">
<script src="https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/ean-resources.js"></script>
```

That stub should **never need to change**. Every content or styling change happens by editing files in this repo and pushing — Squarespace is never touched again for routine updates.

**Caching caveat:** jsDelivr caches files, so a push doesn't show up instantly. A GitHub Action (`.github/workflows/purge-jsdelivr.yml`) auto-purges the cache on every push to `main` that touches the three live files. It can also be triggered manually from the Actions tab. Even after a successful purge, the *browser* may still show a stale cached copy — a hard reload or incognito window is the reliable way to verify a change actually landed.


