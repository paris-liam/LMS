# Membership page rebuild (hero, marquee, perks, closing CTA) — design spec

Date: 2026-07-10
Mockup reference: `docs/become-a-member.dc.html` ("Become a member")
Implementation location: dedicated git worktree off `main` (branch `worktree-membership-page`), targeting the dev store (`lms-sandbox-lutsfahz.myshopify.com`) for preview/push.

## Summary

Rebuild `templates/page.membership.json` using four pieces of the `become-a-member.dc.html` mockup — hero, marquee ticker, "what you get" perks panel, and a closing "become a member" CTA — while keeping the page's existing real conversion mechanism (the Supercycle `membership-plans` app block) intact and simply repositioned. Everything not explicitly named (nav bar, membership-card graphic, "How it works" steps, fake signup form, testimonials, FAQ) is dropped; the theme's real header/footer already cover that ground.

Three of the four new pieces are native Horizon sections used as-is (`hero.liquid` twice, `marquee.liquid` once, both already used elsewhere in the theme — e.g. the homepage ticker). Only the "what you get" panel is new Liquid.

## 1. Section order in `page.membership.json`

1. `main` — existing `main-page` wrapper section, untouched.
2. **Hero** — new `hero.liquid` instance (§2).
3. **Marquee** — new `marquee.liquid` instance (§3).
4. **"What you get"** — new bespoke section `sections/lms-perks-grid.liquid` (§4), section id `perks`.
5. **Supercycle membership-plans app block** — existing section (`1780928794877ebf06`), moved to this position, unchanged settings. Its section id becomes the anchor target `#plans` referenced by the hero and closing CTA buttons below.
6. **Closing CTA** — second `hero.liquid` instance (§5).
7. Footer — theme-level, unaffected.

## 2. Hero (`hero.liquid`, instance 1)

Text-only hero, no media. Matches the "hero_marquee"-family preset shape but without the marquee block (marquee is its own section per §3).

- `background_color`: `#973123` (brick)
- Blocks, in order:
  - `text` (eyebrow-style, `type_preset: h6`): "Little Movie Club · $100/year"
  - `text` (`type_preset: h1`): "Become a member."
  - `text` (`type_preset: rte`, body copy): "The club isn't really about the perks — it's about belonging to a place that's as much yours as it is ours. One flat year. Renters become buyers. That's the whole game, baby."
  - `button` (primary): label "Become a member", link `#plans`
  - `button` (secondary/text style): label "See what's included ↓", link `#perks`
  - `text` (small print, muted): "No app. No fine print. Cancel anytime — just bring yourself."
- `section_height`: `auto` (content-driven, no forced viewport height — this hero has no media to fill).
- `padding-block-start` / `padding-block-end`: match the theme's existing hero padding defaults (72 / 60), consistent with `lms-hero.liquid`'s homepage hero.

## 3. Marquee (`marquee.liquid`)

Exact same pattern as the homepage's `lms_ticker` section instance in `templates/index.json`: alternating `text` blocks (item, `✦` separator) styled uppercase/letter-spaced, separator colored `#8fcdcf` (cyan).

- `background_color`: `#3a2018` (mahogany)
- `movement_direction`: `normal`
- `padding-block-start` / `padding-block-end`: `12`
- `gap_between_elements`: `22`
- Items (repeated in sequence to fill the loop, same as homepage's 8-pair pattern): Rental library · 10% off everything · Free birthday movie · Members events · First dibs on drops · Bring a friend — cycle repeats.

## 4. "What you get" panel (new section: `sections/lms-perks-grid.liquid`)

New bespoke section, following the existing `lms-*` section conventions (design-token CSS variables, `contrast-override` render for text contrast, block-based repeatable items). Section id used as anchor target `perks`.

**Section settings:**
- `eyebrow` (text): default "What you get"
- `heading` (text): default "A year of belonging, for $100."
- `subheading` (text): default "Six small reasons it pays to be a regular. Most members make the hundred back by spring."
- Standard `background_color` + top/bottom padding settings, matching other `lms-*` sections.

**Block type `perk`** (max 6, matches mockup's 6 default perks):
- `number` (text): e.g. "01"
- `title` (text)
- `body` (text)

Default preset blocks (from the mockup):
1. 01 / "The rental library" / "Run of the whole borrow-buddy library, all year. Be our borrow buddy."
2. 02 / "10% off everything" / "Every purchase, every visit, every format. No fine print."
3. 03 / "A free birthday movie" / "Pick anything off the shelf on your birthday — it's on us."
4. 04 / "Members events" / "First invites to screenings, closet tours, and movie nights."
5. 05 / "First dibs on drops" / "Shop the weekly drop and mystery bags before they hit the floor."
6. 06 / "Bring a friend" / "A guest pass so you never have to come browse alone."

**Layout:** centered header block (eyebrow, heading, subheading, max-width ~560px), then a 3-column CSS grid of perk cards below. Each card: large numeral (`--lms-font-display`, brick-colored), title, body, on a bordered card (`--lms-radius-lg`, `--lms-shadow-xs`, `--lms-border-default`) — matches the mockup's perk card styling. Collapses to 1 column under `989px`, consistent with other `lms-*` section breakpoints.

> Per §4 of CLAUDE.md's design-system rules on hardcoding member-perk copy: the "10% off everything" line is presentational copy carried directly from the mockup, not a new claim about discount eligibility — no change to how discounts are actually applied.

## 5. Closing CTA (`hero.liquid`, instance 2)

Second, separate instance of the same native section, configured as a compact centered CTA band.

- `background_color`: `#3a2018` (mahogany)
- `horizontal_alignment_flex_direction_column`: `center` (centered content)
- `section_height`: `small`
- Blocks, in order:
  - `text` (`type_preset: h2`): "Meet me at the movie store."
  - `text` (`type_preset: rte`): "Built by movie lovers, for everyone. Come be a regular."
  - `button` (primary): label "Become a member · $100/yr", link `#plans`

## 6. Supercycle membership-plans block

No code or setting changes — section `1780928794877ebf06` is moved in the `order` array to sit between the perks grid and the closing CTA. Its existing settings (collection `plans`, billing group, button labels, styling) are untouched.

## 7. Out of scope

Dropped from the mockup, per user decision: header/nav bar (theme's real header already renders), the rotated membership-card graphic (no equivalent in the native block-based hero — text-only hero instead), floating monogram background decorations, "How it works" 3-step section, the fake DC-framework signup form (real conversion happens through the Supercycle block per §6), testimonials section, and FAQ accordion. Footer is the theme's existing global footer.

## 8. Testing

- Preview via `shopify theme dev` (run manually by the user — non-interactive contexts can't supply the storefront password) against the dev store, pointed at the worktree's theme path.
- Visually check: hero renders full-bleed brick background with working `#perks` and `#plans` anchor links; marquee scrolls continuously and matches homepage ticker styling; perks grid collapses to 1 column on mobile; Supercycle plans block still renders/functions where repositioned; closing CTA `#plans` anchor link works; page still reads correctly with the existing global header/footer around it.
- `shopify theme check --path theme/lms-redesign-v4` before pushing.
