# Floor Sale upload sheet (design, 2026-10-08)

**Status: spec, not built.** Decisions below were confirmed with the
developer 2026-10-08. Two items need a dev-store test before building (see
"Verify on the dev store first").

**Supersedes**, for Floor Sale only,
`claudedocs/2026-10-01-client-upload-sheet-shopify-and-libib.md` and the
Floor Sale half of `catalog/client_sheet/template/`. The rental half of that
sheet is also going away (rentals will be uploaded to Libib directly, then
synced to Shopify, using Libib-generated barcodes) but is specced separately
— until that spec lands, do not delete the rental code paths.

## The new model (both halves, for context)

| | Rental | Floor Sale |
|---|---|---|
| Entered in | Libib, directly | **This sheet** |
| Reaches Shopify by | Libib → Shopify sync (rental spec, TBD) | Shopify product CSV import |
| Barcode | Libib-generated | Retail Barcode Labels, after import |
| Website | (rental spec) | **Never** — POS only |

## Goal

The client adds floor-sale stock with a Google Sheet that produces a Shopify
product-import CSV. He imports it into production himself, then creates,
prints and applies barcode labels in Retail Barcode Labels. Floor-sale
products are sold at the counter only.

## Decisions (2026-10-08)

| # | Decision |
|---|---|
| 1 | Required data: title, format, **one** genre, price, the `Floor Sale` tag. No image, no description. |
| 2 | Taxable. |
| 3 | Published to **Point of Sale only**, never the Online Store. |
| 4 | **One product per physical copy** (closes CHECKLIST item 8's open question for new uploads). Quantity is always 1. |
| 5 | Handles carry the **batch date**, so a later batch can never collide with an earlier one. The client also leaves "Overwrite products with matching handles" **unchecked** on import (belt and braces). |
| 6 | One genre only (Genre 2/3 dropped). |
| 7 | Variant option stays as it is today (`Option1 Name = Genre`, value = the genre name). |
| 8 | Keep the free-text **Extra tags** column. |
| 9 | Floor Sale gets **its own sheet**; it accepts Floor Sale rows only. |

## Sheet

### Tab 1 `Add floor sale` (fill tab)

| Col | Header | Rules |
|---|---|---|
| A | Title | required |
| B | Format | required, dropdown `VHS, DVD, Blu-Ray, 4K, Laserdisc, Betamax` |
| C | Genre | required, dropdown `mappings!A:A` |
| D | Price | required, number > 0 (data validation: reject ≤ 0 / non-number) |
| E | Extra tags | optional, comma-separated |

Plus one **batch date** cell, above or beside the data (proposed: `G1`
label "Batch date", `G2` the date, validated as a date). The client types
it once per batch. It is **typed, not `=TODAY()`**: a volatile date would
change the handles if the tab is downloaded again on another day, turning a
re-import into a full set of duplicates. The import tab emits an error row
instead of a CSV body while `G2` is blank.

No Type column (every row is Floor Sale), no Description, Image URL, Genre
2/3 or Barcode.

### Tab 2 `Shopify import`

One row per filled row on tab 1. Columns (16, in this order — becomes a new
`FLOOR_SALE_TEMPLATE_COLUMNS` in `catalog/core/columns.py`):

| Column | Value |
|---|---|
| `Handle` | `slug(title)-slug(format)-floor-sale-YYYYMMDD`, plus `-2`, `-3` … for repeats within the batch (e.g. `speed-dvd-floor-sale-20261008`, `speed-dvd-floor-sale-20261008-2`) |
| `Title` | Title, trimmed |
| `Vendor` | Format |
| `Product Category` | `Media > Videos` (Shopify Tax reads this — keep it constant) |
| `Tags` | `Floor Sale` + Extra tags |
| `Status` | `Active` (POS can only sell Active products) |
| `Published` | `FALSE` (Online Store channel only) |
| `Option1 Name` | `Genre` |
| `Option1 Value` | the genre name |
| `Variant Inventory Tracker` | `shopify` |
| `Variant Inventory Qty` | `1` |
| `Variant Inventory Policy` | `deny` |
| `Variant Fulfillment Service` | `manual` |
| `Variant Price` | Price, `TO_TEXT` |
| `Variant Taxable` | `TRUE` (**new**) |
| `Genre (product.metafields.shopify.genre)` | the genre's handle from `mappings` |

Dropped vs. today: `Body (HTML)`, `Image Src`, `Image Alt Text`.

Handle rules are unchanged apart from the date suffix: same `slug` as
`catalog/core/handles.py:slugify`, same in-batch counter.

### `mappings`

Unchanged: the 15-genre table, imported from `genre-mappings.csv`, hidden.

## Client flow

1. Make a copy of the master sheet, clear old rows, set the **batch date**.
2. Fill one row per copy (three copies = three rows).
3. Download `Shopify import` as CSV → Shopify **Products → Import**, with
   **"Overwrite products with matching handles" unchecked**. Summary should
   read all *created*, none *updated*.
4. (If the dev-store test shows it's needed — see below) Products → filter
   tag `Floor Sale` → select the new ones → **Include in sales channels →
   Point of Sale**.
5. In Retail Barcode Labels: create barcodes **saved to the variant**, print,
   apply.

## Verify on the dev store first

Both block the build; results go into this doc.

1. **POS availability after import.** Import one row with `Published=FALSE`.
   Check Products → the product → Sales channels: is **Point of Sale** on?
   If not, step 4 of the client flow is required (or find a CSV/app setting
   that does it). Also confirm it's findable and sellable in POS.
2. **`Variant Taxable` + tax.** Confirm the imported variant shows "Charge
   tax" on, and a test POS sale charges the expected rate for the shop's
   location (Settings → Taxes must have the registration; tax-inclusive vs
   added-on is a store setting — confirm which the client wants).
3. **Overwrite unchecked.** Re-import the same file with the box unchecked
   and confirm Shopify skips (not updates) the existing handle. If it
   updates anyway, the date suffix is the only protection — note it.

## Things the client must know (guide content)

- A blank or $0 price is rejected by the sheet; the old "$0 at the counter"
  trap is gone.
- Retail Barcode Labels must **save** the barcode to the variant, or the
  scanner finds nothing at POS.
- Its last-8-digits-of-variant-ID rule can give two products the same
  barcode (Swashbuckler/Frances, 2026-09-30). If a scan rings up the wrong
  item, tell the developer.
- Import each batch once. Re-downloading on a later day is safe only because
  the batch date is typed, not computed.
- Restocking an existing title = a new row in a new batch (one product per
  copy), not editing the old product's quantity.

## Repo changes

1. `catalog/core/columns.py`: add `FLOOR_SALE_TEMPLATE_COLUMNS` (above).
   Leave `TEMPLATE_COLUMNS` until the rental spec retires it.
2. `catalog/core/handles.py` / `HandleAllocator`: support a date suffix
   (`floor-sale-YYYYMMDD`).
3. `catalog/client_sheet/`: a floor-sale transform
   (`floor_sale_rows_to_import_rows(rows, batch_date)`) alongside the old
   one; `check-upload` gains a `floor-sale` fill shape and import shape:
   - errors: missing title/format/genre, unknown format or genre, price
     blank / ≤ 0 / non-numeric, `Published` not `FALSE`, `Status` not
     `Active`, `Variant Taxable` not `TRUE`, qty not `1`, tag missing
     `Floor Sale`, any `Rental` tag, handle without a valid date suffix,
     duplicate handle in the file.
4. `catalog/client_sheet/template/floor-sale/`: scaffold CSV, tab-2
   formula, expected-output fixture, client guide (rewritten for the 5-step
   flow above). Reuse `genre-mappings.csv`.
5. Tests in `tests/catalog/` for the transform, handle suffix, check
   shapes, and a seam test against a live-sheet export (same pattern as
   today's `sheet-export*.csv`).
6. **Pipeline stops enriching Floor Sale.** `catalog/picker/push.py`
   currently routes floor sales into `floor-sale-NN` picker groups for TMDB
   fill (description/poster). New floor-sale products have neither by
   design, so they must not be queued: skip `Floor Sale` in `push` (and
   anything in `audit`/`tmdb` that treats a missing description/image as
   work). Existing floor-sale products keep whatever image/description
   they have.
7. `audit`: flag a Floor Sale product that is published to the Online Store
   (catches anything the 2026-10-02 one-time unpublish missed) and one that
   is not taxable.
8. `CLAUDE.md` roadmap #3 and `CHECKLIST.md` item 8 point here.

## Out of scope / open

- The rental flow (Libib-first, Libib → Shopify sync, Libib barcodes) —
  next spec. It decides what happens to the current combined sheet and its
  Libib tab.
- The 129 existing Floor Sale products with quantity ≥ 2 stay as they are
  (decision 4 applies to new uploads); whether to split them is a separate
  call.
- Optional retail fields not adopted: condition (new/used), cost per item,
  compare-at price. Easy to add later as optional columns.
