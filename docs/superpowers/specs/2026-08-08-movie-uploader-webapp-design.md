# Movie Uploader Web App — Design

**Date:** 2026-08-08
**Status:** approved, ready for implementation planning
**Context:** `claudedocs/2026-08-07-product-data-model-audit.md`, `docs/superpowers/plans/2026-07-19-client-product-upload-template.md`

## Purpose

"Path C" — a browser tool that lets the client catalogue movies faster and more accurately than the Google Sheets (Paths A and B), then download a Shopify-ready import CSV.

Paths A and B are **not** replaced. This is a third option that produces the same CSV contract.

The real gain is not a nicer form. It is **inverting the lookup**: instead of typing a title and a year and having a script guess the movie afterwards, he searches TMDB first and picks the film. Title, year, description and poster then arrive correct by construction. That removes title typos, year ambiguity (*The Thing* 1982 vs 2011) and the entire TMDB reconciliation pass in one move.

## Scope

**In:** TMDB search-first entry, per-item format/type/genre/copies/price, live-derived handles, localStorage persistence, an export archive, Shopify-ready CSV download.

**Out, deliberately:**
- **Cross-batch handle collision detection.** Same `-n` behaviour as the sheets, same caveat. Dedup stays with the periodic cleanup pass. Solving it properly needs live catalogue access, which needs a backend — the single change that would turn this from a days-long build into a weeks-long one.
- Any write path to Shopify. The app produces a file; a human imports it.
- Editing or deleting existing products.
- Mobile layout. Desktop only (see Operating context).
- Barcode handling. The Retail Barcode Labels app assigns barcodes at print time.

## Operating context

Confirmed with the user:

| | |
|---|---|
| **Hosting** | Netlify/Pages, publish directory `tools/movie-uploader/`, no build command |
| **Who operates it** | The client, unaided |
| **Device** | Desktop, keyboard-driven, physical stack of tapes beside him |
| **Session size** | 50–200 items |
| **TMDB key** | Shipped in `config.js` |

**On the exposed key:** a TMDB v3 key is read-only against public film metadata — no writes, no personal data — and rotating it is a one-line redeploy. Accepted as nuisance risk, not a security issue.

**Verified 2026-08-07:** `api.themoviedb.org` returns `access-control-allow-origin: *` on both preflight and response, so the browser can call TMDB directly. No proxy, no serverless function, no backend.

## Architecture

Static site, no build step. ES modules loaded natively via `<script type="module">`.

`lib/` is pure logic with no DOM access. `app.js` is the only DOM-aware module. That boundary exists so every piece capable of silently corrupting a Shopify import is testable in Node.

```
tools/movie-uploader/
  index.html
  config.js           # TMDB key (rotatable)
  styles.css          # @imports ../../lms-tokens.css
  app.js              # ONLY DOM-aware file
  lib/
    tmdb.js  taxonomy.js  handle.js  csv.js  store.js
tests/movie_uploader/
  handle.test.js  csv.test.js  taxonomy.test.js  tmdb.test.js
```

| Module | Does what | Depends on |
|---|---|---|
| `handle.js` | title + format + type + index → handle string | nothing |
| `taxonomy.js` | 13 genres, 4 formats, TMDB genre → LMS suggestion | nothing |
| `csv.js` | items → CSV text | `handle.js` |
| `tmdb.js` | query → candidates | injected fetch fn |
| `store.js` | state ↔ localStorage | nothing |
| `app.js` | UI wiring, render, events | all of the above |

Nothing depends on `app.js`.

**`tmdb.js` takes an injected fetch function** rather than calling `fetch` directly, mirroring the `fetch_fn` pattern already used in `data-cleanup/tmdb_fill.py`. Its tests run offline against canned responses, with no network and no key.

## Data model

One item = one movie + format + type, with a `copies` count. `csv.js` expands `copies: 3` into three rows at export — the single biggest keystroke saving over the sheets.

```js
{
  id, tmdbId,            // tmdbId null = manual entry
  title, year,
  format,                // "VHS" | "DVD" | "Blu-Ray" | "4K"
  type,                  // "Rental" | "Floor Sale"
  genres: [...],         // 1–3; [0] is the shelf genre → Option1 Value
  copies: 1,
  price: 0,              // forced to 0 when type is Rental
  description, posterUrl,
  extraTags: [],
  createdAt
}
```

**Handles are derived on working items, frozen on export.**

Deriving means a corrected title updates its handle instead of drifting from it. But once a row reaches Shopify that handle is the product's permanent identity, so archived items store the exact string exported. The archive is then a truthful record of what is live, not a recomputation that might differ.

```js
{
  schemaVersion: 1,
  items: [ /* working list */ ],
  archive: [ { exportedAt, filename, items: [ /* + frozen handle */ ] } ],
  prefs: { lastFormat, lastType }   // sticky across the session
}
```

`prefs` makes format and type sticky — with a sorted stack he sets them once, not 200 times.

`schemaVersion` ships from day one. Adding a field later to a store full of real work with no version marker is an afternoon lost.

**Lifecycle:** export moves items from `items` into a dated `archive` batch. The archive guards against double-importing and lets him re-download a past batch if an import fails.

**Known limit, accepted:** the archive lives in the same localStorage as the working list, so it is a double-import guard, *not* a backup. A browser data-clear still loses un-exported work. Exported batches survive because the CSV is a real downloaded file.

## Screen

Single screen, two panes: entry on the left, running list on the right, so items visibly accumulate without a view switch.

```
┌─ Little Movie Store · uploader ──────── 37 items · 41 copies ─ [Export] ┐
│  Search  [rushmo____________]       │  ▸ Rushmore            VHS Rental │
│  ┌────┐┌────┐┌────┐┌────┐┌────┐     │    Comedy · 1 copy                │
│  │ 1  ││ 2  ││ 3  ││ 4  ││ 5  │     │    rushmore-vhs-rental       ✎ ✕  │
│  └────┘└────┘└────┘└────┘└────┘     │                                   │
│  Rushmore (1998)  ← selected        │  ▸ The Thing        4K Floor Sale │
│                       no match? →   │    Horror, Sci-Fi · 2 copies      │
│  Format  [VHS] DVD  Blu-Ray  4K     │    $24.99  ⚠ no poster            │
│  Type    [Rental]  Floor Sale       │    the-thing-4k-floor-sale   ✎ ✕  │
│  Genre   [Comedy ▾] + add           │                                   │
│  Copies  [1]                        │                                   │
│  → rushmore-vhs-rental   [Add ⏎]    │                                   │
└─────────────────────────────────────┴───────────────────────────────────┘
```

**The loop:** type a few letters → `1`–`5` picks a candidate → title/year/description/poster fill → genre arrives pre-suggested → `⏎`. Form clears, focus returns to search.

The derived handle is visible above the Add button, so `-2` on a second copy is seen at entry rather than discovered later.

**Escape hatches**, because obscure VHS is what this shop sells:
- **"no match?"** → manual entry: type title and year, optionally paste a poster URL, write the description. Stored with `tmdbId: null`.
- Any list item is clickable to load back into the form.

**Warn vs block.** Missing poster or description shows `⚠` but does not stop export — sometimes shipping without a poster is right. Export *is* blocked by: no genre, no format, `copies < 1`, or a Floor Sale item with no price. The button greys out and names the offending items.

**Form fields not shown in the sketch above:** `Price` renders only when Type is Floor Sale (Rental forces 0, so the field would be a lie). `Extra tags` is a free-text input below Copies, comma-separated, defaulting to empty — it is the rarest field and should not occupy prime space.

**Genre auto-suggest is a default, never an answer.** TMDB's taxonomy does not map cleanly onto the 13 LMS genres — TMDB has no "Foreign" or "Holiday" and splits categories LMS merges. Unmapped TMDB genres yield *no* suggestion rather than a wrong one. He confirms every time.

**How the suggestion is derived:** TMDB search results carry `genre_ids`, not names. `taxonomy.js` holds a **hardcoded** TMDB genre-id → LMS-genre map (e.g. 35 Comedy → `Comedy`, 878 Science Fiction → `Sci-Fi`, 10751 Family → `Kids & Family`). Hardcoding avoids a second API call on every search and makes the mapping unit-testable offline. TMDB's genre list is stable; if it ever changes, an unmapped id yields no suggestion, which is the safe failure.

`tmdb.js` maps at most **5** candidates per search, matching `MAX_CANDIDATES` in `tmdb_review_page.py` and the `1`–`5` keyboard picks.

## Export

**One CSV, both types.** Shopify imports Rental and Floor Sale rows in the same file. The two-sheet split existed only because a spreadsheet cannot easily make a column conditional; with per-item `type`, one file per session is correct regardless of the stack.

Emits the same 17 columns A–Q as the templates. Filename `lms-upload-YYYY-MM-DD.csv`, UTF-8, no BOM.

RFC-4180 quoting is load-bearing: `Paris, Texas` and `The Monkey's Uncle` are both real catalogue rows, and one missed quote shifts every subsequent column and corrupts the import.

Fixed values per row, matching the templates exactly: `Vendor` = format, `Product Category` = `Media > Videos`, `Status` = `Active`, `Option1 Name` = `Genre`, `Option1 Value` = `genres[0]`, `Variant Inventory Tracker` = `shopify`, `Variant Inventory Qty` = `1`, `Variant Inventory Policy` = `deny`, `Variant Fulfillment Service` = `manual`, `Image Alt Text` = `Title (Year) poster`, genre metafield = handles joined with `"; "`.

`Variant Inventory Tracker` must always be `shopify`. Blank or omitted means Shopify stops tracking stock, which pins `product.available` to true and makes `main-movie.liquid`'s out-of-stock state and notify-me form permanently unreachable.

## Error handling

| Case | Behaviour |
|---|---|
| TMDB unreachable | inline "search unavailable"; manual entry keeps working |
| TMDB 401 | "TMDB key rejected — tell your developer", distinct from a generic failure |
| localStorage unavailable *(private window)* | boot banner: work will not be saved |
| Quota exceeded | offer to prune oldest archived batches |
| Corrupt stored JSON | fall back to empty state **and** offer the raw string as a download, so a parse bug never silently eats a session |
| Poster URL 404s | broken-image chip on the row; cannot be fully detected in advance |
| Duplicate handle within batch | auto `-n` suffix — expected, not an error |

Search is debounced at 250ms, keeping request volume far below TMDB's rate limit.

## Testing

`node --test`, no npm, mirroring how `data-cleanup/` is tested.

- **`csv.test.js` asserts the generated header equals the header row of `client-upload-template-rental.csv` read from disk** (both templates share an identical header, so either serves; rental is named for determinism). This is the seam where the app and the sheets would otherwise drift apart unnoticed. Also covers quoting, copies expansion, rental price forced to 0, and the `"; "` genre delimiter.
- `handle.test.js` — the 12 verified titles (commas, apostrophes, colons, accents, `8½`), plus copy suffixing and type suffix.
- `taxonomy.test.js` — TMDB genre mapping; unmapped genres yield no suggestion.
- `tmdb.test.js` — canned responses via injected fetch: missing `poster_path`, missing `overview`, zero results.

## Gate before implementation — CLEARED 2026-08-11

**Shopify's importer fetches `image.tmdb.org` URLs correctly.** Confirmed on the dev store by a real CSV import: an `https://image.tmdb.org/t/p/w1280/…jpg` value in `Image Src` was downloaded and re-hosted to `cdn.shopify.com` at 1280×1920, media `status: READY`, `mediaErrors: []`, with the CSV's alt text preserved.

The poster path in this design works as specified. No re-hosting step is needed. Nothing blocks implementation.

The same import also confirmed two other assumptions the design depends on:

- **The genre metafield binds.** A bare handle (`kids-family`) in the `product.metafields.shopify.genre` column resolved to a real metaobject reference (`["gid://shopify/Metaobject/299533336638"]`). Bare handles are correct; no GIDs or JSON arrays needed.
- **`Media > Videos` is a valid taxonomy category** (`gid://shopify/TaxonomyCategory/me-7`) and imports cleanly, so the `all-movies` smart-collection rule will match.

## Dependency: template assignment

**The product CSV has no template-suffix column**, so imported movies land on the default product template — which renders price, variant-picker, quantity, add-to-cart and buy-buttons. On a rental priced at 0 that is a $0.00 Buy Now button, contradicting the in-store-only design and the Supercycle contract.

`scripts/set-movie-template.sh` closes this, and must be re-run after every import regardless of which path (A, B or C) produced the CSV. Path C cannot fix this in the file it generates; the spec notes it so the operator runbook includes it.

## Reused prior art

| Piece | Source |
|---|---|
| TMDB search, title cleaning, edition-noise stripping | `data-cleanup/tmdb_fill.py` |
| Card UI, localStorage, inline edit, export button | `data-cleanup/tmdb_review_page.py` |
| Handle slug + copy suffix | the sheet formula, verified against 12 titles |
| 17-column CSV contract | `data-cleanup/client-template/*.csv` |
| Genre/format taxonomy | `data-cleanup/genre_format_mapping.py` |

Estimated ~800–1,200 lines, most of it transliteration rather than new design.
