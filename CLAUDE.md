# CLAUDE.md — Little Movie Store (LMS)

## What this is

Shopify storefront for **Little Movie Store (LMS)** — a physical-media rental/resale/membership shop. The storefront is currently live behind a password page (coming-soon).

- **Dev store (default workspace)**: `lms-sandbox-lutsfahz.myshopify.com`
- **Production store**: `p0wkgv-wy.myshopify.com` — touch only on explicit instruction
- **Theme**: Horizon (Shopify OS 2.0)
- **Circular commerce** is handled by the **Supercycle** app — **installed and live** on the dev store. **Confirmed rental-only scope (2026-07-15): Membership method only** (item-based credits, allowance = 1 movie at a time, unlimited/same-day swaps) — no Calendar, no Subscription, and **no Resale method at all**. A title is either live in Supercycle (rentable) or pulled out of Supercycle and sold as a plain Shopify product/POS sale; never both for the same item. The `Has active subscription` customer tag is applied automatically by the app. See `supercycle-explained.md` for how it works and `supercycle-progress.md` for the build log.

---

## Read first

**`lms-supercycle-feature-plan.md`** (repo root) — the full feature plan. Start with its **"▶ Pre-Supercycle build track"** section and the **buildability index**: what's buildable now (🔨), buildable with a stand-in (🧩), or blocked until install (🔒).

---

## Major next steps (project roadmap — keep in mind, not yet specced)

High-level tracks the work keeps returning to. **These are not specs** — no formal plan exists for #2 or #4 yet; they're recorded so they aren't forgotten. All prior work has been on the **dev store**; several of these are about eventually getting **production** to parity.

1. **Finish the Supercycle setup + availability/waitlist build** (dev store). In progress — see `docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist-admin-runbook.md` (Section A = Supercycle setup, then filter + waitlist). **Near-term.**
2. **Push the reformatted catalogue to PRODUCTION** (not urgent). **Source of truth = the dev store's current live products** (they carry the in-store TMDB fills, dedup, and tag edits — the pipeline CSV is *not* the authority). Not a blind push: diff production against the dev-store set, reformat any products that exist **only on production** (new since the dev export), and reconcile so production ends up with the full, correctly-formatted catalogue. Data-cleanup pipeline (`data-cleanup/`) is the tooling. Note production is a moving target — the client keeps uploading to it (see #3).
3. **Updated client product-upload sheet** (near-term). The client uploads products by importing a Google Sheet that's **already in Shopify product-CSV column format, straight into production**. Deliverable: a **corrected CSV template** with our reformatted fields + rental scoping (Rental tag, `shopify.media-format`/`shopify.genre`, one-product-per-movie+format) so his ongoing uploads land already-formatted. **Duplicate handling is deliberately NOT prevented at upload time** — per decision, he bulk-uploads freely (few duplicates expected), and we periodically **export the full catalogue and run a dedupe + reformat pass** (the 2026-07-15 duplicate-cleanup + copy-consolidation plans) to combine copies and normalize. **No products are included in Supercycle on production until the whole catalogue is cataloged**, so copies-as-items happens after that reconciliation, not at upload.
4. **Stand up all remaining admin work on PRODUCTION** (not urgent): content, collections, Search & Discovery, Supercycle, etc. — the production equivalent of everything configured on the dev store. Depends on #2.

---

## Stores & themes

| Store | Purpose |
|-------|---------|
| `lms-sandbox-lutsfahz.myshopify.com` | **Dev store — the default target for ALL work** (pushes, pulls, theme dev, Admin API scripts, metafield/metaobject definitions, test data). |
| `p0wkgv-wy.myshopify.com` | Production — the real client store. **OFF-LIMITS by default.** Only push, pull, or edit anything here when the user explicitly says the operation targets the official/production store, per-operation. |

**Store rule**: never assume production. If an instruction doesn't name the production store, it means the dev store. When a production operation IS requested, restate the target store before running it.

### Working theme on dev store

| Theme | ID | Status |
|-------|----|--------|
| Working theme (v4) | `140918915134` | Current push/pull target on `lms-sandbox-lutsfahz.myshopify.com` |

### Theme IDs on production store

| Theme | ID | Status |
|-------|----|--------|
| LMS Redesign (WIP) | `164180295930` | **LIVE / published** — despite the name, this is production |
| Horizon 3.5.1 | `161348780282` | Unpublished — rollback backup |
| Studio 15.4.1 | `163892461818` | Unpublished, ignored — older architecture, no `blocks/` dir |

**Rule**: Before any push, run `shopify theme list` and identify the live theme by its `[live]` role — never trust the theme name or a remembered ID.

---

## Repo layout

```
theme/lms-redesign-v4/          ← working copy (Horizon 4.1.1) — edit and push here
lms-tokens.css                  ← source of truth for the design system (repo root)
lms-supercycle-feature-plan.md  ← full Supercycle feature plan and buildability index
```

All work happens in `theme/lms-redesign-v4/`. The pre-4.1.1 `theme/lms-redesign/` copy and the `theme/horizon-baseline-3.5.1/` pristine reference were deleted after the Horizon 3.5.1→4.1.1 migration was completed and merged.

Working branch: `main`

---

## Supercycle integration contract

Supercycle is installed, but the **Methods app block on the PDP is not yet mounted**. These three rules exist so it can mount cleanly when that happens. Treat them as non-negotiable.

### 1. Reserve the Methods-block slot on the PDP — do NOT build a competing rent/buy button

- Keep a single, standard product form with a detectable variant input (`[name="id"]`) and **one** add-to-cart button — Supercycle's Methods block reuses this button once mounted.
- Leave an app-block slot in the product section so the merchant can place the Methods block.
- Do **not** add dynamic checkout / "Buy now" / express-checkout buttons on rentable products — they bypass the takeover. This is a **hard requirement everywhere in this build**, not a per-product judgment call: Supercycle is rental-only (Membership method), nobody purchases a movie through it, so no dynamic-checkout/express-checkout path should ever be reachable from a movie PDP.

### 2. Member-gating reads the `Has active subscription` customer tag

- `{% if customer.tags contains 'Has active subscription' %}…{% endif %}`
- Supercycle applies this tag live to real members. For a test customer, apply it manually to develop/test member discounts, event gating, and the birthday perk.
- The Methods block (once mounted) does its own finer-grained check against `customer.metafields.supercycle.membership.value.quotas.credits.allowance` — the tag check here is coarse ("are they a member at all"), not a substitute for that. See `supercycle-explained.md`.

### 3. Use `custom.*` stand-in metafields for Supercycle data — NEVER create the `supercycle` namespace

- The `supercycle` metafield namespace is app-reserved and will collide on install.
- Build availability facets, badges, and `data-` attributes against `custom.*` keys that **mirror the eventual `supercycle.*` structure** (e.g. `custom.uncommitted_inventory` ↔ `supercycle.uncommitted_inventory`) so swap day is find-and-replace.
- Mark every stand-in so it's greppable: `{# STAND-IN: swap to supercycle.* on install #}`

---

## Build status

### Done

- Theme foundation: design tokens (`assets/lms-tokens.css`), self-hosted brand fonts, all 7 colour schemes, button radius
- `sections/coming-soon.liquid` — the live password page (see below)
- Header + hero: "Join the club" CTA gated on `Has active subscription`, hero button visibility logic
- Homepage sections: `lms-hero`, `lms-new-releases`, `lms-perks-grid`, `lms-promo-pair`, `lms-newsletter`, `lms-social-bar`, `lms-staff-picks` (renamed "Community Picks", sourced from content metaobjects, not product metadata)
- Events: `lms-events-calendar`, `lms-events-full`, `lms-events-membership` sections, plus a dedicated events page/template, backed by the `event` metaobject (see `claudedocs/events-and-staff-picks-setup.md`)
- Membership page (`templates/page.membership.json`, `lms-shop-membership` section)
- Movie catalogue data pipeline (`data-cleanup/`): resale + CircaOS CSV reformatting into a combined Shopify import, with a review-flagging pass for ambiguous rows

### In progress

- TMDB image/description auto-fill script for the movie catalogue (`data-cleanup/`)
- Homepage sections beyond Units 1–2 (see `claudedocs/plans/homepage-units-1-2.md` for what's explicitly deferred)

### Buildable now (no further Supercycle work needed)

- Catalogue + PDP (with the reserved Methods slot)
- Shopify data structure: collection taxonomy, product metafield definitions, and the **non-serialized retail catalogue** (merch / snacks / art / apparel — never touches Supercycle)
- Curation + merchandising: curation tags, collections, badges, weekly-drops collection, retail bundles, recommendation rails
- Facets via Shopify Search & Discovery, wired to `custom.*` stand-ins
- Capture UIs: notify-me form, birthday capture, mystery-pack product, gift-card product

See the plan's buildability index for per-feature detail.

### Still blocked / not yet wired up

Methods app block on the PDP (per the integration contract below, not yet mounted) · availability-filter app blocks · the $100/yr membership plan itself (item-based credits, allowance = 1, unlimited swaps) and enabling membership per product · create-item · shipping buffers · return-trigger automation · player rentals · rental-at-POS + serial scanning · mystery-pack inventory reconciliation.

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

### Default target: the dev store

All routine pushes, pulls, previews, and API scripts go to `lms-sandbox-lutsfahz.myshopify.com`. Production commands (below) run only on explicit per-operation instruction.

### Pull before push — always (production only, on explicit instruction)

```bash
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 164180295930
```

The client edits colour schemes and section settings in the Shopify theme editor **on production**. Those edits exist only on the store. A blind push uploads the full local copy and silently overwrites them. Always pull first, reconcile any incoming changes with git, then push.

For code-only changes, prefer a narrow push with `--only` to avoid touching merchant-managed files:

```bash
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 164180295930 --only sections/coming-soon.liquid
```

### `shopify theme dev` — run in your own terminal

`theme dev` prompts for the storefront password interactively and **fails in non-interactive tool/Bash contexts** ("Failed to prompt: Enter your store password"). Always run it yourself, or pass `--store-password`, or temporarily disable password protection in admin → Online Store → Preferences.

### Common commands

```bash
# Local preview (dev store)
shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com

# Push / pull dev store (working theme 140918915134)
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
shopify theme pull --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134

# Deploy to PRODUCTION — only on explicit instruction (pull first!)
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 164180295930
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 164180295930

# Lint
shopify theme check --path theme/lms-redesign-v4
```

---

## Conventions

- **Media format lives in `product.vendor`** (`VHS` / `DVD` / `Blu-Ray` / `4K`) — decided 2026-08-07, NOT in `shopify.media-format`. Vendor already carries format on 3,274/3,550 production products while the metafield is empty on all of them, and Vendor stays visible in the admin product list so it can't silently drift. The theme reads `product.vendor` behind a `VHS,DVD,BLU-RAY,4K` whitelist (`sections/main-movie.liquid`, `snippets/lms-product-card.liquid`); the facet is Search & Discovery's built-in **Product vendor** filter (`filter.p.vendor`). Studio/label therefore cannot live in Vendor — use a tag. Rationale: `claudedocs/2026-08-07-product-data-model-audit.md`.
- Otherwise prefer **metafields** over tags for typed/structured product data (genre stays on `shopify.genre`, new/used); tags are fine for simple curation buckets ("Rare Finds", "Staff Picks").
- Do not hardcode member perks as "10% off everything" in customer-facing copy — whether Shopify discounts apply to rental/resale line items is an open question (see plan → open question #4).
- Never surface individual `LMS-NNNNNNN` serial numbers on the storefront.
