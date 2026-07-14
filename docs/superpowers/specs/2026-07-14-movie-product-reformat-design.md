# Movie product data reformat — design

## Context

`data-cleanup/current-movies-export.csv` is a full product export from the dev store (2,594 CSV data rows / 2,547 unique product handles). It mixes several structurally different product types that were entered inconsistently over time. This spec covers reformatting the plain resale catalogue into clean, standard Shopify fields, in preparation for a bulk re-upload. It does not touch the current theme's data usage — that will be refactored separately once the underlying product data is clean.

## Scope

**In scope**: the ~1,849 plain resale VHS/DVD/Blu-Ray/4K products, identified by `Option1 Name = "Genre"`.

**Out of scope** (separate future pass):
- ~671 serialized items (`Option1 Name = "Condition"`, `Option2 Name = "Serial Number"`, tagged `Rental`) — these track physical copy condition and serial numbers and tie into Supercycle rental config, a different problem from catalogue formatting.
- 1 stray "Supercycle Plan" product (`Type = "Supercycle Plan"`) mixed into the same export — not a movie product.
- ~27 rows with `Option1 Name = "Title"` (no genre ever set) and 2 rows with corrupted `#VALUE!` genre data — these are excluded from the reformatted output and listed in a review report instead (see "Bad rows" below).

## Current state (verified against the dev store)

Both target metafields already exist as standard Shopify metafields, each backed by a metaobject definition with existing entries:

- `product.metafields.shopify.media-format` (list.metaobject_reference) → metaobject entries: `vhs`, `dvd`, `blu-ray`, `4-k`
- `product.metafields.shopify.genre` (list.metaobject_reference) → metaobject entries: `crime-mystery`, `thriller-suspense`, `comedy`, `action`, `kids-family`, `thriller`, `romantic-comedy`, `musical`, `foreign`, `drama`, `horror`, `fantasy`, `documentary`, plus `sci-fi` (to be added/confirmed present before import — used heavily in the source data but not seen in the initial metaobject listing).

Today, format lives in `Vendor` (messy: `VHS`, `DVD`, `Blu-Ray`, `BLU-RAY`, `4K`, `4k`, plus junk like `Unknown`, `Walt Disney`, `Blockbuster`, `Basquiat`, `Supercycle`) and genre lives in a fake single-value variant option (`Option1 Name = "Genre"`, `Option1 Value = "Comedy"` etc.), meaning every product technically has one purchasable "variant" named after its genre.

Nearly all in-scope products (2,533 of 2,547 handles) have exactly one real variant; extra CSV rows per handle are just additional product images (standard Shopify multi-row export format), not real variants. Two handles (`royal-tenenbaums`, `a-million-to-juan`) have two genuine variants (two physical copies) — these keep their variant structure, just with the genre/format cleanup applied per variant's product record.

## Field mapping

| Current field | New field / value |
|---|---|
| `Vendor` | Fixed to `"Little Movie Store"` for every in-scope product, regardless of current value |
| `Option1 Name/Value = "Genre"/<value>` | Removed. Product collapses to the standard single default variant (no fake option) |
| *(format was hidden in Vendor)* | `product.metafields.shopify.media-format` — metaobject reference, one of `vhs` / `dvd` / `blu-ray` / `4-k` |
| *(genre was hidden in Option1)* | `product.metafields.shopify.genre` — metaobject reference, exactly one genre value per product (matches today's 1:1 data; the field is list-typed but we don't infer additional genres) |
| `Product Category` | Set to `Media > Videos` for every in-scope product (general category, not the per-format subcategory — format is already captured by the metafield) |
| `Tags` | Left untouched this pass (includes redundant genre-copy tags, status tags like `Floor Sale`/`Rental`, curation tags like `Special Interest`/`Criterion Collection`/`A24`, and existing typos — all deferred to a future tags-cleanup pass) |

## Value normalization

`/Users/liamparis/Desktop/format-mapping.md` (user-authored, derived from the full set of distinct values in the export) is the canonical lookup table for this step, with one correction: `Foreign -> foreign` (not `foreignz` — matches the real metaobject handle on the store).

Key normalization rules from that mapping:
- Case/spelling variants collapse to canonical handles: `BLU-RAY`/`Blu-Ray` → `blu-ray`, `4K`/`4k` → `4-k`, `SciFi`/`Sci-Fi` → `sci-fi`, `Romatic Comedy` → `romantic-comedy`, `Muscal` → `musical`, `Kids` → `kids-family`.
- Compound values that jammed format and genre together split into both target fields: e.g. `"4K, Action"` → format `4-k` + genre `action`; `"Kids & Family, 4K"` → format `4-k` + genre `kids-family`.
- Values that aren't real genres (`Special Interest`, `Comedy, Criterion Collection` → the Criterion Collection part, `A24, Sci-Fi` → the A24 part) are dropped from the genre mapping; the underlying real genre value still maps normally where present (e.g. `A24, Sci-Fi` → genre `sci-fi`).
- Junk/non-format `Vendor` values (`Unknown`, `Walt Disney`, `Blockbuster`, etc.) are superseded entirely by the fixed `"Little Movie Store"` vendor rule above — no per-value mapping needed for Vendor.

## Bad rows (excluded from output)

Rows that can't be cleanly reformatted go into a separate `needs-review.csv` (handle, title, and reason) instead of the main output:
- 2 rows with corrupted `#VALUE!` genre data
- ~27 rows with `Option1 Name = "Title"` (no genre ever recorded)

These are not included in the re-upload CSV until fixed by hand.

## Deliverable

A Python script (location TBD in the implementation plan) that:
1. Reads `data-cleanup/current-movies-export.csv`
2. Filters to in-scope rows (`Option1 Name = "Genre"`), collapsing each product's real image rows correctly
3. Applies the field mapping and value normalization above
4. Writes a reformatted CSV ready for Shopify bulk re-upload (to the dev store first)
5. Writes `needs-review.csv` for excluded rows

Exact CSV column layout and metaobject-reference value encoding for the bulk import are implementation details for the plan/build step, not this design.
