# Membership page follow-up fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship five small, independent fixes to the already-live membership page: close the hero/header gap, add an opt-in background-monogram decoration to the hero, switch the hero to a sage background so the (globally brick) primary button is visible, drop the closing CTA section, and give the Supercycle plan card visible shadow/padding chrome.

**Architecture:** All changes are settings/markup edits to two files already touched in the prior round: `theme/lms-redesign-v4/sections/hero.liquid` (one additive checkbox + conditional markup + scoped CSS, same low-risk pattern as the prior floating-card work) and `theme/lms-redesign-v4/templates/page.membership.json` (settings-only edits, no new sections). Plus 3 new static SVG assets copied from `docs/assets/monograms/`.

**Tech Stack:** Shopify Liquid theme (Horizon OS 2.0, theme blocks architecture), `shopify theme check` for linting, `shopify theme push` for deploying to the dev store.

## Global Constraints

- Default target for all pushes/previews is the dev store `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134` (currently the **live** theme there — pushes need `--allow-live` and a quick confirmation, per prior round). Never target production (`p0wkgv-wy.myshopify.com`) without explicit instruction.
- Do not touch the Supercycle app block's functional settings (`collection`, `groups`, `redirect_to_last_product_page`, `button_label`, `template` structure) or anything in the `supercycle.*` metafield namespace.
- No direct Supercycle checkout links — confirmed unsupported (see memory `supercycle-checkout-link-not-supported`).
- All work happens on a new git worktree off `main` (this feature was never given its own branch name in brainstorming — create `membership-page-followup-fixes` as both branch and worktree directory name).
- `shopify theme check --path theme/lms-redesign-v4` baseline is 2 errors (expected — Supercycle app-block file references that only exist on Shopify's side) + 7 warnings, all pre-existing and unrelated to this work. Any task's changes must not add to this count.
- `page.membership.json` has a leading `/* ... */` comment header (not valid JSON as-is) — strip it before parsing with `json.loads`, same as `config/settings_data.json`.

---

## File Structure

| File | Change |
|---|---|
| `theme/lms-redesign-v4/assets/lms-monogram-tape-parchment.svg` | **Create.** Copied from `docs/assets/monograms/tape-parchment.svg`. |
| `theme/lms-redesign-v4/assets/lms-monogram-circles-parchment.svg` | **Create.** Copied from `docs/assets/monograms/circles-parchment.svg`. |
| `theme/lms-redesign-v4/assets/lms-monogram-looped-parchment.svg` | **Create.** Copied from `docs/assets/monograms/looped-parchment.svg`. |
| `theme/lms-redesign-v4/sections/hero.liquid` | **Modify.** Add `show_background_monograms` checkbox setting, conditional monogram markup, scoped CSS. |
| `theme/lms-redesign-v4/templates/page.membership.json` | **Modify.** `main` padding, `membership_hero` settings, remove `membership_closing_cta`, Supercycle block style settings. |

---

### Task 1: Worktree setup + close the hero/header gap

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json` (`main` section settings)

**Interfaces:** None — self-contained settings change.

- [ ] **Step 1: Create the worktree**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
git worktree add -b membership-page-followup-fixes .claude/worktrees/membership-page-followup-fixes main
```

Expected: `Preparing worktree (new branch 'membership-page-followup-fixes')` followed by a checkout confirmation. All subsequent steps run with working directory `/Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes`.

- [ ] **Step 2: Zero out the `main` section's padding**

In `theme/lms-redesign-v4/templates/page.membership.json`, find:

```json
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
```

Replace with:

```json
    "main": {
      "type": "main-page",
      "settings": {
        "content_direction": "column",
        "gap": 32,
        "background_color": "",
        "padding-block-start": 0,
        "padding-block-end": 0
      }
    },
```

- [ ] **Step 3: Validate JSON syntax**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
python3 -c "
import re, json
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
json.loads(content)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: same baseline (2 errors, 7 warnings) as noted in Global Constraints — no new offenses referencing `page.membership.json`.

- [ ] **Step 5: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Remove empty main-section padding causing hero/header gap on membership page"
```

---

### Task 2: Add monogram assets and wire an opt-in background-monogram setting into hero.liquid

**Files:**
- Create: `theme/lms-redesign-v4/assets/lms-monogram-tape-parchment.svg`
- Create: `theme/lms-redesign-v4/assets/lms-monogram-circles-parchment.svg`
- Create: `theme/lms-redesign-v4/assets/lms-monogram-looped-parchment.svg`
- Modify: `theme/lms-redesign-v4/sections/hero.liquid`

**Interfaces:**
- Produces: schema setting `show_background_monograms` (checkbox, default `false`) on the `hero` section. When `true`, renders 3 absolutely-positioned, floating monogram icons behind the hero's content. Consumed by Task 3 (enabling it on the membership page hero).

- [ ] **Step 1: Copy the 3 SVG assets**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
cp ../../../docs/assets/monograms/tape-parchment.svg theme/lms-redesign-v4/assets/lms-monogram-tape-parchment.svg
cp ../../../docs/assets/monograms/circles-parchment.svg theme/lms-redesign-v4/assets/lms-monogram-circles-parchment.svg
cp ../../../docs/assets/monograms/looped-parchment.svg theme/lms-redesign-v4/assets/lms-monogram-looped-parchment.svg
```

(Paths are relative to the worktree root at `.claude/worktrees/membership-page-followup-fixes/`, three levels below the repo root where `docs/` lives — adjust `../../../` if your shell's cwd differs; verify with `ls docs/assets/monograms/tape-parchment.svg` from the repo root first if unsure.)

- [ ] **Step 2: Verify the copies**

```bash
ls -la theme/lms-redesign-v4/assets/lms-monogram-*.svg
```

Expected: 3 files listed, non-zero size.

- [ ] **Step 3: Add the `show_background_monograms` schema setting**

In `theme/lms-redesign-v4/sections/hero.liquid`, find:

```json
    {
      "type": "video",
      "id": "video_2_mobile",
      "label": "t:settings.video",
      "visible_if": "{{ section.settings.custom_mobile_media and section.settings.media_type_2_mobile == 'video' }}"
    },
    {
      "type": "header",
      "content": "t:content.section_link"
    },
```

Replace with:

```json
    {
      "type": "video",
      "id": "video_2_mobile",
      "label": "t:settings.video",
      "visible_if": "{{ section.settings.custom_mobile_media and section.settings.media_type_2_mobile == 'video' }}"
    },
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
    },
    {
      "type": "header",
      "content": "t:content.section_link"
    },
```

- [ ] **Step 4: Add the conditional monogram markup**

In the same file, find:

```liquid
  {% if request.visual_preview_mode %}
    data-shopify-visual-preview
  {% endif %}
  {% if section.settings.blurred_reflection and has_only_video == false or has_only_video_mobile == false %}
    data-blur-shadow="true"
  {% endif %}
>
  {% if section.settings.blurred_reflection %}
```

Replace with:

```liquid
  {% if request.visual_preview_mode %}
    data-shopify-visual-preview
  {% endif %}
  {% if section.settings.blurred_reflection and has_only_video == false or has_only_video_mobile == false %}
    data-blur-shadow="true"
  {% endif %}
>
  {%- if section.settings.show_background_monograms -%}
    <div class="hero__monograms" aria-hidden="true">
      <img src="{{ 'lms-monogram-tape-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--tape" loading="lazy" width="120" height="60">
      <img src="{{ 'lms-monogram-circles-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--circles" loading="lazy" width="96" height="96">
      <img src="{{ 'lms-monogram-looped-parchment.svg' | asset_url }}" alt="" class="hero__monogram hero__monogram--looped" loading="lazy" width="78" height="78">
    </div>
  {%- endif -%}
  {% if section.settings.blurred_reflection %}
```

- [ ] **Step 5: Add the scoped CSS**

In the same file, find the end of the `{% stylesheet %}` block:

```css
      &:last-child {
        right: 0;
        left: auto;
      }
    }
  }
{% endstylesheet %}
```

Replace with:

```css
      &:last-child {
        right: 0;
        left: auto;
      }
    }
  }

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
{% endstylesheet %}
```

- [ ] **Step 6: Run theme check**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
shopify theme check --path theme/lms-redesign-v4
```

Expected: same baseline (2 errors, 7 warnings) — no new offenses referencing `hero.liquid` or the new asset files.

- [ ] **Step 7: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
git add theme/lms-redesign-v4/assets/lms-monogram-tape-parchment.svg \
        theme/lms-redesign-v4/assets/lms-monogram-circles-parchment.svg \
        theme/lms-redesign-v4/assets/lms-monogram-looped-parchment.svg \
        theme/lms-redesign-v4/sections/hero.liquid
git commit -m "Add opt-in background-monogram decoration to the hero section"
```

---

### Task 3: Enable monograms and switch the membership hero background to sage

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json` (`membership_hero.settings`)

**Interfaces:**
- Consumes: `show_background_monograms` checkbox (Task 2).
- Produces: the live membership hero rendered with sage background and floating monogram decoration.

- [ ] **Step 1: Update `membership_hero.settings`**

In `theme/lms-redesign-v4/templates/page.membership.json`, find:

```json
      "block_order": ["copy_group", "membership_card"],
      "settings": {
        "content_direction": "row",
        "horizontal_alignment": "space-between",
        "vertical_alignment": "center",
        "gap": 40,
        "section_width": "page-width",
        "section_height": "auto",
        "background_color": "#973123",
        "hide_placeholder_when_empty": true,
        "text_color": "#fff9ef",
        "padding-block-start": 72,
        "padding-block-end": 60
      }
    },
```

Replace with:

```json
      "block_order": ["copy_group", "membership_card"],
      "settings": {
        "content_direction": "row",
        "horizontal_alignment": "space-between",
        "vertical_alignment": "center",
        "gap": 40,
        "section_width": "page-width",
        "section_height": "auto",
        "background_color": "#5f8d7a",
        "hide_placeholder_when_empty": true,
        "text_color": "#fff9ef",
        "show_background_monograms": true,
        "padding-block-start": 72,
        "padding-block-end": 60
      }
    },
```

(`background_color` changed `#973123` → `#5f8d7a`; added `"show_background_monograms": true`. `text_color` stays `#fff9ef` — it renders an explicit `--color` CSS custom property per `sections/hero.liquid:466`, so it is not affected by the background-color change.)

- [ ] **Step 2: Validate JSON syntax**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
python3 -c "
import re, json
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
json.loads(content)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: same baseline (2 errors, 7 warnings).

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Switch membership hero to sage background and enable monograms"
```

---

### Task 4: Remove the closing CTA section

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json`

**Interfaces:** None — deletion only.

- [ ] **Step 1: Remove the `membership_closing_cta` section object**

In `theme/lms-redesign-v4/templates/page.membership.json`, find:

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
            "link": "#plans",
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
        "hide_placeholder_when_empty": true,
        "text_color": "#fff9ef",
        "padding-block-start": 80,
        "padding-block-end": 80
      }
    }
  },
  "order": [
    "main",
    "membership_hero",
    "membership_marquee",
    "membership_perks",
    "1780928794877ebf06",
    "membership_closing_cta"
  ]
}
```

Replace with:

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
    }
  },
  "order": [
    "main",
    "membership_hero",
    "membership_marquee",
    "membership_perks",
    "1780928794877ebf06"
  ]
}
```

**Important:** this replacement re-states the (unchanged) `membership_perks` section immediately before it — the actual edit is (a) deleting the entire `"membership_closing_cta": { ... }` object and the comma that preceded it, and (b) dropping `"membership_closing_cta"` from the `"order"` array. The `membership_perks` block is shown only to anchor the match precisely (its content does not change); if applying by hand rather than via exact string replacement, do not re-type `membership_perks` — just delete `membership_closing_cta` and its trailing/leading comma, and remove its entry from `order`.

- [ ] **Step 2: Validate JSON syntax**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
python3 -c "
import re, json
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
data = json.loads(content)
assert 'membership_closing_cta' not in data['sections'], 'closing CTA section still present'
assert 'membership_closing_cta' not in data['order'], 'closing CTA still in order array'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: same baseline (2 errors, 7 warnings).

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Remove the membership page closing CTA section"
```

---

### Task 5: Give the Supercycle plan card visible chrome

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json` (block `supercycle_membership_plans_MdRHJR` inside section `1780928794877ebf06`)

**Interfaces:** None — settings-only change to the app block's own exposed style fields.

- [ ] **Step 1: Update `plan_border_radius` and append to `custom_css`**

In `theme/lms-redesign-v4/templates/page.membership.json`, find:

```json
            "color_plan_border": "#8fcdcf",
            "plan_border_radius": 4,
            "space": 20,
            "padding_top": 40,
            "padding_bottom": 52,
            "template": "<p class=\"h2 plan-card-title\">[plan_title]</p>\n<p class=\"h1 plan-card-price\">[plan_price]</p>\n<p class=\"plan-card-interval\">Billed [plan_billing_interval]</p>\n<p class=\"plan-card-credits h3\">\n  [plan_credit_allowance] {{block.settings.credit_name}}\n</p>\n<div class=\"plan-card-features rte\">[plan_description]</div>\n<div class=\"plan-card-button\">\n  [plan_button]\n</div>",
            "custom_css": ".plan-card-title { font-family: var(--lms-font-display); } .plan-card-price, .plan-card-interval, .plan-card-credits, .plan-card-features, .plan-card-button { font-family: var(--lms-font-mono); }"
```

Replace with:

```json
            "color_plan_border": "#8fcdcf",
            "plan_border_radius": 8,
            "space": 20,
            "padding_top": 40,
            "padding_bottom": 52,
            "template": "<p class=\"h2 plan-card-title\">[plan_title]</p>\n<p class=\"h1 plan-card-price\">[plan_price]</p>\n<p class=\"plan-card-interval\">Billed [plan_billing_interval]</p>\n<p class=\"plan-card-credits h3\">\n  [plan_credit_allowance] {{block.settings.credit_name}}\n</p>\n<div class=\"plan-card-features rte\">[plan_description]</div>\n<div class=\"plan-card-button\">\n  [plan_button]\n</div>",
            "custom_css": ".plan-card-title { font-family: var(--lms-font-display); } .plan-card-price, .plan-card-interval, .plan-card-credits, .plan-card-features, .plan-card-button { font-family: var(--lms-font-mono); } .plan-card-wrapper { box-shadow: 0 1px 2px rgba(58, 32, 24, 0.08); padding: 32px 30px; }"
```

(`plan_border_radius`: `4` → `8`. `custom_css` gains a `.plan-card-wrapper` rule — this is the real, confirmed DOM class for each plan's outer card element, verified via live browser inspection in the design phase, not a guessed selector. The shadow value is `--lms-shadow-xs`'s literal value; the app block's injected `<style>` may not resolve theme `:root` CSS custom properties reliably, so the literal is used defensively — see Step 3.)

- [ ] **Step 2: Validate JSON syntax**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
python3 -c "
import re, json
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
json.loads(content)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: same baseline (2 errors, 7 warnings).

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Add shadow and padding chrome to the Supercycle plan card"
```

---

### Task 6: Push to the dev store for preview

**Files:** none (deployment step only)

**Interfaces:** none — pushes the worktree's committed changes to the dev store's live working theme.

- [ ] **Step 1: Push the changed files**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-page-followup-fixes
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --allow-live \
  --only sections/hero.liquid \
  --only templates/page.membership.json \
  --only assets/lms-monogram-tape-parchment.svg \
  --only assets/lms-monogram-circles-parchment.svg \
  --only assets/lms-monogram-looped-parchment.svg
```

Expected: `The theme '...' (#140918915134) was pushed successfully.`

- [ ] **Step 2: Hand off manual visual verification to the user**

Tell the user: preview at `https://lms-sandbox-lutsfahz.myshopify.com/pages/membership` (storefront password required — see memory `dev-store-storefront-password` if browsing directly, or `shopify theme dev` run by the user themselves since it needs an interactive terminal for the password prompt). Ask them to confirm:
- No gap between the header and the hero.
- Three monogram icons float gently behind the hero content, not overlapping the copy or the membership card.
- Hero background is sage; "Become a member" button is clearly visible in brick against it.
- Page ends at the "Pick your plan." banner — no "Meet me at the movie store" band below it.
- The Supercycle plan card has a visible shadow and more internal padding, reading as a page-native card rather than a flat embed. If the shadow doesn't render, the `var(--lms-shadow-xs)` concern from Task 5 was correct for the *literal* value not resolving either — flag this back for a follow-up fix rather than assuming it's cosmetic.

- [ ] **Step 3: No commit for this task** (deployment only, nothing to commit).

---

## Self-Review

**Spec coverage:**
- §1 (close hero/header gap) → Task 1. ✅
- §2a (SVG assets), §2b (hero.liquid checkbox/markup/CSS), §2c (enable on membership page) → Tasks 2 and 3. ✅
- §3 (hero background → sage, text_color unaffected) → Task 3. ✅
- §4 (remove closing CTA) → Task 4. ✅
- §5 (plan card chrome: border radius + custom_css shadow/padding via confirmed `.plan-card-wrapper`) → Task 5. ✅
- Out-of-scope items (no Supercycle functional/namespace changes, no checkout link, no changes to `lms-perks-grid.liquid`/marquee/floating-card block itself) → respected; no task touches those.
- Testing (theme check per task, full visual check) → Task 6 + theme-check steps folded into each task.

**Placeholder scan:** no TBD/TODO markers; every step has literal file content or literal commands with expected output. Task 4's replacement block includes a note explaining why `membership_perks` appears in both old/new strings (anchor for precise matching, not a re-edit) — this is a deliberate clarification, not a placeholder.

**Type/id consistency:** `show_background_monograms` checkbox id matches exactly between Task 2 (schema definition + markup conditional) and Task 3 (JSON instance setting `true`). Asset filenames (`lms-monogram-tape-parchment.svg`, etc.) match exactly between Task 2's `cp` commands, the `asset_url` references in the markup, and Task 6's `--only` push flags. `.plan-card-wrapper` selector in Task 5 matches the class confirmed live during the design/brainstorming phase (not re-derived or guessed here).
