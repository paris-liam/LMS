# Shop-all catalog page (sidebar filtering) — design spec

Date: 2026-07-10
Mockup reference: `docs/search-a.dc.html` ("Search · Direction A — The card catalog · sidebar filtering")

## Summary

Build a dedicated "Shop everything" catalog page for the LMS storefront: a sidebar-filtered product grid (Format, Genre, Boutique label, New arrivals, and Supercycle rental Availability), with a search box that hands off to the existing site-search flow. This targets the all-products collection only — every other collection page keeps its current horizontal-filter layout.

Supercycle is confirmed installed on the dev store (`lms-sandbox-lutsfahz.myshopify.com`); the Methods filter app block referenced below is a real, available integration point, not a future dependency.

## 1. Template & page architecture

- New alternate template: `templates/collection.shop-all.json`, assigned only to the "All products" collection via Shopify admin (collection → Theme template dropdown).
- Reuses `sections/main-collection.liquid` as-is (no section code fork needed) — only block settings differ from the default `collection.json`:
  - `filters` block: `filter_style: "vertical"` (Horizon's `blocks/filters.liquid` already supports this — no custom facet JS required).
  - `product-card` block replaced with a rendered `lms-product-card.liquid` snippet (see §4).
- Every other collection continues using `templates/collection.json` unchanged (horizontal filters, native block-based product card).

### Search box behavior

- The sidebar search input submits to the existing site-search flow (`/search?q=...`), reusing `predictive-search.js` and `sections/search-results.liquid` rather than building a second, parallel text-search/filter engine on the catalog page.
- Rationale: Search & Discovery facets (the `filters` block) filter *within* a fixed result set; they have no text-relevance search of their own. Full-text matching is a separate Shopify subsystem (search/predictive search), already wired up elsewhere in the theme.
- **Filter carryover**: active Format/Genre/Label/Availability filter params are appended to the `/search?q=...` redirect URL, so a customer's active filters persist into the search-results page. Both pages share the same vertical filter sidebar UI, so this is just param passthrough, not a UI rebuild.

## 2. Data model

New product metafields, following the existing `custom.*` convention already used by `lms-product-card.liquid` (`custom.format`, `custom.condition`, `custom.director`, `custom.rare`):

| Field | Type | Notes |
|---|---|---|
| `metafields.custom.genre` | List of single line text | Multi-value (a film can be Drama + Sci-Fi). Marked filterable, shows per-value counts. |
| `metafields.custom.label` | Single line text | Boutique label (Criterion, Arrow Video, 88 Films, Synapse, etc.) — one per product. Deliberately its own metafield, not a reuse of `product.vendor`. |
| `new-arrival` | Product tag | Manually applied/removed by staff as stock is shelved/ages out. |

`custom.format` and `custom.condition` (already in use) get the same admin treatment as the new fields: definitions marked "Filter on the product list" in Shopify Admin → Custom data → Products, then added as filter sources in the Search & Discovery app so they render as facets.

## 3. Sidebar filters & Supercycle Methods integration

- Format, Genre, and Boutique label render as native checkbox-with-count facets via the existing vertical `filters` block (`blocks/filters.liquid` + `snippets/list-filter.liquid`) — no custom JS.
- **New arrivals**: a Search & Discovery "Product tag" filter scoped to just the `new-arrival` tag value. Restyled with CSS so its single checkbox reads as a pill-toggle switch (per the mockup) — same underlying `<input type="checkbox">`, different skin. This is a deliberate visual deviation from a "true" boolean filter component.
- **Availability (Supercycle rental status)**: not a native Search & Discovery facet — it's Supercycle's own **Methods filter** app block, added as an additional block on the collection section and pointed at the section via its own "Collection section ID" setting (not part of the `filters` array).

  One-time admin setup against `collection.shop-all.json`:
  1. Confirm the Shopify Search & Discovery app is installed (already required for the existing horizontal filters elsewhere in the theme).
  2. In Admin → Settings → Custom data → Products → unstructured metafields, find `supercycle.methods`, add the definition (List of single line text), enable "Filter on the product list and in the Admin API" + "Use as a condition in smart collections."
  3. In the Search & Discovery app → Filters, add filter sources: **Rental availability** and **Supercycle Methods**. Save.
  4. In the theme customizer, open the shop-all collection page, use browser dev tools (Network tab) to trigger an existing filter request and copy the section ID from the request, per Supercycle's documented method.
  5. Add the **Methods filter** app block to the collection page's sidebar, paste in the copied section ID, configure which filter types to show (Membership, Calendar, or all).
  6. Hide the native "Rental availability" Search & Discovery checkbox rendering with scoped CSS — the Supercycle block becomes the sole UI for availability; Format/Genre/Label/New arrivals continue rendering through the native vertical filters block untouched.

- **Sidebar order** (top to bottom): Search input → Availability (Supercycle block) → Format → Genre → Boutique label → New arrivals toggle. Availability leads since it's the most decision-relevant facet for a rental-first shop.

## 4. Product grid, card, sorting, pagination

- The grid keeps `main-collection.liquid`'s existing `results-list` / pagination harness (infinite scroll wiring, `ref="cards[]"`, Section Rendering API compatibility) — only the inner card markup changes.
- Each `<li>` renders `{% render 'lms-product-card', card_product: product %}` in place of the native `content_for 'block', type: '_product-card'`. `lms-product-card.liquid` already exists and is wired to `custom.format`, `custom.condition`, `custom.director`, `custom.rare` — matches the mockup's poster-card ProductCard component out of the box.
- Because `lms-product-card` is a fixed-layout snippet (not block-based), the **grid density control** is disabled on this template's `filters` block settings (`enable_grid_density: false`) — there's no block-based card sizing for it to act on. Card sizing is fixed via CSS grid (`minmax(208px,1fr)`, per the mockup), not theme-editor-adjustable.
- **Pagination**: `enable_infinite_scroll: true` — auto-loads on scroll, no "Load more" button (deviates from the mockup's button, per explicit decision).
- **Sort**: native Horizon sort options as-is (Featured, Best selling, Price, Alphabetical, Date). Default sort set to "Date, new to old" — closest native equivalent to the mockup's "Just landed" label. No custom sort key.

## 5. Styling & edge cases

- Visual pass restyles the native `facets` / `list-filter` CSS classes to match `lms-tokens.css` (brick/sage/parchment palette, DM Mono labels, pill-style active-filter chips, checkbox styling per the mockup) rather than replacing the components — preserves the accessible drawer/keyboard/ARIA behavior Horizon already built.
- **Mobile**: uses the existing `filters-drawer` (`theme-drawer`) behavior already built into `blocks/filters.liquid` — no separate mobile design needed.
- **Zero results**: when combined filters (Format/Genre/Label/Availability) return zero products, mirror `search-results.liquid`'s existing empty-state fallback pattern (message + optionally an empty-state collection) rather than showing a bare "0 films" grid.

## Open items carried into implementation

- Exact CSS treatment for the New-arrivals toggle-styled checkbox and the Supercycle Methods block (to visually match the rest of the sidebar) is a styling detail to work out during implementation, not a blocking design question.
- The Supercycle admin setup steps in §3 are manual/admin-console work, not theme code — implementation should call these out explicitly as a runbook step, separate from the Liquid/CSS changes.
