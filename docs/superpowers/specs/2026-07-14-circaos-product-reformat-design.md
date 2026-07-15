# CircaOS product reformat — design

## Context

The first reformatting pass (`docs/superpowers/specs/2026-07-14-movie-product-reformat-design.md`) covered the 1,846 plain resale VHS/DVD/Blu-Ray/4K products and explicitly excluded 672 products with a different structure: `Option1 Name = "Condition"`, `Option2 Name = "Serial Number"`. Those 672 are listed in `data-cleanup/out-of-scope.csv`.

Investigation confirmed these came from a different source than the resale catalogue — most likely the client's prior CircaOS bulk-upload tool:
- **Structural fingerprint**: 669 of 672 (99.6%) have a `Variant SKU` in the format `191-XXXYYY-CC-NNNA`, identical to `Variant Barcode`. Zero of the 1,846 resale products have any SKU at all.
- **Description fingerprint**: descriptions are frequently generic, keyword-matched-to-title text describing the wrong product category entirely (e.g. `Critters Attack!` described as a "collectible plush," `Pulp Fiction` described as "storage solution... for paperbacks," `30 Days of Night` described as a "graphic novel"). ~14% of non-empty out-of-scope descriptions match this signature vs ~1% of resale descriptions.

This spec covers reformatting these 672 products (671 real movies + 1 stray Supercycle Plan product) into the same clean field structure as the first pass. Fixing the wrong description *content* is explicitly a separate, later step — not in scope here.

## Scope

**In scope**: 671 serialized rental movies (`Type != "Supercycle Plan"` among the out-of-scope set).

**Out of scope**: the 1 Supercycle Plan product — not a movie, stays untouched entirely.

## What's different from the first pass, and why

The first pass safely collapsed `Option1 Name = "Genre"` into a single default variant because that data was junk (genre faked as a variant option). This batch's `Option1 Name = "Condition"` / `Option2 Name = "Serial Number"` is **real per-copy inventory data**, not junk — verified across all 671 products:

- **Condition** (`Option1 Value`): real grading values — `50%` (334), `Standard` (306), `F` (24), `70%` (4), `G` (2), `N` (1).
- **Serial Number** (`Option2 Value`) / **Variant SKU** / **Variant Barcode**: all three are the same identifier duplicated three ways (e.g. `191-VHSSCP-001A` appears as both SKU and Barcode; `001A`, the same string's suffix, is the Serial Number value). This is the unique-copy identifier, likely used for POS/serial-scanning of individual physical units (per `CLAUDE.md`'s future Supercycle rental-at-POS scope).
- **7 titles have 2 real physical copies each** (distinct barcodes, sometimes distinct prices, and in one case — `speed-racer` — distinct formats: one Blu-ray copy, one DVD copy under the same handle today).

Keeping `Serial Number` as a literal Shopify variant option is itself a compliance problem: variant options are customer-facing, and `CLAUDE.md` requires serial numbers never be shown to customers. So this pass isn't "make it look like the resale products" verbatim — it's "get the condition/serial/SKU data out of customer-facing variant options while preserving the underlying identifier, and match the resale pass's field treatment everywhere it already applies (vendor, category, genre, format)."

## Field mapping

| Current field | New field / value |
|---|---|
| `Vendor` | Fixed to `"Little Movie Store"` (all 671 vendors already covered by the existing `VENDOR_TO_FORMAT` table from the first pass — zero unmapped) |
| `Product Category` | `"Media > Videos"` |
| `Option1 Name/Value = "Condition"/<grading>` | **Dropped entirely.** Collapses to the standard single default variant: `Option1 Name = "Title"`, `Option1 Value = "Default Title"` |
| `Option2 Name/Value = "Serial Number"/<code>` | **Dropped.** The identifier is preserved via `Variant Barcode` (see below), so nothing is lost |
| `Variant SKU` | **Dropped** (identical to `Variant Barcode` in every case — redundant) |
| `Variant Barcode` | **Unchanged.** Already the unique per-copy identifier; kept exactly as-is |
| *(genre)* | `product.metafields.shopify.genre` — metaobject reference. **New extraction path**: the first tag (in `Tags`, in order) that matches the plain genre vocabulary already defined in `GENRE_VALUE_MAP` (Comedy, Action, Drama, Kids & Family, Sci-Fi, Thriller, Horror, Romantic Comedy, Musical, Fantasy, Documentary, Foreign — including existing typo variants). Unlike the first pass, there's no fake `Option1 Value` to read genre from; `Tags` mixes genre words with status tags (`Rental`, `Floor Sale`) |
| *(format)* | `product.metafields.shopify.media-format` — from `Vendor` via the existing `VENDOR_TO_FORMAT` table, **overridden to `4-k`** if `Tags` contains a `4K`/`4k` tag (mirrors the first pass's compound-value override, sourced from `Tags` membership instead of a compound `Option1 Value` string) |
| `Tags` | **Preserved, plus `CircaOS Import` appended** to every reformatted product's tag list — gives the client (and the later description-fix script) a reliable filter for this whole batch |
| `Body (HTML)` | **Untouched this pass.** Fixing the wrong description content is a separate, later step |

## Multi-copy titles

The 7 titles with 2 real physical copies (`royal-tenenbaums`, `a-million-to-juan`, `finding-dory`, `night-of-the-living-dead`, `speed-racer`, `get-shorty`, `outrageous-fortune`) each split into **2 separate single-variant products**, matching the "one product = one physical unit" pattern every other product in the catalogue (both this batch and the first pass) already follows.

Handle-naming rule:
- If the two copies are different formats (only `speed-racer`: one Blu-ray, one DVD), the new handles get a format suffix: `speed-racer-bluray`, `speed-racer-dvd`.
- If the two copies are the same format, the first copy keeps the original handle unchanged and the second gets `-copy-2` appended (e.g. `royal-tenenbaums`, `royal-tenenbaums-copy-2`).

Each split product gets its own full field mapping applied independently (its own barcode, its own price, its own format/genre metafields) — they are not linked to each other in any way after the split.

## Bad rows (excluded from output)

21 handles have no genre-like tag at all in `Tags` (either no tags, or only status tags like `Rental`/`Floor Sale`) — these can't be assigned a genre and go to a review report (`Handle`, `Title`, `Reason`), excluded from the main output, same philosophy as the first pass's `needs-review.csv`.

No vendor-mapping failures exist in this batch (all 671 vendors are already covered by the existing table), so that failure mode doesn't apply here.

Verified: none of the 7 multi-copy titles are among the 21 no-genre-tag handles, so there's no case in the real data where a title needs both review-flagging and splitting. Classification (in-scope vs. review) happens per original handle, before splitting.

## Deliverable

A second script, following the same pattern/style as the first pass's `data-cleanup/reformat_movies.py` (and reusing `data-cleanup/genre_format_mapping.py`'s `VENDOR_TO_FORMAT`/`GENRE_VALUE_MAP`/`resolve_format` where it applies), that:
1. Reads `data-cleanup/current-movies-export.csv`, filtered to the 671 in-scope serialized-rental handles
2. Applies the field mapping above, including the new Tags-based genre/format extraction
3. Splits the 7 multi-copy titles into separate single-variant products per the naming rule
4. Appends `CircaOS Import` to each output product's tags
5. Writes a reformatted CSV ready for bulk re-upload, plus a review report for the 21 excluded rows

Exact CSV column layout matches the first pass's output (same header set, same `Media format`/`Genre` metafield column encoding — plain metaobject handle text). Script location, module boundaries, and test structure are implementation details for the plan/build step, not this design.
