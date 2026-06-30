# Homepage Build Plan — Units 1 & 2

## Scope

**Building:**
- Unit 1 — Core chrome: header + footer
- Unit 2 — Hero section + ticker strip

**Explicitly deferred:**
- Hero right column (rotating covers + CRT animation) → placeholder
- All other homepage sections (membership, product rail, rentals, events, etc.)
- Membership page shell
- Any Supercycle-dependent features

---

## Unit 1 — Core chrome

### Header

**Approach:** Keep Horizon's built-in `header.liquid` section. Customize via `header-group.json` + logo assets + CSS override for the CTA.

**What changes:**

| Item | Action |
|------|--------|
| Logo | `lms-logo-horizontal-brick.svg` is already in `assets/`. Set it in header settings. |
| Color scheme | `scheme-1` (parchment) for the header background |
| Sticky | `enable_sticky_header: "always"` — already set |
| Nav | Points to Shopify `main-menu` link list — client adds items in admin. Nav items: Shop, Rental library, Events, About |
| "Join the club" CTA | Add as the last nav link, target `/pages/membership`. Style it as a button via a CSS rule scoped to `.header__nav-item:last-child a` — simple override, no JS |
| Announcement bar | Remove the default "Welcome to our store" block — leave empty for now |

**Files touched:**
- `sections/header-group.json` — logo, scheme, CTA link, announcement bar cleanup
- `assets/lms-tokens.css` — CTA nav-link-as-button override

---

### Footer

**Approach:** Rebuild `footer-group.json` blocks to match the 4-column mockup. Horizon's footer uses a flexible block system — each column is a `group` block containing `text`, `linklist`, or `newsletter` child blocks.

**Target structure:**

```
[ Logo + tagline ]   [ Shop ]   [ Visit ]   [ The Club ]
─────────────────────────────────────────────────────────
© 2026 Little Movie Store · Made with love in South Philly    TikTok · Instagram · Threads
```

**Column content:**

| Column | Type | Content |
|--------|------|---------|
| Col 1 — Brand | Logo image + tagline text | `lms-logo-stacked.svg` |
| Col 2 — Shop | Linklist | New arrivals, 4K & Blu-ray, Used & VHS, Mystery bags |
| Col 3 — Visit | Linklist | Passyunk Ave, Hours & map, Rental library, Events calendar |
| Col 4 — The Club | Linklist | Join the club, Member perks, Birthday perk, Gift a membership |

**Bottom bar:** Copyright text + social links (TikTok, Instagram, Threads) — rendered via the `footer_utilities` section.

**Color scheme:** `scheme-6` (mahogany — the darkest brand scheme).

**Files touched:**
- `sections/footer-group.json` — full rebuild of blocks

---

## Unit 2 — Hero + Ticker

### Hero section

**Approach:** New custom section `sections/lms-homepage-hero.liquid`. The Horizon built-in `hero.liquid` is an image-background section — it doesn't match the two-column text-left / art-right layout in the mockup, so a bespoke section is the right call.

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Eyebrow                    │                       │
│  H1 headline                │   [PLACEHOLDER]       │
│  Body copy                  │   right column        │
│  CTA buttons                │   (hero art — TODO)   │
│  ─────────────────────────  │                       │
│  Location · Hours · Price   │                       │
└─────────────────────────────────────────────────────┘
```

**Right column placeholder:**
A `<div>` with `background: var(--lms-mahogany)`, `aspect-ratio: 4/5`, and a visible "Coming soon" label with a `<!-- TODO: hero-right-column — rotating cover art + CRT effect -->` comment. Preserves the layout proportions; obvious to a viewer that it's a placeholder.

**Section schema settings** (all editable in the Shopify theme editor):
- `eyebrow` — text, default "Now open · Passyunk Ave, South Philly"
- `heading` — richtext, default "Meet me at the movie store."
- `body` — richtext, default body copy
- `cta_primary_label` / `cta_primary_url`
- `cta_secondary_label` / `cta_secondary_url`
- `stat_location` / `stat_hours` / `stat_membership`
- `color_scheme`
- Standard padding settings

**Files created:**
- `sections/lms-homepage-hero.liquid`

**Template change:**
- `templates/index.json` — replace the existing `hero_jVaWmY` entry with the new `lms-homepage-hero` section. Keep `product_list_fa6P9H` in place for now (it'll be replaced in Unit 4).

---

### Ticker

**Approach:** Use Horizon's existing `sections/marquee.liquid` — it already has the `marquee-component` web component with proper JS and pause-on-hover. Add it to `index.json` between the hero and the next section.

**Configuration (in `index.json`):**
- Color scheme: `scheme-6` (mahogany)
- Border top + bottom: 1.5px
- Speed: slow (the mockup's 40s feel)
- Items (as text blocks): New arrivals · Weekly drops · Mystery bags · Rental library · Boutique labels · A24 · Arrow · Kino Lorber · Collector editions · VHS · DVD · Blu-ray · 4K
- Separator character between items: `✦` (cyan tint)

**No new files** — existing `sections/marquee.liquid` is used as-is.

---

## Asset checklist

| Asset | Status | Action |
|-------|--------|--------|
| `lms-logo-horizontal-brick.svg` | ✅ In `assets/` | Use in header |
| `lms-logo-stacked.svg` | ✅ In `assets/` | Use in footer |
| `lms-tokens.css` | ✅ In `assets/` | Add header CTA rule |
| `logo-stacked-tagline-parchment.svg` | In `docs/assets/logos/` only | Copy to theme `assets/` if footer needs the tagline variant |

---

## Build order

1. Copy any missing logo assets to `theme/lms-redesign/assets/`
2. Update `header-group.json` + `lms-tokens.css` CTA rule (Unit 1a)
3. Rebuild `footer-group.json` (Unit 1b)
4. Create `sections/lms-homepage-hero.liquid` (Unit 2a)
5. Update `templates/index.json` — wire hero + ticker (Unit 2b)

---

## Open questions (not blocking this build)

- Nav link items (Shop, Rental library, Events, About) need to exist in the `main-menu` link list in Shopify admin before the header renders correctly. These are client-managed — note them in the handoff.
- Footer linklists (Shop, Visit, The Club) similarly need to be created in admin as navigation menus, or can be hardcoded in the footer blocks as text + links. Hardcoding is fine for now; can be swapped to `linklists` later.
- The announcement bar will remain empty until there's a launch message to put there.
