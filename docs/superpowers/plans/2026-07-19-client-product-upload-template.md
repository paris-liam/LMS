# Client Product-Upload Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Google-Sheet upload template (a scaffold CSV + a setup/fill guide) that lets the client's ongoing product uploads land import-perfect — canonical rental/resale movie products with no reformat pass needed.

**Architecture:** A single Google Sheet with **import columns** (some typed directly, some formula/fixed) plus a few **helper input columns** (validated dropdowns for Format / Genre / Type) that formulas transform into the exact Shopify import fields. We ship (1) `client-upload-template.csv` — the full sheet layout with 2 worked example rows, and (2) `client-upload-template-guide.md` — how to wire the dropdowns, the hidden mapping tab, the formulas, and the export→import workflow. No code, no `data-cleanup/` pipeline change; the template mirrors the pipeline's output shape.

**Tech Stack:** Google Sheets (data validation + `TEXTJOIN`/`VLOOKUP` formulas), Shopify product-CSV import, Shopify metaobject-reference metafields. No test framework — validation is by CSV parse-check + a dev-store test import.

**Spec:** `docs/superpowers/specs/2026-07-16-client-product-upload-template-design.md`

## Global Constraints

- **Dev store only.** All store operations target `lms-sandbox-lutsfahz.myshopify.com`. NEVER the production store `p0wkgv-wy.myshopify.com` unless explicitly instructed per-operation (CLAUDE.md).
- **Import-perfect:** only canonical values ship. Genre + media-format are **metaobject handles** taken from `data-cleanup/genre_format_mapping.py`.
- **Fixed column values (verbatim):** `Vendor` = `Little Movie Store`; `Product Category` = `Media > Videos`; `Variant Inventory Tracker` = `shopify`; `Variant Inventory Policy` = `deny`; `Variant Fulfillment Service` = `manual`; `Status` = `Active`.
- **BARCODE-DRIVEN REVISION (2026-07-24 — supersedes the original Option 1 / one-product-per-format design below):** The client prints shelf barcodes with Shopify's **Retail Barcode Labels** app; both templates (LMS: RENTAL, LMS: FOR SALE) print the **genre from Variant Option 1**. So (1) `Option1 Name` = `Genre` and `Option1 Value` = the **primary genre label** (= the Genre 1 dropdown, `=S2`), NOT `Title`/`Default Title`; (2) the sheet is **one row per physical copy** (Variant Inventory Qty always `1`), not one row per movie+format — copies stay separate at upload and are consolidated in a later dedup pass; (3) **format is a tag + `shopify.media-format` metafield, never Option 1**. Barcode column omitted — the app auto-assigns per product. Confirmed against production export (`products_export_1.csv`, 3,550 products): one-product-per-copy is the live reality; `shopify.genre` metafield is empty on 3,549/3,550, so genre backfill is roadmap-#2 reformat scope, not this template. See memory `barcode-driven-upload-model`.
- **VENDOR-FORMAT REVISION (2026-08-07 — supersedes the `Vendor` = `Little Movie Store` constraint and the `shopify.media-format` column everywhere below):** Media format lives in **`Vendor`**, not in a metafield. Rationale in `claudedocs/2026-08-07-product-data-model-audit.md`: Vendor already carries format on 3,274/3,550 production products (245 more need only a case fix, 31 have no format at all), whereas `shopify.media-format` is empty on all 3,550 and isn't even enabled on production. Vendor is also visible in the admin product list, so it can't silently drift the way an unseen metafield does. Consequences: (1) column D `Vendor` = the Format dropdown (`=Q2`), not a fixed string; (2) the `Media format (product.metafields.shopify.media-format)` column is **removed** — import range is now **A:P**, helpers **Q–V**; (3) the `mappings` tab keeps only the genre label→handle table; formats need no handle lookup; (4) theme reads `product.vendor`, gated by a `VHS,DVD,BLU-RAY,4K` whitelist so a real vendor name on a retail product never renders as a format badge — see `sections/main-movie.liquid` and `snippets/lms-product-card.liquid`; (5) the matching facet is the built-in **Product vendor** filter in Search & Discovery (`filter.p.vendor`), which must be enabled there. Genre is unaffected and stays on `shopify.genre` + tags.
- **TWO-SHEET REVISION (2026-08-07 — supersedes the single-sheet layout and the `Type` helper column below):** Ship **two** scaffolds, `client-upload-template-rental.csv` and `client-upload-template-floor-sale.csv`, identical except that rental hard-codes `Variant Price` = `0` and prefixes tags with `Rental`, while floor-sale takes a typed price and prefixes `Floor Sale`. The `Type` helper column is gone (constant per sheet). Two columns added: **`Year`** (helper — required for unambiguous TMDB matching; *The Thing* 1982 vs 2011) and **`Image Alt Text`** (import, formula `=IF(O2="","",B2&…&" poster")`, replacing the existing catalogue's SKU-as-alt-text). Import range is now **A:Q**, helpers **R–W** (`Format`, `Genre 1/2/3`, `Year`, `Extra tags`). Two supported workflows: **Path A** client fills everything and imports A:Q himself; **Path B** he leaves `Body (HTML)` / `Image Src` / `Image Alt Text` blank, exports the whole sheet, and the TMDB script fills them (it needs `Year`, strips the other helpers). **Confirmed against Shopify's CSV reference:** only `Title` is required (plus `Handle` for products with variants); omitted columns take defaults on new products — but a blank/omitted `Variant Inventory Tracker` means inventory is **not tracked**, which would make `product.available` permanently true and render `main-movie.liquid`'s out-of-stock state and notify-me form unreachable. Tracker/Policy/Fulfillment Service must therefore always ship together.
- **Two mutually-exclusive scoping tags:** `Rental` or `Floor Sale` (never both).
- **Genre:** metafield is primary; each chosen genre ALSO emits a tag in **label** form (`Comedy`, not `comedy`). Multi-genre = a **list** metafield (delimiter confirmed in Task 1) + one label tag per genre.
- **Handle: REVERSED 2026-08-07 — now auto-generated by formula**, not client-typed. `slug(title) + "-" + slug(format) + "-rental"|"-floor-sale"`, plus a `-n` suffix from `COUNTIFS` when the same title+format repeats in the sheet. Reason the column can't simply be dropped: Shopify auto-slugs an absent handle from Title, and **rows sharing a handle become one product with multiple variants**, so three copies of the same movie would silently merge into one product with one barcode — destroying the one-product-per-copy model. Two documented limits: non-ASCII titles degrade (`Amélie`→`am-lie`; escape hatch is to overwrite that single cell), and `COUNTIFS` sees only the current sheet, so a copy uploaded in a later batch collides and Shopify **updates** rather than creates. Mitigations: keep one running sheet per type, or let the Path-B script check handles against the live catalogue.
- **No barcode column.** Rental price = `0`; Floor Sale = a real price. `Copies` defaults to `1`.
- **Formats (for now):** VHS / DVD / Blu-Ray / 4K. **Genres (for now):** the canonical 12 + `holiday` = **13** (see value map). The guide MUST show the client how to extend both, plus the Extra-tags list.
- **Deliverables live under** `data-cleanup/client-template/`.

## Canonical value maps (source: `data-cleanup/genre_format_mapping.py`)

**Format label → `shopify.media-format` handle:** VHS→`vhs`, DVD→`dvd`, Blu-Ray→`blu-ray`, 4K→`4-k`.

**Genre label → `shopify.genre` handle (13, confirmed against store metaobjects 2026-07-19):** Comedy→`comedy`, Action→`action`, Drama→`drama`, Kids & Family→`kids-family`, Sci-Fi→`sci-fi`, Thriller→`thriller`, Horror→`horror`, Romantic Comedy→`romantic-comedy`, Musical→`musical`, Fantasy→`fantasy`, Documentary→`documentary`, Foreign→`foreign`, Holiday→`holiday`.

(`holiday` is a real genre metaobject used by 3 products — it is a GENRE here, not an Extra tag. Use `kids-family`, not the stray `family` metaobject, 1 product, flagged for separate cleanup. `thriller-suspense`/`crime-mystery` metaobjects exist but are unused — omitted.)

**Genre metafield list format (Task 1 finding):** semicolon-space-delimited bare handles, e.g. `musical; comedy; horror` (NOT a JSON array).

## Sheet column layout (locked — used by Tasks 2 & 3)

*(Updated by the 2026-08-07 vendor-format revision.)* Columns **A–P are the import columns** (contiguous, so export = "select A:P"). Columns **Q–V are helper inputs**, excluded from export.

| Col | Header | Kind | Value / source |
|---|---|---|---|
| A | `Handle` | typed | client's handle (his convention) |
| B | `Title` | typed | movie title |
| C | `Body (HTML)` | typed | description |
| D | `Vendor` | formula | media format `=Q2` *(vendor-format revision — was fixed `Little Movie Store`)* |
| E | `Product Category` | fixed | `Media > Videos` |
| F | `Tags` | formula | Type + format + genre labels + extra tags (`=TEXTJOIN(", ", TRUE, U2, Q2, R2, S2, T2, V2)`) |
| G | `Status` | fixed | `Active` |
| H | `Option1 Name` | fixed | `Genre` *(barcode revision — was `Title`)* |
| I | `Option1 Value` | formula | primary genre label `=R2` *(barcode revision — was `Default Title`)* |
| J | `Variant Inventory Tracker` | fixed | `shopify` |
| K | `Variant Inventory Qty` | typed | `1` (one row per physical copy) |
| L | `Variant Inventory Policy` | fixed | `deny` |
| M | `Variant Fulfillment Service` | fixed | `manual` |
| N | `Variant Price` | typed | real price / 0 for rental |
| O | `Image Src` | typed | public image URL |
| P | `Genre (product.metafields.shopify.genre)` | formula | genre handles joined (Task-1 delimiter) |
| Q | `Format` | helper dropdown | VHS/DVD/Blu-Ray/4K *(also feeds D `Vendor`)* |
| R | `Genre 1` | helper dropdown | 13 genres (required) |
| S | `Genre 2` | helper dropdown | 13 genres (optional) |
| T | `Genre 3` | helper dropdown | 13 genres (optional) |
| U | `Type` | helper dropdown | Rental / Floor Sale |
| V | `Extra tags` | typed | comma-separated curation tags |

---

### Task 1: Verify the multi-value `shopify.genre` metafield CSV format

**Why a task:** the spec's one open unknown. A `list.metaobject_reference` product metafield has a specific delimiter in Shopify's product-CSV export (commonly `;`, but unconfirmed). Every genre cell in Task 2 and the genre-join formula in Task 3 depend on the real value. Get it from a real export, not a guess.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-19-client-product-upload-template.md` (record the finding in this task)

**Interfaces:**
- Produces: `GENRE_DELIM` (the exact separator string) and whether list values are metaobject **handles** or **GIDs**, consumed by Tasks 2 and 3.

- [ ] **Step 1: Check the documented format**

Invoke the `shopify-plugin:shopify-custom-data` skill (or `shopify-plugin:shopify-dev`) and confirm how a `list.metaobject_reference` metafield (`shopify.genre`) is represented in a **product CSV import/export** — specifically the value delimiter and whether each entry is a metaobject handle or a `gid://…` reference. Note the documented answer.

- [ ] **Step 2: Confirm empirically on the dev store**

On `lms-sandbox-lutsfahz.myshopify.com` (dev only): find or set an existing rental movie to have **two** genres in its `shopify.genre` metafield (Admin → a product → Metafields → Genre → add a second value). Then **Admin → Products → Export → Current page → CSV**. Open the exported CSV and read the `Genre (product.metafields.shopify.genre)` cell for that product.

- [ ] **Step 3: Record the finding**

Documented result (Step 1, 2026-07-19): a web-doc claimed CSV list metafields must be a JSON array — **this was contradicted by the real dev-store export** (below). The store's actual export/import format is authoritative.

**FINDING (Task 1), confirmed by dev-store export 2026-07-19:**
```
GENRE_DELIM = "; "   (semicolon + space)
Entry form = handles (NOT gids, NOT JSON array)
Is shopify.genre a LIST metafield (accepts multiple)? yes
Multi-value cell observed: action; family; holiday; sci-fi; documentary; horror; fantasy; drama; foreign; musical; romantic-comedy; thriller; kids-family; comedy; thriller-suspense; crime-mystery
Single-value cell observed: crime-mystery
```
Consequences: Task 3's genre formula is `TEXTJOIN("; ", TRUE, <vlookup handles>)` (bare handles, semicolon-space separated); Task 2's example column-P values are `comedy` (single) and `musical; comedy; horror` (multi). Export↔import round-trips, so Task 4 confirms import acceptance.

**Also revealed:** the store has **16 genre metaobjects**, not the pipeline's 12 — extras `holiday`, `family`, `thriller-suspense`, `crime-mystery`, plus an apparent `family`/`kids-family` duplicate. The canonical dropdown list is a human decision (see the taxonomy question resolved before Task 3); all 12 pipeline handles remain valid.

- [ ] **Step 4: Commit the finding**

```bash
git add docs/superpowers/plans/2026-07-19-client-product-upload-template.md
git commit -m "docs: record multi-value shopify.genre CSV delimiter finding"
```

---

### Task 2: Create the template scaffold CSV

**Depends on:** Task 1 (`GENRE_DELIM`).

**Files:**
- Create: `data-cleanup/client-template/client-upload-template.csv`

**Interfaces:**
- Consumes: `GENRE_DELIM` from Task 1 (used in row 2's column P).
- Produces: the scaffold CSV the guide (Task 3) references and Task 4 imports. Columns exactly A–W from the locked layout.

- [ ] **Step 1: Write the CSV file**

Create `data-cleanup/client-template/client-upload-template.csv` with the header row (all 23 columns A–W in order) and the two example rows below. Replace `;` in the two column-P values with the confirmed `GENRE_DELIM` if it differs.

Row 1 — Rushmore (Rental, single genre). Row 2 — Little Shop of Horrors (Floor Sale, multi-genre, real price):

```csv
Handle,Title,Body (HTML),Vendor,Product Category,Tags,Status,Option1 Name,Option1 Value,Variant Inventory Tracker,Variant Inventory Qty,Variant Inventory Policy,Variant Fulfillment Service,Variant Price,Image Src,Genre (product.metafields.shopify.genre),Media format (product.metafields.shopify.media-format),Format,Genre 1,Genre 2,Genre 3,Type,Extra tags
rushmore-vhs,Rushmore,"When a beautiful teacher arrives at Rushmore Academy, precocious student Max Fischer falls for her and into rivalry with a gruff industrialist for her affection.",Little Movie Store,Media > Videos,"Rental, Comedy",Active,Title,Default Title,shopify,1,deny,manual,0,https://example.com/posters/rushmore-vhs.jpg,comedy,vhs,VHS,Comedy,,,Rental,
little-shop-of-horrors-blu-ray,Little Shop of Horrors,"A meek flower-shop worker discovers a mysterious, blood-hungry plant that promises fame and fortune at a monstrous price.",Little Movie Store,Media > Videos,"Floor Sale, Musical, Comedy, Horror",Active,Title,Default Title,shopify,1,deny,manual,19.99,https://example.com/posters/little-shop-of-horrors-blu-ray.jpg,musical; comedy; horror,blu-ray,Blu-Ray,Musical,Comedy,Horror,Floor Sale,
```

- [ ] **Step 2: Validate it parses and columns are consistent**

Run:
```bash
python3 -c "import csv; rows=list(csv.reader(open('data-cleanup/client-template/client-upload-template.csv'))); w=len(rows[0]); assert w==23, w; assert all(len(r)==w for r in rows), [len(r) for r in rows]; print('OK', len(rows)-1, 'example rows,', w, 'columns')"
```
Expected: `OK 2 example rows, 23 columns`

- [ ] **Step 3: Spot-check the transformation is internally correct**

Run:
```bash
python3 -c "
import csv
rows=list(csv.DictReader(open('data-cleanup/client-template/client-upload-template.csv')))
r=rows[1]
assert r['Vendor']=='Little Movie Store'
assert r['Product Category']=='Media > Videos'
assert r['Option1 Name']=='Title' and r['Option1 Value']=='Default Title'
assert r['Tags']=='Floor Sale, Musical, Comedy, Horror'
assert r['Media format (product.metafields.shopify.media-format)']=='blu-ray'
assert set(p.strip() for p in r['Genre (product.metafields.shopify.genre)'].split(';'))=={'musical','comedy','horror'}, r['Genre (product.metafields.shopify.genre)']
print('transformation OK')
"
```
Expected: `transformation OK`

- [ ] **Step 4: Commit**

```bash
git add data-cleanup/client-template/client-upload-template.csv
git commit -m "feat: client upload template scaffold CSV with worked examples"
```

---

### Task 3: Write the setup + fill guide

**Depends on:** Task 1 (`GENRE_DELIM`), Task 2 (the scaffold exists and is referenced).

**Files:**
- Create: `data-cleanup/client-template/client-upload-template-guide.md`

**Interfaces:**
- Consumes: the locked column layout, the value maps, `GENRE_DELIM`.
- Produces: the client-facing instructions. Nothing downstream depends on it.

- [ ] **Step 1: Write the guide**

Create `data-cleanup/client-template/client-upload-template-guide.md` with exactly these sections and content (substitute the confirmed `GENRE_DELIM` for `;` in the Genre formula):

````markdown
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
````

- [ ] **Step 2: Validate the guide is internally consistent with the scaffold**

Run:
```bash
python3 -c "
import csv
hdr=next(csv.reader(open('data-cleanup/client-template/client-upload-template.csv')))
guide=open('data-cleanup/client-template/client-upload-template-guide.md').read()
for h in ['Genre (product.metafields.shopify.genre)','Media format (product.metafields.shopify.media-format)','Tags','Variant Price','Image Src']:
    assert h in hdr, ('missing header', h)
for token in ['mappings','TEXTJOIN','A through Q','Little Movie Store','Media > Videos','Default Title']:
    assert token in guide, ('guide missing', token)
print('guide/scaffold consistent')
"
```
Expected: `guide/scaffold consistent`

- [ ] **Step 3: Commit**

```bash
git add data-cleanup/client-template/client-upload-template-guide.md
git commit -m "docs: client upload template setup + fill guide"
```

---

### Task 4: Dev-store acceptance import

**Depends on:** Tasks 2 & 3.

**Why a task:** proves the scaffold actually imports into Shopify and lands every field canonically — the real acceptance test. Dev store only.

**Files:** none (validation + optional cleanup).

- [ ] **Step 1: Build the import-only CSV**

The scaffold has helper columns R–W that must not be imported. Produce an import-only copy (columns A–Q):
```bash
python3 -c "
import csv
rows=list(csv.reader(open('data-cleanup/client-template/client-upload-template.csv')))
out=[r[:17] for r in rows]  # A-Q
csv.writer(open('/private/tmp/claude-501/-Users-liamparis-web-projects-personal-LMS-sandbox/84a40ad9-5d1e-48d1-92b1-8d80dda2c293/scratchpad/client-template-import-test.csv','w')).writerows(out)
print('wrote import-only CSV, cols:', len(out[0]))
"
```
Expected: `wrote import-only CSV, cols: 17`

- [ ] **Step 2: Import into the DEV store**

On `lms-sandbox-lutsfahz.myshopify.com` (dev only — confirm the store before importing): **Products → Import → Add file** → upload the scratchpad `client-template-import-test.csv` → review → **Import products**.

- [ ] **Step 3: Verify both products landed canonically**

Open each imported product (Rushmore, Little Shop of Horrors) in Admin and confirm:
- Vendor = `Little Movie Store`; Product category = `Media > Videos`.
- Single variant titled `Default Title` (no `Genre`/`Condition` option).
- **Metafields:** `shopify.genre` = `comedy` (Rushmore) / the three genres `musical, comedy, horror` as a **list** (Little Shop); `shopify.media-format` = `vhs` / `blu-ray`.
- Tags: `Rental, Comedy` / `Floor Sale, Musical, Comedy, Horror`.
- Price: `0` (Rushmore) / `19.99` (Little Shop). Image loaded from the URL. Description present. Handle matches.

Record PASS/FAIL per field. If the multi-genre metafield did **not** land as a 3-value list, the delimiter from Task 1 is wrong — fix the Task 2 column-P value and the Task 3 Genre formula, re-run Tasks 2–4.

- [ ] **Step 4: Clean up the test products**

Delete the two test products from the dev store (Admin → Products → select both → Delete) so they don't pollute the catalogue. (They import with real handles; remove them.)

- [ ] **Step 5: Commit any fixes**

If Step 3 required changes to the scaffold or guide, commit them:
```bash
git add data-cleanup/client-template/
git commit -m "fix: correct client upload template after dev-store acceptance import"
```
If no fixes were needed, skip this step.

---

## Self-review notes

- **Spec coverage:** two-zone sheet (Tasks 2/3), value maps (constraints + Tasks 2/3), multi-genre list (Task 1 + Tasks 2/3/4), handle passthrough (layout col A, guide), two scoping tags (Tags formula), Floor Sale price / Rental 0 (guide rules + example rows), no barcode (absent from layout), copies default 1 (col K), extensibility (guide "Adding new…"), deliverables under `data-cleanup/client-template/` (all tasks), dev-only + acceptance import (Task 4). Verify-at-build delimiter → Task 1.
- **No pipeline change** required — confirmed; template only mirrors output shape.
