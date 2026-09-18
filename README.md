# website-resources

Powers the antizionism education resource library on the Squarespace site. 
A filterable, searchable card browser for books, articles, essays, legal commentary, organizations, letters, and declarations.

## How it works

This repo is hosted for free via [jsDelivr](https://www.jsdelivr.com/), a CDN that serves files directly from public GitHub repos. 
A tiny snippet pasted into a Squarespace Code Block loads these files on every page view.
This means updating a file here updates the live site automatically, with no further action needed on the Squarespace side.

## Files

- **`ean-resources.css`** / **`ean-resources.js`** — the widget itself (layout, search, tag filtering, category browsing). Deliberately avoids hardcoding fonts or text colors so it inherits the Squarespace template's look; see "Editing appearance" below for the few values that *are* customizable.
- **`data.json`** — all resource content: titles, descriptions, tags, citations, links. Edit this to add or change resources. No code changes needed.
- **`squarespace-stub.html`** — the exact snippet pasted once into the Squarespace Code Block on the Resources page. Should never need to change again unless this repo is renamed, moved, or its default branch changes.

All three working files live at the repo root (no subfolders) — the URLs baked into the stub and into `ean-resources.js` assume that. If you ever move a file into a folder, the corresponding URL needs updating to match.

## Editing resource content

In `data.json`, each entry in `resources` has:

| Field | Notes |
|---|---|
| `id` | Unique slug, lowercase-with-hyphens |
| `title` | Resource title |
| `category` | Must match an `id` from the `categories` list |
| `description` | 1–3 sentences. This may be AI drafted but it _must_ be reviewed and curated by a human |
| `tags` | Array of `id`s from the `tags` list |
| `reference` | Full citation, for findability if the link ever dies |
| `url` | External link, or `null` if none |

To add a brand-new tag: add it to the top-level `tags` array first (with an `id` and display `label`) — it'll then show up automatically as a filter chip and can be assigned to any resource.

## Editing appearance

All customizable colors live in **one labeled block** at the top of `ean-resources.css`, under the comment `CUSTOM VALUES`. Everything else in the file inherits from the Squarespace template automatically and shouldn't need touching.

Current values are placeholders (neutral grays) — swap them out once real brand colors/fonts arrive from the designer.

If different tags ever need different colors (not just one shared color), each tag pill already carries a `data-tag="<id>"` attribute you can target directly in the CSS, e.g.:
```css
.ean-tag[data-tag="campus"] { background: #yourcolor !important; }
```

## Making a change live

1. Edit the relevant file directly on GitHub (or push from a local clone).
2. The Squarespace page picks it up automatically on next load — nothing to do in Squarespace itself.
3. **Caching note:** jsDelivr caches files for a while, so a change may take up to ~12 hours to show up for visitors (browser hard-refreshes don't bypass this — it's server-side caching). For an urgent fix, jsDelivr also supports purging its cache manually via [purge.jsdelivr.net](https://www.jsdelivr.com/tools/purge).

## Naming

Class names in the CSS/JS are prefixed `ean-` deliberately, to avoid colliding with Squarespace's own theme styles or any future Squarespace update that might introduce a generically-named class.