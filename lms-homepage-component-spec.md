# LMS Homepage — Component Architecture & Schema Spec

**Source mockup:** `LMS_Homepage_3_dc.html` (Homepage, side-by-side variant)
**Target:** Shopify Horizon theme, custom `lms-` prefixed sections/blocks
**Governing standards:** Horizon theme-blocks conventions — constrained inputs, presets with real content, grouped settings, `visible_if` progressive disclosure, content in the right scope (theme / section / block / metafield / metaobject)

---

## 1 · Mockup breakdown

The page has seven regions. Two belong to Horizon core; five become `lms-` components.

| # | Region | Shopify home | Build/refactor |
|---|--------|--------------|----------------|
| 1 | Sticky header (logo, nav, "Join the club" CTA, mobile menu) | **Horizon core header section** | Configure only — no custom code |
| 2 | Hero (statement headline w/ italic accent, body, 2 CTAs, info strip, image slideshow) | `sections/lms-hero.liquid` | **New** |
| 3 | New arrivals (eyebrow + heading + "Browse all", 5-up product grid) | `sections/lms-new-releases.liquid` | **Refactor existing** |
| 4 | Events + Membership split card | `sections/lms-events-membership.liquid` | **New** (absorbs/refactors `lms-membership.liquid`) |
| 5 | Rent + Mystery Bag promo pair | `sections/lms-promo-pair.liquid` + `blocks/lms-promo-card.liquid` | **New** |
| 6 | Staff picks (side panel + 4-up pick grid) | `sections/lms-staff-picks.liquid` | **New** |
| 7 | Footer (logo, 3 link columns, socials bar) | **Horizon core footer section** | Configure only — link columns are Navigation menus |

### Design-token mapping (do this first)

The mockup's CSS custom properties translate to Horizon **theme settings**, so every component consumes tokens instead of re-declaring colors/fonts. This is the single biggest lever for keeping component schemas small.

| Mockup token | Horizon home |
|---|---|
| `--lms-parchment`, `--lms-parchment-2` | Color scheme 1 (default light) background / secondary background |
| `--lms-mahogany` (+ parchment text) | Color scheme 2 (dark) |
| `--lms-sage` (+ parchment text) | Color scheme 3 |
| `--lms-brick` | Accent/button color within schemes; also link color role |
| `--lms-cyan` | Secondary accent within the dark scheme |
| `--font-display` | Heading font role |
| `--font-mono` | Body font role |
| DM Serif Display italic | Accent font role (used only via the hero accent-word pattern) |
| `--container-max`, section padding rhythm (72/32px) | Theme layout settings + per-section padding ranges |

**Rebrand test:** the client should be able to change parchment→cream or brick→rust in *theme settings only* and see it propagate through every `lms-` section.

---

## 2 · Content inventory — what's editable, hard-coded, or dynamic

Applying the expose / hard-code / dynamic-source rule to every piece of content in the mockup:

**Editable settings (client will realistically change these):** all eyebrow texts, headings, body copy, button labels + links, info-strip items (hours *will* change), event limit, product count, prices shown in promo cards ($4/week, $35, $100/yr), footer menus.

**Hard-coded (structure that breaks if touched):** grid templates and column ratios, the 2/3 poster aspect ratio, border/divider treatment, the member-card visual composition, typography treatments (sizes, letter-spacing, the uppercase display style), responsive breakpoint behavior, slideshow controls markup.

**Dynamic sources (lives on the resource, not in the editor):** product title/director/price/image from the product itself; format, condition, and rare-badge from `custom.*` metafields (already planned in the taxonomy work); events and staff picks from **metaobjects** (see §4 and §6).

**Deliberately NOT exposed:** font sizes, letter-spacing, pixel offsets, the decorative "?" position, column counts on the arrivals grid (it's tied to the responsive system), z-index/overlay mechanics. If the client wants these changed, it's a design change, not a content edit.

---

## 3 · Section 2: `lms-hero.liquid`

### Architecture
Section with three section-local block types: `slide`, `button`, `info_item`. Layout (copy left / media right, reversing on mobile) is hard-coded. The heading uses the **two-field accent pattern** so the client never touches HTML to get "Movies you can *Feel.*"

### Settings sketch

```json
{
  "name": "LMS hero",
  "tag": "section",
  "class": "lms-hero",
  "settings": [
    { "type": "header", "content": "Heading" },
    { "type": "text", "id": "eyebrow", "label": "Eyebrow",
      "default": "Now open · Passyunk Ave, South Philly" },
    { "type": "text", "id": "heading", "label": "Headline",
      "default": "Movies you can" },
    { "type": "text", "id": "heading_accent", "label": "Accent word",
      "default": "Feel.",
      "info": "Shown in italic serif on its own line. Leave blank to skip." },

    { "type": "header", "content": "Text" },
    { "type": "richtext", "id": "body", "label": "Description",
      "default": "<p>A curated physical media store built for people who actually love movies. DVD, Blu-ray, 4K, VHS — new, used, rare, and everything in between.</p>" },

    { "type": "header", "content": "Slideshow" },
    { "type": "checkbox", "id": "autoplay", "label": "Auto-rotate slides", "default": true },
    { "type": "range", "id": "autoplay_speed", "label": "Change slides every",
      "min": 3, "max": 9, "step": 1, "unit": "s", "default": 5,
      "visible_if": "{{ section.settings.autoplay }}" },

    { "type": "header", "content": "Section style" },
    { "type": "color_scheme", "id": "color_scheme", "label": "Color scheme", "default": "scheme-1" },
    { "type": "range", "id": "padding-block-start", "label": "Top padding",
      "min": 0, "max": 100, "step": 4, "unit": "px", "default": 72 },
    { "type": "range", "id": "padding-block-end", "label": "Bottom padding",
      "min": 0, "max": 100, "step": 4, "unit": "px", "default": 60 }
  ],
  "blocks": [
    {
      "type": "slide", "name": "Slide",
      "settings": [
        { "type": "image_picker", "id": "image", "label": "Image",
          "info": "Recommended: 1920 × 1440 (4:3)" }
      ]
    },
    {
      "type": "button", "name": "Button",
      "settings": [
        { "type": "text", "id": "label", "label": "Label", "default": "Join the club" },
        { "type": "url", "id": "link", "label": "Link" },
        { "type": "select", "id": "style", "label": "Style", "default": "primary",
          "options": [
            { "value": "primary", "label": "Solid" },
            { "value": "outline", "label": "Outline" }
          ] }
      ]
    },
    {
      "type": "info_item", "name": "Info item",
      "settings": [
        { "type": "text", "id": "label", "label": "Label", "default": "Hours" },
        { "type": "text", "id": "value", "label": "Value", "default": "Wed – Sat · 10am – 6pm" }
      ]
    }
  ],
  "presets": [
    {
      "name": "LMS hero",
      "blocks": [
        { "type": "slide" }, { "type": "slide" }, { "type": "slide" },
        { "type": "button", "settings": { "label": "Join the club →", "style": "primary" } },
        { "type": "button", "settings": { "label": "Browse the shelves", "style": "outline" } },
        { "type": "info_item", "settings": { "label": "Location", "value": "Passyunk Ave · South Philly" } },
        { "type": "info_item", "settings": { "label": "Hours", "value": "Wed – Sat · 10am – 6pm" } },
        { "type": "info_item", "settings": { "label": "Membership", "value": "$100 / year" } }
      ]
    }
  ]
}
```

### Notes
- Preset seeds the section fully populated with the mockup's real copy — the client sees the finished design on insert, then swaps text.
- `max_blocks` can't cap per-type counts; render defensively — take the first 2 `button` blocks and first 4 `info_item` blocks, ignore extras (better than breaking layout).
- Slideshow arrows/dots are static markup; hide them when slide count = 1.
- Wrap each block's root element with `{{ block.shopify_attributes }}` so the editor click-to-select works.

---

## 4 · Section 3 refactor: `lms-new-releases.liquid`

### Current → target
The existing file (per the pilot-CSV era) presumably renders a fixed or manually-specified set. Refactor to **collection-driven**: staff maintains a "New arrivals" collection in admin (which they'll do anyway for the shop page), and the homepage follows automatically. Zero homepage editing to rotate stock.

### Settings sketch

```json
"settings": [
  { "type": "header", "content": "Heading" },
  { "type": "text", "id": "eyebrow", "label": "Eyebrow", "default": "Just dropped" },
  { "type": "text", "id": "heading", "label": "Heading", "default": "New arrivals this week" },

  { "type": "header", "content": "Products" },
  { "type": "collection", "id": "collection", "label": "Collection",
    "info": "Products shown newest-first from this collection." },
  { "type": "range", "id": "products_to_show", "label": "Products to show",
    "min": 3, "max": 10, "step": 1, "default": 5 },

  { "type": "header", "content": "Button" },
  { "type": "text", "id": "button_label", "label": "Button label", "default": "Browse all →",
    "info": "Links to the selected collection. Leave blank to hide." }
]
```

### Notes
- Button URL is **not** a setting — it derives from `section.settings.collection.url`. One less thing to break.
- Cards render through the existing `lms-product-card` snippet. Format / condition / rare badges read `product.metafields.custom.*` — this is the dynamic-source boundary; nothing product-specific lives in section settings.
- Desktop 5-up grid and the mobile horizontal scroll-snap behavior are hard-coded (they're load-bearing responsive design, per the mockup's media queries).
- Rare badge: driven by a `custom.rare` boolean metafield, rendered by the card snippet. Don't add a per-section toggle.

---

## 5 · Section 4: `lms-events-membership.liquid`

One section, two hard-coded panels sharing the bordered card (matches the mockup's single visual unit and mobile stacking). The existing `lms-membership.liquid` becomes the right-hand panel; keep the old file until this replaces it in the template, then retire it.

### Events panel → **metaobject-driven**

Events are the textbook metaobject case: structured, repeatable, and needed on both the homepage and a future events page. Managed once in **Admin → Content**, rendered everywhere.

**`event` metaobject definition:**

| Field | Type | Notes |
|---|---|---|
| `name` | Single-line text | "Horror night: Cronenberg classics" |
| `date` | Date | Drives the Jun/07 date chip |
| `description` | Single-line text | "In-store screening · Videodrome + The Fly" |
| `audience` | Single-line text w/ **preset choices**: `Members`, `Public` | Drives badge label + tone (Members→brick, Public→sage — mapping hard-coded) |
| `link` | URL (optional) | Event detail / RSVP |

Section pulls upcoming events automatically (filter `date >= today`, sort ascending, take N). The client never touches the homepage to update events — they add an event in Content and it appears.

**Events-side settings:** eyebrow (default "Coming up"), heading (default "Events & screenings"), `range` events_to_show (2–5, default 3), link label (default "All events →") + link URL.

### Membership panel

Refactor of `lms-membership.liquid` content model:

- **Settings:** eyebrow (default "The Little Movie Club · $100/yr"), heading (default "Become a regular, not a customer."), price text (default "$100"), price suffix (default "/ year"), button label + link.
- **`perk` blocks** (title + detail text pair), preset seeded with the four mockup perks. Blocks — not metaobjects — because perks are managed inline, ordered visually, and only live here.
- **Member card visual:** fully hard-coded except the small "Est. 2026" text (one text setting). The "— your name here —" line is decorative copy; make it a text setting with that default, `info: "Placeholder name shown on the sample card."`
- Membership purchase mechanics (Supercycle plan link, gift toggle) are out of scope here — the button just links wherever the join flow lives.

---

## 6 · Section 5: `lms-promo-pair.liquid` + `blocks/lms-promo-card.liquid`

The Rent card and Mystery Bag card are structurally identical — eyebrow, heading, body, stat (label / big value / suffix), CTA, color, optional background glyph. Per the standards: **one block type with a scheme select, not two components.**

### `blocks/lms-promo-card.liquid` — a real theme block

Build this one as a **theme block in `/blocks`** (not section-local): it's a genuinely reusable promo unit (rental pitch on the shop page, mystery bag on a gift guide, etc.).

```json
{
  "name": "LMS promo card",
  "settings": [
    { "type": "header", "content": "Content" },
    { "type": "text", "id": "eyebrow", "label": "Eyebrow", "default": "The rental library" },
    { "type": "text", "id": "heading", "label": "Heading", "default": "Not ready to commit? Rent it." },
    { "type": "richtext", "id": "body", "label": "Text" },

    { "type": "header", "content": "Price callout" },
    { "type": "text", "id": "stat_label", "label": "Small label", "default": "Rentals from" },
    { "type": "text", "id": "stat_value", "label": "Big number", "default": "$4" },
    { "type": "text", "id": "stat_suffix", "label": "After the number", "default": "/ week · free for members" },

    { "type": "header", "content": "Button" },
    { "type": "text", "id": "button_label", "label": "Label", "default": "Browse library →" },
    { "type": "url", "id": "button_link", "label": "Link" },

    { "type": "header", "content": "Style" },
    { "type": "color_scheme", "id": "color_scheme", "label": "Color scheme", "default": "scheme-3" },
    { "type": "text", "id": "background_glyph", "label": "Background character",
      "info": "One large decorative character behind the content (like the “?”). Leave blank for none." }
  ],
  "presets": [
    { "name": "Promo card — Rental library" },
    { "name": "Promo card — Mystery bag",
      "settings": {
        "eyebrow": "Online · Ships nationwide",
        "heading": "The mystery bag.",
        "stat_label": "Starting at", "stat_value": "$35", "stat_suffix": "",
        "button_label": "Get a bag →",
        "color_scheme": "scheme-2",
        "background_glyph": "?"
      } }
  ]
}
```

Two presets from one file — the Horizon Group-block pattern. The client picks "Mystery bag" from the block picker and gets the mahogany card with the "?" already configured.

### `lms-promo-pair.liquid`
Thin container: the two-up grid (stacking on mobile), padding ranges, and a `blocks` array of `{ "type": "@theme" }` rendered via `{% content_for 'blocks' %}`. Preset seeds one Rental + one Mystery Bag promo card. Accepting `@theme` means the client can also drop any Horizon block into this layout later — flexibility without new code.

---

## 7 · Section 6: `lms-staff-picks.liquid`

### Architecture decision: metaobjects
Staff picks are updated **weekly**, appear on the homepage (first 4) *and* the "Full list →" page (all of them), and each pick ties a real product to editorial content. That's cross-page, structured, repeatable → **metaobject**, same reasoning as events.

**`staff_pick` metaobject definition:**

| Field | Type | Notes |
|---|---|---|
| `product` | Product reference | Poster image, title, and link come from the product — no duplicate data entry |
| `quote` | Multi-line text | The shelf note |
| `staff_name` | Single-line text | "Rosa", "Marcus"… |

Weekly workflow for staff: Admin → Content → Staff picks → add/edit four entries. Homepage and full-list page both update. No theme editor involved — which is exactly right for content that changes weekly and is edited by shop staff, not the owner.

**Section settings:** side-panel eyebrow (default "From the shelves"), heading (default "Staff picks"), description richtext, link label + URL, `range` picks_to_show (2–4, default 4). Poster aspect (2:3), the italic heading treatment, and the divider grid are hard-coded.

**Fallback consideration:** if metaobjects feel heavy during build, the interim version is section-local `pick` blocks (product picker + quote + staff name). It ships faster but duplicates data the moment the full-list page exists — plan to migrate.

---

## 8 · Header & footer (regions 1 and 7)

Do not rebuild these. Horizon's core header/footer sections cover everything in the mockup:

- **Header:** logo → theme settings; nav → main menu (Shop / Rental library / Events / About); "Join the club" CTA → Horizon header button setting (or a small `lms-` header block if Horizon's header doesn't expose a CTA slot — verify against the installed version before writing any code); sticky + blur styling → CSS in `assets/`, not schema.
- **Footer:** three link columns → three navigation menus (Shop / Visit / The Club) assigned to footer menu blocks; logo variant, copyright line, and social links → Horizon footer settings (social URLs live in theme settings and reuse everywhere).

The mockup's specific styling (mahogany footer, cyan column labels, border treatments) is applied via the color scheme assigned to the footer section plus CSS overrides in `assets/` — never by editing Horizon core files.

---

## 9 · Cross-cutting schema conventions (apply to every `lms-` file)

1. **Every section/block gets a preset** seeded with the mockup's actual copy — real content, never placeholder-speak.
2. **Constrained inputs everywhere:** `range` (with unit + sensible min/max/step) over `number`; `select` over free text; `color_scheme` over `color`; `image_picker` with recommended dimensions in `info`; resource pickers over pasted handles.
3. **Group with `header` every ~5–7 settings**, ordered: content first, style last. Master toggles precede the settings they reveal via `visible_if`.
4. **Padding pattern:** Horizon's `padding-block-start` / `padding-block-end` range pair on every section, defaults matching the mockup rhythm (72/60/72px).
5. **Labels in sentence-case plain English** ("Big number", not "Stat value string"). `info` text for anything non-obvious. Plain strings are fine for this single-store build — `t:` keys are optional; if adopted, adopt everywhere.
6. **Scoped CSS:** `{% style %}` blocks keyed to `#shopify-block-{{ block.id }}` / section id; shared LMS styling in one `assets/lms-theme.css`. Never rely on literal block IDs in logic.
7. **`{{ section.shopify_attributes }}` / `{{ block.shopify_attributes }}`** on every root element.
8. **Render defensively:** cap block counts in Liquid where the design has a limit; hide empty settings (blank eyebrow → no empty element).
9. **`shopify theme check`** on every file before push; then the "merchant test" — add the section fresh, confirm the preset renders the mockup, and try to break it with normal inputs.

---

## 10 · Build order

1. **Theme settings pass** — color schemes, font roles, layout width (unblocks everything; validates the token mapping).
2. **Metaobject definitions** — `event`, `staff_pick` (+ storefront access enabled), plus confirming `custom.format` / `custom.condition` / `custom.rare` product metafields from the taxonomy work.
3. **`lms-new-releases` refactor** — smallest change, exercises the collection + metafield pipeline end to end.
4. **`lms-promo-card` block + `lms-promo-pair`** — first theme block; establishes the `/blocks` + preset pattern.
5. **`lms-hero`** — biggest new section, no data dependencies.
6. **`lms-events-membership`** — depends on the `event` metaobject; retires `lms-membership.liquid`.
7. **`lms-staff-picks`** — depends on `staff_pick` metaobject.
8. **Header/footer configuration** + homepage JSON template assembly, mobile pass, merchant test with the client.

---

## Open items

- Verify the installed Horizon version's header exposes a CTA button slot; if not, decide between a small `lms-` header block or CSS-only styling of a menu item.
- Confirm Horizon version's color model (schemes vs. the newer palette system in 4.x) before the theme-settings pass.
- The hero slideshow placeholder says "1920 × 1440" — confirm final art direction/aspect before locking the `info` text and any focal-point guidance.
- "Full list" staff-picks page and events page are implied by the mockup's links but unscoped — the metaobject architecture assumes they'll exist.
