# Dev site audit checklist — 2026-08-28

Full review of `lms-sandbox-lutsfahz.myshopify.com` (working theme `140918915134`), covering homepage, header, footer, PDP, membership page, and events page. Verified against live Shopify admin data via Admin GraphQL (product/collection/metaobject queries) plus a diff of the live theme against this repo.

Legend: 🔴 P0 blocker · 🟡 P1 content gap · 🟢 P2 lower priority · ✅ checked, no action needed

---

## 🔴 P0 — functionally broken right now

- [x] **Membership signup is dead.** ~~The Supercycle Membership Plans app block on `/pages/membership` sources from the `plans` collection. Its only product, "LMS Annual Membership," is set to DRAFT status.~~ **Resolved 2026-08-28** — product set to Active by client, verified via Admin GraphQL.
- [x] **"New arrivals this week" (homepage) always renders empty.** Root cause: no product anywhere in the store carries the `new-arrival` tag (the `Rental` tag and `Videos` category were already correctly applied to ~2,996 products). **Resolved on dev 2026-08-28** — manually tagged 5 sample titles so the rail shows real content; full setup + client workflow + production steps written up in `claudedocs/lms-admin-instructions.md`. Follow-ups tracked there: build the dev-store auto-expiry Flow, run the same setup on production, revisit whether tagging should ever become automatic.
- [x] **4 footer nav links 404** (`4k-blu-ray`, `used-vhs`, `mystery-bags`, `rental-library`). **Decision 2026-08-28: not fixing now** — flagged for a deliberate review pass in `claudedocs/lms-admin-instructions.md` ("Footer links" section).

## 🟡 P1 — placeholder/test content visible to real visitors

- [x] **"Community Picks" (homepage) always renders empty despite 8 entries existing.** Root cause: every entry had the **Product** reference field unset — the section only counts a pick as shown once it resolves a product. **Resolved on dev 2026-08-28** — set the Product field + real quotes on 5 of the 8 entries; full breakdown + client instructions in `claudedocs/lms-admin-instructions.md`. 3 entries still incomplete (need Product set or should be deleted) and 1 stays in Draft — see that doc for which.
- [x] **Events section (homepage + `/pages/events`) shows placeholder content.** 3 `event` metaobjects exist; one placeholder ("sample event 1," dated 2026-08-31) is still upcoming and renders live. **Not fixed** (client will replace with real events) — client instructions for adding/removing events written up in `claudedocs/lms-admin-instructions.md`, including the note that the "audience" field is a display badge only, not an actual access gate.
- [x] **Footer "The Club" column**: all four links point to the same `/pages/membership` URL. **Not fixed** — flagged for review in `claudedocs/lms-admin-instructions.md` ("Footer links" section) rather than assumed.
- [x] **Footer social links use generic root URLs, not real handles** (TikTok, Threads). **Not fixed** — flagged for review in the same "Footer links" section.
- [x] **Header announcement bar** is enabled with one block, but `text` and `link` are both empty. **Found a real bug while writing this up**: the section's outer wrapper always renders (~15px top/bottom padding) regardless of whether the block inside has text, so there's currently a **visible blank strip at the top of every page**, not just an inert empty section. Client explainer + editing instructions + this caveat written up in `claudedocs/lms-admin-instructions.md`. Needs a content decision (real message vs. remove the section) — not fixed yet.
- [x] **Hero background image** (`Screenshot_2026-07-02_at_9.56.45_PM.png`) resolves fine on Shopify's CDN, but the filename suggests it may be a placeholder screenshot rather than finished art. **Not fixed** — flagged for review in the same "Footer links" section of `claudedocs/lms-admin-instructions.md`.

**P1 status: all items either resolved or explicitly flagged for review — closing out P1.**

## 🟢 P2 — worth checking, lower urgency

- [x] **Header had a trailing empty `_blocks` group** (`header-group.json`, block id `1780922431d9826574`) — no content, 50px custom height, leftover theme-editor scaffolding. **Fixed 2026-08-28** — pulled live theme to confirm no drift, removed the dead section from `sections/header-group.json`, pushed to dev (`--allow-live`). Confirmed harmless (no visible gap — it had zero real height since `section_height` was never set to `custom`), removed for cleanliness.
- [x] **`main-menu` and `customer-account-main-menu`** — verified via API once nav read scope was granted. **Found 2 real bugs, not yet fixed:**
  - `main-menu`'s **"Events" link points to `/pages/data-sharing-opt-out`** (the auto-generated privacy page) instead of `/pages/events`. Clearly a wrong-link mistake, not intentional. **Not fixed** — the fix mutation (`menuUpdate`) requires resubmitting the *entire* menu's item list in one call, and getting an item's type/resourceId wrong on that full-replace mutation risks wiping the menu. Safer as a 30-second manual fix: Admin → Online Store → Navigation → Main menu → click "Events" → repoint to Pages → events.
  - Footer's "Visit" column links twice to **`/pages/visit`, which doesn't exist as a page at all** (confirmed via Admin — no page with that handle). Both "Passyunk Ave, Philly" and "Hours & map" 404. Needs a real Visit page created, or repoint to wherever that content actually lives.
  - `customer-account-main-menu` (Orders, Profile) checked out fine.
- [x] **Supercycle membership block has `redirect_type: "custom"` with a blank `redirect_url`.** Not independently testable via API (requires a live browser session past the storefront password). Recommend manually clicking "Become a member" in the theme editor preview now that the plan product is Active, to confirm checkout behaves correctly. Not verified either way — flagged for manual QA.
- [x] `frontpage` (Home page) and `community-picks` collections confirmed **not referenced anywhere in the theme code** (`grep` across all `.liquid`/`.json` came back empty) — safe to ignore or delete as leftover Shopify-default/scaffolding collections. `new-arrivals` collection is real and now correctly wired (see New Arrivals section above).

## ✅ Checked and confirmed fine — no action needed

- [x] `all-movies` (1,739 products) and `online-store` (4 products) collections exist and are correctly referenced from the hero buttons.
- [x] `all-movies` collection correctly uses the `shop-all` theme template (infinite scroll, poster cards, vertical filters); `online-store` uses the plain default collection template.
- [x] Staff Picks section's "Full list →" CTA is **not** broken — it hardcodes a link to `all-movies?filter.p.tag=community-pick`; the section's `link` setting isn't used (only `link_label` gates whether the CTA renders).
- [x] Password/coming-soon page: pulled the live theme and diffed `templates/password.json` + `sections/coming-soon.liquid` against this repo — **byte-identical**. The generic "This store is password protected" page a visitor sees is Shopify's own pre-launch gate on an unlaunched dev store, rendered before the theme is invoked at all — not a theme bug.
- [x] **PDP has no add-to-cart, variant picker, or Supercycle Methods slot** — looks like a contract violation at first glance (CLAUDE.md requires reserving that slot), but it's a **deliberate, documented override** in `docs/superpowers/specs/2026-07-17-movie-product-template-design.md`: movies are in-store-only transactions by design; the Methods slot is explicitly deferred to "if online member-rental is ever wanted." No action needed.

## 📊 Reference data pulled during this audit (2026-08-28)

- Dev store total products: **6,050** (up from 12 test products on 2026-08-07 — see memory `dev-store-not-catalogue-source`, updated).
- `all-movies`: 1,739 products · `online-store`: 4 products · `plans`: 1 product (Draft) · `new-arrivals`: 0 · `community-picks`: 0 · `frontpage`: 0.
- `staff_pick` metaobject: 8 ACTIVE + 1 DRAFT, all missing their Product reference.
- `event` metaobject: 3 ACTIVE (2 past, 1 upcoming — all placeholder content).

## 🟢 Cart & product page pass (2026-08-28)

- [x] **Cart page** (`templates/cart.json`) and **default product page** (`templates/product.json`, used by retail/merch — movies use `product.movie.json` separately) both had a "You may also like" recommendation section (native Shopify product-list / product-recommendations). **Removed both** — confirmed movies were never purchasable anyway (no add-to-cart exists anywhere on the movie PDP or on `lms-product-card.liquid`, the card used everywhere movies are browsed), but the generic native product card used in these two recommendation slots *did* show a real price (checked: a sample Rental movie has a genuine $10.00 price on the product record, not $0.00 as the original design spec assumed) with no way to actually buy it — misleading, and not needed per direction. Pulled live theme to confirm no drift, edited both templates, pushed to dev.
- [x] Confirmed `lms-product-card.liquid` (used on homepage, all-movies, shop-all) has **no price and no add-to-cart** — by design, movies are pure link-through cards. Cart summary's accelerated/express checkout buttons are fine to keep — cart contents can only ever be retail items.
- [ ] **Operational risk flagged, not a code bug**: the default `product.json` template gives full add-to-cart + variant picker to *any* product assigned to it. Nothing in the theme prevents a movie from accidentally being left on this template instead of `product.movie` — since template assignment is being handled separately during upload, make sure it's an explicit, verified step, not an assumption.

## 🟢 Search page pass (2026-08-28)

- [x] **Fixed the same misleading-price issue found on cart/PDP, but couldn't just remove it here** — search results are a primary discovery path, and mix movies + retail in one grid, so the collection-page trick (whole-section poster-style toggle) doesn't apply. Added a per-item conditional in `sections/search-results.liquid`: Rental-tagged results now render the price-free `lms-product-card` (same card used on all-movies/shop-all), retail results keep the native card with price. Mirrors the exact pattern already used in `main-collection.liquid`. Verified no live drift before pushing; `shopify theme check` clean on the file.
- [ ] **Worth a decision, not fixed**: the header search icon is disabled (`show_search: false`). The only route to `/search` at all is a text link in the footer menu — easy to miss. Confirm this is a deliberate minimal/boutique choice, not an oversight, now that search results actually render correctly.

## 🟢 Remaining templates pass (2026-08-28)

- [x] **Fixed a real bug: default page template (`templates/page.json`) had a stray Supercycle Membership Plans app block embedded in it.** This is the template any page uses unless it has a dedicated one — including the still-missing "Visit" page once it's created, and any future generic content page. Every such page would've shown a random membership-signup widget at the bottom. Settings on the block looked like an earlier draft (white/black colors, "Select plan" label, different config than the real one on `page.membership.json`) — reads like leftover scaffolding from before the dedicated membership template existed. Removed it; pulled live theme to confirm no drift first, pushed the fix.
- [x] **404 page** (`templates/404.json`) had the same "You may also like"-style product recommendation section (native card with price) as cart/PDP. Removed for consistency with the "no recommendation sections, movies aren't purchasable" direction — flagging since this one wasn't explicitly called out before removing it.
- [x] `templates/page.contact.json` and `templates/list-collections.json` — both clean, standard native templates, nothing broken. `list-collections.json` isn't linked from any menu we've found, likely orphaned but harmless.
- [x] Blog/article templates — confirmed a default "News" blog exists with **zero articles**, not referenced anywhere in navigation. Unused scaffolding, no action needed.

## 🟢 Search & Discovery filter config review (2026-08-28)

- [x] **Can't verify live config via API** — Search & Discovery's filter setup isn't exposed through any public Admin GraphQL API (confirmed via Shopify's own docs), only manageable in Admin UI. Reviewed the theme code instead to determine ground truth for what needs to be enabled.
- [x] **Confirmed exactly 3 facets the theme actually depends on** (grepped every hardcoded `filter.p.*` reference): **Product vendor** (powers Format), **Genre** (`shopify.genre` metafield), **Product tags** (powers New Arrivals + Community Picks toggles). Documented precisely, with the code citations, in the production runbook's Phase 9.
- [x] **Corrected a stale instruction**: the original July 2026 plan doc said to enable a `shopify.media-format` metafield filter for Format — that predates the 2026-08-07 decision that moved format into Vendor, so it's now wrong and would show a broken empty facet if followed. Production runbook updated to the correct instruction (Product vendor filter, not the metafield).
- [x] **Found and fixed a real gap: the Community Picks filter toggle was silently broken.** It only appears once a product carries the `community-pick` **tag** — a separate mechanism from the `staff_pick` metaobject's Product reference fixed earlier in this audit. Zero products had this tag. Tagged the same 5 products used for the Community Picks fix. Updated `lms-admin-instructions.md`'s client steps to include this as an explicit step going forward — it's easy to miss since the homepage section works fine without it.
- [x] New Arrivals toggle: confirmed working now that 5 products carry the `new-arrival` tag from the earlier fix.

## Not yet audited
- [ ] Mobile-specific rendering (this audit was code + live-data only, no visual/browser pass)
