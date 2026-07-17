# Dedicated movie product template — design

**Date:** 2026-07-17
**Store target:** dev store (`lms-sandbox-lutsfahz.myshopify.com`), working theme `140918915134`
**Status:** approved design, ready for implementation plan

## Problem

Movies and retail products currently share one product template (`templates/product.json` →
`sections/product-information.liquid`), a stock Horizon PDP: media gallery, title, **price**,
divider, **variant picker labelled "Genre"**, **buy buttons (add-to-cart)**, description,
recommendations. For a movie this is wrong on every commercial affordance:

- Price renders **$0.00** (rentals are membership-based / in-store; not an online purchase).
- The variant picker exposes **"Genre" as a fake selectable variant** — one value, not a choice.
- Add-to-cart offers an **online purchase path that must not exist** for movies.
- The refined structured data (media format, genre, availability) is **not surfaced** anywhere.

Now that the catalogue is reformatted with clean structured data, movies need their own
purpose-built, **read-only** page.

## Decision summary (from brainstorming)

- **Dedicated template**, not conditional logic on the shared template. Retail is untouched.
- **Read-only page.** It shows: poster image, description, curated attribute chips, an in-stock
  indicator, and a notify-me-when-back capture. Nothing else — no price, no variant picker, no
  add-to-cart, no recommendations, no reviews.
- **All renting/buying happens in-store.** No online transaction path of any kind.
- **No Supercycle Methods-block slot.** This is a conscious, scoped override of the
  "reserve the Methods slot / keep a standard product form + single add-to-cart" rule in
  `CLAUDE.md`. It applies **only to this movie template**. If online member-rental is ever
  wanted, it is a separate, later template change.
- **Availability signal = Shopify inventory quantity now**, isolated behind a single swappable
  check so it can flip to the Supercycle signal (`scf.avf` / `supercycle.*` /
  `custom.*` uncommitted-inventory stand-in) later as a find-and-replace.
- **Notify-me = native Shopify capture now, automated send deferred.** A `{% form 'contact' %}`
  captures the customer email plus the movie's title/handle so submissions are real and
  reviewable today. The automated back-in-stock email is built later alongside the Supercycle
  availability work (currently deferred — Shopify Flow has no contact-form trigger).
- **Attribute chips = curated metafields, clickable.** Genre (`shopify.genre`) and Media format
  (`shopify.media-format`) render as chips. Internal tags (`Rental`, `Floor Sale`) are never
  shown. Each chip links into the shop-all "All Movies" catalogue with the matching facet.

## Refined movie data available (per product)

| Field | Source | Example |
|-------|--------|---------|
| Poster image | Product image (TMDB) | poster jpg |
| Title | `product.title` | Muppets Treasure Island |
| Synopsis | `product.description` (`Body HTML`, TMDB) | paragraph |
| Genre | `product.metafields.shopify.genre` | `kids-family` |
| Media format | `product.metafields.shopify.media-format` | `vhs` / `dvd` / `blu-ray` |
| Rental availability (future signal) | `product.metafields.scf.avf` | — |
| Tags (curation) | `product.tags` | `Kids & Family, Rental` |
| Inventory | `Variant Inventory Qty` | `1` |

## Architecture

### Files

- **`templates/product.movie.json`** — new product template. Movie/rental products are assigned
  to it in Admin (Products → Theme template → "movie"). Retail products stay on the default
  `product.json`, which is not modified.
- **`sections/main-movie.liquid`** — new, purpose-built section. Dedicated (not a stripped
  `product-information`) so the commerce affordances do not exist in the code at all and cannot
  be re-enabled from the theme editor.
- Existing `product.json` / `sections/product-information.liquid` — **unchanged.**

### Section layout (two-column, Horizon PDP conventions)

**Left — media:** poster via Horizon's media rendering (single-image gallery, zoom on).

**Right — details, stacked:**

1. **Title** — `h1` from `product.title`.
2. **Attribute chips** — Genre + Media format from the metafields, rendered as labelled chips.
   Each chip is a link into the shop-all "All Movies" catalogue with the matching facet applied
   (`?filter.p.m.shopify.genre=<value>` / `?filter.p.m.shopify.media-format=<value>`). Genre/
   format raw values are mapped to display labels (reuse the existing genre/format label mapping
   used elsewhere in the theme/pipeline where practical). Internal tags are excluded.
3. **Availability indicator** — "Available in-store" when `movie_in_stock`, "Currently out"
   otherwise. Visual treatment consistent with `lms-tokens.css` (sage = available, muted = out).
4. **In-store notice** — short line, e.g. *"Rent or buy this title in-store."*
5. **Notify-me** — renders **only when `movie_in_stock == false`**. A native
   `{% form 'contact' %}` with an email input and a hidden field carrying the movie title/handle
   (so the reviewer knows which title). Button: "Notify me when it's back." Shows the standard
   Shopify form success/error state.
6. **Description** — `product.description` (TMDB synopsis) as rich text.

No recommendations rail, price, variant picker, quantity, or buy buttons.

### The single swappable availability check

Exactly one place decides availability, at the top of `main-movie.liquid`, greppable and marked:

```liquid
{# STAND-IN: inventory qty now; swap to scf.avf / supercycle.* on install #}
{%- assign movie_in_stock = false -%}
{%- if product.available -%}{%- assign movie_in_stock = true -%}{%- endif -%}
```

Both the availability indicator and the notify-me visibility read `movie_in_stock`. Swapping to
the Supercycle signal later touches only this block.

### Data flow

```
product (assigned product.movie template)
  → main-movie.liquid
      → poster image
      → title
      → genre/format metafields → display-label map → chips (→ shop-all facet links)
      → movie_in_stock (STAND-IN: product.available) → indicator + notify-me gating
      → notify-me form (contact) → captures email + title/handle  [out of stock only]
      → description
```

## Error / edge handling

- **Missing metafield** (no genre or no format): omit that chip; never render an empty/broken chip.
- **Missing poster image**: fall back to Horizon's placeholder media (or brand placeholder).
- **Out of stock with no inventory tracking**: `product.available` reflects Shopify's own logic;
  the STAND-IN respects it. When later swapped to `scf.avf`, the same single block changes.
- **Notify-me form**: standard Shopify contact-form validation and success/error messaging; no
  custom backend. Empty/invalid email is handled by the native form.
- **Retail products**: unaffected — they never use this template.

## Testing / verification

- Assign a movie product to `product.movie` on the dev store; confirm the page renders poster,
  title, genre+format chips, availability indicator, description — and no price/variant/buy UI.
- In-stock product: indicator shows "Available in-store", notify-me hidden.
- Out-of-stock product (set inventory to 0): indicator shows "Currently out", notify-me visible;
  submit the form and confirm the submission (email + title/handle) appears in Shopify.
- Click a genre chip and a format chip; confirm each lands on the shop-all catalogue with the
  correct facet applied.
- Confirm a retail product still renders the normal `product.json` page unchanged.
- `shopify theme check` passes (watch full offense count vs baseline for translation-key regressions).

## Out of scope / deferred

- Automated back-in-stock email send (deferred with the Supercycle availability work).
- Swapping the availability signal to `scf.avf` / Supercycle (single-block change, later).
- Online member-rental via the Supercycle Methods block (separate template change if ever wanted).
- Retail template changes.
