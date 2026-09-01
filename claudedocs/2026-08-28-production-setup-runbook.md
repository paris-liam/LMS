# Production setup runbook — starting from a blank store

Assumed production (`p0wkgv-wy.myshopify.com`) had **no theme content, no collections, no metaobjects, and no Supercycle setup** — turned out to be only partly true (see Status note below). Assumes you are handling product upload + formatting + assigning the `product.movie` template **separately** — this runbook doesn't touch product data itself, only the store structure those products plug into.

This is a living planning document, updated as phases are executed — production is off-limits by default per this project's rules, and nothing here gets executed without explicit go-ahead on a specific phase.

Order matters — collections and theme sections reference tags/metaobjects/pages that need to exist first. Follow top to bottom.

**Status as of 2026-09-01**: Production was NOT a true blank slate — it already had 4 collections (2 empty junk, 1 empty wrong-handle, `plans` with a real Supercycle-typed product in it), empty stub pages (`about`, `plans`, `membership` all with no content), a working nav skeleton, and Shopify-standard metafield definitions (no `custom.*` stand-ins yet). Supercycle also appears to already be installed (a "Little Movie Club" product with productType "Supercycle Plan" sits in `plans`), which contradicts the "blocked until install" assumption elsewhere — **investigation deferred** pending an Admin access issue on the client's end. Phases 0, 2, 3, and parts of 5/6 are done; Phase 4 (Collections) and Phase 7 (Supercycle) remain deferred — Phase 4 until the catalogue exists, Phase 7 until Supercycle's Admin UI is reachable again.

---

## Phase 0: Theme code — done 2026-09-01

1. Confirmed the live theme (`164180295930`, renamed to "LMS Theme w/ coming soon page" but same ID as CLAUDE.md's record) — still running the **pre-migration Horizon 3.5.1 base** with only the coming-soon page, tokens, and fonts. None of the full redesign (homepage sections, movie PDP, events, membership) had ever been pushed.
2. Given the scale of the diff (essentially every file, since production predates the 4.1.1 migration), reconciling file-by-file wasn't practical — pushed the full current `lms-redesign-v4` theme to a **new unpublished theme** instead: `LMS Redesign v4 (review)` (`#166751961338`). Preview: `https://p0wkgv-wy.myshopify.com?preview_theme_id=166751961338`.
3. **Not published live** — collections, metaobjects, and Supercycle setup still need finishing first, or sections will render empty/broken exactly like we found on dev.
4. Three unrelated unpublished themes found on production (`lms-7.8` ×2, `LMS-Theme-7.19`) — confirmed as old test pushes, left alone.

---

## Phase 1: Product tag structure (reference only — you're handling upload separately)

The theme code depends on these tags/fields existing on every movie product. Just documenting the contract here so upload formatting matches what the theme expects:

- **`Rental` tag** — required on every rentable movie. Powers the `all-movies` collection, the New Arrivals collection, and the PDP genre/format chips.
- **Category = Videos** — the Shopify standard product taxonomy category. Required alongside `Rental` for the same collections.
- **`product.vendor` = one of `VHS` / `DVD` / `Blu-Ray` / `4K`** — format lives in Vendor, not a metafield (see CLAUDE.md's data-model convention). The PDP and filters read this against a fixed whitelist.
- **`shopify.genre` metafield** — standard category metafield, `list.metaobject_reference` type, populated automatically once Category = Videos is set and a genre value is chosen.

  **Known gotcha, hit 2026-09-01 on the first real CSV upload (126 products, 74 failed with "Value require that you select a metaobject")**: dev's exports use several genre values (`action`, `comedy`, `thriller`, `romantic-comedy`, `musical`, `foreign`, `holiday`) that are legitimate Shopify taxonomy values but weren't yet instantiated as local `shopify--genre` metaobject entries on production — only the canonical Shopify-seeded set was (`Action & adventure`, `Humor & comedy`, etc., which dev's actual data doesn't use). CSV import can't auto-create a missing metaobject entry, so any product using one of those 7 values fails outright. **Fixed by creating all 7 entries on production directly via `metaobjectCreate` (type `shopify--genre`), matching dev's exact handle/label/`taxonomy_reference` GID.** If a future batch introduces yet another genre value dev has that production doesn't, it'll fail the same way — check dev's `shopify--genre` metaobjects against production's before a big import, not after.
- Two tags applied **manually, ongoing** (not part of bulk upload): `new-arrival` and `community-pick` (see Phases 6 and 8 below).

---

## Phase 2: Metafield definitions — done 2026-09-01

Movie-specific metafield definitions (the `custom.*` stand-ins for future Supercycle fields, plus any others `data-cleanup/` relies on). The script itself needs a raw admin token (`SHOPIFY_ADMIN_TOKEN` or client credentials) which wasn't available this session, so the same 9 `metafieldDefinitionCreate` mutations were run directly via `shopify store execute` (CLI OAuth) instead — same result, script kept as-is for future runs where a token is available:

```bash
SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-movie-metafield-definitions.sh
```
Requires `SHOPIFY_ADMIN_TOKEN` or `SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET` env vars (older auth pattern this script uses, distinct from the CLI's own OAuth session). Idempotent — safe to re-run.

Also found an unexplained pre-existing metafield definition on production, `scf.avf` ("Rental Availability", single-line text, only 1 product uses it) — not from any of our scripts, not Supercycle (`supercycle.*`). Trivial usage, left alone; flag for cleanup during the catalogue-reconciliation pass.

---

## Phase 3: Metaobject definitions — done 2026-09-01

Two content types need their definitions created before any entries can exist.

1. **Community Pick** (`community_pick`) — script: `scripts/create-community-pick-metaobject.sh`.
   Creates fields: `product` (product reference), `quote` (multi-line text), `staff_name` (single-line text, labeled "Community Name"), `staff_link` (URL, labeled "Community Link"). Storefront access must be Public Read.

   **Renamed from `staff_pick` on 2026-09-01**: that handle was reserved by another application on production (an old test definition from earlier work, which stays reserved even after deletion). Both dev and production were moved to `community_pick` so the theme code stays identical across stores — dev's 9 existing entries were migrated in place, the old `staff_pick` definition was deleted on dev, and `sections/lms-staff-picks.liquid` now reads `shop.metaobjects.community_pick.values`. Created on production 2026-09-01, no entries yet.

2. **Event** (`event`) — created directly via Admin GraphQL on production 2026-09-01, matching dev's live definition exactly:
   - `name` — single-line text
   - `description` — single-line text
   - `audience` — single-line text, with choices restricted to `["public", "member"]`
   - `link` — URL
   - `date` — date

   Storefront access: Public Read. Publishable capability enabled — the theme only renders Active entries. No entries yet on production.

---

## Phase 4: Collections — partly done 2026-09-01

1. **All Movies** (`all-movies`) — **done 2026-09-01**. Smart collection created matching dev exactly: Category = Videos AND tag = Rental, sort Newest-to-oldest, `templateSuffix: shop-all` (the infinite-scroll/vertical-filters template — easy to miss, dev had it, production needed it set explicitly). 0 products until the catalogue lands.
2. **Online Store** (`online-store`) — **not created**, deliberately skipped for now. Smart collection: tag = `online-store`. This is the non-rental retail catalogue (merch, snacks, etc. — anything sold outright, never touches Supercycle).
3. **New Arrivals** (`new-arrivals`) — **done 2026-09-01**. Same rule as the script (`create-new-arrivals-collection.sh`) but run directly via `shopify store execute` since the script needs a raw admin token: Category = Videos AND tag = Rental AND tag = new-arrival, sort Newest-to-oldest. See `claudedocs/lms-admin-instructions.md` for the full New Arrivals mechanism and the Flow that needs building alongside this (Phase 6).
4. **Plans** (`plans`) — already existed on production before this runbook started (manual collection, 1 product — "Little Movie Club", productType "Supercycle Plan"). No action needed, ties into the still-unresolved Supercycle question (Phase 7).
5. **Optional curation collections** — a script already exists for three tag-driven merchandising collections, not required for any core section to function, create only if wanted:
   ```bash
   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-curation-collections.sh
   ```
   Creates: Staff Picks (`staff-picks`, tag `staff-pick`), Rare Finds (`rare-finds`, tag `rare`), Holiday Movies (`holiday-movies`, tag `holiday`).
6. **Footer/nav collections currently missing even on dev** — `4k-blu-ray`, `used-vhs`, `mystery-bags`, `rental-library` are linked from the footer but don't exist anywhere yet (flagged in `claudedocs/lms-admin-instructions.md`). Decide whether these are wanted before launch; create them (smart, by format/condition tags) if so.

---

## Phase 5: Pages

Page records need to exist with the right handle + template assignment for the theme's page templates to apply:

| Page | Handle | Template | Status |
|---|---|---|---|
| Membership | `membership` | `membership` | **Done 2026-09-01** — page existed but on the default template; reassigned to `membership`. Still needs real content (hero copy + perks, see `templates/page.membership.json`). Nav's old "Plans" link (pointing at an empty, now-deleted `plans` page) was retargeted here. |
| Events | `events` | `events` | **Done 2026-09-01** — created, empty body (template-driven, matches dev). Added to main-menu. |
| Contact | `contact` | `contact` | Already existed, correct template — no action needed |
| Visit | `visit` | *(none exists — default page template)* | **Still doesn't exist.** Needs real address/hours copy before creating — deferred, footer links to `/pages/visit` still 404 |
| ~~Plans~~ | ~~`plans`~~ | — | **Deleted 2026-09-01** — was an empty stub duplicating membership's role; nav retargeted to `/pages/membership` instead |
| ~~About~~ | ~~`about`~~ | — | **Deleted 2026-09-01** — empty stub, unreferenced in any nav |

`/pages/data-sharing-opt-out` ("Your Privacy Choices") is auto-generated by Shopify's own privacy/consent settings, not something to create manually — it'll appear once relevant regional privacy settings are configured.

---

## Phase 6: Navigation menus

Three menus needed, matching dev's structure (fix the two bugs found there, don't copy them):

1. **Main menu** (`main-menu`): production currently has Home, Contact, Membership (retargeted from the deleted `plans` page), and Events (**done 2026-09-01**). Rental Library and Shop links still need to be added once the `all-movies`/`online-store` collections exist with real products (Phase 4, deferred). Consider whether "Join the Club" belongs in the main nav too.
   - Also fixed the same bug on **dev**: its Events link pointed at `/pages/data-sharing-opt-out` (the privacy page) instead of `/pages/events` — corrected 2026-09-01.
2. **Footer menu** (`footer`): Search, Privacy Choices (auto-links once the privacy page exists) — production already has both, no action needed.
3. **Customer account main menu** (`customer-account-main-menu`): Orders, Profile — standard, already correct on production, no custom setup needed.

---

## Phase 7: Supercycle app

1. Install the Supercycle app on production (separate installation from dev — app installations are per-store).
2. Configure the **Membership** method only — item-based credits, allowance = 1 movie at a time, unlimited/same-day swaps. **No Calendar, no Subscription, no Resale** — confirmed out of scope entirely (see CLAUDE.md).
3. Create the membership plan product (mirror dev's "LMS Annual Membership" — $100/yr, whatever credit/quota config was finalized on dev). Set it to **Active** status before launch — this was the exact bug that made membership signup dead on dev.
4. Add the plan product to the **Plans** collection (Phase 4, item 4) — check whether Supercycle auto-creates and auto-populates this collection when the plan is created, or whether it needs manual assignment.
5. **The Membership Plans app block on `/pages/membership` needs to be manually re-added in the theme editor on production.** The block reference baked into `templates/page.membership.json` (`shopify://apps/supercycle/blocks/membership-plans/7b3228ed-...`) is tied to the specific Supercycle **installation** on dev — that exact block ID will not resolve against a different store's Supercycle install. Pushing the JSON as-is will likely show a broken/missing app block. Fix: in the theme editor on production, add the Supercycle Membership Plans app block fresh to the membership page, and re-apply the same settings dev uses (collection: `plans`, button label, styling) — cross-reference `templates/page.membership.json` for the exact settings to replicate.
6. Per CLAUDE.md's Supercycle integration contract: don't add dynamic checkout/"Buy now" buttons anywhere on rentable products, don't create the `supercycle` metafield namespace (use `custom.*` stand-ins), and the movie PDP intentionally has **no** Methods-block slot — that's a documented, deliberate override (in-store-only transactions), not something to add here.
7. Once real members exist, Supercycle applies the `Has active subscription` customer tag automatically — no setup needed, just confirm it's working with a real test membership purchase.

---

## Phase 8: New Arrivals & Community Picks — ongoing tagging mechanism

Already fully documented in `claudedocs/lms-admin-instructions.md` — summarizing the production-specific steps:

- **New Arrivals**: after the collection exists (Phase 4), build the "New Arrival tag auto-expiry" Flow in Admin → Apps → Flow (trigger: tag added = `new-arrival` → wait 7 days → remove tag). Client tags products by hand going forward.
- **Community Picks**: after the metaobject definition exists (Phase 3) and products are uploaded, create real entries (Admin → Content → Staff picks) with a real Product reference, quote, and name for each. Nothing shows until at least one entry has a resolved Product.

---

## Phase 9: Search & Discovery

**Resolved 2026-08-28** (previously an open question) — grepped the theme code for every hardcoded `filter.p.*` reference to find the ground truth instead of trusting the original plan doc, which predates the Vendor-format decision and is now stale on this point.

Admin → Apps → Search & Discovery → Filters, enable exactly these three:

- **Product vendor** (built-in filter, `filter.p.vendor`) → this is what actually powers Format. Confirmed via `sections/main-movie.liquid`'s format chip link. **Do not** enable `product.metafields.shopify.media-format` — that was the original plan's instruction, written before the 2026-08-07 decision moved format into Vendor; the metafield is unpopulated on real product data now, so enabling it would show a broken empty facet, exactly the mistake the plan itself warned against for `custom.*` filters.
- **Genre** on `product.metafields.shopify.genre` (`filter.p.m.shopify.genre`) → confirmed via the same file's genre chip link.
- **Product tags** (`filter.p.tag`) → required for the New Arrivals and Community Picks toggle switches on the shop-all page, even though the generic tag checkbox list is suppressed in the theme. **Both toggles need at least one product carrying the matching tag to even appear** — Shopify's facet API only returns values that exist on ≥1 product in the result set. Don't just tag via the Community Pick metaobject (see `lms-admin-instructions.md`) — the product itself also needs the `community-pick` tag, and Rental products need `new-arrival` per the New Arrivals workflow. Confirmed on dev: this was silently broken until both tags were manually applied.
- Don't enable any `custom.format` / `custom.genres` / `custom.genre` (singular) / `custom.label` / `custom.condition` filters — unpopulated on the current catalogue, would show as broken empty facets.

---

## Phase 10: Theme editor content (assets, copy, links)

Things that live in `config/settings_data.json` / theme editor state, not code — need setting independently on production even after the theme code push:

- **Logo assets**: header logo (`Logo_Horiztonal_Black.svg`) and footer logo (`LittleMovieStore__Logo_Stacked_with_Tagline_Parchment.png`) need uploading to production's Files/shop images with matching filenames, or the `shopify://shop_images/...` references in the pushed JSON will point at nothing.
- **Hero image**: same issue — `Screenshot_2026-07-02_at_9.56.45_PM.png` reference needs a real uploaded asset on production. Also a good moment to replace it with finished hero art rather than carrying over what may be a placeholder screenshot (flagged in the dev audit).
- **Social links**: Instagram is correct on dev; TikTok and Threads need real handles (currently blank on the homepage social bar, and generic root URLs in the footer — fix both, don't just copy dev's placeholders forward).
- **Header announcement bar**: currently blank on dev, which leaves a visible empty strip at the top of every page — decide on real copy (a launch message, hours, a promo) or remove the section before this goes live on production.
- **Footer "The Club" column**: currently all four links point to the same membership page on dev — decide if that's fine for production launch or if distinct destinations are wanted.
- **Color schemes / fonts / spacing tokens**: already baked into the theme code (`lms-tokens.css`, `config/settings_data.json`) — comes along with the Phase 0 push, no separate action needed.

---

## Phase 11: Launch

- Decide when to disable password protection (Admin → Online Store → Preferences) — until then, production shows the same generic Shopify pre-launch splash dev currently does, regardless of how finished the theme is underneath.
- Final QA pass once Phases 0–10 are done: walk every page (home, PDP, collections, membership, events) as a real visitor would, ideally with the storefront password if still enabled.

---

## Open questions to resolve before/during this work

- **Is Supercycle actually installed and configured on production already?** A `plans` collection with an Active "Little Movie Club" product (productType "Supercycle Plan", zero metafields) exists, suggesting partial setup predating this runbook — but it can't be confirmed via Admin GraphQL (no generic "list installed apps" access with current auth), and the client currently can't open Supercycle's Admin UI to check directly. **Blocks Phase 7** until resolved.
- Does Supercycle auto-create the `plans` collection, or does it need manual creation? (Phase 4/7) — moot if Supercycle turns out to already be installed; check its actual state first.
- Is the 4-collection footer gap (`4k-blu-ray` etc.) worth building for launch, or genuinely deferred? (Phase 4)
- What should the `visit` page and header announcement bar actually say? (Phases 5, 10) — Visit page creation deferred 2026-09-01 pending real address/hours copy.
- What created the orphan `scf.avf` product metafield on production, and is it safe to delete? (Phase 2)
