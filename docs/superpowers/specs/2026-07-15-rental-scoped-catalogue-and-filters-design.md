# Rental-scoped catalogue, New Arrivals, and inventory-page filters — Design Spec

**Date:** 2026-07-15
**Source requirements:** `Updated search and homepage for produc.md` (repo root)

## Goal

1. Only Rental-tagged, `Media > Videos`-category movies should appear on browse surfaces (homepage, inventory/search page).
2. A "New Arrivals" concept — Rental movies uploaded in the last 7 days — drives both a homepage rail (10 items + "+N more") and a toggle filter on the inventory/search page.
3. The inventory/search page exposes exactly four filter criteria: New Arrivals toggle, Community Picks toggle, Format checkboxes, Genre checkboxes (format/genre OR within group, toggles AND across groups). Everything else currently on that page not in this list goes away.

## Context established during brainstorming

- The "All Movies" smart collection (`all-movies` handle) already powers the hero's "Browse the shelves" button and is the base collection for the shop-all/search page (`templates/collection.shop-all.json`). It's a smart collection with a single rule (`Category = Media > Videos`, `appliedDisjunctively: false`), currently 2,526 products.
- 925 of 2,675 total store products carry the `Rental` tag. Non-rental movies are titles pulled out of Supercycle and sold as plain in-store/POS products (per CLAUDE.md's 2026-07-15 Supercycle rental-only-via-Membership confirmation) — they're legitimate products, just not part of the online rental browse experience.
- The catalogue reformat pipeline (`data-cleanup/`) populates Shopify's **standard** metaobject-reference metafields `product.metafields.shopify.media-format` and `product.metafields.shopify.genre` — not the `custom.format`/`custom.genres` fields the existing shop-all filters (`blocks/filters.liquid`, built 2026-07-14) were wired to. Confirmed live via Admin API: `custom.format`/`custom.director`/`custom.media_condition` are `null` on reformatted products; `shopify.media-format`/`shopify.genre` hold real metaobject-reference values. (The homepage product card, `snippets/lms-product-card.liquid`, already had this fixed in a prior session — this spec applies the same fix to the search-page facets.)
- Shopify has no native way to filter by relative date (e.g. "created in the last 7 days") in smart collections or Search & Discovery facets. A stable tag, kept in sync by automation, is required to make "New Arrivals" a real toggle filter (not just a homepage-render-time computation).
- `staff_pick` is a metaobject (product-reference field, quote, staff name) used for the homepage's editorial "Community Picks" cards. Metaobject references aren't filterable by Search & Discovery, so a parallel product tag is needed to make it a toggle filter.
- Known transient state: the whole catalogue was bulk-imported 2026-07-14/15, so nearly every Rental product will show as a "new arrival" for the first week after this ships. Expected, self-corrects, not a bug.

## Design

### 1. Movie-catalogue scoping

Add a `tag = Rental` rule to the existing "All Movies" smart collection (admin-only change, no code). Rules AND together already (`appliedDisjunctively: false`), so the collection becomes `Category = Media > Videos AND tag = Rental` (~925 products). This collection is already the base for the hero button and the shop-all/search page, so both are scoped for free.

Non-rental movie PDPs remain reachable by direct link (not blocked/404'd) — they're simply absent from collection-driven browse surfaces (homepage rail, inventory/search grid). Individual PDP templates are not modified by this spec.

### 2. New Arrivals

- **Flow A** (event-triggered): on product create → add tag `new-arrival`.
- **Flow B** (scheduled, daily): find products where `tag:new-arrival` AND `created_at` is more than 7 days ago → remove the tag.
- **New smart collection "New Arrivals"**: rules `Category = Media > Videos` AND `tag = Rental` AND `tag = new-arrival`, sort newest-first. This is the single source of truth for both the homepage rail and the inventory-page toggle target.

### 3. Community Picks tag

Staff manually adds a `community-pick` tag to a product whenever they create its `staff_pick` metaobject entry (two manual steps at pick-creation time; no automated sync). The metaobject remains the source for editorial content (quote, staff name) shown on the homepage; the tag exists purely to make the pick filterable on the inventory page. Sync between the two is a documented workflow convention, not code-enforced.

### 4. Homepage "New Arrivals" section

Repurpose `sections/lms-new-releases.liquid` (rename during implementation as appropriate):

- Data source becomes the "New Arrivals" smart collection (replaces the current merchant-picked `collection` setting — that setting goes away).
- Render first 10 products via the existing `lms-product-card` grid.
- "+N more" button: `collection.products_count | minus: 10`, rendered only when `products_count > 10`; hidden entirely otherwise. Replaces the current "Browse all →" button.
- Button links to the shop-all/search page with the New Arrivals toggle pre-set via URL param (exact param name confirmed against `filters.liquid` during implementation planning, e.g. `filter.p.tag=new-arrival`).
- Empty state: keep the section's existing onboarding placeholder-card fallback for when the New Arrivals collection is briefly empty.

### 5. Inventory/search page filters (`blocks/filters.liquid`)

- **Format checkboxes**: repoint from `custom.format` to `product.metafields.shopify.media-format` (list.metaobject_reference; Search & Discovery filters natively on metaobject-reference metafields, using each entry's `label`/`displayName` as the visible checkbox text with real counts).
- **Genre checkboxes**: repoint from `custom.genres` to `product.metafields.shopify.genre`, same mechanism.
- **New Arrivals toggle**: already scaffolded as a switch on the `new-arrival` tag from the 2026-07-14 work — becomes functionally real once Flow A/B (above) maintain the tag. Verify end-to-end wiring; no new UI code expected.
- **Community Picks toggle**: new switch, mirroring the New Arrivals switch pattern, keyed on the `community-pick` tag; suppressed from any generic tag listing the same way `new-arrival` is.
- **Remove the generic Tags facet** (`label-*`/`rare`/`staff-pick`/`holiday` checkbox group) entirely — not among the four required filters, and `staff-pick` is superseded by the Community Picks toggle.
- AND/OR semantics come from Search & Discovery natively: Format values OR within the group, Genre values OR within the group, toggle groups AND against everything else and each other. No custom filter logic needed.
- Search input and sort control are unchanged (out of scope for the "only these 4 filters" requirement — that requirement is read as scoped to filter criteria specifically).
- Base collection for this page stays "All Movies" (now Rental-scoped per §1), so every filter combination operates within the Rental+Media>Video universe automatically.

## Edge cases

- **Product recommendations** (`sections/product-recommendations.liquid`, Shopify's native algorithmic engine) are not Rental-scoped — Shopify's recommendation engine doesn't support collection restriction. A non-rental movie could theoretically appear as a "You may also like" on a rental movie's PDP. Accepted as a known gap for this spec (see Deferred work).
- **Zero New Arrivals**: homepage falls back to its existing empty/placeholder state; the search-page toggle returns zero results via the existing empty-state handling in `main-collection.liquid`.
- **List-typed metafields**: `shopify.media-format`/`shopify.genre` are list type (one value in practice, per the reformat pipeline design) — native facet rendering already handles list values correctly; no special-casing needed.
- **Legacy rows never touched by the reformat pipeline**: correctly excluded from browse since the collection rule keys on tag presence, not on data completeness.

## Testing / verification

No JS test framework in this repo. Verification = `shopify theme check` (no new offenses beyond the known baseline: 9 offenses / 2 pre-existing Supercycle `JSONMissingBlock` errors) + manual QA on the pushed dev theme (`140918915134`, store `lms-sandbox-lutsfahz`):

1. "All Movies" collection count drops from 2,526 → ~925 after the rule change; hero button and search page both reflect it.
2. New Arrivals Flow: new/duplicated product gets tagged `new-arrival`; a backdated or aged test product loses the tag via the daily cleanup Flow.
3. Homepage rail: ≤10 cards; "+N more" shows only when `products_count > 10` with correct count; links land on the search page with the New Arrivals toggle already active.
4. Community Picks toggle: tagging a product `community-pick` makes it appear when the toggle is on; untagged products don't.
5. Format/Genre facets: non-zero checkbox counts matching real catalogue data.
6. Generic Tags facet no longer renders on the shop-all sidebar.
7. AND/OR behavior: Format + Genre selections narrow correctly; adding a toggle further ANDs.
8. Zero-result and zero-new-arrivals states render existing empty-state UI, not a blank page.

## Deferred work (explicitly out of scope for this spec, to revisit later)

- Automating `community-pick` tag sync with the `staff_pick` metaobject (currently a manual two-step convention).
- Scoping `product-recommendations` (native Shopify recommendations on the PDP) to Rental-only.
- Supercycle Methods-block / availability filtering (separate track per CLAUDE.md; blocked on Supercycle app-block mounting).
- Any change to the individual product page template itself beyond what already exists.
- Search box / sort control behavior on the inventory page (unchanged by this spec).
