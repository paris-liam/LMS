# LMS Homepage Components

Custom `lms-` prefixed sections, blocks, and snippets for the Little Movie Store
Horizon storefront, built from `LMS_Homepage_3_dc.html` per the component spec
(`lms-homepage-component-spec.md`). No Horizon core files are modified.

## Files

```
assets/
  lms-theme.css                    Shared tokens + utilities (eyebrow, buttons, badges, container)
snippets/
  lms-eyebrow.liquid               Uppercase label above headings
  lms-product-card.liquid          2:3 poster card (metafield-driven badges)
sections/
  lms-hero.liquid                  Hero: headline + accent word, buttons, info strip, slideshow
  lms-new-releases.liquid          Collection-driven product grid
  lms-events-membership.liquid     Split card: events (metaobject) + membership (perk blocks)
  lms-promo-pair.liquid            Two-up container accepting @theme blocks
  lms-staff-picks.liquid           Side panel + picks grid (metaobject)
blocks/
  lms-promo-card.liquid            Theme block, 2 presets: Rental library / Mystery bag
```

## Install

1. Copy each folder's contents into the corresponding theme directory.
2. Load the stylesheet once in `layout/theme.liquid`, inside `<head>`:
   ```liquid
   {{ 'lms-theme.css' | asset_url | stylesheet_tag }}
   ```
3. The hero uses DM Serif Display for the accent word. Horizon may already
   load it via font settings; if not, add to `<head>`:
   ```html
   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@1&display=swap" rel="stylesheet">
   ```
4. Run `shopify theme check`, then `shopify theme push`.

## Required custom data definitions (Settings → Custom data)

### Product metafields (namespace `custom`, per repo convention)
| Key | Type | Used by |
|---|---|---|
| `custom.director` | Single-line text | Product card |
| `custom.format` | Single-line text (Blu-ray / DVD / 4K / VHS) | Product card badge |
| `custom.condition` | Single-line text (New / Used) | Product card badge |
| `custom.rare` | True/false | Product card "Rare" badge |

### `event` metaobject
| Field key | Type | Notes |
|---|---|---|
| `name` | Single-line text | |
| `date` | Date | Section auto-filters past events, sorts soonest-first |
| `description` | Single-line text | |
| `audience` | Single-line text, preset choices: `Members`, `Public` | Badge tone: Members→brick, Public→sage |
| `link` | URL | Optional |

### `staff_pick` metaobject
| Field key | Type | Notes |
|---|---|---|
| `product` | Product reference | Poster/title/link derive from the product |
| `quote` | Multi-line text | Shelf note |
| `staff_name` | Single-line text | |

**Enable "Storefront" access on both metaobject definitions** or the sections
render their empty states.

Field keys must match exactly (`name`, `date`, `description`, `audience`,
`link`, `product`, `quote`, `staff_name`) — the Liquid reads them literally.

## Theme settings pass (do first)

Map the design-system tokens to Horizon theme settings, per the spec:
scheme-1 ≈ parchment (default light), scheme-2 ≈ mahogany (dark),
scheme-3 ≈ sage; heading font → display face, body font → mono face.

## Verify against the installed Horizon version

- **Placeholder palette:** the `--lms-*` hex values in `lms-theme.css` are
  approximations — replace with the design-system token values.
- **Scheme CSS variables:** components consume `--color-background` /
  `--color-foreground` with `--lms-*` fallbacks. Confirm the installed
  Horizon version emits these names from its `color-{scheme}` classes (the
  color model changed in recent releases); adjust the two var names if not.
- **Font variables:** `lms-theme.css` maps `--lms-font-display/body` to
  `--font-heading--family` / `--font-body--family`. Confirm against the
  installed version's generated font vars.
- **`{% stylesheet %}` tags:** standard in Horizon-era themes; if theme check
  flags them, move the CSS into `lms-theme.css`.
- **`visible_if`** (hero autoplay speed): supported in current Shopify; if the
  installed version predates it, the setting simply always shows.

## Editor experience (what the client sees)

- Every section/block inserts fully populated with the real homepage copy.
- Text, images, links, prices shown, and counts are editable; layout, type
  treatment, and responsive behavior are not.
- Events and staff picks are **not** edited in the theme editor — staff
  manages them in Admin → Content, and the homepage follows.
- New arrivals rotate by updating the selected collection, not the section.

## Homepage template order

`lms-hero` → `lms-new-releases` → `lms-events-membership` → `lms-promo-pair`
→ `lms-staff-picks`, with Horizon's core header/footer configured per the spec
(nav menus: Shop / Rental library / Events / About; footer menus: Shop /
Visit / The Club).
