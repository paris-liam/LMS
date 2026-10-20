# Duplicate copies lookup — plan (2026-10-02)

**Status:** built as `python3 -m catalog duplicates` (`catalog/duplicates/`);
the audit snapshot now also records `Variant Inventory Qty` and `Created At`.

**Question:** if we moved from "one product per physical copy" to "one product
per movie + format, with a copy count", how many products would collapse, and
into what? Two DVDs + one VHS of a film = **two** products (DVD ×2, VHS ×1).

This is a **read-only** count and review list. Nothing here merges, deletes or
edits a product; any actual consolidation is a separate, later plan (see
"What merging would break").

## Baseline (rough, from the stale 2026-09-28 snapshot)

7,148 products: 3,258 Rental, 3,852 Floor Sale, 38 untyped; VHS 3,750 ·
DVD 2,257 · Blu-Ray 976 · 4K 125 · Laserdisc 33 · Betamax 1 · 6 with Vendor
"Little Movie Store".

| Grouping key | Groups of 2+ | Products in them | Products saved |
|---|---|---|---|
| Exact title + format | 555 | 1,175 | 620 |
| Normalized title + format | ~620–640 | ~1,320–1,360 | ~700 |
| Normalized title + format **+ type** | 230 | 465 | 235 |

**410 of the 555 exact groups pair a Rental copy with a Floor Sale copy**, so
the rental-vs-sale question below changes the answer by ~3×. Group sizes are
mostly 2 (492), some 3 (61), a few 4 (2).

## Decisions (all four recommendations accepted 2026-10-02)

1. **Rental and Floor Sale copies of the same movie + format: one product or
   two?** Recommended: **two**. They differ in price, storefront collection
   and Libib (rentals only), so they can't share one variant/price.
2. **Editions** (Extended, Director's Cut, Collector's/Special, Unrated,
   Criterion, Screener): same product as the plain release, or separate?
   Recommended: **separate**, flagged for review rather than auto-grouped.
3. **Drafts** (94): include in the count? Recommended: count them, report
   them separately.
4. **Box sets / double features** ("Casino / Carlito's Way", "… Collection",
   "Trilogy"): never grouped with a single film (recommended default).

## Method

### 0. Fresh data
`python3 -m catalog audit --skip-tmdb` against production (read-only) for a
current snapshot. The snapshot has no inventory quantity today; add
`Variant Inventory Qty` to it (item 8 already read quantities), because 129
Floor Sale products already hold more than one copy and those copies count.

### 1. Scope
Movies only: skip `retail`-template products and any Vendor that isn't a
media format (the 6 "Little Movie Store" items go on a "can't classify"
list). Group **within a format** always — a DVD never matches a VHS.

### 2. Matching, in tiers (each later tier only adds groups)

| Tier | Match on | Example it catches |
|---|---|---|
| 1. Exact | title trimmed + case-folded | `Matilda` / `Matilda` |
| 2. Normalized | punctuation removed, `&` → `and`, leading The/A/An dropped, format words in the title dropped (`Hostel (DVD)`), whitespace collapsed | `The Grifters` / `Grifters`, `My Boyfriend's Back` / `My Boyfriends Back` |
| 3. Fuzzy | near-identical normalized titles in the same format (≈ one typo: edit distance ≤ 2 on titles ≥ 8 chars, or similarity ≥ 0.92) | `Cowbows & Aliens` / `Cowboys & Aliens`, `101 Dalmations` / `101 Dalmatians`, `Unknown Origin` / `Unknown Origins` |

Normalization keeps what distinguishes films: **numbers and roman numerals are
never stripped or fuzzed** (`101` vs `102 Dalmatians`, `Rocky II` vs
`Rocky III`, `Malevolence 2`), and a year in the title (`Dune (1984)`) is
pulled out as a separate field rather than deleted.

### 3. Evidence for and against a group

- **Supports:** same description (normalized text, ≥ 40 chars — 403 such
  groups in the baseline); same poster file (Shopify CDN filename with its
  `_uuid` suffix removed — usually the TMDB poster path, e.g.
  `9I7gV6wRbGnbfI3XOKjHeLMjYEo.jpg`); same TMDB id where the picker recorded a
  pick.
- **Ignore:** poster files shared by more than ~3 *different* titles — those
  are placeholder images (one DVD placeholder covers ~90 titles).
- **Against:** different years, different sequel numbers, an edition word on
  one side only, one side a box set, two different specific posters.

### 4. Confidence

- **Certain** — tier 1 or 2, at least one supporting signal, nothing against.
- **Likely** — tier 2 with no signal either way, or tier 3 with a supporting
  signal.
- **Review** — tier 3 alone, or anything with a signal against. Only this
  bucket needs a person.

### 5. Output (`runs/<id>/`)

- `duplicates.csv` — one line per product in a group: group id, confidence,
  format, type, handle, title, barcode, status, quantity, created date,
  matching tier, reasons.
- `duplicates-summary.txt` — products today vs. after consolidation (per
  confidence level, so "certain only" and "certain + likely" both show);
  copies-per-product distribution; split by format and by type; how many
  groups contain rentals (the Libib-affected ones).

### 6. Build

A read-only `python3 -m catalog duplicates` command (reads the latest audit
snapshot, writes the two files), with tests in `tests/catalog/` built from
the real cases above: the typos that should match, and the sequels, editions
and box sets that must not.

## What merging would break (out of scope here, but decides the next plan)

- **Rentals and Libib.** Libib has one item per copy, keyed by call number =
  the Shopify variant barcode. A product holding three copies has one variant
  barcode, so `libib sync`'s join breaks for copies 2 and 3. Rentals need a
  per-copy barcode store (e.g. a list metafield) before any rental is merged.
- **The upload sheet** writes one row per copy; it would need a Quantity
  column (Floor Sale) and a way to add a copy to an existing product.
- **Orders/history** sit on the products that would be deleted.

Floor Sale is the easy half: its copies have no Libib side, so it could be
consolidated first if the numbers justify it.
