# Production setup runbook — starting from a blank store

Assumes production (`p0wkgv-wy.myshopify.com`) has **no theme content, no collections, no metaobjects, and no Supercycle setup** — a true blank slate on everything covered here. Assumes you are handling product upload + formatting + assigning the `product.movie` template **separately** — this runbook doesn't touch product data itself, only the store structure those products plug into.

This is a planning document, not a log of actions taken — production is off-limits by default per this project's rules. Nothing here gets executed without you explicitly saying "go" on a specific phase.

Order matters — collections and theme sections reference tags/metaobjects/pages that need to exist first. Follow top to bottom.

---

## Phase 0: Theme code

1. Confirm the live theme on production with `shopify theme list --store p0wkgv-wy.myshopify.com` — check the `[live]` role, don't assume by name (per project rule).
2. **Pull before push**: `shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme <id>` — reconcile any merchant-made edits in the theme editor before overwriting.
3. Push the theme code. Consider pushing to an **unpublished** theme first (`--unpublished`) so you can review/QA before it goes live, rather than pushing straight to the live theme.
4. Don't publish it live yet — everything below (collections, metaobjects, pages, Supercycle) needs to exist first, or sections will render empty/broken the moment it's live, exactly like we found on dev.

---

## Phase 1: Product tag structure (reference only — you're handling upload separately)

The theme code depends on these tags/fields existing on every movie product. Just documenting the contract here so upload formatting matches what the theme expects:

- **`Rental` tag** — required on every rentable movie. Powers the `all-movies` collection, the New Arrivals collection, and the PDP genre/format chips.
- **Category = Videos** — the Shopify standard product taxonomy category. Required alongside `Rental` for the same collections.
- **`product.vendor` = one of `VHS` / `DVD` / `Blu-Ray` / `4K`** — format lives in Vendor, not a metafield (see CLAUDE.md's data-model convention). The PDP and filters read this against a fixed whitelist.
- **`shopify.genre` metafield** — standard category metafield, populated automatically once Category = Videos is set and a genre value is chosen.
- Two tags applied **manually, ongoing** (not part of bulk upload): `new-arrival` and `community-pick` (see Phases 6 and 8 below).

---

## Phase 2: Metafield definitions

Movie-specific metafield definitions (the `custom.*` stand-ins for future Supercycle fields, plus any others `data-cleanup/` relies on):

```bash
SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-movie-metafield-definitions.sh
```
Requires `SHOPIFY_ADMIN_TOKEN` or `SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET` env vars (older auth pattern this script uses, distinct from the CLI's own OAuth session). Idempotent — safe to re-run.

---

## Phase 3: Metaobject definitions

Two content types need their definitions created before any entries can exist.

1. **Community Pick** (`staff_pick`) — script exists:
   ```bash
   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-staff-pick-metaobject.sh
   ```
   Creates fields: `product` (product reference), `quote` (multi-line text), `staff_name` (single-line text), `staff_link` (URL). Storefront access must be Public Read.

2. **Event** (`event`) — **no script exists yet**, needs creating (either a new script mirroring the staff-pick one, or by hand in Admin → Content → Metaobject definitions → Add definition). Fields needed, matching what the theme reads:
   - `name` — single-line text
   - `description` — single-line text
   - `audience` — single-line text, with choices restricted to `["public", "member"]`
   - `link` — URL
   - `date` — date
   
   Storefront access: Public Read. Enable the "Publishable" capability (Active/Draft status) — the theme only renders Active entries.

---

## Phase 4: Collections

In this order (some depend on tags from Phase 1 already being applied to at least some products, so this phase and product upload can interleave):

1. **All Movies** (`all-movies`) — smart collection: Category = Videos AND tag = Rental. Sort: Newest to oldest. No existing script for this one specifically — check if `create-curation-collections.sh` or a similar one-off needs writing, or create manually in Admin.
2. **Online Store** (`online-store`) — smart collection: tag = `online-store`. This is the non-rental retail catalogue (merch, snacks, etc. — anything sold outright, never touches Supercycle).
3. **New Arrivals** (`new-arrivals`) — script exists and is idempotent:
   ```bash
   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-new-arrivals-collection.sh
   ```
   Rule: Category = Videos AND tag = Rental AND tag = new-arrival. Sort: Newest to oldest. See `claudedocs/lms-admin-instructions.md` for the full New Arrivals mechanism and the Flow that needs building alongside this (Phase 6).
4. **Plans** (`plans`) — **manual collection, not smart** (confirmed on dev — no rule set, products added by hand). This is what the Supercycle Membership Plans app block reads from. Likely gets auto-created by Supercycle itself during Membership-method setup (Phase 8) — check before creating manually to avoid a duplicate.
5. **Optional curation collections** — a script already exists for three tag-driven merchandising collections, not required for any core section to function, create only if you want them live:
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
| Membership | `membership` | `membership` | Create — content: hero copy + perks (see `templates/page.membership.json` for the structure to match) |
| Events | `events` | `events` | Create — the full events calendar page |
| Contact | `contact` | `contact` | Create if wanted — template exists in the theme |
| Visit | `visit` | *(none exists — default page template)* | **Doesn't exist even on dev** — footer links to `/pages/visit` twice and both currently 404. Create this page (address, hours, map) before launch, or repoint those footer links elsewhere. |

`/pages/data-sharing-opt-out` ("Your Privacy Choices") is auto-generated by Shopify's own privacy/consent settings, not something to create manually — it'll appear once relevant regional privacy settings are configured.

---

## Phase 6: Navigation menus

Three menus needed, matching dev's structure (fix the two bugs found there, don't copy them):

1. **Main menu** (`main-menu`): Home (`/`), Rental Library (→ `all-movies` collection), Shop (→ `online-store` collection), Events (→ the `events` **page**, not the privacy page — this was a real bug on dev, get it right the first time here). Consider whether "Join the Club" belongs in the main nav too (it currently only lives as a hero CTA and header-gated element on dev).
2. **Footer menu** (`footer`): Search, Privacy Choices (auto-links once the privacy page exists).
3. **Customer account main menu** (`customer-account-main-menu`): Orders, Profile — standard, no custom setup needed.

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

- Does Supercycle auto-create the `plans` collection, or does it need manual creation? (Phase 4/7)
- Is the 4-collection footer gap (`4k-blu-ray` etc.) worth building for launch, or genuinely deferred? (Phase 4)
- What should the `visit` page and header announcement bar actually say? (Phases 5, 10)
