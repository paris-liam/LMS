# CLAUDE.md — Little Movie Store (LMS)

## What this is

Shopify storefront for **Little Movie Store (LMS)** — a physical-media rental/resale/membership shop. The storefront is currently live behind a password page (coming-soon).

- **Production store**: `p0wkgv-wy.myshopify.com`
- **Theme**: Horizon (Shopify OS 2.0)
- **Circular commerce** (rental / membership / resale / serialized inventory) will be handled by the **Supercycle** app — currently **NOT installed** (blocked on client).

---

## Read first

**`lms-supercycle-feature-plan.md`** (repo root) — the full feature plan. Start with its **"▶ Pre-Supercycle build track"** section and the **buildability index**: what's buildable now (🔨), buildable with a stand-in (🧩), or blocked until install (🔒).

---

## Stores & themes

| Store | Purpose |
|-------|---------|
| `p0wkgv-wy.myshopify.com` | Production — the real client store. Handle with care. |
| `lms-sandbox-lutsfahz.myshopify.com` | Original sandbox dev store — superseded, ignore. |

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
theme/horizon-live-baseline/    ← pristine Horizon pull — READ-ONLY reference/rollback
theme/lms-redesign/             ← working copy — edit and push here
lms-tokens.css                  ← source of truth for the design system (repo root)
lms-supercycle-feature-plan.md  ← full Supercycle feature plan and buildability index
```

Working branch: `feat/lms-redesign`

---

## Supercycle integration contract

These three rules exist so Supercycle can mount cleanly at install. Treat them as non-negotiable.

### 1. Reserve the Methods-block slot on the PDP — do NOT build a competing rent/buy button

- Keep a single, standard product form with a detectable variant input (`[name="id"]`) and **one** add-to-cart button — Supercycle's Methods block reuses this button at install.
- Leave an app-block slot in the product section so the merchant can place the Methods block.
- Do **not** add dynamic checkout / "Buy now" / express-checkout buttons on rentable products — they bypass the takeover.

### 2. Member-gating reads the `Has active subscription` customer tag

- Now: `{% if customer.tags contains 'Has active subscription' %}…{% endif %}`
- Apply that tag manually to a test customer to develop and test member discounts, event gating, and the birthday perk.
- Post-install, the canonical signal will also be `customer.metafields.supercycle.membership`.

### 3. Use `custom.*` stand-in metafields for Supercycle data — NEVER create the `supercycle` namespace

- The `supercycle` metafield namespace is app-reserved and will collide on install.
- Build availability facets, badges, and `data-` attributes against `custom.*` keys that **mirror the eventual `supercycle.*` structure** (e.g. `custom.uncommitted_inventory` ↔ `supercycle.uncommitted_inventory`) so swap day is find-and-replace.
- Mark every stand-in so it's greppable: `{# STAND-IN: swap to supercycle.* on install #}`

---

## Build status

### Done

- Theme foundation: design tokens (`assets/lms-tokens.css`), self-hosted brand fonts, all 7 colour schemes, button radius
- `sections/coming-soon.liquid` — the live password page (see below)

### Buildable now (no Supercycle needed)

- Catalogue + PDP (with the reserved Methods slot)
- Shopify data structure: collection taxonomy, product metafield definitions, and the **non-serialized retail catalogue** (merch / snacks / art / apparel — never touches Supercycle)
- Curation + merchandising: curation tags, collections, badges, weekly-drops collection, retail bundles, recommendation rails
- Facets via Shopify Search & Discovery, wired to `custom.*` stand-ins
- Member-gated logic against the stand-in tag
- Capture UIs: notify-me form, birthday capture, membership page layout, mystery-pack product, gift-card product

See the plan's buildability index for per-feature detail.

### Blocked until Supercycle is installed

Methods / Membership / availability-filter app blocks · plan + calendar config · resale + rental config and create-item · shipping buffers · return-trigger automation · player rentals · rental-at-POS + serial scanning · mystery-pack inventory reconciliation.

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

### Pull before push — always

```bash
shopify theme pull --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930
```

The client edits colour schemes and section settings in the Shopify theme editor. Those edits exist only on the store. A blind push uploads the full local copy and silently overwrites them. Always pull first, reconcile any incoming changes with git, then push.

For code-only changes, prefer a narrow push with `--only` to avoid touching merchant-managed files:

```bash
shopify theme push --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930 --only sections/coming-soon.liquid
```

### `shopify theme dev` — run in your own terminal

`theme dev` prompts for the storefront password interactively and **fails in non-interactive tool/Bash contexts** ("Failed to prompt: Enter your store password"). Always run it yourself, or pass `--store-password`, or temporarily disable password protection in admin → Online Store → Preferences.

### Common commands

```bash
# Local preview
shopify theme dev --path theme/lms-redesign --store p0wkgv-wy.myshopify.com

# Deploy (pull first!)
shopify theme pull --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930
shopify theme push --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930

# Lint
shopify theme check --path theme/lms-redesign
```

---

## Conventions

- Prefer **metafields** over tags for typed/structured product data (format, label, new/used); tags are fine for simple curation buckets ("Rare Finds", "Staff Picks").
- Do not hardcode member perks as "10% off everything" in customer-facing copy — whether Shopify discounts apply to rental/resale line items is an open question (see plan → open question #4).
- Never surface individual `LMS-NNNNNNN` serial numbers on the storefront.
