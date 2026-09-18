# CLAUDE.md — website-resources

Context for Claude Code sessions working in this repo. Read this before making changes.

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

## Files

| File | Purpose |
|---|---|
| `ean-resources.js` | All widget logic: fetches `data.json`, renders category cards → drills into resource cards, handles search + tag filtering (filtering is global/cross-category, not scoped to one category), renders the "back to categories" link. |
| `ean-resources.css` | All widget styling. See "Design philosophy" below — most of it deliberately does *not* set fonts or colors. |
| `data.json` | All content: `categories`, `tags`, and `resources` arrays. This is the single source of truth — the widget has no other data source. |
| `README.md` | User-facing (non-technical) explanation of the same things, written for the org's founder, not for an engineer. |
| `.github/workflows/purge-jsdelivr.yml` | Auto-purges jsDelivr cache on push. |

## Design philosophy: inherit, don't impose

The org's founder is not a designer and wants the widget to look like a native part of the Squarespace template, not a bolted-on tool. The CSS is written accordingly:

- **No hardcoded font-family, anywhere.** Text inherits the surrounding page's typography.
- **No hardcoded text/heading colors.** Uses `color: inherit` / `currentColor` throughout.
- **Tag filter pills use Squarespace's own button classes** (`sqs-block-button-element`, `--primary`/`--tertiary`) so their shape/hover behavior comes from the site's actual Design → Buttons settings, not from us.
- **The "back to categories" control is a real `<a>`**, not a styled `<button>`, specifically so it inherits the theme's real link color/hover state rather than looking like plain underlined text.
- **The widget container is `width: 100%`**, not a hardcoded `max-width` — it defers to whatever width Squarespace's own section settings establish.

**The exceptions, and why they exist** (don't "fix" these back to full inheritance without checking with the user first):
- Card title font-size (`.ean-cat-card h3`, `.ean-res-card h4`) is explicitly capped. Inheriting the raw theme heading size caused severe word-wrapping (the template's default H3 is a large display size meant for page headers, not compact card titles).
- Card backgrounds, borders, and the tag "active" color are real, intentional custom colors — the founder explicitly wants cards to read as filled cards, not transparent outlines, and wants tag pills to be able to carry brand color. These live in **one clearly-labeled block at the top of `ean-resources.css`** (`CUSTOM VALUES`), as CSS custom properties, specifically so they're easy to find and swap.

### Brand assets are coming (~2.5 weeks out as of Sept 2026)

The founder's graphic designer is delivering a real color palette, fonts, and logo. Current values (`--ean-card-bg`, `--ean-border`, `--ean-border-strong`, `--ean-tag-bg`, `--ean-tag-border`, `--ean-tag-active-bg`) are **neutral gray placeholders**, explicitly marked as such. When brand assets arrive, updating those variables (and possibly the tag-active color specifically) is the expected change — no other refactor should be needed.

### Tags are placeholder, not finalized

The current tag taxonomy (`soviet-origins`, `campus`, `genocide-accusation`, etc.) was drafted alongside the first batch of resource content and may well change. Do not build tag-name-specific logic (e.g., a hardcoded name→color mapping) — if per-tag colors are wanted later, each tag pill already carries a `data-tag="<id>"` attribute as a hook for an additive CSS rule, deliberately so no restructuring is needed.

## Naming convention

All CSS classes and the root `<div>` id are prefixed `ean-` (Expose Antizionism Now) deliberately, to avoid colliding with Squarespace's own theme classes or a future Squarespace update that introduces a generically-named class like `.card` or `.tag`. Keep this prefix on any new classes.

## Content status (as of Sept 2026)

- `data.json` currently ships with **7 sample resources** (one per category) used for testing the display/interactivity end-to-end. The full set (~57 resources, already drafted with descriptions/tags/citations) has **not yet been merged in** — this is the next real content task.
- Separately, the same 7 sample resources were also imported into Squarespace as native **draft blog posts** (via a WordPress-XML bulk-import trick), as a possible parallel, human-browsable, citable copy of the content. Whether to keep maintaining that blog-post copy alongside this widget, given the widget is now the actual source of truth, is an **open decision** — don't assume it should stay in sync with `data.json` without checking.

## Constraints worth knowing

- **No budget for paid tools or plugins** beyond the Squarespace subscription itself — this ruled out paid Squarespace filter plugins (Spark Plugin, Elfsight paid tier) in favor of this free, custom, GitHub+jsDelivr approach.
- Squarespace's Code Block only supports JavaScript/iframes on **Core plan tier or higher** (or during any trial, regardless of tier) — Basic/Personal-tier plans cannot run this widget at all.


# Coding rules and expectations

- ALWAYS assume we are having a design discussion UNLESS I explicitly give you permission to write code.
- Do NOT run `git add`, `git commit`, `git push`, `git revert`, or any other git write commands. The human will handle all git operations unless you are explicitly given permission to do so on a case-by-case basis.
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
- When you have made changes, stop and describe what you changed and why so the human can review.
- If you are unsure whether an action is allowed, ask rather than proceeding.
- Keep changes small and incremental. Prefer multiple small steps over one large batch of changes.
- When writing scripts that interact with a third party API, ensure that the code treats the API with respect with regard to rate limits. 