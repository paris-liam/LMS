# CLAUDE.md — Little Movie Store (LMS)

## What this is

Shopify storefront for **Little Movie Store (LMS)** — a physical-media rental/resale/membership shop. The storefront is currently live behind a password page (coming-soon).

- **Dev store (default workspace)**: `lms-sandbox-lutsfahz.myshopify.com`
- **Production store**: `p0wkgv-wy.myshopify.com` — touch only on explicit instruction
- **Theme**: Horizon (Shopify OS 2.0)
- **Circular commerce** is handled by the **Supercycle** app — **installed and live on PRODUCTION** (`p0wkgv-wy.myshopify.com`), not the dev store (verified 2026-09-10 via Admin API; the dev store has no Supercycle products). **Confirmed rental-only scope (2026-07-15): Membership method only** (item-based credits, **allowance = 3 items at a time**, unlimited/same-day swaps, **$160/yr** — revised 2026-09-03 from the earlier $100/allowance-1 figure) — no Calendar, no Subscription, and **no Resale method at all**. A title is either live in Supercycle (rentable) or pulled out of Supercycle and sold as a plain Shopify product/POS sale; never both for the same item. The `Has active subscription` customer tag is applied automatically by the app. See `supercycle-explained.md` for how it works and the running build log (`supercycle-progress.md` was retired into it on 2026-09-10).

---

## ⚠️ TEMPORARY: production is the working store (until major release)

**Decided 2026-09-03.** Until the site's major release, **production (`p0wkgv-wy.myshopify.com`) is the source of truth and the default target for theme work** — this inverts the normal "Store rule" below. Pull-before-push still applies (the client edits live there), but skip asking "did they mean production" — assume yes. Revert to the dev-default rule once the major release ships; this block should be removed at that point.

**"Push" / "deploy" default to production.** When the user says "push", "deploy", or "push to production" without naming a store, target `p0wkgv-wy.myshopify.com` — do not ask for confirmation first. Still pull before pushing (see Deployment workflow below), and still restate the target store in the response so the action is visible. Say so explicitly only if the user names the dev store instead.

---

## Read first

**`claudedocs/2026-09-08-supercycle-scope-rebuild.md`** — the canonical, production-audited scope for the Supercycle system. It supersedes `lms-supercycle-feature-plan.md`, which bundled in a lot of work that never touches Supercycle; that older plan is still useful as product-vision background and for its buildability index, but it is **not** the current scope.

---

## Major next steps (project roadmap — keep in mind, not yet specced)

High-level tracks the work keeps returning to. **These are not specs** — no formal plan exists for #2 or #4 yet; they're recorded so they aren't forgotten. Earlier work happened on the **dev store**, but since 2026-09-02/03 **production is the working store** for products *and* theme code, and Supercycle runs there.

1. **Finish the Supercycle setup + availability/waitlist build** (**production**). In progress — see `docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist-admin-runbook.md` (Section A = Supercycle setup, then filter + waitlist). **Near-term.**
2. **Push the reformatted catalogue to PRODUCTION** (not urgent). **Source of truth = the dev store's current live products** (they carry the in-store TMDB fills, dedup, and tag edits — the pipeline CSV is *not* the authority). Not a blind push: diff production against the dev-store set, reformat any products that exist **only on production** (new since the dev export), and reconcile so production ends up with the full, correctly-formatted catalogue. The `formatting-scripts/` pipeline is the tooling. Note production is a moving target — the client keeps uploading to it (see #3).
3. **Updated client product-upload sheet** (near-term). The client uploads products by importing a Google Sheet that's **already in Shopify product-CSV column format, straight into production**. Deliverable: a **corrected CSV template** with our reformatted fields + rental scoping (Rental tag, `shopify.media-format`/`shopify.genre`, one-product-per-movie+format) so his ongoing uploads land already-formatted. **Duplicate handling is deliberately NOT prevented at upload time** — per decision, he bulk-uploads freely (few duplicates expected), and we periodically **export the full catalogue and run a dedupe + reformat pass** (the 2026-07-15 duplicate-cleanup + copy-consolidation plans) to combine copies and normalize. **Superseded 2026-09-10:** products *are* now being included in Supercycle on production ahead of a full catalogue pass — 79 titles imported, a handful with the Membership method enabled. Copies-as-items still happens after reconciliation for the bulk of the catalogue.
4. **Stand up all remaining admin work on PRODUCTION** (not urgent): content, collections, Search & Discovery, Supercycle, etc. — the production equivalent of everything configured on the dev store. Depends on #2.

---

## Stores & themes

| Store | Purpose |
|-------|---------|
| `lms-sandbox-lutsfahz.myshopify.com` | **Dev store — the default target for ALL work** (pushes, pulls, theme dev, Admin API scripts, metafield/metaobject definitions, test data). |
| `p0wkgv-wy.myshopify.com` | Production — the real client store. **OFF-LIMITS by default.** Only push, pull, or edit anything here when the user explicitly says the operation targets the official/production store, per-operation. |

**Store rule (normal state — currently overridden, see the TEMPORARY note above)**: never assume production. If an instruction doesn't name the production store, it means the dev store. When a production operation IS requested, restate the target store before running it.

### Working theme on dev store

| Theme | ID | Status |
|-------|----|--------|
| Working theme (v4) | `140918915134` | Current push/pull target on `lms-sandbox-lutsfahz.myshopify.com` |

### Theme IDs on production store

| Theme | ID | Status |
|-------|----|--------|
| LMS Redesign v4 (review) | `166751961338` | **LIVE / published** (as of 2026-09-02) |
| LMS Theme w/ coming soon page | `164180295930` | Unpublished — was previously live |
| Horizon 3.5.1 | `161348780282` | Unpublished — rollback backup |
| Studio 15.4.1 | `163892461818` | Unpublished, ignored — older architecture, no `blocks/` dir |
| lms-7.8 | `164724637946` | Unpublished |
| lms-7.8 | `164724867322` | Unpublished |
| LMS-Theme-7.19 | `165100781818` | Unpublished |

**Rule**: Before any push, run `shopify theme list` and identify the live theme by its `[live]` role — never trust the theme name or a remembered ID.

---

## Repo layout

```
theme/lms-redesign-v4/          ← working copy (Horizon 4.1.1) — edit and push here
lms-tokens.css                  ← source of truth for the design system (repo root)
lms-supercycle-feature-plan.md  ← full Supercycle feature plan and buildability index
formatting-scripts/             ← catalogue CSV normalizer + TMDB fill (see its README)
```

All work happens in `theme/lms-redesign-v4/`. The pre-4.1.1 `theme/lms-redesign/` copy and the `theme/horizon-baseline-3.5.1/` pristine reference were deleted after the Horizon 3.5.1→4.1.1 migration was completed and merged.

Working branch: `main`

---

## Supercycle integration contract

Supercycle is installed and live on production. Treat these rules as non-negotiable.

### 1. The movie PDP is READ-ONLY — no product form, no add-to-cart, no Methods-block slot

**Reversed 2026-09-08** (see `claudedocs/2026-09-08-supercycle-scope-rebuild.md` §1). The earlier version of this rule told you to reserve a Methods-block slot and keep an add-to-cart button on the PDP. That is no longer the design: **rental checkout stays in-store**, at the counter via Shopify POS + Supercycle. `sections/main-movie.liquid` therefore has no price, variant selector, add-to-cart, dynamic checkout, or app-block slot — and that is correct, not an omission. Do not "restore" any of them.

The PDP shows: poster, description, attribute chips, and an in-stock indicator (see `supercycle-explained.md` → availability label). Membership enrollment is the one online transaction, and it happens on the membership page via the Membership Plans app block, not on a movie PDP.

- Do **not** add dynamic checkout / "Buy now" / express-checkout buttons on rentable products — they bypass the takeover. This is a **hard requirement everywhere in this build**, not a per-product judgment call: Supercycle is rental-only (Membership method), nobody purchases a movie through it, so no dynamic-checkout/express-checkout path should ever be reachable from a movie PDP.

### 2. Member-gating reads the `Has active subscription` customer tag

- `{% if customer.tags contains 'Has active subscription' %}…{% endif %}`
- Supercycle applies this tag live to real members. For a test customer, apply it manually to develop/test member discounts, event gating, and the birthday perk.
- Supercycle's own Methods block does a finer-grained check against `customer.metafields.supercycle.membership.value.quotas.credits.allowance` — the tag check here is coarse ("are they a member at all"), not a substitute for that. See `supercycle-explained.md`.

### 3. READ the real `supercycle.*` metafields — but NEVER create anything in that namespace

- Supercycle is installed, so the `custom.*` stand-ins are obsolete: read the real fields directly. `sections/main-movie.liquid` already does this for the availability label.
- The namespace is app-reserved and **owned by the app** — never create, write, or hand-edit a value in it.
- **Never delete a `supercycle.*` metafield *definition*.** Deleting one wipes its values across the entire catalogue in seconds, and re-creating the definition does **not** restore them — only re-toggling the method per product does, and that only works on some products. This happened on 2026-09-10; see `supercycle-explained.md`.
- Creating a *definition* for an app-owned metafield (to make it filterable) is the one safe exception — but note Shopify rejects the admin-filterable capability on **variant** metafields (`INVALID_CAPABILITY`).

---

## Build status

### Done

- Theme foundation: design tokens (`assets/lms-tokens.css`), self-hosted brand fonts, all 7 colour schemes, button radius
- `sections/coming-soon.liquid` — the live password page (see below)
- Header + hero: "Join the club" CTA gated on `Has active subscription`, hero button visibility logic
- Homepage sections: `lms-hero`, `lms-new-releases`, `lms-perks-grid`, `lms-promo-pair`, `lms-newsletter`, `lms-social-bar`, `lms-staff-picks` (renamed "Community Picks", sourced from content metaobjects, not product metadata)
- Events: `lms-events-calendar`, `lms-events-full`, `lms-events-membership` sections, plus a dedicated events page/template, backed by the `event` metaobject (see `claudedocs/events-and-staff-picks-setup.md`)
- Membership page (`templates/page.membership.json`, `lms-shop-membership` section)
- Movie catalogue data pipeline (`formatting-scripts/`): resale + CircaOS CSV reformatting into a combined Shopify import, with a review-flagging pass for ambiguous rows

### In progress

- Homepage sections beyond Units 1–2 (see `claudedocs/plans/homepage-units-1-2.md` for what's explicitly deferred)

### Buildable now (no further Supercycle work needed)

- Catalogue + PDP (read-only; no Methods slot — see integration contract §1)
- Shopify data structure: collection taxonomy, product metafield definitions, and the **non-serialized retail catalogue** (merch / snacks / art / apparel — never touches Supercycle)
- Curation + merchandising: curation tags, collections, badges, weekly-drops collection, retail bundles, recommendation rails
- Facets via Shopify Search & Discovery, wired to the real `supercycle.*` metafields
- Capture UIs: notify-me form, birthday capture, mystery-pack product, gift-card product

See `claudedocs/2026-09-08-supercycle-scope-rebuild.md` for current scope, and the older feature plan's buildability index for per-feature background.

### Still blocked / not yet wired up

The storefront availability filter (broken — the `supercycle.uncommitted_inventory` variant metafield returns no products through Search & Discovery despite 81 populated values; see `supercycle-explained.md`) · enabling the Membership method per product at catalogue scale · create-item · shipping buffers · return-trigger automation · player rentals · rental-at-POS + serial scanning · mystery-pack inventory reconciliation.

Out of scope entirely (not just blocked): Supercycle's Calendar, Subscription, and Resale methods. Supercycle is rental-only via Membership — no Supercycle-mediated purchase path exists or is planned.

---

## Design system

Source of truth: `lms-tokens.css` (repo root). Applied in theme as `assets/lms-tokens.css`, loaded in `theme.liquid` **after** `color-schemes.css`. Namespaced `--lms-*`.

### Brand colours

| Token | Hex | Role |
|-------|-----|------|
| `--lms-brick` | `#973123` | Primary / wordmark |
| `--lms-mahogany` | `#3a2018` | Dark background |
| `--lms-sage` | `#5f8d7a` | Accent |
| `--lms-parchment` | `#fff9ef` | Light background |
| `--lms-cyan` | `#8fcdcf` | Secondary accent |

### Typography

- **Headings**: Epilogue (variable, 100–900) — self-hosted in `assets/` (OFL), NOT in Shopify font_picker
- **Body**: DM Mono (300 / 400 / 500) — self-hosted in `assets/` (OFL)
- Font families are overridden via CSS (`--lms-*` tokens override Horizon `--font-*--family`), not through theme settings.
- **Fallback**: if a self-hosted font 404s (relative `url()` in a plain `.css` file), convert to `.css.liquid` and use `| asset_url`.

### Buttons & spacing

- `button_border_radius_primary` / `secondary` = `0` (squared)
- 4px base spacing unit

### Colour schemes

All 7 Horizon colour schemes are mapped to brand in `config/settings_data.json`.

**Editing `settings_data.json`**: the file is not valid JSON as-is — it has a leading `/* … */` comment block. Strip that comment, `json.loads` from the first `{`, edit, dump with `indent=2`, then re-prepend the header comment.

---

## Coming-soon page (`sections/coming-soon.liquid`)

This is the current live page — it IS the Shopify password page. Key details:

- DVD-bounce logo animation in a 16:9 box (Calm/Midnight palette, boxed on all viewports)
- Centered brick wordmark + centered body copy
- "Opening soon" CTA links to `instagram.com/littlemoviestore` (profile page, not `/reels/`)
- Newsletter signup via `{% form 'customer' %}`
- Instagram feed: **LightWidget** iframe (widget ID `f499811476365393bcf281510dc81f1c`), script loaded with `defer` + `RemoteAsset` theme-check disable comment. Do not replace with a different embed approach — earlier curated-embed approaches were removed in favour of this.

---

## Deployment workflow

### Default target: production (temporary — see the ⚠️ TEMPORARY block above)

**"Push" or "deploy" with no store named means production** (`p0wkgv-wy.myshopify.com`, live theme `166751961338`) — don't ask which store first, just restate the target when you act. Target the dev store only when the user names it explicitly. This inverts Horizon's normal default; revert once the TEMPORARY block above is removed.

### Pull before push — always, on every production push

```bash
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338
```

The client edits colour schemes and section settings in the Shopify theme editor **on production**. Those edits exist only on the store. A blind push uploads the full local copy and silently overwrites them. Always pull first, reconcile any incoming changes with git, then push.

For code-only changes, prefer a narrow push with `--only` to avoid touching merchant-managed files. Pushing to the live theme in a non-interactive context (e.g. Claude Code's Bash tool) requires `--allow-live`, or the CLI fails with "Failed to prompt":

```bash
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 --only sections/coming-soon.liquid --allow-live
```

### `shopify theme dev` — run in your own terminal

`theme dev` prompts for the storefront password interactively and **fails in non-interactive tool/Bash contexts** ("Failed to prompt: Enter your store password"). Always run it yourself, or pass `--store-password`, or temporarily disable password protection in admin → Online Store → Preferences.

### Common commands

```bash
# Deploy to PRODUCTION — the default for "push"/"deploy" right now (pull first!)
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 --allow-live

# Push / pull dev store (working theme 140918915134) — only when the user names the dev store
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
shopify theme pull --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134

# Local preview (dev store)
shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com

# Lint
shopify theme check --path theme/lms-redesign-v4
```

---

## Conventions

- **Media format lives in `product.vendor`** (`VHS` / `DVD` / `Blu-Ray` / `4K` / `Laserdisc` / `Betamax`, the last two added 2026-09-02) — decided 2026-08-07, NOT in `shopify.media-format`. Vendor already carries format on 3,274/3,550 production products while the metafield is empty on all of them, and Vendor stays visible in the admin product list so it can't silently drift. The theme reads `product.vendor` behind a `VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX` whitelist (`sections/main-movie.liquid`, `snippets/lms-product-card.liquid`); the facet is Search & Discovery's built-in **Product vendor** filter (`filter.p.vendor`). `scripts/set-movie-template.sh`'s vendor search predicate carries the same whitelist. Studio/label therefore cannot live in Vendor — use a tag. Rationale: `claudedocs/2026-08-07-product-data-model-audit.md`.
- Otherwise prefer **metafields** over tags for typed/structured product data (genre stays on `shopify.genre`, new/used); tags are fine for simple curation buckets ("Rare Finds", "Staff Picks").
- Do not hardcode member perks as "10% off everything" in customer-facing copy — whether Shopify discounts apply to rental/resale line items is an open question (see plan → open question #4).
- Never surface individual `LMS-NNNNNNN` serial numbers on the storefront.
