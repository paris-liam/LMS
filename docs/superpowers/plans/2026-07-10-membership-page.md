# Membership Page Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `theme/lms-redesign-v4/templates/page.membership.json` with a hero, a scrolling marquee, a new "what you get" perks-grid section, and a closing CTA — pulled from `docs/become-a-member.dc.html` — while keeping the existing Supercycle `membership-plans` app block as the real conversion mechanism, just repositioned.

**Architecture:** Three of the four new page pieces are native Horizon sections used exactly as they already are elsewhere in this theme (`sections/hero.liquid` used twice — once as the page hero, once as a compact closing CTA — and `sections/marquee.liquid` used once, configured identically to the homepage's ticker). Only the "what you get" panel is new code: a bespoke section `sections/lms-perks-grid.liquid` following this theme's existing `lms-*` section conventions (design-token CSS variables, `contrast-override` snippet for text contrast, block-based repeatable items, matching `sections/lms-events-membership.liquid`'s structure).

**Tech Stack:** Shopify Liquid (Horizon OS 2.0 theme), JSON section/template data, `shopify theme check` for static validation, `shopify theme dev` for manual visual QA (no JS framework, no automated test runner — this theme has none, so "tests" in this plan are `theme check` runs plus a manual visual QA checklist).

## Global Constraints

- Work happens in a dedicated git worktree off `main` (per explicit user instruction) — see Task 0.
- Default target store for all preview/push commands is the dev store `lms-sandbox-lutsfahz.myshopify.com`. Never touch the production store (`p0wkgv-wy.myshopify.com`) as part of this plan.
- Do not create anything in the `supercycle` metafield namespace and do not add a second add-to-cart-style checkout button — not applicable to this page, but stays true project-wide per `CLAUDE.md`.
- Design tokens live in `theme/lms-redesign-v4/assets/lms-theme.css.liquid` — reuse existing `--lms-*` custom properties; do not invent new ones or hardcode raw hex values in new CSS (hex values are only used in JSON settings, matching how every other `lms-*` section instance configures its `background_color`).
- Follow existing `lms-*` section conventions exactly (see `sections/lms-events-membership.liquid`): render `contrast-override` for any section with a `background_color` setting, use the `lms-eyebrow` snippet for eyebrow text, wrap content in `.lms-container`, use `--lms-pad-top` / `--lms-pad-bottom` CSS custom properties driven by `padding-block-start` / `padding-block-end` settings, and match the `989px` / `549px` responsive breakpoints used throughout the theme.
- Every native section (`hero`, `marquee`) is configured purely through `templates/page.membership.json` block/setting data — no changes to `sections/hero.liquid` or `sections/marquee.liquid` themselves.
- Shopify auto-wraps every template-level JSON section in `<div id="shopify-section-{{ section.id }}">` — this is the anchor mechanism used for the hero's `#shopify-section-<key>` links; no section code needs to emit its own `id` attribute for this to work.

---

## Task 0: Set up the isolated worktree

**Files:** none (environment setup only)

- [ ] **Step 1: Set up an isolated worktree**

Use the `superpowers:using-git-worktrees` skill to create an isolated workspace off `main` for this feature (branch name suggestion: `worktree-membership-page`, matching the existing `worktree-shop-all-search-page` convention already in this repo). Follow that skill's detection/creation steps exactly (native tool first, `git worktree add` fallback second).

- [ ] **Step 2: Confirm the worktree is on the right branch and clean**

```bash
git status
git branch --show-current
```

Expected: branch is the new feature branch, working tree clean, based on latest `main`.

All remaining tasks in this plan operate inside that worktree's copy of `theme/lms-redesign-v4/`.

---

## Task 1: Create the "What you get" perks-grid section

**Files:**
- Create: `theme/lms-redesign-v4/sections/lms-perks-grid.liquid`

**Interfaces:**
- Consumes: `contrast-override` snippet (`theme/lms-redesign-v4/snippets/contrast-override.liquid`, params `background_color`, `section_id`), `lms-eyebrow` snippet (`theme/lms-redesign-v4/snippets/lms-eyebrow.liquid`, param `text`), design tokens from `theme/lms-redesign-v4/assets/lms-theme.css.liquid` (`--lms-brick`, `--lms-bg`, `--lms-border-default`, `--lms-border-width`, `--lms-radius-lg`, `--lms-shadow-xs`, `--lms-font-display`, `--lms-font-mono`, `--lms-fw-head-med`, `--lms-fw-head-semi`, `--lms-fw-mono-light`, `--lms-lh-tight`, `--lms-text-strong`, `--lms-text-muted`).
- Produces: a new section type `lms-perks-grid` with settings `eyebrow` (text), `heading` (text), `subheading` (text), `background_color` (color), `padding-block-start` / `padding-block-end` (range), and a repeatable block type `perk` with settings `number`, `title`, `body` (all text, max 6 blocks). Task 3 instantiates this section type by key `membership_perks` in `templates/page.membership.json`.

- [ ] **Step 1: Write the new section file**

```liquid
{% comment %}
  lms-perks-grid — centered eyebrow/heading/subheading, then a 3-column grid
  of numbered perk cards. Used for the membership page's "What you get" panel.
{% endcomment %}

{% render 'contrast-override', background_color: section.settings.background_color, section_id: section.id %}
<div class="lms-perks color-custom-{{ section.id }}"
  style="--lms-pad-top: {{ section.settings.padding-block-start }}px; --lms-pad-bottom: {{ section.settings.padding-block-end }}px;"
  {{ section.shopify_attributes }}>
  <div class="lms-container">
    <div class="lms-perks__header">
      {% render 'lms-eyebrow', text: section.settings.eyebrow %}
      {%- if section.settings.heading != blank -%}
        <h2 class="lms-perks__heading">{{ section.settings.heading }}</h2>
      {%- endif -%}
      {%- if section.settings.subheading != blank -%}
        <p class="lms-perks__subheading">{{ section.settings.subheading }}</p>
      {%- endif -%}
    </div>

    {%- if section.blocks.size > 0 -%}
      <div class="lms-perks__grid">
        {%- for block in section.blocks -%}
          <div class="lms-perks__card" {{ block.shopify_attributes }}>
            <div class="lms-perks__number">{{ block.settings.number }}</div>
            <h3 class="lms-perks__title">{{ block.settings.title }}</h3>
            <p class="lms-perks__body">{{ block.settings.body }}</p>
          </div>
        {%- endfor -%}
      </div>
    {%- endif -%}
  </div>
</div>

{% stylesheet %}
.lms-perks {
  background: var(--lms-bg, var(--lms-parchment));
  padding-block: var(--lms-pad-top, 84px) var(--lms-pad-bottom, 84px);
}
.lms-perks__header {
  text-align: center;
  max-width: 560px;
  margin: 0 auto 46px;
}
.lms-perks .lms-eyebrow { display: block; }
.lms-perks__heading {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 38px;
  line-height: var(--lms-lh-tight);
  color: var(--lms-text-strong);
  margin: 12px 0 12px;
}
.lms-perks__subheading {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 15px;
  line-height: 1.6;
  color: var(--lms-text-muted);
  margin: 0;
}
.lms-perks__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 22px;
}
.lms-perks__card {
  background: var(--lms-bg);
  border: var(--lms-border-width) solid var(--lms-border-default);
  border-radius: var(--lms-radius-lg);
  box-shadow: var(--lms-shadow-xs);
  padding: 32px 30px;
}
.lms-perks__number {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-semi);
  font-size: 34px;
  line-height: 1;
  color: var(--lms-brick);
  margin-bottom: 16px;
}
.lms-perks__title {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 20px;
  margin: 0 0 8px;
}
.lms-perks__body {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 13px;
  line-height: 1.6;
  color: var(--lms-text-muted);
  margin: 0;
}

@media screen and (max-width: 989px) {
  .lms-perks__grid { grid-template-columns: 1fr; }
}
@media screen and (max-width: 549px) {
  .lms-perks__header { margin-bottom: 32px; }
  .lms-perks__card { padding: 26px 24px; }
}
{% endstylesheet %}

{% schema %}
{
  "name": "LMS perks grid",
  "tag": "section",
  "class": "lms-perks-grid-section",
  "settings": [
    { "type": "header", "content": "Header" },
    { "type": "text", "id": "eyebrow", "label": "Eyebrow", "default": "What you get" },
    { "type": "text", "id": "heading", "label": "Heading", "default": "A year of belonging, for $100." },
    { "type": "text", "id": "subheading", "label": "Subheading", "default": "Six small reasons it pays to be a regular. Most members make the hundred back by spring." },
    { "type": "header", "content": "Section style" },
    { "type": "color", "id": "background_color", "label": "t:settings.background_color", "placeholder": "t:settings.default" },
    { "type": "range", "id": "padding-block-start", "label": "Top padding", "min": 0, "max": 100, "step": 4, "unit": "px", "default": 84 },
    { "type": "range", "id": "padding-block-end", "label": "Bottom padding", "min": 0, "max": 100, "step": 4, "unit": "px", "default": 84 }
  ],
  "blocks": [
    {
      "type": "perk",
      "name": "Perk",
      "settings": [
        { "type": "text", "id": "number", "label": "Number", "default": "01" },
        { "type": "text", "id": "title", "label": "Title", "default": "Perk title" },
        { "type": "text", "id": "body", "label": "Body", "default": "Perk description." }
      ]
    }
  ],
  "max_blocks": 6,
  "presets": [
    {
      "name": "LMS perks grid",
      "blocks": [
        { "type": "perk", "settings": { "number": "01", "title": "The rental library", "body": "Run of the whole borrow-buddy library, all year. Be our borrow buddy." } },
        { "type": "perk", "settings": { "number": "02", "title": "10% off everything", "body": "Every purchase, every visit, every format. No fine print." } },
        { "type": "perk", "settings": { "number": "03", "title": "A free birthday movie", "body": "Pick anything off the shelf on your birthday — it's on us." } },
        { "type": "perk", "settings": { "number": "04", "title": "Members events", "body": "First invites to screenings, closet tours, and movie nights." } },
        { "type": "perk", "settings": { "number": "05", "title": "First dibs on drops", "body": "Shop the weekly drop and mystery bags before they hit the floor." } },
        { "type": "perk", "settings": { "number": "06", "title": "Bring a friend", "body": "A guest pass so you never have to come browse alone." } }
      ]
    }
  ]
}
{% endschema %}
```

- [ ] **Step 2: Run theme check to verify the new section is valid**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors reported against `sections/lms-perks-grid.liquid` (pre-existing warnings elsewhere in the theme, if any, are unrelated and out of scope).

- [ ] **Step 3: Commit**

```bash
git add theme/lms-redesign-v4/sections/lms-perks-grid.liquid
git commit -m "Add lms-perks-grid section for membership page 'what you get' panel"
```

---

## Task 2: Add the Hero and Marquee sections to the membership template

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json`

**Interfaces:**
- Consumes: native `sections/hero.liquid` (settings: `content_direction`, `horizontal_alignment_flex_direction_column`, `vertical_alignment_flex_direction_column`, `gap`, `section_width`, `section_height`, `background_color`, `padding-block-start`, `padding-block-end`; block types `text` with settings `text` (richtext HTML string), `width`, `max_width`, `type_preset`; block type `button` with settings `label`, `link`, `style_class`) and native `sections/marquee.liquid` (settings: `movement_direction`, `background_color`, `padding-block-start`, `padding-block-end`, `gap_between_elements`; block type `text` — the marquee's item/separator blocks must carry the *full* field set (`text`, `width`, `max_width`, `alignment`, `type_preset`, `font`, `font_size`, `line_height`, `letter_spacing`, `case`, `wrap`, `text_color`, `background`, `background_color`, `corner_radius`, all four `padding-*` fields, plus an empty `blocks: {}`) copied verbatim from the homepage's `lms_ticker` section instance in `templates/index.json` — only the `text` and separator `text_color` differ. Only `text_color` is honored outside the `custom` type-preset per `snippets/text.liquid`, but the rest are copied anyway to exactly match the known-working homepage pattern rather than relying on unverified default fallbacks.).
- Produces: template section keys `membership_hero` and `membership_marquee`, added to the `order` array. Task 3 inserts `membership_perks`, repositions the existing `1780928794877ebf06` key, and appends `membership_closing_cta` — all relative to these two keys.

The current file (read before editing — do not guess at whitespace):

```json
{
  "sections": {
    "main": {
      "type": "main-page",
      "settings": {
        "content_direction": "column",
        "gap": 32,
        "background_color": "",
        "padding-block-start": 40,
        "padding-block-end": 80
      }
    },
    "1780928794877ebf06": {
      "type": "_blocks",
      "blocks": { "...": "unchanged, see file" },
      "block_order": ["supercycle_membership_plans_MdRHJR"],
      "settings": { "...": "unchanged, see file" }
    }
  },
  "order": ["main", "1780928794877ebf06"]
}
```

- [ ] **Step 1: Insert the `membership_hero` and `membership_marquee` sections**

Edit `theme/lms-redesign-v4/templates/page.membership.json`. Add these two new entries inside `"sections": { ... }`, alongside the existing `"main"` and `"1780928794877ebf06"` keys (exact placement within the object doesn't matter — JSON object key order is irrelevant; the `order` array controls render order, updated in Step 2):

```json
    "membership_hero": {
      "type": "hero",
      "blocks": {
        "eyebrow": {
          "type": "text",
          "settings": {
            "text": "<p>Little Movie Club · $100/year</p>",
            "width": "fit-content",
            "max_width": "normal",
            "type_preset": "h6"
          }
        },
        "heading": {
          "type": "text",
          "settings": {
            "text": "<p>Become a member.</p>",
            "width": "fit-content",
            "max_width": "narrow",
            "type_preset": "h1"
          }
        },
        "body": {
          "type": "text",
          "settings": {
            "text": "<p>The club isn't really about the perks — it's about belonging to a place that's as much yours as it is ours. One flat year. Renters become buyers. That's the whole game, baby.</p>",
            "width": "fit-content",
            "max_width": "narrow",
            "type_preset": "rte"
          }
        },
        "button_primary": {
          "type": "button",
          "settings": {
            "label": "Become a member",
            "link": "#shopify-section-1780928794877ebf06",
            "style_class": "button"
          }
        },
        "button_secondary": {
          "type": "button",
          "settings": {
            "label": "See what's included ↓",
            "link": "#shopify-section-membership_perks",
            "style_class": "button-unstyled"
          }
        },
        "fine_print": {
          "type": "text",
          "settings": {
            "text": "<p>No app. No fine print. Cancel anytime — just bring yourself.</p>",
            "width": "fit-content",
            "max_width": "narrow",
            "type_preset": "rte"
          }
        }
      },
      "block_order": ["eyebrow", "heading", "body", "button_primary", "button_secondary", "fine_print"],
      "settings": {
        "content_direction": "column",
        "horizontal_alignment_flex_direction_column": "flex-start",
        "vertical_alignment_flex_direction_column": "center",
        "gap": 20,
        "section_width": "page-width",
        "section_height": "auto",
        "background_color": "#973123",
        "padding-block-start": 72,
        "padding-block-end": 60
      }
    },
    "membership_marquee": {
      "type": "marquee",
      "blocks": {
        "item_1": { "type": "text", "settings": { "text": "<p>Rental library</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_1": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "item_2": { "type": "text", "settings": { "text": "<p>10% off everything</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_2": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "item_3": { "type": "text", "settings": { "text": "<p>Free birthday movie</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_3": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "item_4": { "type": "text", "settings": { "text": "<p>Members events</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_4": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "item_5": { "type": "text", "settings": { "text": "<p>First dibs on drops</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_5": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "item_6": { "type": "text", "settings": { "text": "<p>Bring a friend</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "0.18em", "case": "uppercase", "wrap": "pretty", "text_color": "", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} },
        "sep_6": { "type": "text", "settings": { "text": "<p>✦</p>", "width": "fit-content", "max_width": "normal", "alignment": "left", "type_preset": "rte", "font": "var(--font-body--family)", "font_size": "0.75rem", "line_height": "normal", "letter_spacing": "normal", "case": "none", "wrap": "pretty", "text_color": "#8fcdcf", "background": false, "background_color": "#00000026", "corner_radius": 0, "padding-block-start": 0, "padding-block-end": 0, "padding-inline-start": 0, "padding-inline-end": 0 }, "blocks": {} }
      },
      "block_order": ["item_1", "sep_1", "item_2", "sep_2", "item_3", "sep_3", "item_4", "sep_4", "item_5", "sep_5", "item_6", "sep_6"],
      "settings": {
        "movement_direction": "normal",
        "background_color": "#3a2018",
        "padding-block-start": 12,
        "padding-block-end": 12,
        "gap_between_elements": 22
      }
    },
```

- [ ] **Step 2: Update the `order` array**

Change:

```json
  "order": ["main", "1780928794877ebf06"]
```

to:

```json
  "order": ["main", "membership_hero", "membership_marquee", "1780928794877ebf06"]
```

(Task 3 will insert `membership_perks` before `1780928794877ebf06` and append `membership_closing_cta` after it.)

- [ ] **Step 3: Validate JSON and run theme check**

```bash
python3 -c "import json; json.load(open('theme/lms-redesign-v4/templates/page.membership.json'))" && echo "valid JSON"
shopify theme check --path theme/lms-redesign-v4
```

Expected: `valid JSON` printed, no new theme check errors.

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Add hero and marquee sections to the membership page"
```

---

## Task 3: Add the perks-grid section, reposition the Supercycle plans block, and add the closing CTA

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json`

**Interfaces:**
- Consumes: `lms-perks-grid` section type (from Task 1), `membership_hero` / `membership_marquee` keys (from Task 2), native `sections/hero.liquid` (same interface as Task 2).
- Produces: final section order for the membership page — `main → membership_hero → membership_marquee → membership_perks → 1780928794877ebf06 → membership_closing_cta`.

- [ ] **Step 1: Add the `membership_perks` section**

Add this entry inside `"sections": { ... }` (uses the `lms-perks-grid` section type and preset content defined in Task 1 — restated here explicitly, not relying on the schema `default`/preset values, since template JSON always specifies settings explicitly):

```json
    "membership_perks": {
      "type": "lms-perks-grid",
      "blocks": {
        "perk_1": { "type": "perk", "settings": { "number": "01", "title": "The rental library", "body": "Run of the whole borrow-buddy library, all year. Be our borrow buddy." } },
        "perk_2": { "type": "perk", "settings": { "number": "02", "title": "10% off everything", "body": "Every purchase, every visit, every format. No fine print." } },
        "perk_3": { "type": "perk", "settings": { "number": "03", "title": "A free birthday movie", "body": "Pick anything off the shelf on your birthday — it's on us." } },
        "perk_4": { "type": "perk", "settings": { "number": "04", "title": "Members events", "body": "First invites to screenings, closet tours, and movie nights." } },
        "perk_5": { "type": "perk", "settings": { "number": "05", "title": "First dibs on drops", "body": "Shop the weekly drop and mystery bags before they hit the floor." } },
        "perk_6": { "type": "perk", "settings": { "number": "06", "title": "Bring a friend", "body": "A guest pass so you never have to come browse alone." } }
      },
      "block_order": ["perk_1", "perk_2", "perk_3", "perk_4", "perk_5", "perk_6"],
      "settings": {
        "eyebrow": "What you get",
        "heading": "A year of belonging, for $100.",
        "subheading": "Six small reasons it pays to be a regular. Most members make the hundred back by spring.",
        "background_color": "",
        "padding-block-start": 84,
        "padding-block-end": 84
      }
    },
```

- [ ] **Step 2: Add the `membership_closing_cta` section**

Add this entry inside `"sections": { ... }`:

```json
    "membership_closing_cta": {
      "type": "hero",
      "blocks": {
        "heading": {
          "type": "text",
          "settings": {
            "text": "<p>Meet me at the movie store.</p>",
            "width": "100%",
            "max_width": "narrow",
            "alignment": "center",
            "type_preset": "h2"
          }
        },
        "body": {
          "type": "text",
          "settings": {
            "text": "<p>Built by movie lovers, for everyone. Come be a regular.</p>",
            "width": "100%",
            "max_width": "narrow",
            "alignment": "center",
            "type_preset": "rte"
          }
        },
        "button": {
          "type": "button",
          "settings": {
            "label": "Become a member · $100/yr",
            "link": "#shopify-section-1780928794877ebf06",
            "style_class": "button"
          }
        }
      },
      "block_order": ["heading", "body", "button"],
      "settings": {
        "content_direction": "column",
        "horizontal_alignment_flex_direction_column": "center",
        "vertical_alignment_flex_direction_column": "center",
        "gap": 20,
        "section_width": "page-width",
        "section_height": "small",
        "background_color": "#3a2018",
        "padding-block-start": 80,
        "padding-block-end": 80
      }
    },
```

- [ ] **Step 3: Update the `order` array to its final sequence**

Change:

```json
  "order": ["main", "membership_hero", "membership_marquee", "1780928794877ebf06"]
```

to:

```json
  "order": ["main", "membership_hero", "membership_marquee", "membership_perks", "1780928794877ebf06", "membership_closing_cta"]
```

- [ ] **Step 4: Validate JSON and run theme check**

```bash
python3 -c "import json; json.load(open('theme/lms-redesign-v4/templates/page.membership.json'))" && echo "valid JSON"
shopify theme check --path theme/lms-redesign-v4
```

Expected: `valid JSON` printed, no new theme check errors.

- [ ] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Add perks grid and closing CTA to membership page, reposition plans block"
```

---

## Task 4: Manual visual QA on the dev store

**Files:** none (verification only)

- [ ] **Step 1: Push the worktree's theme to the dev store as a preview (unpublished) theme**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --unpublished --theme "Membership page WIP"
```

Expected: command prints a preview URL for the new unpublished theme.

- [ ] **Step 2: Open the preview URL's `/pages/membership` in a browser and check the following**

- [ ] Hero renders full-bleed brick (`#973123`) background with eyebrow, "Become a member." heading, body copy, two buttons, and the fine-print line — no leftover media placeholder.
- [ ] Clicking "See what's included ↓" scrolls to the perks grid.
- [ ] Marquee scrolls continuously below the hero, mahogany background, matches the homepage ticker's visual style (uppercase, cyan `✦` separators).
- [ ] Perks grid shows 6 numbered cards in 3 columns on desktop, collapses to 1 column under ~989px (resize browser or use device toolbar).
- [ ] Supercycle membership-plans block renders and functions (plan cards visible, "Select plan" button present) directly below the perks grid.
- [ ] Clicking either "Become a member" button (hero or closing CTA) scrolls to the Supercycle plans block.
- [ ] Closing CTA renders centered on a mahogany background with "Meet me at the movie store." heading, body copy, and button, directly above the theme's real global footer.
- [ ] Theme's real header (not the mockup's fake header) still renders normally above the hero.

- [ ] **Step 3: Run theme check one final time across the whole theme**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: no errors introduced by this feature's files (pre-existing unrelated warnings, if any, are out of scope).

- [ ] **Step 4: Report results to the user**

Summarize the QA checklist results (pass/fail per item) and the preview URL. Do not push to the dev store's live working theme (`140918915134`) or merge/push the branch — that's a separate, explicit follow-up decision for the user.
