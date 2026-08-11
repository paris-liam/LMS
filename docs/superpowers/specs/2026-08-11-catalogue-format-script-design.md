# Catalogue Format Script — Design

**Date:** 2026-08-11
**Status:** approved, ready for implementation planning
**Context:** `claudedocs/2026-08-07-product-data-model-audit.md`, `docs/superpowers/specs/2026-08-08-movie-uploader-webapp-design.md`, `data-cleanup/client-template/client-upload-template-guide.md`

## Purpose

One command that takes any movie CSV — a batch from the new upload template, or a Shopify export of the existing catalogue — and returns a file that is safe to import, plus separate files for everything it could not resolve on its own.

The two failure modes get their own files so that fixing them is a loop rather than a hunt: correct the rows in the file you were handed, run the same command on that file, import what comes out.

## Scope

**In:** format detection, normalization to the current data model, TMDB description/poster fill, an issues file, an unmatched file, a poster-picker page, and an importable CSV.

**Out:**
- **Cross-batch handle-collision detection.** Same limit as the sheets and the web app. Two runs cannot see each other. Duplicates are deliberately deferred to the periodic cleanup pass.
- Any write path to Shopify. The script produces files; a human imports them.
- Deleting or merging products. Consolidating copies is a separate pass.
- Deciding a genre or a rental/floor-sale type when the data does not say. Both are flagged, never guessed.

## Why a new folder

`data-cleanup/` was written against a data model that has since been reversed twice: `Option1 Name = Title` / `Option1 Value = Default Title` (now `Genre` / the genre label, because the Retail Barcode Labels templates print Option 1) and media format in `shopify.media-format` (now `product.vendor`). `reformat_movies.py`, `circaos_reformat.py` and `run_pipeline.py` encode the retired model in their core transforms.

New code lives in `formatting-scripts/` at the repo root. Files worth keeping are **copied** there and updated; `data-cleanup/` is left untouched as a record of the earlier pass.

## Input shapes

Detected from the header row. Three shapes:

| Shape | Detected by | Handle behaviour |
|---|---|---|
| **New template** (23 cols) | has the `Format` / `Genre 1` / `Year` helper columns | derived from title + format + type, `-n` suffixed within the batch |
| **Old Shopify export** (44 cols) | has `Published` and `Variant Barcode` | **preserved verbatim** |
| **Prior output** of this script | has a leading `Reason` column | `Reason` stripped; treated as whichever shape it came from |

**Handles on export rows are never rewritten.** A handle is a live product's identity: changing it does not rename the product, it creates a second one and orphans the first. Only new-template rows, which describe products that do not exist yet, get a derived handle.

Unrecognised headers are a hard error naming the columns that were expected and missing, not a best-effort guess.

## Normalization

### Auto-fixed silently

- Vendor case: `BLU-RAY`→`Blu-Ray`, `4k`→`4K`, `Dvd`→`DVD`
- Known genre and type typos: `Horor`, `Sc-Fi`, `Kids & Famiy`, `Romatic Comedy`, `Floorsale`, `Foor Sale`, `Floor sale`
- `Genre (product.metafields.shopify.genre)` derived from the genre label(s) as `"; "`-joined metaobject handles
- Tags rebuilt as `Type, Format, Genre…, extras`, preserving unrecognised extras (`Criterion Collection`, `A24`)
- `Option1 Name` = `Genre`, `Option1 Value` = primary genre label
- Fixed columns: `Product Category` = `Media > Videos`, `Variant Inventory Tracker` = `shopify`, `Variant Inventory Policy` = `deny`, `Variant Fulfillment Service` = `manual`, `Variant Inventory Qty` = `1`

`Variant Inventory Tracker` must always be `shopify`. Blank means Shopify stops tracking stock, which pins `product.available` to true and makes `main-movie.liquid`'s out-of-stock state and notify-me form permanently unreachable.

### Flagged to `issues.csv`

| Reason | Approximate count in `products_export_1.csv` |
|---|---|
| No usable genre (`Special Interest`, `Chicago`, `Ivory Hunters`, `#REF!`, `#VALUE!`, blank) | ~25 |
| Vendor carries no format (`Unknown`, `Unknown Brand`, `Little Movie Store`, `Walt Disney`, …) | ~31 |
| Cannot determine Rental vs Floor Sale (no type tag) | ~60 |
| Rental with a nonzero price, or Floor Sale priced 0 | counted at run time |
| Product with 2+ real variants | 7 |
| Two input rows resolving to the same output handle | counted at run time |

Genre is never inferred from a title, and type is never inferred from price. Both would silently mislabel physical shelf stock, and a wrong shelf-label genre is worse than a flagged row.

## Output

**Output shape follows input provenance.** A client batch creates products; a catalogue export updates them. They are never mixed in one input file, so they are never mixed in one output file.

- **Template input** → the exact 17-column contract the sheets and the web app already emit, `Status = Active`.
- **Export input** → an update-shaped CSV: `Handle, Title, Body (HTML), Vendor, Product Category, Tags, Option1 Name, Option1 Value, Variant Inventory Tracker, Variant Inventory Qty, Variant Inventory Policy, Variant Fulfillment Service, Variant Price, Variant Barcode, Image Src, Image Position, Image Alt Text, Genre (product.metafields.shopify.genre)`.

No `Status`, no `Published`, no `SEO Title`/`SEO Description`, no `Variant SKU`, no `Variant Grams` on the export shape. **Shopify leaves absent columns untouched**, so anything the script does not deliberately set cannot be clobbered by the import. Extra image rows pass through carrying only `Handle`, `Image Src`, `Image Position`, `Image Alt Text`.

### Barcodes

`Variant Barcode` is populated from the export on old-export rows, and blank on template rows (the barcode app assigns one at print time).

This exists because reformatting changes `Option1 Value` on the 669 `Condition` products (`Standard`/`50%`/`70%` → a genre label). Shopify matches variants by option value on import, so a changed value can drop and recreate the variant, taking its barcode and inventory with it. Those barcodes are already printed on shelf labels. Carrying the barcode through means that even if the variant is recreated, the printed label still scans.

RFC-4180 quoting is load-bearing throughout: `Paris, Texas` and `The Monkey's Uncle` are both real catalogue rows, and one missed quote shifts every subsequent column.

### Files per run

Written to `out-<inputname>/` beside the input, so re-running on `issues.csv` cannot clobber the first run's `upload.csv`:

```
upload.csv           ← import this to Shopify
issues.csv           ← format problems: full row + leading Reason
tmdb-unmatched.csv   ← no TMDB match: same fixable shape
review-picker.html   ← ambiguous matches, click the right poster
tmdb-picks.json      ← the picker's export
.tmdb-cache.json     ← query cache
run-report.txt       ← counts per bucket
```

## TMDB fill

Fills `Body (HTML)`, `Image Src` and `Image Alt Text` **only when empty** — never overwrites what the client or a previous run already wrote. Alt text is `Title (Year) poster` using TMDB's release year, which is how export rows acquire a year at all: a Shopify export has no Year column.

Poster URLs use `https://image.tmdb.org/t/p/w1280/…`. Confirmed 2026-08-11 by a real dev-store import: Shopify downloads and re-hosts the image to its own CDN at 1280×1920, `status: READY`, `mediaErrors: []`, alt text preserved.

**Match confidence.** Auto-fill requires all three: the top candidate scores ≥0.9 on normalized title similarity, no runner-up within 0.05 of it, and the year matches when one is known. Anything else is ambiguous and goes to the picker. Zero results goes to `tmdb-unmatched.csv`. The existing single-candidate threshold accepts a lone weak match too readily for a 2,500-row run.

**Caching.** Every query is cached on disk keyed by normalized title + year. The first pass over ~2,500 rows takes roughly ten minutes at TMDB's rate limit; every fix-and-re-run afterwards costs no API calls for rows already looked up. Without the cache the correction loop is unusable.

## The loop

```
python3 formatting-scripts/run.py products_export_1.csv
# → import out-products_export_1/upload.csv
# → open review-picker.html, pick posters, export picks, then:
python3 formatting-scripts/apply_picks.py \
    out-products_export_1/tmdb-picks.json out-products_export_1/upload.csv
# → fix out-products_export_1/issues.csv in Excel, then:
python3 formatting-scripts/run.py out-products_export_1/issues.csv
# → import out-issues/upload.csv
```

Rows that are still broken after a fix land in the next run's `issues.csv` with a fresh reason. The loop repeats until that file is empty. There is no merge step — each run produces its own importable file.

The pipeline is idempotent: running it over its own `upload.csv` produces the same file and no new issues.

## Modules

```
formatting-scripts/
  run.py            entry point: detect → normalize → TMDB → write report
  detect.py         input-shape detection
  normalize.py      per-product classify + transform → clean row or issue
  taxonomy.py       13 genres, 4 formats, typo→canonical maps, genre→handle
  columns.py        the two output column contracts + fixed values
  tmdb_fill.py      copied from data-cleanup/, updated
  review_page.py    copied from data-cleanup/tmdb_review_page.py
  apply_picks.py    copied from data-cleanup/apply_review_picks.py
  catalog_common.py copied ~as-is
  tmdb_cache.py     disk-backed query cache
```

`normalize.py` is pure — row dicts in, row dicts out, no filesystem and no network — so the entire classification table is testable without a CSV or an API key. `run.py` is the only module that touches the filesystem. `tmdb_fill.py` keeps the existing injected-`fetch_fn` pattern so its tests run offline.

### Changes to the copied files

- **`tmdb_fill.py`** — remove the `Needs Review` / `needs data` / `CircaOS Import` tag machinery. Issues now live in a file, not as tags on live products; writing review tags into an import would pollute the real catalogue. Add the disk cache, switch the poster base to `w1280`, and apply the stricter confidence rule above.
- **`review_page.py`** — unchanged behaviour, 5 candidates per product, retargeted at the new unmatched-file shape.
- **`genre_format_mapping.py` is not copied.** It maps to `shopify.media-format` metaobject handles, which is the retired model. `taxonomy.py` replaces it.

## Testing

`unittest`, in `tests/formatting_scripts/`, mirroring `tests/data_cleanup/`. Fixtures cut from the real files (`products_export_1.csv`, `test-rental.csv`, `test-floor-sale.csv`, `sample1.csv`).

- **`test_normalize.py`** — one case per row of the issues table (each flag fires) and per auto-fix (each correction applies); handle preservation on export rows; handle derivation and `-n` suffixing on template rows.
- **`test_columns.py`** — the template output header equals the header of `client-upload-template-rental.csv` read from disk; the export output header contains no column outside the intended set. This is the seam where the script and the sheets would otherwise drift apart unnoticed.
- **`test_detect.py`** — the three input shapes, including a `Reason`-carrying prior output round-tripping back to its origin shape, and a hard error on an unrecognised header.
- **`test_tmdb_fill.py`** — canned responses via injected fetch: confident match, ambiguous pair, zero results, already-filled row must not be overwritten, cache hit costs no fetch.
- **`test_run.py`** — end-to-end on a small fixture: the right files appear with the right row counts, and a second run over the first run's `upload.csv` changes nothing.

## Operational dependencies

- **Template assignment.** The product CSV has no template-suffix column, so newly imported movies land on the default product template, which renders price, variant picker, quantity and buy-buttons — a $0.00 Buy Now on a rental, contradicting the Supercycle contract. `scripts/set-movie-template.sh` must be run after every import. The script cannot fix this in the file it generates.
- **Recommended before the full catalogue import:** import ~20 reformatted products to the dev store, re-export, and diff barcodes and inventory against the input. This is the one assumption in the design that has not been verified against a live store, and it affects 669 products with printed shelf labels.

## Reused prior art

| Piece | Source |
|---|---|
| TMDB search, title cleaning, edition-noise stripping | `data-cleanup/tmdb_fill.py` |
| Poster picker page and picks export | `data-cleanup/tmdb_review_page.py`, `apply_review_picks.py` |
| CSV I/O, tag helpers, handle grouping | `data-cleanup/catalog_common.py` |
| 17-column CSV contract, handle derivation | `data-cleanup/client-template/*.csv` and its guide |
| Genre taxonomy and metaobject handles | `data-cleanup/genre_format_mapping.py` (values only) |
