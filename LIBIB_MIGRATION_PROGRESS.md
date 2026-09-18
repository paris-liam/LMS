# Libib Migration — Progress

Status as of 2026-09-18.

## Current strategy (supersedes the UPC-matching approach below)

Shopify is the source of truth. A Libib item's **title, poster, barcode,
description, genres, tags, and format must be 1:1 with its Shopify
counterpart**. The TMDB/UPCMDB enrichment pipeline (`imdb_upc_fill.py`,
`libib_pipeline.py`) is **deprecated as an import gate** — Libib's
Force Import Mode only requires `title`, so a UPC is no longer needed to get
an item into Libib at all.

**New pipeline:**
1. A Shopify rental product qualifies once all 7 fields are filled in Shopify:
   `Title`, `Image Src`, `Variant Barcode`, `Body (HTML)`, `Genre` metafield,
   `Tags`, `Vendor`.
2. Force-import qualifying products into Libib via CSV (title-only requirement).
3. Run `formatting-scripts/libib_barcode_update.py` (existing, unchanged) to
   set each copy's physical barcode to match `call_number`.
4. Run a **new script** (in progress — see below) that opens each item's Edit
   form, verifies `title`/`description` match Shopify exactly, and uploads
   the Shopify poster image via the `#cover-image` file input. Confirmed
   feasible: Libib's edit form has plain `input[name="title"]`,
   `textarea[name="description"]`, and `input#cover-image` (type=file,
   accepts png/jpeg/gif/webp) — same automatable shape as the barcode script.
5. **Ongoing**: periodically revisit incomplete Shopify products (see below)
   to fill gaps, then run them through steps 1-4.

## Master numbers (full current Shopify rental catalogue, 3,130 primary products)

Computed from `Libib_Migration_Master/shopify_rental_current_9.16.csv` (the
committed HEAD version — the working copy has since had 652 already-in-Libib
rows stripped out, see below).

| | count |
|---|---|
| **Complete on all 7 fields — eligible for the new pipeline** | **2,977** |
| Incomplete — missing poster | 133 |
| Incomplete — missing description | 118 |
| Incomplete — missing genre | 11 |
| **Total incomplete (the real ongoing backlog)** | **153** |

## Cross-tabulated against registry state (`libib-batches/_handle-index.json`)

| complete-per-Shopify handles | registry status | what happens next |
|---|---|---|
| 657 | `barcoded` (already live in Libib) | **Audit queue** — verify title/description/poster against Shopify with the new script, fix drift (we already confirmed some UPC-sourced posters are wrong, e.g. "101 Dalmations" got matched to 102 Dalmatians' UPC). |
| 674 | `exported` (batches 40-46, was queued for old-style import) | **Re-route** — import as-is via Force Import Mode (CSVs don't need rebuilding, UPC presence is irrelevant now), then run the new script instead of trusting Libib's auto-lookup. |
| 1,172 | `awaiting-upc` | **New force-import candidates** — retires the entire "ambiguous/typo/no-record" UPC backlog concern; these no longer need a UPC match to go in. |
| 328 | not in registry at all | **Brand new** — never touched by the pipeline (added to Shopify since the original 9/14 export, or otherwise missed). Onboard fresh. |
| 146 | `needs-review` | **Still held** per 2026-09-18 decision — separate track, not sequenced yet. |

(657+674+1172+328+146 = 2,977, checks out. A handful of `barcoded`/`exported`
handles are *not* in the complete set — edge cases not yet investigated.)

## In progress

- **Image-upload script**: not built yet. Feasibility confirmed (see above).
  A 15-item test batch is staged at `libib-batches/test-force-import/` —
  `upload-title-only.csv` (title/description/tags/call_number filled, no UPC)
  plus posters already downloaded from Shopify — **waiting on manual Force
  Import of that CSV into Libib** before the script can be written against
  real data.
- Once the script works on the test batch: decide execution order across the
  657 (audit) / 674 (re-route) / 1,172 (new) / 328 (new) pools.

## Historical: UPC-based pipeline (superseded, kept for context)

Old pipeline: enrich each product with a UPC (for Libib's poster/metadata
lookup) via TMDB → UPCMDB, import via CSV in batches, then barcode. Driver
was `formatting-scripts/libib_batch.py`.

**What got done under the old approach:**
- Batches 1-29: originally exported, mix of `awaiting-upc`/`barcoded`.
- Batches 30-37 (736 rows): reconciled after batch-30's partial import — 51
  confirmed-uploaded rows, 67 legacy-call-number rows split to
  `bad-barcode-batch`, 49 duplicate-UPC/EAN rows split to `duplicate-batch`,
  remainder regrouped into batch-38/39.
- Batch-38 (284 rows) imported: 264 confirmed in Libib, barcoded (206
  updated, 56 already correct); 20 never made it in → `batch-0038-missing`.
- Batch-39 (285 rows) imported: 266 confirmed in Libib, barcoded (0 final
  errors); 19 never made it in → `batch-0039-missing`.
- All 659 `barcoded` handles spot-checked against `libib_9.18.csv` — barcode
  field matched call_number exactly, no drift, as of that check.
- Format-relaxation fix to `pick_upc_record` (UPC no longer needed to match
  our exact Vendor/format) resolved 677 of 692 stuck rows to `exported`
  using cached data, zero new UPCMDB quota. **This is now moot** — Force
  Import Mode means no UPC match is needed at all going forward, but the 674
  of those 677 that are still `exported` get re-routed per the plan above
  rather than re-processed.

**`needs-review` breakdown (157, still held)**

| batch | count | why |
|---|---|---|
| `bad-barcode-batch` | 67 | Legacy `191-XXX-001A` call numbers — need renumbering to the 8-digit LMS serial format. |
| `duplicate-batch` | 49 | Same UPC/EAN as another row in the 30-37 cohort — legitimate multi-copy titles, but 4 pairs have inconsistent title text worth normalizing. |
| `batch-0038-missing` | 20 | Rows from batch-38's CSV that didn't land in Libib on import — cause not diagnosed. |
| `batch-0039-missing` | 19 | Same, batch-39. Two (`06863866` Chronicles of Riddick, `96085242` Kangaroo Jack G'Day USA) have failed import twice across two batches. |
| `batch-0001` | 2 | Pre-existing, unrelated (`1917`, `One Battle After Another`) — never investigated. |

## Decisions log

- **2026-09-18**: Relax UPC format-matching constraint — done, +677 (see above). Order was: upload 677 → ambiguous cleanup → typo fixes → dead-end decision. **Superseded same day** by the Force Import strategy above.
- **2026-09-18**: `needs-review` pile (157) — held entirely, not sequenced.
- **2026-09-18**: Strategy pivot to Force Import Mode + verify/image script, dropping UPC as an import gate. The already-queued 676 (batches 40-46) get re-routed through the new approach rather than old-style UPC import. The 659 already-barcoded items get audited (not just left alone) since UPC-sourced posters are confirmed unreliable.
