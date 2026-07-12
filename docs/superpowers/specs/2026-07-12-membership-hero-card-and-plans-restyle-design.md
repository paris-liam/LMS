# Membership page: floating hero card + Supercycle plans restyle — design spec

Date: 2026-07-12
Mockup reference: `docs/become-a-member.dc.html` ("Become a member")
Prior spec: `docs/superpowers/specs/2026-07-10-membership-page-design.md` (hero/marquee/perks/CTA rebuild — implemented on branch `worktree-membership-page`, not yet merged to `main`)
Implementation location: continue on branch `worktree-membership-page` (or a fresh worktree off it), targeting the dev store (`lms-sandbox-lutsfahz.myshopify.com`) for preview/push.

## Summary

Two independent changes to the already-rebuilt `templates/page.membership.json`:

1. Give the hero an optional floating membership-card visual (from the mockup's rotated card), implemented as a reusable theme block that automatically hides the hero's background image/video when present — no new checkbox setting needed.
2. Restyle the existing Supercycle "Membership plans" app block section to look like a designed dark banner (matching the page's closing-CTA band) instead of a bare white widget — the app block itself is **not removed or replaced**, because it's the only enrollment path that actually activates a Supercycle membership (`supercycle-explained.md`: a direct checkout/buy-button link on the plan product processes payment without activating membership, requiring a manual refund). Also fixes a pre-existing dead `#plans` anchor link used by the hero and closing-CTA buttons.

## 1. Floating membership card block

### 1a. New file: `blocks/lms-membership-card.liquid`

A global theme block (same category as the existing `blocks/lms-promo-card.liquid`), usable anywhere a section accepts `@theme` blocks.

Visually reuses the `.lms-member-card` pattern already established in `sections/lms-events-membership.liquid` (top row: brand name + est-text; holder row: "Member" label + holder-name) rather than the mockup's more elaborate version — keeps one consistent card language across the site, and skips the mockup's "No. 0042" serial-style field entirely (nothing resembling an inventory serial belongs on the storefront).

Additional to the existing pattern: this block variant renders "floating" — fixed width, rotated, drop shadow — for use inside a hero, distinct from the flatter card in the events section.

**Settings:**
- `card_est_text` (text, default `"Est. 2026"`)
- `card_name_text` (text, default `"— your name here —"`)

**Markup/CSS**: copy the `.lms-member-card` structure and its existing CSS custom properties (`--lms-surface-inverse`, `--lms-cyan`, `--lms-radius-sm`, `--lms-shadow-md`, font tokens) from `lms-events-membership.liquid`, scoped under a new `.lms-membership-card` class so the two components don't share (and can't accidentally collide via) the same CSS. Add:
- `width: 380px` (scales down on mobile, see breakpoint below)
- `transform: rotate(-4deg)`
- `box-shadow: var(--lms-shadow-lg)` (stronger than the flat card's `--lms-shadow-md`, since this one visually floats)
- `align-self: center` so it centers vertically against the hero's text column in a horizontal flex layout
- Mobile (`max-width: 549px`): drop the rotation and cap width at `100%` / `320px`, consistent with how other `lms-*` components flatten on small screens.

### 1b. Edit to `sections/hero.liquid` (shared native section)

Two small, additive changes only:

- Add `{"type": "lms-membership-card"}` to the section's `"blocks"` schema array (alongside the existing `"text"`, `"button"`, `"logo"`, etc. entries), so it's discoverable in the block picker. (It would already be usable via the existing `"@theme"` entry — this just surfaces it explicitly, matching how other common block types are listed.)
- Where the section currently outputs `{{ media }}` (the captured image/video markup), wrap it:
  ```liquid
  {%- assign has_membership_card = section.blocks | where: 'type', 'lms-membership-card' | size -%}
  {%- unless has_membership_card > 0 -%}{{ media }}{%- endunless -%}
  ```
  This is the entire "hide image, show card" behavior — adding the block hides any configured image/video for that hero instance; removing the block restores normal media rendering. No new schema checkbox, no change to any other hero behavior, no risk to other pages/sections using `hero.liquid`.

### 1c. Membership page hero config (`templates/page.membership.json`)

On the `membership_hero` section instance:
- Change `content_direction` from `column` to `horizontal` (renders text and the new card block side by side, matching the mockup's two-column hero).
- Add a `lms-membership-card` block as the last entry in `block_order`, after `fine_print`.
- Leave all existing text/button blocks and their settings untouched.

## 2. Supercycle plans section restyle + anchor fix

No changes to the Supercycle app block's functional settings (`collection`, `groups`, `redirect_to_last_product_page`, `button_label`, etc.) or to anything in the `supercycle.*` metafield namespace — restyling only, through settings the app block already exposes.

### 2a. Wrapper section settings (`1780928794877ebf06` in `page.membership.json`)

- `background_color`: `#3a2018` (mahogany — matches `membership_closing_cta`)
- `horizontal_alignment_flex_direction_column`: `center`
- `padding-block-start` / `padding-block-end`: `80` (matches the closing CTA band)
- `section_width`: unchanged (`page-width`)

`render 'contrast-override'` (already wired into the shared `snippets/section.liquid` used by `_blocks.liquid`) auto-flips text/foreground contrast for the dark background, same mechanism every other dark `lms-*` section on the site already relies on.

### 2b. Heading blocks (new, added to the same section)

Two `text` theme blocks added before the Supercycle block in `block_order`, centered, mirroring the closing CTA's typographic treatment:
- Eyebrow-style (`type_preset: h6`): "Choose your plan"
- Heading (`type_preset: h2`): "Pick your plan."

### 2c. Supercycle block color/style settings (restyled, not replaced)

Adjust only the block's existing style-related settings:
- `color_background`: `#3a2018` (blend into the section background rather than showing its own white box)
- `color_plan_background`: `#fff9ef` (parchment — plan cards read as light cards on the dark band, consistent with how `lms-promo-card`'s dark variant and the mockup's join-panel both put light content on dark)
- `color_plan_text`: `#3a2018`
- `color_plan_border`: `#8fcdcf` (cyan, matching the accent color used for card/borders elsewhere on dark backgrounds)
- `plan_border_radius`: `4` (matches `--lms-radius-sm`)
- `custom_css`: add font-family declarations targeting the block's own template classes (`.plan-card-title`, `.plan-card-price`, `.plan-card-interval`, `.plan-card-credits`, `.plan-card-features`, `.plan-card-button`) to `var(--lms-font-display)` / `var(--lms-font-mono)` per the site's existing heading/body split, so the plan cards read as part of the page rather than a generic embed.
- `template` HTML field: left as-is (structure/classes are already compatible with the CSS targeting above).

### 2d. `#plans` anchor fix

The hero's primary button and the closing CTA's button both link to `#plans`, but Shopify auto-wraps every rendered section in `id="shopify-section-{{ section.id }}"` — there is no element with `id="plans"` anywhere on the page today, so this link is currently dead on the already-built (unmerged) branch.

Fix: add a `custom-liquid` theme block (`blocks/custom-liquid.liquid`, already exists in the theme) as the first block in section `1780928794877ebf06`, containing:
```html
<span id="plans"></span>
```
Scoped to this one section instance via block settings only — no shared file changes, no risk to other pages.

## 3. Out of scope

- No direct Supercycle checkout/buy-button links anywhere on the page (would bypass membership activation per `supercycle-explained.md`).
- No changes to the Supercycle `membership-plans` app block's functional settings, the `supercycle.*` metafield namespace, or `customer.metafields.supercycle.membership`.
- No changes to `lms-perks-grid.liquid`, the marquee section, or the closing CTA hero instance beyond what's described above.
- The existing flat `.lms-member-card` in `sections/lms-events-membership.liquid` is left untouched — the new floating card is a separate block, not a refactor of that section.

## 4. Testing

- Preview via `shopify theme dev` (run manually — non-interactive contexts can't supply the storefront password) against the dev store, pointed at the branch/worktree's theme path.
- Visually check: hero renders brick background, text on the left, rotated membership card on the right, no image/video showing; removing the card block (in editor) restores normal media/placeholder behavior.
- Click "Become a member" and "See what's included ↓"-style buttons: `#plans` now scrolls to the restyled plans band; plans band renders parchment cards on a mahogany background with legible LMS typography; Supercycle's plan-selection flow (add to cart / redirect) still functions unchanged.
- `shopify theme check --path theme/lms-redesign-v4` before pushing.
