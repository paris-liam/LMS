# Client product-upload template — design

**Date:** 2026-07-16 (revised 2026-07-19 after client input)
**Roadmap item:** #3 in CLAUDE.md "Major next steps" — give the client a corrected upload sheet so his ongoing Google-Sheet imports land **already-formatted** (import-perfect), scoped for rental vs resale, with no reformat pass required afterward (only the periodic dedupe pass).

## Problem

The client uploads products by filling a Google Sheet and importing it straight into the **production** store. His current sheet (`current-sheet.csv`, 14 columns) produces products that diverge from the reformatted catalogue and require the `data-cleanup/` pipeline to fix. We want a template that emits canonical products directly, so the reformat step is unnecessary for his uploads. The sheet is **add-only** — editing/removing and bulk *updates* are separate procedures (admin UI and a separate import), not this template.

### How his current sheet diverges from import-perfect

Observed from `current-sheet.csv`:

| Field | Current behaviour | Import-perfect target |
|---|---|---|
| `Vendor` | holds the **format** (`VHS`) | fixed `Little Movie Store` + real `shopify.media-format` metafield |
| `Option1 Name` / `Value` | `Genre` / `Drama` (fake variant) | `Title` / `Default Title` + `shopify.genre` metafield |
| Genre | only a tag + the fake Option1 | canonical metaobject **handle(s)** in the genre metafield **and** kept as tag(s) |
| `Product Category` | missing | fixed `Media > Videos` |
| Data quality | free-text typos (`Kids & Famiy`, `Floorsale`), `Holiday` used as a genre | dropdown-validated canonical values |
| `Price` | `0` on every row | real price for Floor Sale; `0` for Rental |

(Handles are **not** on this list — see decision 8: we keep his handle convention.)

## Decisions (brainstormed 2026-07-16, confirmed with client 2026-07-19)

1. **Goal = import-perfect.** Uploads must be fully canonical on import; no reformat pass, only the periodic dedupe pass still runs (weekly before opening, ~monthly after).
2. **Rental vs non-rental = two explicit, mutually-exclusive tags:** `Rental` and `Floor Sale`. A title is only ever one or the other; moving between them is done by hand in admin, not via this sheet. Distinguished by a `Type` dropdown.
3. **Client supplies image + description himself** (no TMDB fill in this workflow). `Image Src` = a public URL he pastes (accepted as-is for now, despite some being fragile hotlinks); `Body (HTML)` = text he writes.
4. **Price:** Floor Sale rows carry a real price he enters; Rental rows stay `0` (priced via membership credits, not a Shopify price).
5. **No barcode column.** Rental per-copy serials (`191-…` / `LMS-NNNNNNN`) are created **inside Supercycle**, not via the product CSV — and one variant holds only one barcode while a title can have many copies. Commercial UPC declined; add later in admin if POS scanning is ever needed.
6. **Copies default to 1.** Rental copy-tracking is handled later in Supercycle; the sheet just sets `Variant Inventory Qty` (default 1, editable for Floor Sale stock).
7. **Genre is stored as the metafield (primary) AND kept as tag(s).** Browse/collections run off the `shopify.genre` metafield; the genre tag(s) ride along for continuity and future use.
8. **Handle = client-filled passthrough — keep his existing handle convention.** The sheet does **not** auto-generate handles. It's add-only; product updates are a separate import procedure that matches on the existing handle, so handles must stay under his control and stable. The guide recommends clean handles (no commas) but does not force them.
9. **Multi-genre supported.** A title may have any number of genres. Genre input is several validated columns (`Genre 1/2/3`, extensible); the `shopify.genre` metafield is a **multi-value list** of metaobject handles; each chosen genre also emits a tag.
10. **Extensible by the client.** Formats are VHS/DVD/Blu-Ray/4K and genres are the canonical 12 *for now*; the guide documents how the client adds a new genre/format (dropdown list + mapping tab) and new curation tags himself.
11. **`Special Interest` is dropped** — the client replaces it with a real existing tag/genre. Not in any dropdown.
12. **Approach A — Google Sheet with friendly input columns + formula-generated output columns.** The only approach that is both import-perfect and typo-proof for a non-technical filler.

## Architecture — the two-zone sheet

A **fill zone** (client edits) and a **generated zone** (formulas he never edits; exported and imported).

### Fill zone (client input)

| Column | Input | Notes |
|---|---|---|
| Handle | text | he keeps his handle convention (decision 8); guide recommends no commas |
| Title | free text | movie title |
| Format | dropdown | `VHS / DVD / Blu-Ray / 4K` |
| Genre 1 | dropdown | required; the 12 canonical genres |
| Genre 2 | dropdown | optional |
| Genre 3 | dropdown | optional (more columns can be added the same way) |
| Type | dropdown | `Rental / Floor Sale` |
| Price | number | real price for Floor Sale; `0` for Rental |
| Copies | number | default `1`; becomes Variant Inventory Qty |
| Image URL | text | public image URL |
| Description | text | product description |
| Extra tags (optional) | text | seasonal/curation tags, e.g. `Holiday`, `Criterion Collection`; comma-separated; client-managed allowed list in the guide |

### Generated zone (formula output → the import CSV)

| Column | Kind | Value |
|---|---|---|
| `Handle` | passthrough | Handle |
| `Title` | passthrough | Title |
| `Body (HTML)` | passthrough | Description |
| `Vendor` | fixed | `Little Movie Store` |
| `Product Category` | fixed | `Media > Videos` |
| `Tags` | formula | `{Rental\|Floor Sale}` + each non-blank genre label + each non-blank extra tag → `Rental, Comedy, Musical` |
| `Status` | fixed | `Active` |
| `Option1 Name` / `Option1 Value` | fixed | `Title` / `Default Title` |
| `Variant Inventory Tracker` | fixed | `shopify` |
| `Variant Inventory Qty` | passthrough | Copies |
| `Variant Inventory Policy` | fixed | `deny` |
| `Variant Fulfillment Service` | fixed | `manual` |
| `Variant Price` | passthrough | Price |
| `Image Src` | passthrough | Image URL |
| `Genre (product.metafields.shopify.genre)` | lookup + join | each genre label → handle, joined as a list (delimiter — see Open items) |
| `Media format (product.metafields.shopify.media-format)` | lookup | format label → handle |

This reproduces the `data-cleanup/` pipeline's output shape for the single-genre case, extended to a genre *list*. The metafield columns take the **plain metaobject handle string(s)** (e.g. `drama`) — confirmed for the single-value case; the multi-value list delimiter is the one thing to verify at build (Open items).

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

`Holiday` and other seasonal/curation labels are **not** genres — they go in **Extra tags**.

## Formula sketch (final formulas live in the guide)

- **Tags:** comma-space join of: the Type tag (`Rental`/`Floor Sale`), each non-blank genre **label** (`Genre 1/2/3`), and each non-blank extra tag.
- **Genre metafield:** `VLOOKUP` each non-blank `Genre N` against a hidden `mappings` tab, joined with the Shopify list delimiter.
- **Media format metafield:** single `VLOOKUP` against the same tab.
- **Fixed columns:** literal strings filled down. **Passthrough columns:** `=` reference to the matching fill column (Handle included).

## Open items to verify at build

- **Multi-value metafield CSV delimiter.** Confirm the exact separator Shopify's product-CSV import expects for a `list.metaobject_reference` metafield (e.g. `;` vs `,` vs a JSON-ish list), by exporting a hand-made multi-genre product from the store and reading its `Genre (…shopify.genre)` cell. The genre-join formula uses whatever that export shows. Verify on the **dev** store.

## Handle collisions

Handles are the client's responsibility (decision 8). Two rows with the same handle merge on Shopify import — acceptable, since duplicate handling is deferred to the periodic dedupe pass (weekly→monthly). The template does not prevent duplicates at fill time.

## Deliverables

Both under `data-cleanup/client-template/`:

1. **`client-upload-template.csv`** — the full column layout (fill zone + generated zone) with 2 worked example rows (one Rental single-genre, one Floor Sale multi-genre) demonstrating the transformation.
2. **`client-upload-template-guide.md`** — setup + fill instructions:
   - Set up the dropdowns (Format, Genre 1/2/3, Type) with the exact lists.
   - Create the hidden `mappings` tab (genre + format tables).
   - Paste the formula definitions (`Tags`, genre list, format lookup) into row 2 and fill down; Handle and the other passthroughs.
   - The per-row fill workflow.
   - Export: copy the generated-zone columns → new CSV → Shopify **Products → Import**.
   - **How to extend:** add a new genre or format (append to the dropdown list + the `mappings` tab), and add curation tags to the Extra-tags allowed list.

## Scope / non-goals

- **Production push of the reformatted catalogue** (roadmap #2) — separate, not covered here.
- **Duplicate prevention at upload** — out; handled by the periodic dedupe pass.
- **Product updates / edits / removals** — out; done in admin UI or a separate update-import procedure.
- **Supercycle item/serial creation** and **rental copy-tracking** — out; done in-app later.
- **TMDB auto-fill** — not part of the client workflow.
- No change to the `data-cleanup/` pipeline is required by this work; the template mirrors its output shape (extended for multi-genre).

## Testing / validation

No code/unit tests — the deliverable is a CSV + a guide. Validation is:
1. Fill the 2 example rows through the sheet's formulas and confirm the generated zone matches a known-good reformatted product row shape (compare against a pipeline `reformatted.csv` row).
2. Verify the multi-genre metafield delimiter (Open items), then do one real test import of the example CSV into the **dev** store (never production) and confirm: Vendor, Product Category, Option (Title/Default Title), the genre **list** + media-format metafields, tags (`Rental`/`Floor Sale` + genre labels + extra tags), price, inventory qty, image, description, and the client-provided handle all land correctly.
3. Confirm dropdown validation rejects a bad value (e.g. `Kids & Famiy`).
