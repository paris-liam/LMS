# Client upload sheet — Shopify **and** Libib (design, 2026-10-01)

**Status 2026-10-02: built and tested.** Repo changes below are done; the
live-sheet steps and the end-to-end dry run (seam export, dev-store Shopify
import, throwaway Libib import) all passed. Two formula fixes came out of
pasting into real Sheets — see the notes in import-tab-formula.txt.

**Supersedes** `docs/superpowers/specs/2026-09-09-client-upload-template-rebuild-design.md`
for the sheet's end goal. That spec's Shopify half (10 fill columns, the
17-column import tab, handle rules, one product per physical copy) still
stands except where this doc changes it. Replaces checklist item 5 and folds
in items 4 and 14.

## Goal

The client adds new stock **without the pipeline**: one Google Sheet produces
both the Shopify import CSV and the Libib import CSV, and he does every import
himself. The automated pipeline (`audit`, `libib sync`) keeps running
occasionally alongside and must not fight his manual work. (An automated
upload system may be a later paid job; this sheet must not depend on it.)

## The client's flow

1. **Fill in `Add movies`** — one row per physical copy, as today. He pastes
   each poster's URL into Image URL **and downloads the image file**, saved
   under the movie's title (copies of one title share a poster).
2. **Shopify:** download the `Shopify import` tab → Products → Import. No
   barcodes exist yet.
3. **Barcodes:** create and print labels in Retail Barcode Labels, then type
   each copy's 8-digit barcode into the new **Barcode** column on
   `Add movies`, on that copy's row.
4. **Libib:** once every Rental row has a barcode, download the
   `Libib import` tab → Libib import with **Force Import Mode**.
5. **Libib, by hand, per item:** set the item's barcode (same number as its
   call number) and upload the downloaded image.

Floor Sale rows never reach the Libib tab.

## Decisions (2026-10-01)

| # | Decision |
|---|---|
| 1 | The client writes each barcode into the sheet after printing. |
| 2 | `libib sync` keeps running occasionally next to the manual flow. |
| 3 | Description and Image URL are **not required** on a client upload. |

## The one hard rule: Libib call number = barcode

Every piece of the Libib tooling joins Libib to Shopify on the call number,
which is always the 8-digit barcode (`catalog/libib/columns.py:import_row`,
`catalog/libib/diff.py`, `browser.py` searches `call:<barcode>`). `libib diff`
also falls back to Libib's barcode field when the call number is blank, but
`libib fix` can only find an item by call number, so a blank one is reported
as drift that needs a manual fix. The sheet therefore always writes the
barcode into `call_number`.

Why this keeps the manual and automated flows from fighting:

- A manually imported rental matches its Shopify product by call number, so
  `libib sync` never re-imports it (no duplicates).
- A rental imported with no description or poster (decision 3) is **not**
  blocked: `diff` only gates *new* imports on completeness. Once an item exists
  in Libib it is compared field by field, so when TMDB/the picker later fills
  the description or genre in Shopify, `libib sync` reports it as drift and
  `libib fix` writes it into Libib.
- The barcode he types must equal the Shopify variant's barcode (what Retail
  Barcode Labels assigned). If they differ, `diff` shows the Shopify product as
  missing and the Libib item as an orphan — visible, not silent.

Known gap: the poster check in `diff` only covers rentals the pipeline has
tracked (`libib-sync/_state.json`), so a manual item whose image he never
uploaded is not flagged. Acceptable for now; revisit if posters go missing.

## Sheet changes

### `Add movies` (fill tab): 10 → 11 columns

Add **K `Barcode`**, filled after printing (step 3). Format the column as
**Plain text** first — barcodes can start with 0 (`07530234`) and Sheets
strips the leading zero from a number. Data validation (reject input):
custom formula `=REGEXMATCH(TO_TEXT(K2), "^\d{8}$")`.

Rentals left without a barcode are the risk (a second Libib import of the
same batch duplicates items). Add a status cell above the data or in the
guide's checklist: `="Rentals missing a barcode: "&COUNTIFS(C2:C,"Rental",A2:A,"<>",K2:K,"")`
and tell him to import into Libib only when it reads 0.

### `Shopify import` (tab 2): 18 columns (was 17 — `Published` added 2026-10-02)

- **`Published` (after `Status`), added 2026-10-02:** `FALSE` on Floor Sale
  rows, `TRUE` otherwise — Floor Sale is sold at the counter only and must
  not be on the website. It controls the Online Store channel only; `Status`
  stays `Active` so POS can still sell the copy (Draft would hide it there
  too). `check-upload` fails a published Floor Sale or an unpublished Rental.
  Floor Sale products imported before this need a one-time unpublish
  (Products → filter tag `Floor Sale` → select all → Exclude from sales
  channels → Online Store).

- Still reads `A2:J` — the Barcode column is ignored, so the Shopify import
  never carries or clears barcodes.
- **Item 14:** Tags becomes `Type` + Extra tags only (no format or genre
  tags): `tags, MAP(typ, extra, LAMBDA(y, e, TEXTJOIN(", ", TRUE, y, e)))`.
- Re-importing this tab after barcodes exist is harmless to barcodes but does
  overwrite the products; the guide should say "import it once".

### `Libib import` (new tab 3)

Exactly the 26 `LIBIB_MOVIE_COLUMNS` in order (the same header the pipeline's
`import.csv` uses, so Libib's column matching is the one
`EXPECTED_MAPPINGS` already checks). One row per **Rental** row that has a
barcode. Values mirror `import_row` so the pipeline sees no drift:

| Libib column | Value |
|---|---|
| `title` | Title, whitespace collapsed |
| `description` | Description, whitespace collapsed (may be blank) |
| `tags` | `Format, genre-handles` — e.g. `VHS, drama; documentary` (same string as `expected_tags_string`: Vendor + the genre metafield) |
| `price` | `0` |
| `copies` | `1` |
| `call_number` | Barcode, as text |
| everything else | blank |

Sketch (to be finished and tested in Sheets):

```
=LET(
  raw, IFERROR(FILTER('Add movies'!A2:K, 'Add movies'!A2:A<>"",
                      'Add movies'!C2:C="Rental", 'Add movies'!K2:K<>""), ""),
  empty, COLUMNS(raw) = 1,
  … title / fmt / g1-g3 / descr / bc as in tab 2 …,
  ws,     LAMBDA(t, TRIM(REGEXREPLACE(TO_TEXT(t), "\s+", " "))),
  genres, (same as tab 2),
  tags,   MAP(fmt, genres, LAMBDA(f, g, TEXTJOIN(", ", TRUE, f, g))),
  header, {"title","creators","description", … 26 columns …},
  body,   HSTACK(MAP(title, ws), blank, MAP(descr, ws), blank×5, tags, blank×2,
                 konst("0"), blank×4, konst("1"), MAP(bc, LAMBDA(b, TO_TEXT(b))), blank×8),
  IF(empty, header, VSTACK(header, body))
)
```

### `mappings` and dropdowns (item 4 + review fixes)

- 15 genres (Special Interest, Anime added) — in the client's live sheet too.
- Genre dropdown range `mappings!A:A`, not `A1:A13` (the guide's range hides
  the two new genres).

## Repo changes

1. `catalog/client_sheet/template/`
   - `client-upload-template.csv`: add the `Barcode` column (example rows: one
     with a barcode, one Floor Sale without).
   - `import-tab-formula.txt`: item 14 tags line; note that K is ignored.
   - New `libib-tab-formula.txt`: the tab-3 formula + notes.
   - `client-upload-guide.md`: rewrite around the 5-step flow; remove the
     Supercycle section; description/image optional; barcode column as plain
     text; "import Libib only when missing-barcode count is 0"; Libib manual
     step (set barcode = call number, upload image); dropdown range fix;
     drop "not caught by anything" (point at `check-upload`).
   - Regenerate fixtures: `client-upload-template.expected.csv`,
     `sheet-export*.csv` (seam test), plus a Libib expected fixture.
2. `catalog/client_sheet/transform.py`: `FILL_COLUMNS` gains `Barcode`; tags
   per item 14; new `fill_rows_to_libib_rows()` built on
   `catalog/libib/columns.py:import_row` (so the sheet and the pipeline share
   one definition of a Libib row).
3. `catalog/client_sheet/check.py` (`check-upload`):
   - Accept a third shape, `libib` (the 26 columns): call number present,
     8 digits, unique in the file; title present; tags start with a known
     format.
   - Fill shape: Barcode, when present, is 8 digits and unique; a Rental with
     no barcode is a warning ("not in the Libib tab yet"), not an error.
   - Description / Image URL no longer reported as problems (decision 3).
   - Fix the stale "one of the 13" message and the `check.py:83` comment.
4. Tests in `tests/catalog/` for all of the above.
5. `CHECKLIST.md` items 4, 5, 14 and `CLAUDE.md` roadmap #3 point here.

## Then, in the client's live sheet (by hand)

Paste the new tab-2 and tab-3 formulas, add the Barcode column (plain text +
validation), the missing-barcode count, the two genres, and the dropdown
range. Then a dry run: one Rental + one Floor Sale through Shopify on the dev
store, and one Libib force import of a throwaway item, before he uses it for
real.

## Open, not in this change

- Floor Sale quantity column (checklist item 8's question for the client).
- Cross-checking the sheet's barcodes against Shopify's (would need a
  snapshot — a `check-upload --against runs/<latest>` option later).
