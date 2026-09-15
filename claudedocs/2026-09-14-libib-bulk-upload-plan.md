# Libib bulk upload — field research + migration plan (2026-09-14)

Follow-up to `2026-09-12-libib-vs-supercycle-assessment.md` (which recommended Libib and estimated 2–3 dev days for "catalogue export → Libib movie CSV"). This doc does that research: exact import mechanism, exact fields, and a mapping plan against the current production export (`products_9.14.csv`, root of repo, 7,010 movie products).

Sources: support.libib.com (`libib/website/add-items.html`, `ultimate/website/exports.html`, `rest-api/introduction.html`), the actual downloadable template at `support.libib.com/downloads/libib_movie_import_template.csv`. Fetched 2026-09-14.

---

## 1. How Libib bulk upload works

- **CSV only, via the web UI ("Add Items" → CSV import).** There is **no items endpoint in the REST API** — the API only covers accounts/managers/patrons, confirming the 2026-09-12 doc. Bulk creation must go through the CSV importer, not a script hitting an API.
- **One media type per import.** Movies and books (etc.) cannot be mixed in one file. We only care about the Movie template.
- **UTF-8 required.**
- **Identifier requirement, with an escape hatch:** normally a row needs a valid `upc_isbn10` or `ean_isbn13` to import (Libib uses it to look up metadata). **Force Import Mode** (Pro/Ultimate, toggled on the Field Alignment step) drops that requirement — a row imports off `title` alone. Given our data (see §3), we will need Force Import Mode.
- **Column alignment step:** after upload, Libib tries to auto-match your CSV headers to its field names and shows a preview of the first 5 rows per column; unmatched columns are dropped silently. Practical implication: **name our export columns exactly as Libib's field names** (below) so nothing needs manual remapping, and so nothing silently drops.
- No documented row-count or file-size cap.

## 2. Exact Movie template fields

Pulled directly from the downloaded template (`libib_movie_import_template.csv`), not just the docs:

```
title,creators,description,upc_isbn10,ean_isbn13,number_of_discs,ensemble,aspect_ratio,tags,notes,group,price,added,publisher,publish_date,length_of,copies,call_number,ddc,lcc,rating,review,review_created,status,began_date,completed_date
```

| Field | Meaning | Required? |
|---|---|---|
| `title` | Movie title | **Yes**, always. Only mandatory field under Force Import Mode. |
| `upc_isbn10` / `ean_isbn13` | Identifier | Required *unless* Force Import Mode is on. |
| `creators` | Director/cast, free text | No |
| `description` | Synopsis | No |
| `number_of_discs` | Movie-specific | No |
| `ensemble` | Cast, movie-specific | No |
| `aspect_ratio` | Movie-specific | No |
| `length_of` | Runtime in minutes (movie-specific meaning) | No |
| `tags` | Free-text tags, comma-separated presumably | No |
| `notes` | Internal note | No |
| `group` | Libib's shelf/section grouping | No |
| `price` | Numeric | No |
| `added` | Date added | No |
| `publisher` / `publish_date` | Studio / release date | No |
| `copies` | Integer — collapses multiple physical copies of one title into one row | No, defaults presumably to 1 |
| `call_number` | Free text — good candidate for our internal serial/barcode if we don't want it in the identifier field | No |
| `ddc` / `lcc` | Book classification — irrelevant to movies, leave blank | No |
| `rating`, `review`, `review_created` | Patron review fields | No |
| `status`, `began_date`, `completed_date` | Reading/watching-status fields (borrowed from Libib's book model) | No, not meaningful for a rental-shelf import |

**Bottom line:** only `title` is truly required (via Force Import Mode). Everything else is optional, which gives us latitude — but a useless import (title-only, no identifier, no format info) would make the catalogue unsearchable/unusable, so the real target is which *optional* fields we populate well.

## 3. What our export data actually supports

Checked against `products_9.14.csv` (7,010 rows with `Product Category = Media > Videos`, one row per physical copy):

| Libib field | Source column | Fill rate | Notes |
|---|---|---|---|
| `title` | `Title` | 100% | Direct. |
| `upc_isbn10` / `ean_isbn13` | `Variant Barcodes` | 100% present, but **not real UPC/EAN** | Mostly 8-digit internal serials (6,338 rows), some 15/17/18-digit (barcode-format artifacts from Shopify). **56 duplicate values** across otherwise-distinct products. These will not resolve against Libib's metadata lookup and are not safe as a unique identifier. → Do not put these in `upc_isbn10`/`ean_isbn13`; put in `call_number` instead, and use **Force Import Mode**. |
| `description` | `Body (HTML)` | 86.2% | Needs HTML stripped (Libib field is presumably plain text/short markup — confirm, but strip to be safe). |
| `creators` (director) | `Director (product.metafields.custom.director)` | **0%** | Not populated in this export at all — despite CLAUDE.md's note about "in-store TMDB fills" on the dev store, this metafield is empty across all 7,010 production movie rows. |
| genre-ish data | `Genre (product.metafields.shopify.genre)` | 99.5% | Only real genre signal we have; also embedded in `Tags` (e.g. `Blu-Ray, Drama, Formatted, new-arrival, Rental, Supercycle product`). Maps best to Libib's `tags`, not a dedicated field (Libib has no genre field). |
| format (VHS/DVD/Blu-Ray/4K/Laserdisc/Betamax) | `Vendor` | 100% | No dedicated Libib field for media format either — also goes into `tags` (matches the LMS convention of format-as-vendor, per CLAUDE.md's "Media format lives in Vendor" decision). |
| `price` | `Variant Price` | 100% | Direct. |
| `Runtime (min)`, `Year`, `Country`, `Decade`, `Media condition` (all `custom.*` metafields) | — | **0%** across the board | None of these custom metafields have ever been populated on the production catalogue. If we want `length_of` (runtime) or `publish_date` (year) in Libib, we need a TMDB enrichment pass first — same tooling as `formatting-scripts/tmdb_fill.py`, just pointed at these fields instead of (or in addition to) whatever it currently fills. |
| `copies` | — | n/a, computed | 884 titles have multiple physical copies (1,177 extra copies total). Two ways to use this — see open decision below. |
| Rental vs Floor Sale status | `Tags` (`Rental` / `Floor Sale`, mutually exclusive across all 7,010 rows) | 100% | Not a rental-relevant field in Libib itself (Libib doesn't know about "for sale" items), but useful as a `tags` value so staff can filter the Libib catalogue down to just the circulating (Rental) subset, since Floor Sale items presumably shouldn't be checked out through Libib at all. |

## 4. Open decisions (need your call before building the export script)

1. **One row per physical copy vs. `copies` aggregation.**
   - *Per-copy rows* (7,010 rows, `copies` always 1): preserves the "one product per physical copy" model CLAUDE.md establishes for Shopify, and lets each physical item carry its own `call_number` (internal serial). Matches how Libib's own per-copy barcode/condition-note model works if we later scan items in individually.
   - *Aggregated rows* (884 fewer rows via `copies` > 1): simpler catalogue browsing, but loses the individual serial → we'd have to pick one `call_number` per title or drop it, and it doesn't match the "never surface individual serials" + per-item tracking pattern already established.
   - **Recommendation: per-copy rows.** It's the model already in place everywhere else in this project, and Libib's own circulation model (checkout/return, condition notes) is inherently per-copy — aggregating would just have to be undone later if Libib is ever used for actual checkout tracking, not just a catalogue.

2. **What goes in the identifier fields.** Given the barcode data isn't real UPC/EAN and has duplicates, recommend leaving `upc_isbn10`/`ean_isbn13` blank, using **Force Import Mode**, and putting the internal barcode in `call_number` where it's descriptive but not load-bearing for import matching.

3. **Runtime/year/director enrichment.** These are genuinely absent from current data, not just unmapped. Decide whether to:
   - (a) Import now without them (title + genre/format tags + description + price only), or
   - (b) Run a TMDB enrichment pass first (extending `formatting-scripts/tmdb_fill.py`) to populate `creators`, `length_of`, `publish_date` before import.
   - Given the catalogue is ~7,000 items and TMDB fill is already built tooling, (b) is not a large lift, but it does delay the import. **Recommend (a) first as a fast v1 import to validate the pipeline on ~50 titles, then (b) as a follow-up enrichment pass that can update the same rows later** (Libib CSV import appears to be create-only per the docs — re-importing to *update* existing items isn't described, so an enrichment pass may mean deleting and re-importing, or manual edits; needs verification on a trial).

4. **Which subset to import.** All 7,010, or only the 3,178 `Rental`-tagged rows (the ones that actually circulate), excluding the 3,832 `Floor Sale` rows Libib has no use for? **Recommend Rental-only** — Floor Sale stock isn't checked in/out, so it doesn't belong in a circulation catalogue.

5. **Libib tier.** Force Import Mode and CSV import both require **Pro** at minimum (confirmed in the 2026-09-12 doc: CSV import and force-import are Pro/Ultimate features, $9/mo or $99/yr). Confirm the trial/subscription is active before building against this.

## 5. Proposed pipeline

1. Add a new script to `formatting-scripts/` (e.g. `libib_export.py`), sibling to the existing Shopify-CSV pipeline, that reads the same normalized product data and emits a CSV with exactly the Libib movie template headers.
2. Column mapping (pending decisions above):
   - `title` ← `Title`
   - `description` ← `Body (HTML)`, HTML stripped
   - `tags` ← genre (`Genre (shopify.genre)`) + format (`Vendor`) combined, comma-separated
   - `price` ← `Variant Price`
   - `call_number` ← `Variant Barcodes` (internal serial, not a real identifier)
   - `copies` ← `1` (per-copy rows, decision #1)
   - leave `upc_isbn10`, `ean_isbn13`, `creators`, `number_of_discs`, `ensemble`, `aspect_ratio`, `length_of`, `publisher`, `publish_date`, `ddc`, `lcc`, `rating`, `review*`, `status`, `began_date`, `completed_date` blank for v1
3. **Trial import of ~50 rows first** on the Libib Pro trial, with Force Import Mode on, verify: rows land correctly, tags are usable for filtering, `call_number` is visible somewhere useful, description renders acceptably.
4. Full import of the Rental subset (3,178 rows) once the trial is clean.
5. Only after that: decide on the TMDB enrichment pass for `creators`/`length_of`/`publish_date`, and confirm whether Libib supports re-import/update of existing rows or whether enrichment requires a fresh delete + re-import.

## 6. What's still unverified (needs a live Libib trial, not just docs)

- Whether `description` accepts HTML or needs plain text.
- Whether CSV import can **update** existing items (by identifier or title match) or is strictly additive — matters a lot for decision #3's "enrich later" plan.
- Exact behavior of `tags` field (single string vs. delimiter Libib expects).
- Whether Force Import Mode still consumes an identifier column if present-but-invalid, or requires the columns to be entirely absent/blank.
