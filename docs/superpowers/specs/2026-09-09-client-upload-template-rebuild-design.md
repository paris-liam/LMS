# Client upload template — rebuild design

**Date:** 2026-09-09
**Status:** approved, ready for implementation planning
**Supersedes:** `docs/superpowers/specs/2026-07-16-client-product-upload-template-design.md` and its plan `docs/superpowers/plans/2026-07-19-client-product-upload-template.md`
**Roadmap item:** #3 in `CLAUDE.md` — a corrected upload sheet so the client's ongoing imports land already-formatted.

## Why restart instead of revise

The 2026-07-16 design accumulated four rounds of superseding revisions (barcode-driven 07-24, vendor-format 08-07, two-sheet 08-07, auto-handle 08-11). Reading it now means reading a design plus four corrections to it. Its deliverables lived at `data-cleanup/client-template/`, were last present at commit `d4feb42`, and were deleted in the `data-cleanup/` → `formatting-scripts/` reorg (`c4f4b85`). Nothing survives in the working tree.

Its acceptance test — Task 4, a real dev-store import — was never run. The template was never validated against Shopify.

Meanwhile the ground moved: `formatting-scripts/` grew a normalizer that derives most of what the sheet's formulas derived, production became the source of truth (2026-09-02), Supercycle went live on production (2026-09-09), and the format list grew from four to six.

## Problem

The client uploads products by importing a Google Sheet straight into production. He must be able to keep doing that **unaided**. The sheet must therefore emit an import-perfect Shopify CSV on its own, with no pipeline pass in between.

The prior design achieved that but pushed the cost onto him: 23 columns, a hidden mapping tab, ~11 fill-down formulas, a 7-line `LET` handle formula, interleaved typed and generated cells, and a "select A:Q, copy to a new sheet, download" export ritual.

**The goal of this rebuild is the same output with the complexity moved off his side of the sheet.**

## Decisions

Confirmed with the user during brainstorming, 2026-09-09:

1. **Self-import is mandatory.** Every batch must be importable by the client without the pipeline. This is the constraint that keeps the formula machinery; it is not negotiable for convenience.
2. **He types the description and the poster URL.** No TMDB backfill on his path. Products are complete on import.
3. **Two tabs, not two zones.** Tab 1 holds only columns he types. Tab 2 is generated and never touched.
4. **One row = one physical copy = one product.** Status quo, matching production and the Retail Barcode Labels model (one barcode per tape). Three copies = three rows.
5. **One workbook with a Type dropdown**, not separate rental and floor-sale files.
6. **Fresh copy of the sheet per batch.** No running-sheet state to maintain. The cross-batch collision risk this creates is accepted and documented (see *Handle collisions*).
7. **`Year` is cut.** It existed solely to let the TMDB script disambiguate films on the never-shipped Path B. With the client typing his own copy and poster, TMDB never runs on his rows and nothing consumes it.
8. **Scope includes closing two gaps that would otherwise block him** (Fixes A and B below). Supercycle enrollment and duplicate cleanup remain developer work and are documented as such.

## Grounding

All figures from the production export `9.8-products/products_export_1.csv` (2026-09-08): 7,056 rows, **7,014 distinct products**.

| Fact | Value |
|---|---|
| Movie products (Vendor carries a format) | 7,004 |
| Genuine non-movie products | **4** — 2 Supercycle plan products, 1 shirt, 1 bumper sticker |
| Products with Vendor `Little Movie Store` that are really movies | 6 (missing format data; a separate cleanup) |
| Distinct `shopify.genre` handles in use | 13, exactly matching `formatting-scripts/taxonomy.py` |
| `shopify.genre` populated | 5,578 of 7,056 rows |
| Formats in Vendor | VHS 3,750 · DVD 2,181 · Blu-Ray 855+61 · 4K 96+27 · Laserdisc 33 · Betamax 1 |

## Architecture — one workbook, two tabs

### Tab 1 — "Add movies" (everything he sees)

| Col | Field | Input | Required |
|---|---|---|---|
| A | Title | typed | ✅ |
| B | Format | dropdown — VHS / DVD / Blu-Ray / 4K / Laserdisc / Betamax | ✅ |
| C | Type | dropdown — Rental / Floor Sale | ✅ |
| D | Genre 1 | dropdown — the 13 genres | ✅ |
| E | Genre 2 | dropdown | — |
| F | Genre 3 | dropdown | — |
| G | Price | number | Floor Sale only |
| H | Description | typed | ✅ |
| I | Image URL | typed | ✅ |
| J | Extra tags | typed, comma-separated | — |

**10 columns; 6 touches per rental row, 7 per floor-sale row** (Title, Format, Type, Genre 1, Description, Image URL, + Price). Genre 1 is the shelf genre — it becomes `Option1 Value` and prints on the barcode label.

### Tab 2 — "Shopify import" (never touched)

**One array formula anchored in A1** emitting the header plus exactly as many rows as tab 1 holds. No fill-down, no trailing blank rows, nothing to drag. Export is `File → Download → CSV` with tab 2 active — no column selection, no copy-to-a-new-sheet.

Its 17 columns are exactly `formatting-scripts/columns.py:TEMPLATE_COLUMNS`, so the downloaded CSV is both directly importable **and** re-runnable through `run.py` losslessly if a batch ever needs rescuing.

| Import column | Derivation |
|---|---|
| `Handle` | `slug(Title)-slug(Format)-slug(Type)`, `-2`/`-3` on repeats within the sheet |
| `Title` | passthrough |
| `Body (HTML)` | Description |
| `Vendor` | Format label verbatim — media format lives in Vendor (2026-08-07 decision) |
| `Product Category` | `Media > Videos` |
| `Tags` | Type, Format, Genre 1–3, Extra tags — comma-space joined, blanks skipped |
| `Status` | `Active` |
| `Option1 Name` | `Genre` |
| `Option1 Value` | Genre 1 |
| `Variant Inventory Tracker` | `shopify` |
| `Variant Inventory Qty` | `1` |
| `Variant Inventory Policy` | `deny` |
| `Variant Fulfillment Service` | `manual` |
| `Variant Price` | Rental → `0`; Floor Sale → Price |
| `Image Src` | passthrough |
| `Image Alt Text` | `<Title> poster`, blank when no image |
| `Genre (product.metafields.shopify.genre)` | genre labels → handles via `mappings`, joined `"; "` |

The three inventory columns must always ship together. A blank `Variant Inventory Tracker` means inventory is not tracked, which makes `product.available` permanently true and renders the out-of-stock state and notify-me form in `sections/main-movie.liquid` unreachable.

### Tab 3 — "mappings" (hidden)

A single 13-row table, genre label → `shopify.genre` handle:

Comedy→`comedy` · Action→`action` · Drama→`drama` · Kids & Family→`kids-family` · Sci-Fi→`sci-fi` · Thriller→`thriller` · Horror→`horror` · Romantic Comedy→`romantic-comedy` · Musical→`musical` · Fantasy→`fantasy` · Documentary→`documentary` · Foreign→`foreign` · Holiday→`holiday`

Formats need no lookup — Vendor takes the label directly — so the format table from the old design is gone.

## Handle collisions

Within a sheet, the counter suffixes repeats `-2`, `-3`. Across batches it is blind: a fresh sheet cannot know he uploaded two copies of *Rushmore* last month, so a third copy generates `rushmore-vhs-rental` again and Shopify **updates the existing product instead of creating a new one** — silently merging two physical tapes into one product with one barcode.

Accepted per decision 6. Two mitigations, neither costing him effort:

- The guide instructs him to check the Shopify import summary's **created vs updated** counts. Any "updated" on a batch he believes is all-new means a collision.
- The periodic dedupe pass catches what slips through.

Non-ASCII titles degrade the same way they did before (`Amélie` → `am-lie`). The escape hatch is unchanged: type over that one cell.

## Fix A — invert the product template default

**The problem.** Shopify's product CSV has 66 columns and **none of them sets a template suffix** (verified against the production export). Imported movies therefore land on the *default* product template, which renders price, variant picker, quantity and buy buttons — a **$0.00 "Buy now" button** on every rental. That violates the hard requirement in `CLAUDE.md` that no express-checkout path is reachable from a movie PDP.

Today the remedy is `scripts/set-movie-template.sh`, which needs Shopify CLI auth and `--apply`. The client cannot run it, so every product he uploads unaided is broken.

**The fix.** With movies at 7,004 of 7,014 products, the default is backwards. The movie layout becomes `templates/product.json`; the current default layout moves to `templates/product.retail.json`; the four non-movie products take the `retail` suffix.

**The predicate for identifying non-movies is `normalize.py:is_non_catalogue_product`** — Vendor `Supercycle`, or a tag of `online-store` — which selects exactly the four genuine non-movies. Do **not** use "Vendor isn't a format": six real movies carry Vendor `Little Movie Store` and would be misfiled onto the retail template.

**Migration order is load-bearing, and the obvious orders all break something.** Pushing the new default first leaves 7,004 products pointing at a deleted `product.movie.json`; clearing suffixes first drops every movie onto the retail layout with its $0.00 Buy now button. This five-step sequence has no broken window at any point:

1. **Push** `templates/product.retail.json` (a copy of today's `product.json`). Nothing renders differently — no product references it yet.
2. **Set** `templateSuffix = retail` on the four non-movie products. They now render the retail layout from the new file. Correct.
3. **Push** `product.json` with the movie layout, leaving `product.movie.json` in place and unchanged. Now movies with the `movie` suffix use `product.movie.json`, movies without it use `product.json`, and non-movies use `product.retail.json`. All three correct.
4. **Clear** the `movie` suffix from the 7,004 movies. They fall through to `product.json`, which is already the movie layout. Correct throughout.
5. **Delete** `product.movie.json` and push. Safe — no product references it any more. Retire `set-movie-template.sh`.

Steps 2 and 4 are product mutations with the same blast radius as `set-movie-template.sh`, which already exists, dry-runs by default and is idempotent. Adapt it rather than write something new.

**Result:** any product imported with no suffix gets the movie template automatically, forever. The sheet needs no new column.

## Fix B — format whitelist becomes a theme setting

The recognised-format list is hardcoded in three places: `sections/main-movie.liquid:25`, `snippets/lms-product-card.liquid:28`, and `scripts/set-movie-template.sh`. A format the client adds to his dropdown renders no badge and gets no filter until someone edits Liquid.

Add `lms_known_formats` to `config/settings_schema.json` — a text setting defaulting to `VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX`. Both Liquid files read `settings.lms_known_formats`, falling back to the literal when blank so a cleared setting cannot blank every badge on the storefront. The third copy disappears with `set-movie-template.sh`.

The Search & Discovery vendor facet (`filter.p.vendor`) picks up new vendor values on its own — no action there.

**Genre needs no equivalent fix.** All 13 handles are Shopify's standard `shopify.genre` taxonomy, not custom metaobjects. The client cannot add one, and does not need a developer to: the list is fixed and complete. This is a paragraph in the guide, not code. *(Confirm the list is genuinely closed during implementation — it affects only that paragraph.)*

## Still needs a developer — stated plainly in the guide

- **Supercycle enrollment.** A sheet-uploaded product tagged `Rental` is an ordinary Shopify product and is **not rentable**. Someone must import the title into Supercycle, enable the Membership method, and create an item per physical copy. Production stands at 52 of 3,130 rental products enrolled. The guide must say this outright so he is never surprised by a rental that will not rent.
- **Duplicate cleanup.** Cross-batch collisions and copy consolidation need `formatting-scripts/`.

## Deliverables

Under `formatting-scripts/client-template/` — the sheet is the input contract to that pipeline.

| File | Purpose |
|---|---|
| `client-upload-template.csv` | The 10 fill-tab columns + 2 worked example rows. He does File → Import to create the sheet. |
| `import-tab-formula.txt` | The single array formula for tab 2, plus the 13-row `mappings` table. |
| `client-upload-guide.md` | One-time setup checklist, per-row fill rules, export, extending formats, and the two developer-only items above. |

Plus the Fix A and Fix B theme and script changes.

## Validation

1. **A Python test that reimplements the array formula's transform** and asserts its output matches `normalize.py` for the same input. This pins the sheet to the pipeline, so a future taxonomy change breaks a test instead of drifting silently. Runs under the existing `tests/formatting_scripts/` suite — standard library only.
2. **A real test import to the dev store** (`lms-sandbox-lutsfahz.myshopify.com`) — 2 rows, verify every field lands, then delete the test products. This is the step the 07-19 plan never ran.
3. **Fix A verification, per migration step:** after step 2, confirm the four non-movie products carry `templateSuffix = retail` and the membership page still has a working add-to-cart. After step 3, confirm a suffixed and an unsuffixed movie PDP both render read-only with no buy button. After step 5, confirm no product still carries the `movie` suffix.

## Open items to verify at build

- Whether Google Sheets' `MAP`/`LAMBDA` performs acceptably on a 200-row batch when the handle counter is O(n²). If not, fall back to a hidden helper column on tab 2 holding the base handle.
- Whether the `shopify.genre` taxonomy value list is genuinely closed to merchant additions.
- Whether Shopify's admin bulk editor exposes Theme template. Fix A makes this moot for new uploads, but it would be a useful repair tool.

**I cannot execute Google Sheets formulas.** They can be written but not run from here. One manual pass — building the sheet once from the CSV + formula file — is required before this reaches the client. The guide is written as a checklist for exactly that pass.

## Non-goals

- TMDB backfill on the client's path (decision 2).
- Product edits, removals or bulk updates — admin UI, not this sheet.
- Preventing duplicates at upload time — deliberate, per `CLAUDE.md`.
- Supercycle item/serial creation.
- Pushing the reformatted catalogue to production (roadmap #2).
