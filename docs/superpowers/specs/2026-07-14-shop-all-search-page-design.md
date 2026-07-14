# Shop-All "Shop everything" Search Page — Design Spec

**Date:** 2026-07-14
**Supersedes:** the 2026-07-10 shop-all plan/spec/runbook (written against the old metadata model). This spec is the current source of truth.
**Mockup:** `docs/search-a.dc.html` — "Direction A — The card catalog · sidebar filtering".

## Goal

A dedicated **"Shop everything"** catalog page: a left **sidebar of filters** (search box, Format, Genre, Tags, New-arrivals toggle) beside a **poster-card grid** with active-filter chips, a result count, a sort control, and infinite scroll. It must match the mockup's look while reusing Shopify's native filtering rather than reimplementing it.

## Approach (chosen): reuse & reconcile

Build on the **existing committed shop-all implementation**, which is a Horizon **collection page** (native `main-collection` section + `filters` block, powered by Shopify Search & Discovery). All filter mechanics — facet checkboxes with counts, active-filter chips, "clear all", "+ N more" expander, AND-across-groups filtering, sort, result count — come from Horizon + Search & Discovery for free. We adapt the existing files to the **finalized 2026-07-14 metadata model** and polish styling to the mockup.

Everything is **gated to the shop-all template only** (`filter_style == 'vertical'` / `product_card_style == 'poster'` / `.facets--vertical` CSS scope), so no other collection page changes.

## Data & facet mapping

Sidebar controls map to the finalized model (metafields `custom.*`; label/curation as tags):

| Sidebar control | Source | Facet mechanism |
|---|---|---|
| **Format** | `custom.format` metafield | native metafield facet (real counts) |
| **Genre** | `custom.genres` metafield | native metafield facet (counts, "+ N more") |
| **Tags** | product tags | one **combined** native Product-tags facet showing `label-*`, `rare`, `staff-pick`, `holiday` together |
| **New arrivals** | `new-arrival` tag | same tag filter; its `new-arrival` value is rendered as a **switch** at the sidebar bottom and **suppressed** from the Tags list above |

**Tag-label prettify:** the combined Tags facet prettifies display labels in Liquid — strip a leading `label-`, replace `-` with spaces, title-case each word (`label-criterion` → "Criterion", `kino-lorber` → "Kino Lorber", `rare` → "Rare"). Underlying tag values/param names are untouched; only the visible label changes.

**Accepted divergences from the mockup** (decided during brainstorming):
- The mockup's dedicated "Boutique label" group becomes the generic **Tags** group (label-* mixed with curation tags), because native Search & Discovery cannot split tags into separate named facets by prefix. No custom prefix-grouping, no metafield revert.
- The mockup card's per-film **accent color** is a decorative flourish and is **out of scope**.

## Components (files, all reuse; gated to shop-all)

1. **`templates/collection.shop-all.json`** — alternate collection template. Settings: `filter_style: vertical`, `product_card_style: poster`, `enable_infinite_scroll: true`, search input on. Assignable to the catalog collection in admin.
2. **`sections/main-collection.liquid`** — poster-card render branch (`product_card_style == 'poster'` → `{% render 'lms-product-card' %}`), zero-result empty state, poster-grid CSS. Already present; keep/verify.
3. **`blocks/filters.liquid`** — vertical sidebar: carryover search form, facet restyle to LMS tokens, tag-label prettify, and the **New-arrivals switch** (special-render the `new-arrival` tag value + suppress it from the Tags list). Search box + restyle + pill CSS already present; add prettify + new-arrival extraction/suppression.
4. **`snippets/lms-product-card.liquid`** — 2:3 poster card: title, director, price, Format + `media_condition` badges, Rare (from `rare` tag). Already on the new model; no change expected.

## Non-code setup (admin runbook)

- **Search & Discovery filters:** enable filters for `custom.format`, `custom.genres`, and **Product tags**. **Remove** stale filters from the old plan if present: `custom.genre` (singular), `custom.label`, `custom.condition`.
- **Collection:** create/confirm the catalog collection (all products), assign the `collection.shop-all` template, set its **sort order to newest-first** (drives the "Just landed" default).
- **Tags on demo data:** the mock back-fill already applies `label-*`/`rare`/`staff-pick`; add a `new-arrival` tag to a few products so the toggle has something to filter.

## Intro copy (theme-editor editable)

Eyebrow "The shelves" · H1 "Shop everything" · one-line subtitle. The intro is composed of native Horizon **text blocks** in the template's heading section, so all three strings are **editable in the theme editor** (Customize → the shop-all collection → heading blocks) with no code change to update copy. The subtitle block ships with default copy — "Every format, every shelf, every note we've left. Browse without pressure." — that the client can overwrite inline; it is a default, not a hardcoded value. (The H1 may either be a literal text block or bound to `collection.title`; default to a literal "Shop everything" text block so it's editable independently of the collection's name.)

## Error / edge handling

- **Zero results:** filtered-to-empty shows the empty-state message, not a blank grid (native/existing branch).
- **Gating:** all changes activate only for the shop-all template; a normal `collection.json` page keeps the horizontal bar, native cards, no search box.
- **New-arrival de-dup:** the `new-arrival` value must appear only as the toggle, never also as a Tags checkbox.

## Testing / verification

No JS test framework exists; "tests" = `shopify theme check` (static lint) + manual QA on the pushed dev theme (`140918915134`, store `lms-sandbox-lutsfahz`):
1. Each facet (Format, Genre, Tags) filters the grid and shows real counts.
2. Active-filter chips, "Clear all", and "+ N more" work.
3. New-arrivals toggle reads as a switch and filters to `new-arrival` products; that value is absent from the Tags list.
4. Tag labels render prettified (e.g. "Criterion", not "label-criterion").
5. Sidebar search submits to `/search` carrying active filters; results page keeps them.
6. Zero-result state renders; infinite scroll appends pages.
7. Mobile: filters collapse into the drawer with the same controls.
8. A normal `collection.json` collection page is visually unchanged.

## Out of scope

Supercycle rental **Availability / Methods** filter (separate Supercycle track), card accent colors, "Load more" button (using infinite scroll), custom prefix-split label facet.
