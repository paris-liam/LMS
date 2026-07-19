# Little Movie Store — product upload sheet: setup & fill guide

This sheet makes your product uploads land already-formatted in Shopify. You fill a few friendly columns; the sheet builds the exact import fields for you. You only ever ADD products with this sheet — edits and removals are done in the Shopify admin.

## One-time setup

1. **Import the scaffold.** In Google Sheets: File → Import → Upload `client-upload-template.csv` → "Replace spreadsheet". You'll get the header row and two example rows (Rushmore, Little Shop of Horrors).
2. **Add the hidden mapping tab.** Add a sheet named `mappings`. Paste this:

   | A (Genre) | B (handle) |   | D (Format) | E (handle) |
   |---|---|---|---|---|
   | Comedy | comedy | | VHS | vhs |
   | Action | action | | DVD | dvd |
   | Drama | drama | | Blu-Ray | blu-ray |
   | Kids & Family | kids-family | | 4K | 4-k |
   | Sci-Fi | sci-fi | | | |
   | Thriller | thriller | | | |
   | Horror | horror | | | |
   | Romantic Comedy | romantic-comedy | | | |
   | Musical | musical | | | |
   | Fantasy | fantasy | | | |
   | Documentary | documentary | | | |
   | Foreign | foreign | | | |
   | Holiday | holiday | | | |

   (Genre labels in `mappings!A2:A14`, handles in `B2:B14`; Format labels in `D2:D5`, handles in `E2:E5`.)
3. **Add dropdowns (Data → Data validation) on the helper columns:**
   - `Format` (col R): list from range `mappings!D2:D5`
   - `Genre 1/2/3` (cols S, T, U): list from range `mappings!A2:A14`
   - `Type` (col V): list of items `Rental`, `Floor Sale`
4. **Paste the formulas into row 2** of these columns, then select row 2 and drag the fill handle down as far as you need (formulas copy per row):

   | Column | Formula (in row 2) |
   |---|---|
   | D `Vendor` | `="Little Movie Store"` |
   | E `Product Category` | `="Media > Videos"` |
   | F `Tags` | `=TEXTJOIN(", ", TRUE, V2, S2, T2, U2, W2)` |
   | G `Status` | `="Active"` |
   | H `Option1 Name` | `="Title"` |
   | I `Option1 Value` | `="Default Title"` |
   | J `Variant Inventory Tracker` | `="shopify"` |
   | L `Variant Inventory Policy` | `="deny"` |
   | M `Variant Fulfillment Service` | `="manual"` |
   | P `Genre (…shopify.genre)` | `=TEXTJOIN("; ", TRUE, IFERROR(VLOOKUP(S2,mappings!$A:$B,2,FALSE),""), IFERROR(VLOOKUP(T2,mappings!$A:$B,2,FALSE),""), IFERROR(VLOOKUP(U2,mappings!$A:$B,2,FALSE),""))` |
   | Q `Media format (…shopify.media-format)` | `=IFERROR(VLOOKUP(R2,mappings!$D:$E,2,FALSE),"")` |

   (Columns A, B, C, K, N, O and the helper columns R–W are typed by hand — no formula.)

## Filling in a movie (per row)

Type into: **Handle**, **Title**, **Body (HTML)** (description), **Variant Inventory Qty** (copies, usually 1), **Variant Price**, **Image Src** (public image URL). Pick from the dropdowns: **Format**, **Genre 1** (and Genre 2/3 if it fits more than one genre), **Type**. Optionally type **Extra tags** (comma-separated, e.g. `Criterion Collection, A24`). (Holiday is a **genre** — pick it in a Genre dropdown, not here.)

Rules:
- **Type = Rental** → leave **Variant Price** at `0` (rentals are priced by membership, not a shelf price).
- **Type = Floor Sale** → enter the real sale **Variant Price**.
- **Handle** — keep it short, lowercase, hyphenated, **no commas** (e.g. `rushmore-vhs`). One handle per movie+format.
- Same movie in two formats = **two separate rows** (e.g. `rushmore-vhs` and `rushmore-dvd`).

The grey formula columns fill themselves — don't type in them.

## Exporting for import

1. Select columns **A through Q** only (Handle … Media format). Do NOT include the helper columns R–W (Format, Genre 1/2/3, Type, Extra tags).
2. Copy them into a new blank sheet → File → Download → **Comma-separated values (.csv)**.
3. In Shopify: **Products → Import → Add file** → upload that CSV → review → **Import products**.

## Adding new genres, formats, or tags

- **New genre:** add a row to `mappings` (label in col A, its metaobject handle in col B), then extend the `Genre 1/2/3` dropdown ranges to include the new row. Ask your developer for the exact handle of a new genre metaobject.
- **New format:** add a row to `mappings` cols D/E and extend the `Format` dropdown range.
- **New curation tag:** just type it into **Extra tags** (comma-separated). No setup needed.

## Notes
- Duplicates are OK — don't worry if you upload a movie twice; they're merged in a periodic cleanup pass.
- Rental copy counts and barcodes are handled later in Supercycle, not in this sheet.
