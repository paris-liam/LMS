# Product data model audit — where product info lives today

**Date:** 2026-08-07
**Inputs:** `products_export_1.csv` (3,597 rows / 3,550 products — a **production** export), the dev store (`lms-sandbox-lutsfahz.myshopify.com`) via Admin GraphQL, and `theme/lms-redesign-v4/`.
**Purpose:** step back before finalising the client upload template — establish what the catalogue actually contains, what the theme actually reads, and where those two disagree.

---

## 1. Which store is which (corrects a stale assumption)

| | Dev `lms-sandbox-lutsfahz` | Production `p0wkgv-wy` |
|---|---|---|
| Product count | **12** (verified via Admin API 2026-08-07) | ~3,550 (per `products_export_1.csv`) |
| Contents | 2 Supercycle plans, 2 movies (`Deja Vu`, `Zack & Reba`), 8 "Rango" test merch products | the real catalogue |
| `shopify.genre` / `shopify.media-format` definitions | **exist** | not present in the export's column set |

**CLAUDE.md currently says "Source of truth = the dev store's current live products". That is no longer true** — the dev store holds 12 products, none of them the reformatted catalogue. The only artefact of the reformat work that still exists is the `data-cleanup/` pipeline plus this production export. Roadmap item #2 ("push the reformatted catalogue to production") therefore has no reformatted source to push; it has to be re-derived from the production export.

I did not authenticate against production for this audit (no writes, no reads) — everything about production comes from the CSV.

---

## 2. The 49 CSV columns, and what LMS does with each

The export uses Shopify's standard product-CSV layout. Grouped by role, with observed fill rate across the 3,550 products:

### Product-level identity

| Column | Fill | LMS usage today | Notes |
|---|---|---|---|
| `Handle` | 100% | URL + import key | One product per physical copy. One bad handle observed: `vhs` (title = *Basquiat*). |
| `Title` | 100% | PDP `<h1>`, card title | Movie title only, no format/edition suffix. |
| `Body (HTML)` | **31%** | PDP description | Some are wrong — LLM-filled. e.g. *Escape Clause* (a thriller VHS) is described as "an engaging board game". |
| `Vendor` | 100% | **de-facto media format** | 21 distinct values: `VHS` 2158, `DVD` 590, `Blu-Ray` 521, `BLU-RAY` 238, plus `4K`/`4k`/`Dvd`/`Unknown`/studio names. This is the only format signal in the live data. |
| `Product Category` | **4%** | intended smart-collection rule | Only **3 products** carry `Media > Videos`; only **1** of them is `Rental`. |
| `Type` | 0% | unused | Single non-empty value: `Supercycle Plan`. |
| `Tags` | 99% | scoping + genre + curation | See §3. |
| `Published` / `Status` | 100% | visibility | 121 unpublished, 98 draft. |

### Options & variants

| Column | Fill | Notes |
|---|---|---|
| `Option1 Name` | 100% | `Genre` (2,853) · `Condition` (669) · `Title` (28). **Three generations of data model coexist.** |
| `Option1 Value` | 100% | genre label, or `Standard` (Condition), or `Default Title`. Junk present: `50%`, `70%`, `F`, `#REF!`, `4K, Action`, `Romatic Comedy`. |
| `Option2 Name/Value` | 18% | `Serial Number` = `001A`/`002A` — the CircaOS/Supercycle serialized copies. |
| `Option3 *` | 0% | unused. |
| `Variant SKU` | 18% | only the CircaOS rows: `191-VHSSCP-001A` (675 distinct). |
| `Variant Barcode` | 100% | Two schemes: 8-digit Shopify/Retail-Barcode-Labels codes (majority) and the CircaOS SKU string reused as barcode. **22 duplicate barcodes.** |
| `Variant Price` | 100% | `0.00` on 1,062 (rentals); Floor Sale prices $3–$30. |
| `Variant Inventory Qty` | 100% | `1` on essentially all — one row = one copy. |
| `Variant Inventory Tracker/Policy/Fulfillment Service` | 100% | `shopify` / `deny` / `manual` — constant. |
| `Variant Grams` / `Weight Unit` / `Requires Shipping` / `Taxable` | 100% | `0.0` / `lb` / `true` / `true` — constant, meaningless for in-store rental. |
| `Variant Compare At Price`, `Unit Price *`, `Variant Tax Code`, `Cost per item` | 0% | unused. |
| `Gift Card` | 100% | `false`. |

### Media

| Column | Fill | Notes |
|---|---|---|
| `Image Src` / `Image Position` | **29%** | 1,045 products have a poster; 910 of those are Rentals. Extra images arrive as continuation rows (handle only, 47 such rows). |
| `Image Alt Text` | 14% | where present it's the SKU, not descriptive alt text. |
| `Variant Image` | 14% | CircaOS rows only. |

### Metafield columns present in the export

| Column | Fill |
|---|---|
| `Rental Availability (product.metafields.scf.avf)` — Supercycle | **0%** |
| `Genre (product.metafields.shopify.genre)` | **0%** |
| `Language version (product.metafields.shopify.language-version)` | 0% |
| `Media content type (product.metafields.shopify.media-content-type)` | 0% |
| `MPAA rating (product.metafields.shopify.mpaa-rating)` | 0% |
| `Target audience (product.metafields.shopify.target-audience)` | 0% |

Two things follow. First, **no structured product data exists on production at all** — every metafield column is empty across 3,550 products. Second, **`shopify.media-format` is not in the export's column set**, meaning that definition isn't enabled on production even though it is on dev and the theme reads it. A CSV import carrying `product.metafields.shopify.media-format` will auto-enable the standard definition, but that should be confirmed on a small test import rather than assumed.

### SEO

`SEO Title` / `SEO Description` — 0%.

---

## 3. Tags: the only structured-ish data that exists

31 distinct tags, doing three unrelated jobs at once:

**Scoping (mutually exclusive):** `Rental` (1,042) · `Floor Sale` (2,451). 0 products carry both; **57 carry neither**.

**Genre (duplicating what should be a metafield):** Comedy 817, Drama 624, Action 602, Thriller 392, Kids & Family 387, Sci-Fi 225, Horror 202, Romantic Comedy 82, Musical 64, Fantasy 49, Documentary 35, Foreign 17, Special Interest 8, Holiday 5. **42 products have no genre tag.**

**Format / curation:** `4K` 36, `Criterion Collection` 2, `A24` 1, `Chicago` 1, `Supercycle product` 2.

**Typos in live data** (each creates a silently separate facet value): `Romatic Comedy` (7), `Floorsale` (2), `Floor sale` (1), `Foor Sale` (1), `Sc-Fi` (1), `Horor` (1), `Kids & Famiy` (1), `Kids` (1), `4k` (1).

Tag matching in Shopify smart-collection rules is exact, so `Floor sale` and `Foor Sale` products fall out of any `tag = Floor Sale` collection.

---

## 4. What the theme actually reads

### `sections/main-movie.liquid` — the movie PDP (`templates/product.movie.json`)

Read-only PDP, no price / variant selector / add-to-cart / Methods slot (all transactions are in-store).

| Rendered element | Source |
|---|---|
| Poster | `product.featured_image` |
| Title | `product.title` |
| Genre chip → `/collections/all-movies?filter.p.m.shopify.genre=…` | `product.metafields.shopify.genre.value.first.label.value` + `.system.handle` |
| Format chip → `?filter.p.m.shopify.media-format=…` | `product.metafields.shopify.media-format.value.first.label.value` + `.system.handle` |
| "Available in-store" / "Currently out" | `product.available` — marked `{# STAND-IN: swap to scf.avf / supercycle.* #}` |
| Notify-me form | shown when out of stock; posts via `{% form 'contact' %}` |
| Description | `product.description` |

Both chips read **list metaobject-reference metafields and take only the first entry**. Extra genres are stored but never displayed on the PDP.

### `snippets/lms-product-card.liquid` — the poster card

Used by `main-collection`, `lms-new-releases`, `lms-shop-membership`.

| Element | Source | Status |
|---|---|---|
| Poster | `card_product.featured_image` | works |
| Title | `card_product.title` | works |
| Director line | `card_product.metafields.custom.director` | **definition does not exist** — never renders |
| Format badge | `card_product.metafields.custom.format`, falling back to `shopify.media-format` | `custom.format` **not defined**; fallback is empty on production |
| Condition badge | `card_product.metafields.custom.media_condition` | **definition does not exist** — never renders |
| "Rare" badge | `card_product.tags contains 'rare'` | works (lowercase `rare`; production has none) |

Verified against dev-store product metafield definitions (2026-08-07): the only `custom.*` product definition that exists is `custom.waitlist_emails`. Three of the card's six data points are wired to metafields nobody has created. (Two dev products carry unstructured `custom.year` / `custom.decade` / `custom.country` values — orphans from an earlier experiment, not read anywhere in the theme.)

### Collections and filters

- `all-movies` smart collection: `Category = Media > Videos AND tag = Rental` (per `docs/superpowers/plans/2026-07-15-rental-scoped-catalogue-and-filters.md`). Against production data that rule matches **1 product** — 1,042 are tagged `Rental`, but only 1 of them has the category set.
- `new-arrivals` smart collection: the same rules plus `tag = new-arrival`, kept current by Shopify Flow on product-created.
- Facets are configured in the **Search & Discovery** admin app, not in the theme; `blocks/filters.liquid` just renders `results.filters` generically. The PDP chip URLs assume facets named `filter.p.m.shopify.genre` and `filter.p.m.shopify.media-format` exist.

### Not read anywhere in the theme

`product.vendor` (movie surfaces), `product.type`, `Variant SKU`, `Variant Barcode`, price on movie products, `Product Category` (except indirectly via the smart-collection rule), and every `shopify.*` metafield other than `genre` and `media-format`.

---

## 5. Where the current upload template disagrees with reality

`data-cleanup/client-template/client-upload-template.csv` + guide, as of commit `9a58382`:

1. **`Vendor` is set to a constant `Little Movie Store`.** In the live catalogue Vendor *is* the media format, and `data-cleanup/genre_format_mapping.py` reads Vendor to derive format. Blanking it means new uploads lose the one format signal the existing 3,550 products carry, and the dedupe/reformat pass loses its input. Either keep format in Vendor, or accept that new rows are format-identifiable only via tag + metafield and update the pipeline accordingly. Worth an explicit decision.
2. **`Product Category` = `Media > Videos`** is correct and necessary (the `all-movies` rule depends on it) — but the existing 3,550 products don't have it, so the backfill is unavoidable regardless of the template.
3. **`Option1 Name` = `Genre`** matches the majority of production (2,853 products) and the Retail Barcode Labels templates. Consistent.
4. **`shopify.media-format` column**: the theme and template both use it; production's export doesn't show the definition as enabled. Verify with a small test import before handing the sheet over.
5. **No barcode column** is right — the Retail Barcode Labels app assigns on print. Note that 22 duplicate barcodes already exist in production.
6. **Genre delimiter `; ` with bare handles** was empirically confirmed on a dev-store export (Task 1 of the plan). That finding stands.
7. **`custom.director`** is not in the template and not defined in the store, yet the card is built to show it. If the director line is wanted, it needs a definition and a template column; if not, the card code should drop it.

---

## 6. Open items, ranked by what actually blocks the storefront

1. **Posters.** 71% of products have no image. The card and PDP are both poster-first; without images the catalogue page is a wall of placeholders. Biggest single gap.
2. **`Product Category` backfill** on ~3,547 products, or the `all-movies` / `new-arrivals` collections stay empty.
3. **Genre + media-format metafield backfill** — 0/3,550 populated; the PDP chips and both facets depend on them. Genre can be derived from the existing genre tag / Option1 value; format from Vendor.
4. **Decide `custom.*` card fields** — define `director` / `format` / `media_condition`, or remove them from `lms-product-card.liquid`. Currently the code claims data that structurally cannot exist.
5. **Tag normalisation** — 9 typo variants, 57 products with no scoping tag, 42 with no genre tag.
6. **Descriptions** — 31% filled and some factually wrong (LLM-generated). Needs a verification pass, not just a fill pass.
7. **Duplicate barcodes** (22) and the malformed `vhs` handle.
8. **Update CLAUDE.md** — the "dev store is the catalogue source of truth" line is stale.

---

## 7. Recommended shape for a movie product (proposal, for discussion)

Nothing here is decided; this is what the audit points toward.

| Field | Value | Why |
|---|---|---|
| Handle | `movie-format-type[-n]` | unique per copy; already the guide's rule |
| Title | movie title, no suffix | PDP h1 + card |
| Vendor | format (`VHS`/`DVD`/`Blu-Ray`/`4K`) | keeps continuity with 3,550 existing products and the pipeline — **decision needed** |
| Product Category | `Media > Videos` | required by `all-movies` |
| Tags | `Rental` \| `Floor Sale`, format label, genre labels, curation tags | scoping + fallback facets |
| Option1 | `Genre` = primary genre label | Retail Barcode Labels prints it |
| `shopify.genre` | `handle; handle` | PDP chip + facet (primary) |
| `shopify.media-format` | single handle | PDP chip + facet (primary) |
| Price | `0` rental / real price Floor Sale | |
| Inventory Qty | `1` | one row = one physical copy |
| Image Src | public poster URL | the highest-value field and the most-missing one |

**Redundancy is deliberate:** genre and format live in both a tag and a metafield. The metafield drives the PDP and facets; the tag is what the client can see and edit in the admin product list, and what smart-collection rules match on. Keeping both in sync is the sheet's job, not the client's.
