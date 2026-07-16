# Client product-upload template — design

**Date:** 2026-07-16
**Roadmap item:** #3 in CLAUDE.md "Major next steps" — give the client a corrected upload sheet so his ongoing Google-Sheet imports land **already-formatted** (import-perfect), scoped for rental vs resale, with no reformat pass required afterward (only the periodic dedupe pass).

## Problem

The client uploads products by filling a Google Sheet and importing it straight into the **production** store. His current sheet (`current-sheet.csv`, 14 columns) produces products that diverge from the reformatted catalogue and require the `data-cleanup/` pipeline to fix. We want a template that emits canonical products directly, so the reformat step is unnecessary for his uploads.

### How his current sheet diverges from import-perfect

Observed from `current-sheet.csv`:

| Field | Current behaviour | Import-perfect target |
|---|---|---|
| `Vendor` | holds the **format** (`VHS`) | fixed `Little Movie Store` + real `shopify.media-format` metafield |
| `Option1 Name` / `Value` | `Genre` / `Drama` (fake variant) | `Title` / `Default Title` + `shopify.genre` metafield |
| Genre | only a tag + the fake Option1 | canonical metaobject **handle** in the genre metafield **and** kept as a tag |
| `Handle` | hand-built, contains commas (`…-floor-sale,-drama`) | clean, unique per movie+format |
| `Product Category` | missing | fixed `Media > Videos` |
| Data quality | free-text typos (`Kids & Famiy`, `Floorsale`), `Holiday` used as a genre | dropdown-validated canonical values |
| `Price` | `0` on every row | real price for Floor Sale; `0` for Rental |

## Decisions (settled during brainstorming 2026-07-16)

1. **Goal = import-perfect.** Uploads must be fully canonical on import; no reformat pass, only the periodic dedupe pass still runs.
2. **Rental vs non-rental = two explicit tags:** `Rental` and `Floor Sale`. Confirmed by tag frequency in the live export (925 `Rental`, 1,690 `Floor Sale`). Both types go through the same sheet, distinguished by a `Type` dropdown.
3. **Client supplies image + description himself** (no TMDB fill in this workflow). `Image Src` = a public URL he pastes; `Body (HTML)` = text he writes.
4. **Price:** Floor Sale rows carry a real price he enters; Rental rows stay `0` (priced via membership credits, not a Shopify price).
5. **No barcode column.** Rental per-copy serials (`191-…` / `LMS-NNNNNNN`) are created **inside Supercycle**, not via the product CSV — and one variant holds only one barcode while a title can have many copies, so serials can't live on the product row anyway. The commercial UPC was considered and declined; add it later in admin if POS scanning is ever needed.
6. **Genre kept as a tag** in addition to the metafield (metafield is the source of truth for the filter; the tag rides along to keep new uploads consistent with the existing catalogue's tag-based collections/curation).
7. **Approach A — Google Sheet with friendly input columns + formula-generated output columns.** The only approach that is both import-perfect and typo-proof for a non-technical filler.

## Architecture — the two-zone sheet

The sheet has a **fill zone** (the client edits) and a **generated zone** (formulas he never edits; this is what gets exported and imported).

### Fill zone (client input)

| Column | Input | Notes |
|---|---|---|
| Title | free text | movie title |
| Format | dropdown | `VHS / DVD / Blu-Ray / 4K` |
| Genre | dropdown | the 12 canonical genres (below) |
| Type | dropdown | `Rental / Floor Sale` |
| Price | number | real price for Floor Sale; `0` for Rental |
| Copies | number | default `1`; becomes Variant Inventory Qty |
| Image URL | text | public image URL |
| Description | text | product description |
| Extra tags (optional) | text | seasonal/curation tags, e.g. `Holiday`, `Criterion Collection`; allowed list documented in the guide |

### Generated zone (formula output → the import CSV)

| Column | Kind | Value |
|---|---|---|
| `Handle` | formula | slug(Title) + `-` + format slug → `terms-of-endearment-vhs` |
| `Title` | passthrough | Title |
| `Body (HTML)` | passthrough | Description |
| `Vendor` | fixed | `Little Movie Store` |
| `Product Category` | fixed | `Media > Videos` |
| `Tags` | formula | `{Rental\|Floor Sale}` + `, ` + genre label + optional extra tags → `Rental, Drama` |
| `Status` | fixed | `Active` |
| `Option1 Name` / `Option1 Value` | fixed | `Title` / `Default Title` |
| `Variant Inventory Tracker` | fixed | `shopify` |
| `Variant Inventory Qty` | passthrough | Copies |
| `Variant Inventory Policy` | fixed | `deny` |
| `Variant Fulfillment Service` | fixed | `manual` |
| `Variant Price` | passthrough | Price |
| `Image Src` | passthrough | Image URL |
| `Genre (product.metafields.shopify.genre)` | lookup | genre label → handle |
| `Media format (product.metafields.shopify.media-format)` | lookup | format label → handle |

This reproduces the `data-cleanup/` pipeline's proven output shape. The metafield columns take the **plain metaobject handle string** (e.g. `drama`) — confirmed, that's what the pipeline writes and imports successfully.

## Value mappings (source: `data-cleanup/genre_format_mapping.py`)

**Format label → `shopify.media-format` handle:**

| Label | Handle |
|---|---|
| VHS | `vhs` |
| DVD | `dvd` |
| Blu-Ray | `blu-ray` |
| 4K | `4-k` |

**Genre label → `shopify.genre` handle (the 12 canonical):**

| Label | Handle | Label | Handle |
|---|---|---|---|
| Comedy | `comedy` | Horror | `horror` |
| Action | `action` | Romantic Comedy | `romantic-comedy` |
| Drama | `drama` | Musical | `musical` |
| Kids & Family | `kids-family` | Fantasy | `fantasy` |
| Sci-Fi | `sci-fi` | Documentary | `documentary` |
| Thriller | `thriller` | Foreign | `foreign` |

Edge values:
- **`Special Interest`** — left out of the dropdown (maps to a blank genre metafield anyway). The filler picks the closest real genre or leaves Genre blank.
- **`Holiday`** — not a genre in the taxonomy. Goes in **Extra tags**, not Genre. So a holiday title = Genre `Drama` (or blank) + Extra tag `Holiday`.

## Formula sketch (final formulas live in the guide)

- **Handle:** lowercase the Title, replace any run of non-alphanumerics with a single `-`, trim leading/trailing `-`, append `-` + the format slug. (Google Sheets: `LOWER` + `REGEXREPLACE` + the format lookup.)
- **Tags:** join, comma-space, of: the Type tag (`Rental`/`Floor Sale`), the genre **label** (when Genre is non-blank), and each non-blank Extra tag.
- **Genre / Media format handles:** `VLOOKUP` against a hidden `mappings` tab holding the two tables above.
- **Fixed columns:** literal strings filled down.
- **Passthrough columns:** `=` reference to the matching fill column.

## Handle collisions

`slug(Title)-format` is unique per movie+format. Two rows that produce the same handle (the same movie+format entered twice) will **merge on Shopify import** — acceptable and expected, because duplicate handling is deliberately deferred to the periodic export → dedupe pass (per the CLAUDE.md upload decision). Distinct movies sharing a title+format (rare remakes) are also caught by that dedupe pass. The template does not try to prevent duplicates at fill time.

## Deliverables

Both under `data-cleanup/client-template/`:

1. **`client-upload-template.csv`** — the full column layout (fill zone + generated zone) with 2 worked example rows (one Rental, one Floor Sale) demonstrating the transformation.
2. **`client-upload-template-guide.md`** — setup + fill instructions:
   - Set up the three dropdowns (Google Sheets data validation) with the exact lists.
   - Create the hidden `mappings` tab (genre + format tables).
   - Paste the four formula definitions (`Handle`, `Tags`, genre lookup, format lookup) into row 2 and fill down.
   - The per-row fill workflow.
   - Export: copy the generated-zone columns → new CSV → Shopify **Products → Import**.
   - The Extra-tags allowed list.

## Scope / non-goals

- **Production push of the reformatted catalogue** (roadmap #2) is separate and not covered here.
- **Duplicate prevention at upload** is explicitly out — handled by the periodic dedupe pass.
- **Supercycle item/serial creation** is out — done in-app after the catalogue is fully cataloged.
- **TMDB auto-fill** is not part of the client workflow (he supplies image + description).
- No change to the `data-cleanup/` pipeline is required by this work; the template simply mirrors its output shape.

## Testing / validation

No code/unit tests — the deliverable is a CSV + a guide. Validation is:
1. Fill the 2 example rows through the sheet's formulas and confirm the generated zone matches a known-good reformatted product row (compare against a pipeline `reformatted.csv` row shape).
2. Do one real test import of the example CSV into the **dev** store (never production) and confirm: Vendor, Product Category, Option (Title/Default Title), genre + media-format metafields, tags (`Rental`/`Floor Sale` + genre), price, inventory qty, image, and description all land correctly.
3. Confirm dropdown validation rejects a bad value (e.g. `Kids & Famiy`).
