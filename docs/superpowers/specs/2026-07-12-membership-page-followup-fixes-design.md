# Membership page follow-up fixes — design spec

Date: 2026-07-12
Mockup reference: `docs/become-a-member.dc.html` ("Become a member")
Prior specs: `docs/superpowers/specs/2026-07-10-membership-page-design.md`, `docs/superpowers/specs/2026-07-12-membership-hero-card-and-plans-restyle-design.md` (both implemented, merged to `main`)
Implementation location: new git worktree off `main`, targeting the dev store (`lms-sandbox-lutsfahz.myshopify.com`) for preview/push.

## Summary

Five independent, small fixes to the already-shipped membership page (`templates/page.membership.json` + `sections/hero.liquid`), found via visual review of the live page:

1. Remove the empty gap between the header and the hero.
2. Add an opt-in "background monograms" decoration to the hero (matches the mockup).
3. Change the hero's background color so the (globally brick-colored) primary button is visible against it.
4. Remove the "Meet me at the movie store" closing CTA section.
5. Give the Supercycle plan card visible chrome (shadow + matching padding) so it reads as one of the page's own cards rather than a bare embed.

None of these touch the Supercycle app block's functional settings, the `supercycle.*` metafield namespace, or add any direct checkout link — confirmed via `supercycle-builders-mcp` docs research that the block's own `template`/`custom_css`/color settings already provide full styling control (see [[supercycle-checkout-link-not-supported]] memory for the checkout-link research from the prior round; this round only needed the styling-options docs, not that finding).

## 1. Close the hero/header gap

**File:** `theme/lms-redesign-v4/templates/page.membership.json`, `"main"` section (`type: "main-page"`).

Root cause: `main` is Shopify's required, empty main-content wrapper for `page` templates. It carries no blocks on this page, but its `padding-block-start: 40` / `padding-block-end: 80` still render 120px of blank vertical space between the header and `membership_hero`.

Change:
```json
"padding-block-start": 0,
"padding-block-end": 0
```
(was `40` / `80`). Since the section has no content, this is a pure fix — nothing else depends on that padding.

## 2. Hero background monograms (opt-in)

### 2a. New assets

Copy 3 files from `docs/assets/monograms/` into `theme/lms-redesign-v4/assets/`, renamed to match the theme's existing `lms-*` asset-naming convention (e.g. `lms-logo-stacked-tagline-parchment.svg`):

- `docs/assets/monograms/tape-parchment.svg` → `theme/lms-redesign-v4/assets/lms-monogram-tape-parchment.svg`
- `docs/assets/monograms/circles-parchment.svg` → `theme/lms-redesign-v4/assets/lms-monogram-circles-parchment.svg`
- `docs/assets/monograms/looped-parchment.svg` → `theme/lms-redesign-v4/assets/lms-monogram-looped-parchment.svg`

These are the pre-colored parchment (`fill="#fff9ef"`) variants — no CSS filter/invert hack needed (the mockup's `filter: brightness(0) invert(1)` was a workaround for not having a pre-colored asset; our theme already has one).

### 2b. `sections/hero.liquid` changes

Add one checkbox setting, in the same schema `"settings"` array, in a new header group placed after the existing "Media 1"/"Media 2" headers and before "Content" (or any single consistent location — exact position doesn't affect behavior):

```json
{
  "type": "header",
  "content": "Background decoration"
},
{
  "type": "checkbox",
  "id": "show_background_monograms",
  "label": "Show background monograms",
  "default": false,
  "info": "Decorative floating icons behind the hero content, matching the membership page mockup."
}
```

Markup: inside the section's root `<div id="Hero-{{ section.id }}" ...>`, immediately after the opening tag (so it renders behind `.hero__container`, which is `position: relative`), add:

```liquid
{%- if section.settings.show_background_monograms -%}
  <div class="hero__monograms" aria-hidden="true">
    <img src="{{ 'lms-monogram-tape-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--tape" loading="lazy" width="120" height="60">
    <img src="{{ 'lms-monogram-circles-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--circles" loading="lazy" width="96" height="96">
    <img src="{{ 'lms-monogram-looped-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--looped" loading="lazy" width="78" height="78">
  </div>
{%- endif -%}
```

Stylesheet, appended to the section's existing `{% stylesheet %}` block:

```css
.hero__monograms {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.hero__monogram {
  position: absolute;
  opacity: 0.12;
}
.hero__monogram--tape {
  width: 120px;
  top: 6%;
  left: 41%;
  animation: hero-monogram-float 8s ease-in-out infinite;
}
.hero__monogram--circles {
  width: 96px;
  bottom: 9%;
  left: 47%;
  opacity: 0.11;
  animation: hero-monogram-float 11s ease-in-out infinite reverse;
}
.hero__monogram--looped {
  width: 78px;
  top: 16%;
  right: 41%;
  opacity: 0.11;
  animation: hero-monogram-float 9s ease-in-out infinite;
}
@keyframes hero-monogram-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-14px); }
}
@media (prefers-reduced-motion: reduce) {
  .hero__monogram { animation: none; }
}
```

`.hero__container` (existing) is `position: relative` with content at a higher stacking context already (`.hero__media-grid` and `.hero__content-wrapper` render after `.hero__monograms` in DOM order and are not `position: static`, so no z-index conflict — verify visually in testing, add explicit `z-index: 1` to `.hero__content-wrapper`'s existing rule only if the monograms render on top of text).

This is additive-only to the shared `hero.liquid` (one setting, one conditional markup block, one scoped stylesheet block) — same low-risk pattern as the floating-card work in the prior round.

### 2c. Membership page hero config

On `membership_hero` in `page.membership.json`, add:
```json
"show_background_monograms": true
```

## 3. Hero background color → sage

**File:** `page.membership.json`, `membership_hero.settings`.

```json
"background_color": "#5f8d7a"
```
(was `#973123`). `text_color` stays `"#fff9ef"` (already explicitly set — this hero setting renders a `--color` CSS custom property that overrides automatic contrast detection, per `sections/hero.liquid:466`, so it is not affected by the background change). The primary button's fill color is a **global** theme setting (`palette_primary_button_background` = `settings.color_palette.color1` = brick `#973123`, in `config/settings_data.json`) — unrelated to any single section's background, so it does not need to change; it will now read clearly (brick-on-sage) instead of blending (brick-on-brick).

Button_secondary's `link_text_color` (`#fff9ef`) is unaffected — already parchment, still legible on sage.

## 4. Remove the closing CTA

**File:** `page.membership.json`.

Delete the `"membership_closing_cta"` key entirely from `"sections"`, and remove `"membership_closing_cta"` from the `"order"` array (so `order` ends `[..., "membership_perks", "1780928794877ebf06"]`, i.e. the plans banner becomes the last section before the footer).

No replacement content — the hero's own "Become a member" button (linking to `#plans`) already serves the same purpose, and the perks-grid + plans-banner sequence is a complete enough close to the page without a second, redundant CTA band.

## 5. Plan card chrome

**File:** `page.membership.json`, section `1780928794877ebf06`, block `supercycle_membership_plans_MdRHJR`.

Confirmed via live DOM inspection: each plan renders inside a `.plan-card-wrapper` element (plus a plan-specific slug class, e.g. `.lms-annual-membership`) — this is the element that the block's own `color_plan_background` / `color_plan_border` / `plan_border_radius` settings already target internally. It currently has a flat parchment background and a thin cyan border but no depth — reads as an embedded widget, not a page card.

Changes:
- `plan_border_radius`: `4` → `8` (matches `--lms-radius-lg`, used by `.lms-perks__item` and other page cards, rather than the smaller default).
- `custom_css`: append (don't replace) the existing font-family rules with:
  ```css
  .plan-card-wrapper { box-shadow: 0 1px 2px rgba(58, 32, 24, 0.08); padding: 32px 30px; }
  ```
  (the shadow value is `--lms-shadow-xs`'s literal value, copied in rather than referenced as a CSS variable, since the Supercycle block's `custom_css` field is unlikely to have access to the storefront's `:root`-scoped custom properties reliably outside the theme's own stylesheet cascade — confirm in testing whether `var(--lms-shadow-xs)` resolves correctly inside the block's injected `<style>`; if it does, prefer the variable form for consistency with the rest of the page and drop the literal.)

No other block settings change — `collection`, `groups`, `redirect_to_last_product_page`, `button_label`, `template` structure, `color_background`, `color_plan_background`, `color_plan_text`, `color_plan_border` all stay as already set from the prior round.

## Out of scope

- No changes to the Supercycle app block's functional settings or the `supercycle.*` metafield namespace.
- No direct checkout link (per `supercycle-checkout-link-not-supported` memory).
- No changes to `lms-perks-grid.liquid`, the marquee section, or the `lms-membership-card` floating-card block itself.
- The monogram toggle is additive to `hero.liquid` only — no other page using `hero.liquid` is affected unless it also enables the new checkbox (default `false`).

## Testing

- Preview via `shopify theme dev` (run manually by the user — non-interactive contexts can't supply the storefront password) or by pushing to the dev store's live theme and viewing directly, consistent with the prior round.
- Visually check: no gap between header and hero; 3 monogram icons floating behind hero content, not overlapping/obscuring text or the floating membership card; hero background is sage, "Become a member" button reads clearly in brick against it; page ends at the plans banner with no closing CTA band below it; each Supercycle plan renders as a distinct shadowed card with more internal padding.
- `shopify theme check --path theme/lms-redesign-v4` before pushing — expect the same baseline (2 pre-existing errors from the Supercycle app-block file reference, 7 unrelated warnings) with no new offenses.
