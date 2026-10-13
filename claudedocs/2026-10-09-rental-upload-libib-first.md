# Rental upload — Libib first, then Shopify (design, 2026-10-09)

**Status: spec, not built.** Decisions confirmed with the developer
2026-10-09. Items under "Verify first" need a test on the dev store and the
client's Libib account before building.

**Companion to** `claudedocs/2026-10-08-floor-sale-upload-sheet.md`. Together
they **supersede** `claudedocs/2026-10-01-client-upload-sheet-shopify-and-libib.md`
and the combined sheet in `catalog/client_sheet/template/` (both now
historical).

## Goal

The client adds rentals **in Libib first**, one item at a time (UPC/ISBN
lookup or typed in), and Libib assigns the barcode. After a batch he
exports from Libib, a Google Sheet turns the export into a Shopify
product-import CSV, he imports it, and then prints the labels — carrying the
Libib barcode — from Shopify.

**Libib is the source of truth for rentals added this way.** Shopify copies
it; nothing writes back into Libib for these items.

## Decisions (2026-10-09)

| # | Decision |
|---|---|
| 1 | Scope is **the client's new flow**. Legacy rentals (Shopify-first, 8-digit barcodes) keep being reconciled by the existing `libib diff` / `fix` until every Shopify rental is in Libib; after that the client uses only this flow. |
| 2 | Format and genre are entered as **Libib tags from a fixed vocabulary** (below). |
| 3 | The Shopify **handle includes the Libib barcode**. |
| 4 | New items leave Libib's **`call_number` blank**. The join key for these items is the **barcode**. |
| 5 | The conversion is a **Google Sheet the client runs himself** (not a developer CLI). |
| 6 | Rentals are **not taxable** and **not available on POS**. |
| 7 | Barcodes are **Libib-generated** (`201` + 9-digit counter + check digit, 13 digits). Labels are printed **from Shopify**. |

Defaults adopted from the review (change here if wrong):

| # | Default |
|---|---|
| 8 | Poster: the Shopify import leaves `Image Src` blank — neither Libib export carries a cover URL. The TMDB picker fills it later (Shopify only). |
| 9 | Messy lookup titles (`The Curse [VHS]`, `… (Widescreen Edition)`) are **fixed in Libib**, not in the sheet. The sheet holds such rows back until they're fixed, so Libib and Shopify titles stay identical. |
| 10 | More copies of a title: **add a copy to the existing Libib item** (keeps availability together on the published site). Each copy still becomes its own Shopify product. *Subject to Verify #3.* |
| 11 | A copy deleted in Libib (lost/damaged) is **not** removed from Shopify by the sheet. Handled later by a reconcile report (open). |

## Libib conventions for the client

Every new rental item, before he saves it:

- **Collection:** `Rental Library`.
- **Title:** the film's title as it should appear on the website — delete
  lookup noise such as `[VHS]`, `(Widescreen Edition)`, `Special Edition`.
- **Tags — exactly one format and 1–3 genres**, each as its own tag, from
  this list only (Libib lowercases tags on save; the sheet compares
  case-insensitively):

  | Formats | Genres |
  |---|---|
  | `vhs`, `dvd`, `blu-ray`, `4k`, `laserdisc`, `betamax` | `comedy`, `action`, `drama`, `kids-family`, `sci-fi`, `thriller`, `horror`, `romantic-comedy`, `musical`, `fantasy`, `documentary`, `foreign`, `holiday`, `special-interest`, `anime` |

  These are the values already on the 3,496 legacy Libib items (same
  vocabulary the pipeline writes), so the published site's tag filter stays
  consistent. Any other tag holds the row back.
- **Description:** optional (lookup usually fills it).
- **Barcode:** leave Libib's generated `201…` value. Do not override it.
- **Call #:** leave blank.

## Libib exports — facts (from `exports/2026-10-08/`)

| Export | Rows | Has | Lacks |
|---|---|---|---|
| Barcodes (`barcodes_*.csv`) | one per copy | `id`, `barcode`, `title`, `collection`, `tags`, `call_number`, `created`, `format (movie)` | description, cover |
| Library (`library_*.csv`) | one per item | `id`, `title`, `description`, `tags`, `added`, `copies` | barcode, cover |

Both are needed, joined on `id` (as `catalog/libib/exports.py` already
does). Both export the **whole** collection — there is no "recently added"
export — so the sheet filters by date. Tags export as one comma-separated
lowercased string, e.g. `dvd, kids-family`. The only 13-digit item in that
export, `The Curse [VHS]` (2026-10-08), has no tags and a bracketed title —
exactly the two problems the conventions above address.

(Libib also has a native movie **Format** field — the `format (movie)`
column — set on one item today. Not used: decision 2 keeps format in tags.)

## The sheet

### Tabs

| Tab | Who fills it | Content |
|---|---|---|
| `Start here` | client | One cell: **Added on or after** (date). |
| `Libib barcodes` | client | The barcodes export, imported (File → Import → Replace current sheet, **"Convert text to numbers" unchecked**). |
| `Libib library` | client | The library export, imported the same way. |
| `mappings` | setup, hidden | Genre name ↔ handle (the 15-row `genre-mappings.csv`) and format tag ↔ Vendor (`vhs`→`VHS`, `dvd`→`DVD`, `blu-ray`→`Blu-Ray`, `4k`→`4K`, `laserdisc`→`Laserdisc`, `betamax`→`Betamax`). |
| `Problems` | formula | Rows held back, with the reason. |
| `Shopify import` | formula | The CSV to download. |

### Which rows are in the batch

A row of `Libib barcodes` is in the batch when **all** of:

- `collection` = `Rental Library`
- `barcode` is 13 digits starting `201` (excludes every legacy 8-digit item —
  those are already in Shopify)
- `created` ≥ the **Added on or after** date

Overlapping date ranges between batches are harmless: the handle contains
the barcode, so a copy already imported has the same handle and the import
skips it (overwrite unchecked — *Verify #4*).

### Held back (`Problems` tab), never on `Shopify import`

| Reason | Rule |
|---|---|
| No format tag | none of the 6 format tags |
| More than one format tag | |
| No genre tag | none of the 15 genre tags |
| Unknown tag | any tag outside the vocabulary |
| Title needs fixing | contains `[`, `]`, `(`, `)`, or `edition` (case-insensitive) |
| Blank title | |

Each Problems row shows title, barcode, tags and reason. The client fixes the
item **in Libib**, re-exports, re-imports both tabs; the row moves to
`Shopify import` on its own.

A missing description is **not** a problem (shown on Problems as a warning
only, still imported).

### `Shopify import` columns

19 columns, in this order — a new `RENTAL_TEMPLATE_COLUMNS` in
`catalog/core/columns.py`:

| Column | Value |
|---|---|
| `Handle` | `slug(title)-slug(format)-rental-<barcode>`, e.g. `the-curse-vhs-rental-2010000002155` |
| `Title` | Libib title, whitespace collapsed |
| `Body (HTML)` | Libib description (library tab, by `id`), whitespace collapsed |
| `Vendor` | format, via mappings (`VHS`, `Blu-Ray`, …) |
| `Product Category` | `Media > Videos` |
| `Tags` | `Rental` |
| `Status` | `Active` |
| `Published` | `TRUE` (Online Store) |
| `Option1 Name` | `Genre` |
| `Option1 Value` | first genre's **name** (mappings, handle → name) |
| `Variant Barcode` | Libib barcode, `TO_TEXT` (**new** — today's import never carried barcodes) |
| `Variant Inventory Tracker` | `shopify` |
| `Variant Inventory Qty` | `1` |
| `Variant Inventory Policy` | `deny` |
| `Variant Fulfillment Service` | `manual` |
| `Variant Price` | `0` |
| `Variant Taxable` | `FALSE` |
| `Image Src` | blank (decision 8) |
| `Genre (product.metafields.shopify.genre)` | genre handles, `; `-joined, in tag order |

`slug` = `catalog/core/handles.py:slugify` (same formula as today's tab).
Genre order: Libib reorders tags alphabetically, so "first genre" means
first alphabetically — acceptable (Option1 is a display label only).

### Client flow

1. Add each rental in Libib (conventions above). Note the date the batch
   started.
2. Libib: export **Barcodes** and **Library**.
3. In a fresh copy of the sheet: set **Added on or after**, import the two
   exports into their tabs.
4. Check `Problems`. Fix anything listed **in Libib**, then repeat 2–3.
   Continue when Problems has no held-back rows (warnings are fine).
5. Download `Shopify import` as CSV → Shopify **Products → Import**,
   **"Overwrite products with matching handles" unchecked**. The summary
   should be all *created* (any *skipped* = already imported earlier).
6. Retail Barcode Labels: print labels for the new products **using each
   variant's existing barcode** — never "generate barcodes" on rentals.
   Apply them.

## Verify first

1. **Retail Barcode Labels prints an existing barcode.** Confirm the app
   can print the variant's barcode as-is (not generate one), and which
   symbology it uses. A 13-digit Code 128 is wider than today's 8-digit
   label; `201…` numbers carry a valid EAN-13 check digit, so EAN-13 may fit
   better. Print one on his label stock and **scan it in Libib's Lending
   page** — one hit, right copy.
2. **POS channel.** Confirm a CSV-imported rental is *not* on Point of Sale
   (the floor-sale spec tests the opposite case with the same import). If
   it is, add a bulk "Exclude from sales channels → Point of Sale" step.
3. **Multiple copies.** Add a second copy to one Libib item: does the
   barcodes export list it as its own row with its own `201…` barcode, and
   what does its `created` show (the copy's date, or the item's)? If the
   item's, a later copy falls outside the date filter — then the client
   creates a new item per copy instead (decision 10 flips) or the filter
   drops the date and relies on handle-skip alone.
4. **Overwrite unchecked skips.** Re-import the same CSV with the box
   unchecked: existing handles skipped, not updated. (Shared with the
   floor-sale spec.)
5. **Large numbers survive the sheet.** Import a barcodes export with
   "Convert text to numbers" unchecked, download `Shopify import`, confirm
   `Variant Barcode` is the full 13 digits (not `2.01E+12`).

## Pipeline changes (developer side)

1. **Leave new-flow items out of the legacy Libib tooling.** `libib diff`
   joins on call number with a barcode fallback; a new `201…` item with a
   blank call number would show as an orphan before import and as drift
   that `fix` can't locate after. `diff`/`fix`/`sync` skip any Libib item
   whose barcode is 13 digits starting `201`, and any Shopify rental whose
   `Variant Barcode` is. Nothing writes into Libib for these items.
2. **Shopify-side enrichment may fill the poster only.** The TMDB picker /
   `apply` may set `Image Src` on new-flow rentals but must not change their
   title, description, Vendor or genre — those come from Libib. Add the
   guard in `apply`.
3. `audit`: flag a new-flow rental (201-barcode) that is taxable, on POS,
   unpublished, or whose handle doesn't end in its barcode.
4. `check-upload` gains a `rental` import shape (the 19 columns above):
   errors for a barcode that isn't 13 digits/`201`, handle not ending in it,
   unknown Vendor or genre, `Variant Taxable` not `FALSE`, price not `0`,
   qty not `1`, tag not exactly `Rental`, duplicate barcode or handle.
5. A Python twin of the sheet (`catalog/client_sheet/rental.py`:
   `libib_exports_to_rental_rows(barcodes, library, since)` → rows +
   problems) built on `catalog/libib/exports.py`, with fixtures and a seam
   test against a live-sheet export — same pattern as today's template.
6. Template files in `catalog/client_sheet/template/rental/`: formulas for
   `Problems` and `Shopify import`, a mappings CSV extended with formats,
   and the client guide.
7. Retire the combined sheet (`catalog/client_sheet/template/` root files
   and its `Libib import` tab) once both new sheets are live; update
   `CLAUDE.md` roadmap #3 and `CHECKLIST.md`.

## Open, not in this change

- **Retired copies** (decision 11): a reconcile report listing Shopify
  rentals whose barcode is no longer in Libib.
- **Legacy rentals on POS:** existing rentals are on the POS channel today.
  Remove them (one bulk action) to match decision 6? Not done here.
- **Cut-over:** when the last legacy Shopify rental is in Libib, the
  legacy `libib sync` path is retired. Track in `CHECKLIST.md`.
- **Curation tags** (e.g. `Criterion Collection`) on rentals: the fixed
  vocabulary currently rejects them. If wanted, add an allowed curation
  list that passes through to Shopify `Tags`.
