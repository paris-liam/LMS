# Membership hero floating card + Supercycle plans restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable floating membership-card theme block that auto-hides the hero's image when present, wire it into the membership page's hero, and restyle (without removing) the Supercycle plans app block section into a dark banner matching the page's closing CTA — including fixing its currently-dead `#plans` anchor link.

**Architecture:** Two independent, additive changes on top of the already-built (unmerged) membership page rebuild on branch `worktree-membership-page`: (1) a new global theme block (`blocks/lms-membership-card.liquid`) plus a two-line conditional edit to the shared `sections/hero.liquid`, and (2) settings-only edits to `templates/page.membership.json` (no section/block code changes) to restyle the existing Supercycle app block instance and add a tiny anchor-fix block.

**Tech Stack:** Shopify Liquid theme (Horizon OS 2.0, theme blocks architecture), `shopify theme check` for linting, `shopify theme dev` / `theme push` for preview against the dev store.

## Global Constraints

- Default target for all pushes/previews is the dev store `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`. Never target production (`p0wkgv-wy.myshopify.com`) without explicit instruction.
- Do not create or touch anything in the `supercycle.*` metafield namespace — it is app-reserved (`CLAUDE.md`).
- Never add a direct checkout/buy-button link to the Supercycle plan product — it bypasses membership activation and requires a manual refund to undo (`supercycle-explained.md`).
- Never surface individual `LMS-NNNNNNN`-style serial numbers on the storefront (`CLAUDE.md`) — the membership card must not include anything resembling a serial/member number.
- All work happens on git branch `worktree-membership-page` (already exists, has 3 prior commits implementing the hero/marquee/perks/CTA rebuild; not yet merged to `main`).
- `theme dev` cannot run in non-interactive tool contexts (it prompts for the storefront password) — any live preview is a manual step for the user, not an agent-executable step.
- `shopify theme check --path theme/lms-redesign-v4` must pass (no new errors) before any task is considered complete.

---

## File Structure

| File | Change |
|---|---|
| `theme/lms-redesign-v4/blocks/lms-membership-card.liquid` | **Create.** New global theme block: floating membership-card visual. |
| `theme/lms-redesign-v4/sections/hero.liquid` | **Modify.** Add block type to schema; hide `{{ media }}` when a `lms-membership-card` block is present. |
| `theme/lms-redesign-v4/templates/page.membership.json` | **Modify.** `membership_hero` → horizontal layout + card block. Supercycle section (`1780928794877ebf06`) → dark banner restyle + heading blocks + anchor-fix block + app block color/style settings. |

---

### Task 1: Worktree setup + create the floating membership-card block

**Files:**
- Create: `theme/lms-redesign-v4/blocks/lms-membership-card.liquid`

**Interfaces:**
- Produces: a theme block of type `lms-membership-card` with settings `card_est_text` (text, default `"Est. 2026"`) and `card_name_text` (text, default `"— your name here —"`). Root element renders with class `lms-membership-card`. Consumed by Task 2 (hero.liquid detects blocks of this type) and Task 3 (added as a block instance in `page.membership.json`).

- [ ] **Step 1: Create the worktree for branch `worktree-membership-page`**

```bash
git -C /Users/liamparis/web-projects/personal/LMS-sandbox worktree add .claude/worktrees/membership-hero-card-plans-restyle worktree-membership-page
```

Expected: `Preparing worktree (checking out 'worktree-membership-page')` followed by a `HEAD is now at <sha> ...` line. All subsequent steps run with working directory `/Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle`.

- [ ] **Step 2: Confirm the branch has the expected prior commits**

```bash
git -C /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle log --oneline -3
```

Expected: top commit is `51a2647 Add perks grid and closing CTA to membership page, reposition plans block` (or later).

- [ ] **Step 3: Create the new theme block file**

Create `theme/lms-redesign-v4/blocks/lms-membership-card.liquid` with this exact content:

```liquid
{% comment %}
  lms-membership-card — reusable theme block (/blocks). A "floating" variant
  of the .lms-member-card pattern already used in lms-events-membership.liquid
  (same brand/est/holder-label/holder-name structure), rotated with a
  stronger shadow for use inside a hero. Usable inside any section that
  accepts @theme blocks. When added to sections/hero.liquid specifically,
  its presence automatically hides that hero instance's configured
  image/video (see the has_membership_card check in hero.liquid).
{% endcomment %}

<div class="lms-membership-card" {{ block.shopify_attributes }}>
  <div class="lms-membership-card__top">
    <span class="lms-membership-card__brand">Little Movie Club</span>
    <span class="lms-membership-card__est">{{ block.settings.card_est_text }}</span>
  </div>
  <div class="lms-membership-card__holder">
    <div class="lms-membership-card__holder-label">Member</div>
    <div class="lms-membership-card__holder-name">{{ block.settings.card_name_text }}</div>
  </div>
</div>

{% stylesheet %}
.lms-membership-card {
  position: relative;
  width: 380px;
  max-width: 100%;
  flex-shrink: 0;
  align-self: center;
  background: var(--lms-surface-inverse);
  border-radius: var(--lms-radius-sm);
  padding: 24px;
  box-shadow: var(--lms-shadow-lg);
  overflow: hidden;
  transform: rotate(-4deg);
}
.lms-membership-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.lms-membership-card__brand {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-med);
  font-size: 10px;
  letter-spacing: var(--lms-tracking-eyebrow);
  text-transform: uppercase;
  color: var(--lms-cyan);
}
.lms-membership-card__est {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 11px;
  color: color-mix(in oklch, var(--lms-text-on-dark) 60%, transparent);
}
.lms-membership-card__holder { margin-top: 26px; }
.lms-membership-card__holder-label {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: color-mix(in oklch, var(--lms-text-on-dark) 55%, transparent);
  margin-bottom: 5px;
}
.lms-membership-card__holder-name {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 22px;
  color: var(--lms-text-on-dark);
  line-height: var(--lms-lh-tight);
}
@media screen and (max-width: 549px) {
  .lms-membership-card {
    width: 100%;
    max-width: 320px;
    transform: none;
  }
}
{% endstylesheet %}

{% schema %}
{
  "name": "LMS membership card",
  "settings": [
    { "type": "header", "content": "Content" },
    {
      "type": "text",
      "id": "card_est_text",
      "label": "Card corner text",
      "default": "Est. 2026"
    },
    {
      "type": "text",
      "id": "card_name_text",
      "label": "Card sample name",
      "default": "— your name here —",
      "info": "Placeholder name shown on the floating card."
    }
  ],
  "presets": [
    { "name": "LMS membership card" }
  ]
}
{% endschema %}
```

- [ ] **Step 4: Run theme check to verify the new block is valid**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors referencing `lms-membership-card.liquid` (pre-existing warnings elsewhere in the theme, if any, are not this task's concern).

- [ ] **Step 5: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
git add theme/lms-redesign-v4/blocks/lms-membership-card.liquid
git commit -m "Add lms-membership-card theme block for the floating hero card"
```

---

### Task 2: Wire the card block into `sections/hero.liquid`

**Files:**
- Modify: `theme/lms-redesign-v4/sections/hero.liquid:1-10` (top `{% liquid %}` block) and `theme/lms-redesign-v4/sections/hero.liquid:523-528` (blocks schema array)

**Interfaces:**
- Consumes: block type `lms-membership-card` (from Task 1).
- Produces: `has_membership_card` Liquid variable (boolean-ish integer count) used only within this file; any hero instance with a `lms-membership-card` block present will render with no image/video, regardless of what's configured in `image_1`/`video_1`/etc.

- [ ] **Step 1: Add the `has_membership_card` check to the top liquid block**

In `theme/lms-redesign-v4/sections/hero.liquid`, find:

```liquid
{% liquid
  assign media_count = 0
  assign media_count_mobile = 0
  assign fallback_to_desktop = false
  assign media_1 = 'none'
  assign media_2 = 'none'
  assign media_1_mobile = 'none'
  assign media_2_mobile = 'none'
  assign has_only_video = false
  assign has_only_video_mobile = false
```

Replace with:

```liquid
{% liquid
  assign media_count = 0
  assign media_count_mobile = 0
  assign fallback_to_desktop = false
  assign media_1 = 'none'
  assign media_2 = 'none'
  assign media_1_mobile = 'none'
  assign media_2_mobile = 'none'
  assign has_only_video = false
  assign has_only_video_mobile = false
  assign has_membership_card = section.blocks | where: 'type', 'lms-membership-card' | size
```

- [ ] **Step 2: Add the block type to the section's schema `blocks` array**

Find:

```json
  "blocks": [
    {
      "type": "@theme"
    },
    {
      "type": "text"
    },
    {
      "type": "button"
    },
    {
      "type": "logo"
    },
    {
      "type": "jumbo-text"
    },
    {
      "type": "spacer"
    },
    {
      "type": "group"
    },
    {
      "type": "_marquee"
    }
  ],
```

Replace with:

```json
  "blocks": [
    {
      "type": "@theme"
    },
    {
      "type": "text"
    },
    {
      "type": "button"
    },
    {
      "type": "logo"
    },
    {
      "type": "jumbo-text"
    },
    {
      "type": "spacer"
    },
    {
      "type": "group"
    },
    {
      "type": "lms-membership-card"
    },
    {
      "type": "_marquee"
    }
  ],
```

- [ ] **Step 3: Wrap the `{{ media }}` output**

Find:

```liquid
      {% liquid
        if section.settings.toggle_overlay
          render 'overlay', settings: section.settings
        endif
      %}
      {{ media }}
    </div>
```

Replace with:

```liquid
      {% liquid
        if section.settings.toggle_overlay
          render 'overlay', settings: section.settings
        endif
      %}
      {%- unless has_membership_card > 0 -%}{{ media }}{%- endunless -%}
    </div>
```

- [ ] **Step 4: Run theme check**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors referencing `hero.liquid`.

- [ ] **Step 5: Verify the file still has exactly one `{{ media }}` reference and it's the wrapped one**

```bash
grep -n "{{ media }}" theme/lms-redesign-v4/sections/hero.liquid
```

Expected: one line, showing `{%- unless has_membership_card > 0 -%}{{ media }}{%- endunless -%}`.

- [ ] **Step 6: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
git add theme/lms-redesign-v4/sections/hero.liquid
git commit -m "Hide hero image/video when a lms-membership-card block is present"
```

---

### Task 3: Configure the membership page hero to use the floating card

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json` (the `membership_hero` section object)

**Interfaces:**
- Consumes: block type `lms-membership-card` with settings `card_est_text`, `card_name_text` (Task 1); `has_membership_card` behavior in `hero.liquid` (Task 2).
- Produces: the live membership page hero instance, rendered horizontally with the card visible and no image.

- [ ] **Step 1: Locate and update the `membership_hero` section's `blocks`, `block_order`, and `settings.content_direction`**

In `theme/lms-redesign-v4/templates/page.membership.json`, find the `membership_hero` section object. Its `"blocks"` object currently ends with:

```json
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
        "hide_placeholder_when_empty": true,
        "text_color": "#fff9ef",
        "padding-block-start": 72,
        "padding-block-end": 60
      }
    },
```

Replace with:

```json
        "fine_print": {
          "type": "text",
          "settings": {
            "text": "<p>No app. No fine print. Cancel anytime — just bring yourself.</p>",
            "width": "fit-content",
            "max_width": "narrow",
            "type_preset": "rte"
          }
        },
        "membership_card": {
          "type": "lms-membership-card",
          "settings": {
            "card_est_text": "Est. 2026",
            "card_name_text": "— your name here —"
          }
        }
      },
      "block_order": ["eyebrow", "heading", "body", "button_primary", "button_secondary", "fine_print", "membership_card"],
      "settings": {
        "content_direction": "horizontal",
        "horizontal_alignment_flex_direction_column": "flex-start",
        "vertical_alignment_flex_direction_column": "center",
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

(`content_direction` changed `column` → `horizontal`; `gap` bumped `20` → `40` to give the card breathing room next to the text column; new `membership_card` block added to both `blocks` and `block_order`.)

- [ ] **Step 2: Validate JSON syntax**

`page.membership.json` has a leading `/* ... */` comment block (like `config/settings_data.json`), so it isn't parseable as strict JSON directly — strip the header first:

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
python3 -c "
import re
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
import json
json.loads(content)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors referencing `page.membership.json` or `hero.liquid`.

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Show the floating membership card in the membership page hero"
```

---

### Task 4: Restyle the Supercycle plans section into a dark banner + fix the `#plans` anchor

**Files:**
- Modify: `theme/lms-redesign-v4/templates/page.membership.json` (the section keyed `1780928794877ebf06`)

**Interfaces:**
- Consumes: `blocks/custom-liquid.liquid` (existing theme block, setting id `custom_liquid`, type `liquid`) for the anchor fix; native `text` theme block (existing, settings `text`, `width`, `max_width`, `alignment`, `type_preset`) for the two heading blocks.
- Produces: the live "Choose your plan" banner, with a working `#plans` scroll target, restyled Supercycle plan cards.

- [ ] **Step 1: Replace the section's `blocks`, `block_order`, and `settings`**

In `theme/lms-redesign-v4/templates/page.membership.json`, find the section keyed `"1780928794877ebf06"`:

```json
    "1780928794877ebf06": {
      "type": "_blocks",
      "blocks": {
        "supercycle_membership_plans_MdRHJR": {
          "type": "shopify://apps/supercycle/blocks/membership-plans/7b3228ed-a72a-4935-9fee-0cebe8daa0aa",
          "settings": {
            "collection": "plans",
            "groups": "billing",
            "value_labels": "",
            "credit_name": "items",
            "redirect_to_last_product_page": true,
            "redirect_type": "custom",
            "redirect_url": "",
            "create_account": false,
            "button_label": "Select plan",
            "membership_in_cart_message": "A membership is already in cart",
            "button_class": "button button--secondary",
            "primary_button_class": "button button--primary",
            "color_background": "#ffffff",
            "color_plan_background": "#f5f5f5",
            "color_plan_text": "#000000",
            "color_plan_border": "#000000",
            "plan_border_radius": 8,
            "space": 20,
            "padding_top": 40,
            "padding_bottom": 52,
            "template": "<p class=\"h2 plan-card-title\">[plan_title]</p>\n<p class=\"h1 plan-card-price\">[plan_price]</p>\n<p class=\"plan-card-interval\">Billed [plan_billing_interval]</p>\n<p class=\"plan-card-credits h3\">\n  [plan_credit_allowance] {{block.settings.credit_name}}\n</p>\n<div class=\"plan-card-features rte\">[plan_description]</div>\n<div class=\"plan-card-button\">\n  [plan_button]\n</div>",
            "custom_css": ""
          }
        }
      },
      "block_order": [
        "supercycle_membership_plans_MdRHJR"
      ],
      "settings": {
        "content_direction": "column",
        "vertical_on_mobile": true,
        "horizontal_alignment": "flex-start",
        "vertical_alignment": "center",
        "align_baseline": false,
        "horizontal_alignment_flex_direction_column": "flex-start",
        "vertical_alignment_flex_direction_column": "center",
        "gap": 12,
        "section_width": "page-width",
        "section_height": "",
        "section_height_custom": 50,
        "background_media": "none",
        "background_color": "",
        "video_position": "cover",
        "background_image_position": "cover",
        "toggle_overlay": false,
        "overlay_color": "#00000026",
        "overlay_style": "solid",
        "gradient_direction": "to top",
        "border": "none",
        "border_width": 1,
        "border_opacity": 100,
        "border_color": "",
        "border_radius": 0,
        "padding-block-start": 0,
        "padding-block-end": 0
      }
    },
```

Replace with:

```json
    "1780928794877ebf06": {
      "type": "_blocks",
      "blocks": {
        "plans_anchor": {
          "type": "custom-liquid",
          "settings": {
            "custom_liquid": "<span id=\"plans\"></span>"
          }
        },
        "plans_eyebrow": {
          "type": "text",
          "settings": {
            "text": "<p>Little Movie Club</p>",
            "width": "100%",
            "max_width": "narrow",
            "alignment": "center",
            "type_preset": "h6"
          }
        },
        "plans_heading": {
          "type": "text",
          "settings": {
            "text": "<p>Pick your plan.</p>",
            "width": "100%",
            "max_width": "narrow",
            "alignment": "center",
            "type_preset": "h2"
          }
        },
        "supercycle_membership_plans_MdRHJR": {
          "type": "shopify://apps/supercycle/blocks/membership-plans/7b3228ed-a72a-4935-9fee-0cebe8daa0aa",
          "settings": {
            "collection": "plans",
            "groups": "billing",
            "value_labels": "",
            "credit_name": "items",
            "redirect_to_last_product_page": true,
            "redirect_type": "custom",
            "redirect_url": "",
            "create_account": false,
            "button_label": "Select plan",
            "membership_in_cart_message": "A membership is already in cart",
            "button_class": "button button--secondary",
            "primary_button_class": "button button--primary",
            "color_background": "#3a2018",
            "color_plan_background": "#fff9ef",
            "color_plan_text": "#3a2018",
            "color_plan_border": "#8fcdcf",
            "plan_border_radius": 4,
            "space": 20,
            "padding_top": 40,
            "padding_bottom": 52,
            "template": "<p class=\"h2 plan-card-title\">[plan_title]</p>\n<p class=\"h1 plan-card-price\">[plan_price]</p>\n<p class=\"plan-card-interval\">Billed [plan_billing_interval]</p>\n<p class=\"plan-card-credits h3\">\n  [plan_credit_allowance] {{block.settings.credit_name}}\n</p>\n<div class=\"plan-card-features rte\">[plan_description]</div>\n<div class=\"plan-card-button\">\n  [plan_button]\n</div>",
            "custom_css": ".plan-card-title { font-family: var(--lms-font-display); } .plan-card-price, .plan-card-interval, .plan-card-credits, .plan-card-features, .plan-card-button { font-family: var(--lms-font-mono); }"
          }
        }
      },
      "block_order": [
        "plans_anchor",
        "plans_eyebrow",
        "plans_heading",
        "supercycle_membership_plans_MdRHJR"
      ],
      "settings": {
        "content_direction": "column",
        "vertical_on_mobile": true,
        "horizontal_alignment": "flex-start",
        "vertical_alignment": "center",
        "align_baseline": false,
        "horizontal_alignment_flex_direction_column": "center",
        "vertical_alignment_flex_direction_column": "center",
        "gap": 12,
        "section_width": "page-width",
        "section_height": "",
        "section_height_custom": 50,
        "background_media": "none",
        "background_color": "#3a2018",
        "video_position": "cover",
        "background_image_position": "cover",
        "toggle_overlay": false,
        "overlay_color": "#00000026",
        "overlay_style": "solid",
        "gradient_direction": "to top",
        "border": "none",
        "border_width": 1,
        "border_opacity": 100,
        "border_color": "",
        "border_radius": 0,
        "padding-block-start": 80,
        "padding-block-end": 80
      }
    },
```

Changes: added `plans_anchor` (fixes the dead `#plans` link), `plans_eyebrow` + `plans_heading` (banner-style heading, centered), restyled the Supercycle block's colors/radius/`custom_css` for a parchment-on-mahogany look, changed `horizontal_alignment_flex_direction_column` to `center`, `background_color` to `#3a2018`, and top/bottom padding to `80`. All other Supercycle block settings (`collection`, `groups`, `redirect_to_last_product_page`, `redirect_type`, `button_label`, `template` structure, etc.) are untouched.

- [ ] **Step 2: Validate JSON syntax**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
python3 -c "
import re
with open('theme/lms-redesign-v4/templates/page.membership.json') as f:
    content = f.read()
content = re.sub(r'^\s*/\*.*?\*/\s*', '', content, count=1, flags=re.DOTALL)
import json
json.loads(content)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Confirm the anchor and Supercycle functional settings are intact**

```bash
grep -n '"id=\\"plans\\"' theme/lms-redesign-v4/templates/page.membership.json
grep -n '"collection": "plans"' theme/lms-redesign-v4/templates/page.membership.json
grep -n '"redirect_to_last_product_page": true' theme/lms-redesign-v4/templates/page.membership.json
```

Expected: all three greps return one match each.

- [ ] **Step 4: Run theme check**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors referencing `page.membership.json`.

- [ ] **Step 5: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
git add theme/lms-redesign-v4/templates/page.membership.json
git commit -m "Restyle Supercycle plans section into a dark banner and fix #plans anchor"
```

---

### Task 5: Push to the dev store for preview

**Files:** none (deployment step only)

**Interfaces:** none — this task pushes the worktree's committed theme files to the dev store's working theme so the changes can be previewed in a browser.

- [ ] **Step 1: Push the theme files to the dev store**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox/.claude/worktrees/membership-hero-card-plans-restyle
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only sections/hero.liquid --only blocks/lms-membership-card.liquid --only templates/page.membership.json
```

Expected: push summary listing the three uploaded files with no errors.

- [ ] **Step 2: Hand off manual preview to the user**

Tell the user: preview requires `shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com` (or the storefront directly, since password protection may already be handled), run by them — it prompts for the storefront password interactively and fails in non-interactive contexts. Ask them to check on `/pages/membership` (or whatever the page's handle is):
- Hero: brick background, text on the left, rotated membership card on the right, no image showing.
- Clicking "Become a member" / "See what's included ↓"-style links: `#plans` scrolls to the new dark "Pick your plan." banner.
- Supercycle plan cards render as parchment cards on the mahogany banner, with the LMS mono/display fonts applied, and plan selection still works (add to cart / redirect).

- [ ] **Step 3: No commit for this task** (deployment only, nothing to commit).

---

## Self-Review

**Spec coverage:**
- §1a (new block, reused `.lms-member-card` pattern, no serial number, `card_est_text`/`card_name_text` settings) → Task 1. ✅
- §1b (blocks schema entry + conditional `{{ media }}` wrap in `hero.liquid`) → Task 2. ✅
- §1c (`content_direction: horizontal`, card block appended to `membership_hero`) → Task 3. ✅
- §2a (dark background, centered, 80px padding on the Supercycle wrapper section) → Task 4. ✅
- §2b (eyebrow + heading text blocks before the Supercycle block) → Task 4. ✅
- §2c (Supercycle block color/radius/`custom_css` restyle, functional settings untouched) → Task 4. ✅
- §2d (`#plans` anchor fix via `custom-liquid` block) → Task 4. ✅
- §3 out-of-scope items (no checkout links, no `supercycle.*` namespace changes, `lms-events-membership.liquid`/perks-grid/marquee/closing-CTA untouched) → respected; no task touches those files. ✅
- §4 testing (theme check, visual check, plan-flow check) → Task 5 + theme-check steps folded into Tasks 1–4. ✅

**Placeholder scan:** no TBD/TODO markers; every step has literal file content or literal commands with expected output.

**Type/id consistency:** block type `lms-membership-card` and settings `card_est_text` / `card_name_text` match exactly between Task 1 (block definition), Task 2 (`where: 'type', 'lms-membership-card'` filter), and Task 3 (JSON block instance). Anchor id `plans` matches between Task 4's `custom-liquid` block content and the pre-existing `href="#plans"` links already present in `membership_hero`'s `button_primary` and `membership_closing_cta`'s `button` blocks (unmodified by this plan).
