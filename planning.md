
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

### Brand assets have arrived but have not yet been integrated

Current values (`--ean-card-bg`, `--ean-border`, `--ean-border-strong`, `--ean-tag-bg`, `--ean-tag-border`, `--ean-tag-active-bg`) are **neutral gray placeholders**, explicitly marked as such. When brand assets arrive, updating those variables (and possibly the tag-active color specifically) is the expected change — no other refactor should be needed.

### Tags are placeholder, not finalized

The current tag taxonomy (`soviet-origins`, `campus`, `genocide-accusation`, etc.) was drafted alongside the first batch of resource content and may well change. Do not build tag-name-specific logic (e.g., a hardcoded name→color mapping) — if per-tag colors are wanted later, each tag pill already carries a `data-tag="<id>"` attribute as a hook for an additive CSS rule, deliberately so no restructuring is needed.

## Naming convention

All CSS classes and the root `<div>` id are prefixed `ean-` (Expose Antizionism Now) deliberately, to avoid colliding with Squarespace's own theme classes or a future Squarespace update that introduces a generically-named class like `.card` or `.tag`. Keep this prefix on any new classes.

## Content status (as of Oct 2026)

- `data.json` currently ships with **7 sample resources** (one per category) used for testing the display/interactivity end-to-end. The full set (~57 resources, already drafted with descriptions/tags/citations) has **not yet been merged in** — this is the next real content task.
- Separately, the same 7 sample resources were also imported into Squarespace as native **draft blog posts** (via a WordPress-XML bulk-import trick), as a possible parallel, human-browsable, citable copy of the content. Whether to keep maintaining that blog-post copy alongside this widget, given the widget is now the actual source of truth, is an **open decision** — don't assume it should stay in sync with `data.json` without checking.

## Constraints worth knowing

- **No budget for paid tools or plugins** beyond the Squarespace subscription itself — this ruled out paid Squarespace filter plugins (Spark Plugin, Elfsight paid tier) in favor of this free, custom, GitHub+jsDelivr approach.
- Squarespace's Code Block only supports JavaScript/iframes on **Core plan tier or higher** (or during any trial, regardless of tier) — Basic/Personal-tier plans cannot run this widget at all.
