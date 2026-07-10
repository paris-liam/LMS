# Shop-All Catalog Page (Sidebar Filtering) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated "Shop everything" catalog page for the LMS Shopify storefront, with a sidebar-filtered product grid (Format, Genre, Boutique label, New arrivals, Supercycle rental Availability) and a search box that hands off to the existing site-search flow.

**Architecture:** A new alternate collection template (`templates/collection.shop-all.json`) reuses the existing `main-collection` section and `filters` block, driven entirely by config where possible (vertical filter style, infinite scroll are existing settings). Two shared Liquid files gain small, settings-gated additions: `sections/main-collection.liquid` gets an opt-in poster-card rendering path and an empty-state branch; `blocks/filters.liquid` gets an opt-in search input with filter-carryover, gated behind `filter_style == 'vertical'` so horizontal (all other) collection pages are unaffected. Supercycle's Methods filter app block is configured separately in the Shopify admin/theme editor (no code changes to add the block itself, only CSS to hide the native filter it replaces).

**Tech Stack:** Shopify Horizon theme (Liquid, OS 2.0 JSON templates/sections/blocks), Shopify CLI (`shopify theme dev` / `theme check`), Shopify Search & Discovery app, Supercycle app blocks. No JS unit test framework exists in this repo — "tests" in this plan mean `shopify theme check` (static lint) plus manual verification in a running `shopify theme dev` preview, checking exact URLs/selectors called out per step.

## Global Constraints

- Default target store for all work: dev store `lms-sandbox-lutsfahz.myshopify.com`. Never touch production (`p0wkgv-wy.myshopify.com`) as part of this plan.
- Never create anything under the `supercycle` metafield namespace by hand — only `custom.*` for our own stand-ins/fields. (`supercycle.methods` is the one exception: it's a Supercycle-defined metafield we *enable filtering on*, not create data under.)
- Do not touch `theme/lms-redesign/` (retired) or `theme/horizon-baseline-3.5.1/` (read-only reference) — all edits go in `theme/lms-redesign-v4/`.
- Do not modify `sections/search-results.liquid`, `templates/collection.json`, or any other collection's rendering — every code change must be gated so it only activates for `collection.shop-all.json`.
- Run `shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com` yourself in your own terminal for manual verification steps (it prompts for the storefront password interactively and fails in non-interactive contexts).

---

### Task 1: Product metafield definitions and Search & Discovery filters (admin runbook)

**Files:** None — this task is Shopify Admin configuration, no repo changes. It unblocks Tasks 3–7, which reference these fields.

**Interfaces:**
- Produces: `product.metafields.custom.genre` (List of single line text, filterable), `product.metafields.custom.label` (Single line text, filterable), `product.metafields.custom.format` and `product.metafields.custom.condition` marked filterable (they already exist, used by `lms-product-card.liquid`), a `new-arrival` product tag applied to at least 2 test products, and four Search & Discovery filter sources: Format, Genre, Boutique label, Product tag (scoped to `new-arrival`).

- [ ] **Step 1: Create the `custom.genre` metafield definition**

In Shopify Admin (dev store) → Settings → Custom data → Products → Add definition:
- Name: `Genre`
- Namespace and key: `custom.genre`
- Type: List of single line text
- Enable: "Filter on the product list" (this is the "Storefront filtering" toggle in Search & Discovery-integrated stores — if the toggle is labeled differently, enable whichever option exposes it as a filter source in the Search & Discovery app)

- [ ] **Step 2: Create the `custom.label` metafield definition**

Same location, Add definition:
- Name: `Boutique label`
- Namespace and key: `custom.label`
- Type: Single line text
- Enable filtering, same as Step 1.

- [ ] **Step 3: Enable filtering on the existing `custom.format` and `custom.condition` definitions**

Settings → Custom data → Products → find `custom.format` and `custom.condition` (already exist, used by `snippets/lms-product-card.liquid`) → edit each → enable "Filter on the product list" if not already on.

- [ ] **Step 4: Set genre and label values, and the `new-arrival` tag, on at least 5 test products**

For at least 5 products in the dev store, set `custom.genre` (1–2 values each, e.g. `Drama`, `Horror`, `Sci-Fi`) and `custom.label` (e.g. `Criterion`, `Arrow Video`). Tag at least 2 of them with `new-arrival` (Product → Organization → Tags). This gives Task 9's manual QA something real to filter against.

- [ ] **Step 5: Add filter sources in the Search & Discovery app**

Shopify Admin → Apps → Search & Discovery → Filters → Add filter, once for each:
- Source: Format (`custom.format`)
- Source: Genre (`custom.genre`)
- Source: Boutique label (`custom.label`)
- Source: Product tag — in the tag-selection step, restrict it to only the `new-arrival` value if the app allows scoping a tag filter to specific tag values; otherwise add it unscoped and note in Task 7 that the sidebar will show all tags, not just `new-arrival` (flag this back to the user if the scoping option isn't available — it changes Task 7's CSS-targeting approach).

Save changes before leaving the app.

- [ ] **Step 6: Verify**

On any existing collection page in the theme editor preview (e.g. the default `collection.json` template on any collection with tagged/metafielded products), confirm the horizontal filter bar now shows Format, Genre, Boutique label, and a tag filter as options (their presence confirms the filter sources are live — the *visual* vertical-sidebar version comes in later tasks).

---

### Task 2: Create the shop-all alternate template

**Files:**
- Create: `theme/lms-redesign-v4/templates/collection.shop-all.json`

**Interfaces:**
- Consumes: `sections/main-collection.liquid` (existing, section type `main-collection`), `blocks/filters.liquid` (existing block type `filters`).
- Produces: the alternate template file, assignable to a collection from Shopify Admin. Does not yet render poster cards or the sidebar search box — those depend on Tasks 3 and 5, wired in via the settings this task turns on.

- [ ] **Step 1: Write the template JSON**

Base this on `theme/lms-redesign-v4/templates/collection.json` (read it first to confirm current structure hasn't changed), with three differences: `filter_style` set to `"vertical"`, `enable_grid_density` set to `false` (poster cards aren't block-based, so there's nothing for grid density to resize — see Task 3), and a new `product_card_style: "poster"` section setting (defined in Task 3) turned on.

```json
/*
 * ------------------------------------------------------------
 * IMPORTANT: The contents of this file are auto-generated.
 *
 * This file may be updated by the Shopify admin theme editor
 * or related systems. Please exercise caution as any changes
 * made to this file may be overwritten.
 * ------------------------------------------------------------
 */{
  "sections": {
    "section": {
      "type": "section",
      "blocks": {
        "text_tqQTNE": {
          "type": "text",
          "name": "Title",
          "settings": {
            "text": "<h1>{{ closest.collection.title }}</h1>",
            "width": "fit-content",
            "max_width": "normal",
            "alignment": "left",
            "type_preset": "h2",
            "font": "var(--font-primary--family)",
            "font_size": "",
            "line_height": "normal",
            "letter_spacing": "normal",
            "case": "none",
            "wrap": "pretty",
            "text_color": "",
            "background": false,
            "background_color": "#00000026",
            "corner_radius": 0,
            "padding-block-start": 0,
            "padding-block-end": 0,
            "padding-inline-start": 0,
            "padding-inline-end": 0
          },
          "blocks": {}
        },
        "text_twGGkJ": {
          "type": "text",
          "name": "Description",
          "settings": {
            "text": "{{ closest.collection.description }}",
            "width": "fit-content",
            "max_width": "normal",
            "alignment": "left",
            "type_preset": "rte",
            "font": "var(--font-primary--family)",
            "font_size": "",
            "line_height": "normal",
            "letter_spacing": "normal",
            "case": "none",
            "wrap": "pretty",
            "text_color": "",
            "background": false,
            "background_color": "#00000026",
            "corner_radius": 0,
            "padding-block-start": 0,
            "padding-block-end": 0,
            "padding-inline-start": 0,
            "padding-inline-end": 0
          },
          "blocks": {}
        }
      },
      "block_order": ["text_tqQTNE", "text_twGGkJ"],
      "name": "Collection heading",
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
        "video_position": "cover",
        "background_image_position": "cover",
        "border": "none",
        "border_width": 1,
        "border_opacity": 100,
        "border_radius": 0,
        "toggle_overlay": false,
        "overlay_color": "#00000026",
        "overlay_style": "solid",
        "gradient_direction": "to top",
        "padding-block-start": 48,
        "padding-block-end": 48
      }
    },
    "main": {
      "type": "main-collection",
      "blocks": {
        "filters": {
          "type": "filters",
          "static": true,
          "settings": {
            "enable_filtering": true,
            "filter_style": "vertical",
            "filter_width": "centered",
            "text_label_case": "default",
            "show_swatch_label": false,
            "show_filter_label": false,
            "enable_sorting": true,
            "enable_grid_density": false,
            "show_search_input": true,
            "search_input_placeholder": "Search titles, directors…",
            "padding-block-start": 8,
            "padding-block-end": 8,
            "padding-inline-start": 0,
            "padding-inline-end": 0,
            "facets_margin_bottom": 8,
            "facets_margin_right": 20
          },
          "blocks": {}
        }
      },
      "settings": {
        "layout_type": "grid",
        "product_card_size": "medium",
        "mobile_product_card_size": "small",
        "product_grid_width": "centered",
        "full_width_on_mobile": true,
        "columns_gap_horizontal": 16,
        "columns_gap_vertical": 24,
        "padding-inline-start": 0,
        "padding-inline-end": 0,
        "padding-block-start": 0,
        "padding-block-end": 32,
        "enable_infinite_scroll": true,
        "product_card_style": "poster"
      }
    }
  },
  "order": ["section", "main"]
}
```

Note there is no `"product-card"` block under `"main"` — `product_card_style: "poster"` (added to `main-collection.liquid`'s schema in Task 3) makes the section render `lms-product-card.liquid` directly instead of looking for a `_product-card` block, so that block entry is intentionally omitted here.

- [ ] **Step 2: Verify the file is valid JSON**

Run: `python3 -m json.tool theme/lms-redesign-v4/templates/collection.shop-all.json > /dev/null && echo VALID`

Note the leading `/* ... */` comment block is the same pattern already used by every generated template in this theme (see `templates/collection.json`) — Shopify's editor tooling handles it, but if you re-run the JSON validator later, strip the comment first (same caveat as `config/settings_data.json`, documented in `CLAUDE.md`).

Expected: `VALID` printed (after temporarily stripping the leading comment for the validator — the comment itself is not valid JSON on its own, this check is just confirming the `{...}` body parses).

- [ ] **Step 3: Commit**

```bash
git add theme/lms-redesign-v4/templates/collection.shop-all.json
git commit -m "Add shop-all alternate collection template"
```

---

### Task 3: Poster-card rendering and empty-state in main-collection.liquid

**Files:**
- Modify: `theme/lms-redesign-v4/sections/main-collection.liquid`

**Interfaces:**
- Consumes: `snippets/lms-product-card.liquid` (existing, `{% render 'lms-product-card', card_product: product %}`), `section.settings.product_card_style` (new setting this task adds).
- Produces: `section.settings.product_card_style` (select: `"native"` default / `"poster"`) — consumed by Task 2's template JSON.

- [ ] **Step 1: Add the `product_card_style` setting to the section schema**

In `theme/lms-redesign-v4/sections/main-collection.liquid`, inside the `{% schema %}` block's `"settings"` array, add a new entry. Insert it right after the `"layout_type"` setting (find `"id": "layout_type"` — it's the first setting in the array) and before `"product_card_size"`:

```json
    {
      "type": "select",
      "id": "product_card_style",
      "label": "Product card style",
      "options": [
        {
          "value": "native",
          "label": "Native (theme-editor configurable)"
        },
        {
          "value": "poster",
          "label": "Poster (lms-product-card, fixed layout)"
        }
      ],
      "default": "native"
    },
```

- [ ] **Step 2: Branch the card rendering on the new setting**

Find this block (around line 60–77 in the current file):

```liquid
      {% paginate collection.products by products_per_page %}
        {% capture children %}
          {% for product in collection.products %}
            <li
              id="{{ section.id }}-{{ product.id }}"
              class="product-grid__item product-grid__item--{{ forloop.index0 }}"
              data-page="{{ paginate.current_page }}"
              data-product-id="{{ product.id }}"
              ref="cards[]"
            >
              {% content_for 'block',
                type: '_product-card',
                id: 'product-card',
                closest.product: product,
                product_view_context: 'collection'
              %}
            </li>
          {% endfor %}
        {% endcapture %}
```

Replace the `<li>` body's card rendering with a branch on `section.settings.product_card_style`:

```liquid
      {% paginate collection.products by products_per_page %}
        {% capture children %}
          {% for product in collection.products %}
            <li
              id="{{ section.id }}-{{ product.id }}"
              class="product-grid__item product-grid__item--{{ forloop.index0 }}"
              data-page="{{ paginate.current_page }}"
              data-product-id="{{ product.id }}"
              ref="cards[]"
            >
              {% if section.settings.product_card_style == 'poster' %}
                {% render 'lms-product-card', card_product: product %}
              {% else %}
                {% content_for 'block',
                  type: '_product-card',
                  id: 'product-card',
                  closest.product: product,
                  product_view_context: 'collection'
                %}
              {% endif %}
            </li>
          {% endfor %}
        {% endcapture %}
```

- [ ] **Step 3: Add an empty-state branch for zero-result collections**

Find the section's outermost wrapper — the `<div class="collection-wrapper ...">` that contains the `content_for 'block', type: 'filters'` call and the `{% paginate %}` block (around lines 43–87). Wrap the existing `{% paginate collection.products by products_per_page %}...{% endpaginate %}` block in a check for `collection.products_count`, so a filtered-to-zero result shows a message instead of an empty grid. Replace:

```liquid
      {% assign products_per_page = 24 %}

      {% if section.settings.enable_infinite_scroll == false %}
        {% assign products_per_page = section.settings.products_per_page %}
      {% endif %}

      {% paginate collection.products by products_per_page %}
```

with:

```liquid
      {% assign products_per_page = 24 %}

      {% if section.settings.enable_infinite_scroll == false %}
        {% assign products_per_page = section.settings.products_per_page %}
      {% endif %}

      {% if collection.products_count == 0 %}
        <div class="collection-empty-state" role="status">
          <p>{{ 'content.no_products_found' | t }}</p>
        </div>
      {% endif %}

      {% paginate collection.products by products_per_page %}
```

Leave the rest of the `{% paginate %}...{% endpaginate %}` block as-is — when `products_count` is 0 it still runs (looping zero times), just now with the message rendered above it instead of a silent empty grid.

- [ ] **Step 4: Check the `content.no_products_found` translation key exists**

Run: `grep -r "no_products_found" theme/lms-redesign-v4/locales/en.default.json`

Expected: a match. If there's no match, use whatever equivalent key `search-results.liquid`'s empty-state path already relies on instead (re-check `theme/lms-redesign-v4/sections/search-results.liquid` and its `content_for 'block', type: 'filters'` empty-state handling from `templates/search.json`'s `empty_state_collection` reference) — do not invent a new key without adding it to `locales/en.default.json` first.

- [ ] **Step 5: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`

Expected: no new errors introduced by this file (pre-existing warnings elsewhere in the theme are not this task's concern — confirm by re-running against a clean git stash if unsure whether a warning is pre-existing).

- [ ] **Step 6: Commit**

```bash
git add theme/lms-redesign-v4/sections/main-collection.liquid
git commit -m "Add poster-card rendering path and empty-state to main-collection section"
```

---

### Task 4: Search input and filter carryover in the vertical filters block

**Files:**
- Modify: `theme/lms-redesign-v4/blocks/filters.liquid`

**Interfaces:**
- Consumes: `filters` (Liquid variable already assigned in this file at the top, `assign filters = filters | default: results.filters`), `results.terms` (blank on collection pages, populated on search pages).
- Produces: `block_settings.show_search_input` and `block_settings.search_input_placeholder` (new schema settings) — consumed by Task 2's template JSON.

- [ ] **Step 1: Add the two new schema settings**

In `theme/lms-redesign-v4/blocks/filters.liquid`, inside `{% schema %}`'s `"settings"` array, insert right after the `"filter_style"` setting entry (the one with `"id": "filter_style"`) and before `"filter_width"`:

```json
    {
      "type": "checkbox",
      "id": "show_search_input",
      "label": "Show search input above filters",
      "default": false,
      "visible_if": "{{ block.settings.enable_filtering == true and block.settings.filter_style == 'vertical' }}"
    },
    {
      "type": "text",
      "id": "search_input_placeholder",
      "label": "Search input placeholder",
      "default": "Search titles, directors…",
      "visible_if": "{{ block.settings.show_search_input == true }}"
    },
```

- [ ] **Step 2: Render the search form above the vertical sidebar**

Find this line (the vertical-style top control bar's closing `{% endif %}`, immediately before the sidebar wrapper div begins):

```liquid
  {% endif %}

  <div
    class="
      {% if should_show_pane == false %}
        hidden
      {% endif %}
      facets-block-wrapper
```

Insert a new block right after that `{% endif %}` and before the `<div class="facets-block-wrapper...">`:

```liquid
  {% endif %}

  {% if block_settings.filter_style == 'vertical' and block_settings.show_search_input %}
    <form
      method="get"
      action="/search"
      class="facets-search-form"
    >
      <input type="hidden" name="options[prefix]" value="last">
      {%- for filter in filters -%}
        {%- case filter.type -%}
          {%- when 'price_range' -%}
            {%- if filter.min_value.value != null -%}
              <input type="hidden" name="{{ filter.min_value.param_name }}" value="{{ filter.min_value.value }}">
            {%- endif -%}
            {%- if filter.max_value.value != null -%}
              <input type="hidden" name="{{ filter.max_value.param_name }}" value="{{ filter.max_value.value }}">
            {%- endif -%}
          {%- else -%}
            {%- for value in filter.active_values -%}
              <input type="hidden" name="{{ value.param_name }}" value="{{ value.value }}">
            {%- endfor -%}
        {%- endcase -%}
      {%- endfor -%}
      <input
        type="search"
        name="q"
        value="{{ results.terms | escape }}"
        placeholder="{{ block_settings.search_input_placeholder }}"
        class="facets-search-form__input"
        aria-label="{{ 'content.search_input_label' | t }}"
      >
    </form>
  {% endif %}

  <div
    class="
      {% if should_show_pane == false %}
        hidden
      {% endif %}
      facets-block-wrapper
```

- [ ] **Step 3: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`

Expected: no new errors from this file.

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Add optional search input with filter-carryover to vertical filters block"
```

---

### Task 5: Restyle vertical facets and product grid to LMS design tokens

**Files:**
- Modify: `theme/lms-redesign-v4/blocks/filters.liquid`
- Modify: `theme/lms-redesign-v4/sections/main-collection.liquid`

**Interfaces:**
- Consumes: `--lms-brick`, `--lms-mahogany`, `--lms-sage`, `--lms-sage-dark`, `--lms-parchment`, `--lms-parchment-2`, `--lms-ink-700`, `--lms-ink-500`, `--lms-ink-300` (existing tokens, defined in `assets/lms-tokens.css`, loaded globally per `CLAUDE.md`).
- Produces: none consumed by later tasks — this is a leaf styling task.

- [ ] **Step 1: Append vertical-facet styling to `blocks/filters.liquid`'s existing `{% stylesheet %}` block**

Every rule here is scoped under `.facets--vertical`, which only renders when `filter_style == 'vertical'` (i.e., only on `collection.shop-all.json` today) — this cannot leak into any other collection page. Find the closing `{% endstylesheet %}` at the end of `theme/lms-redesign-v4/blocks/filters.liquid` and insert the following rules immediately before it:

```css
  /* LMS shop-all: vertical sidebar restyle */
  .facets--vertical {
    font-family: var(--lms-font-mono, monospace);
  }

  .facets--vertical .facets__label {
    font-weight: 500;
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--lms-mahogany);
  }

  .facets--vertical .checkbox .icon-checkmark {
    border-radius: 4px;
    border-color: var(--lms-ink-300);
  }

  .facets--vertical .checkbox__input:checked + .checkbox__label .icon-checkmark {
    background-color: var(--lms-sage);
    border-color: var(--lms-sage);
  }

  .facets--vertical .checkbox__label-text {
    font-family: var(--lms-font-mono, monospace);
    font-weight: 300;
    font-size: 14px;
    color: var(--lms-ink-700) !important;
  }

  .facets-search-form {
    margin-block-end: var(--gap-lg, 24px);
  }

  .facets-search-form__input {
    width: 100%;
    height: 48px;
    padding-inline: 16px;
    border: 1.5px solid var(--lms-ink-300);
    border-radius: 999px;
    background: var(--lms-parchment);
    font-family: var(--lms-font-mono, monospace);
    font-size: 14px;
    color: var(--lms-ink-700);
  }

  .facets-search-form__input:focus-visible {
    outline: 2px solid var(--lms-sage);
    outline-offset: 2px;
  }

  /* New-arrivals tag filter rendered as a pill toggle switch instead of a checkbox.
     Targets the checkbox by its `value` attribute since the tag filter's
     param_name is shared across all tag values (see Task 1, Step 5's
     scoping note if this selector ever needs to change). */
  .facets--vertical .checkbox:has(input[value='new-arrival']) {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .facets--vertical input[value='new-arrival'] {
    appearance: none;
    width: 42px;
    height: 24px;
    border-radius: 999px;
    background: var(--lms-ink-300);
    position: relative;
    cursor: pointer;
    transition: background-color 140ms ease;
  }

  .facets--vertical input[value='new-arrival']::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--lms-parchment);
    transition: left 140ms ease;
  }

  .facets--vertical input[value='new-arrival']:checked {
    background: var(--lms-sage);
  }

  .facets--vertical input[value='new-arrival']:checked::after {
    left: 20px;
  }
```

- [ ] **Step 2: Append active-filter-chip and grid styling to `sections/main-collection.liquid`**

This file has no existing `{% stylesheet %}` block — add one at the very end of the file, after the closing `{% endschema %}`:

```liquid
{% stylesheet %}
  [data-product-card-style='poster'] .product-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(208px, 1fr));
    gap: 28px 24px;
  }

  .collection-empty-state {
    padding-block: 48px;
    text-align: center;
    font-family: var(--lms-font-mono, monospace);
    color: var(--lms-ink-500);
  }
{% endstylesheet %}
```

- [ ] **Step 3: Add the `data-product-card-style` attribute the CSS above targets**

Find the `<results-list ...>` opening tag near the top of `main-collection.liquid` (added in Task 3's context, unchanged element otherwise):

```liquid
<collection-component view-event-payload="{{ collection | standard_event_data: 'view' | escape }}">
  <results-list
    class="section product-grid-container{% if section.settings.background_color != blank %} color-custom-{{ section.id }}{% endif %}"
    style="--padding-block-start: {{ section.settings.padding-block-start }}px; --padding-block-end: {{ section.settings.padding-block-end }}px;"
    section-id="{{ section.id }}"
    infinite-scroll="{{ section.settings.enable_infinite_scroll }}"
  >
```

Add the data attribute:

```liquid
<collection-component view-event-payload="{{ collection | standard_event_data: 'view' | escape }}">
  <results-list
    class="section product-grid-container{% if section.settings.background_color != blank %} color-custom-{{ section.id }}{% endif %}"
    style="--padding-block-start: {{ section.settings.padding-block-start }}px; --padding-block-end: {{ section.settings.padding-block-end }}px;"
    section-id="{{ section.id }}"
    infinite-scroll="{{ section.settings.enable_infinite_scroll }}"
    data-product-card-style="{{ section.settings.product_card_style }}"
  >
```

- [ ] **Step 4: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`

Expected: no new errors from either modified file.

- [ ] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/blocks/filters.liquid theme/lms-redesign-v4/sections/main-collection.liquid
git commit -m "Restyle vertical facets and poster-card grid to LMS design tokens"
```

---

### Task 6: Push to dev store and assign the template

**Files:** None — deployment and admin config.

**Interfaces:** None.

- [ ] **Step 1: Push the theme to the dev store**

Run (in your own terminal, or confirm with the user before running — this pushes to the shared dev store working theme):

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
```

- [ ] **Step 2: Assign the alternate template to the All products collection**

Shopify Admin → Products → Collections → open the "All" / "All products" collection (create it first via a smart collection with no conditions if it doesn't already exist) → Theme template dropdown → select `collection.shop-all`. Save.

- [ ] **Step 3: Verify in the theme editor preview**

Open the collection in the theme customizer preview. Confirm:
- Filters render as a left sidebar, not a horizontal bar.
- A search input appears above the filter list.
- Products render as 2:3 poster cards (title, director, price, format/condition badges), not the native card layout.
- Scrolling to the bottom of the grid loads more products automatically (no "Load more" button).

---

### Task 7: Supercycle Methods filter block setup (admin runbook + CSS)

**Files:**
- Modify: `theme/lms-redesign-v4/blocks/filters.liquid`

**Interfaces:**
- Consumes: the live `filter.param_name` for the "Rental availability" Search & Discovery filter — only knowable once Step 4 below has been done against the real store, since Shopify generates it from the filter's underlying resource.

- [ ] **Step 1: Confirm Search & Discovery is installed**

Already required by Task 1; if the dev store doesn't have it, install via https://apps.shopify.com/search-and-discovery before continuing.

- [ ] **Step 2: Create the `supercycle.methods` metafield definition**

Shopify Admin → Settings → Custom data → Products → View unstructured metafields → find `supercycle.methods` → Add definition. Set Type: List of single line text. Enable "Filter on the product list and in the Admin API" and "Use as a condition in smart collections." Save.

- [ ] **Step 3: Add Rental availability and Supercycle Methods filters in Search & Discovery**

Apps → Search & Discovery → Filters → Add filter → source **Rental availability** → save. Add filter again → source **Supercycle Methods** → save.

- [ ] **Step 4: Find the collection.shop-all section ID**

Shopify Admin → Online Store → Customize → open the shop-all collection page. Open browser DevTools → Network tab → clear the log → toggle any existing filter (e.g. Format) on the live preview to trigger a filter network request → find the request containing `.json` with a filter param in it → inspect its query string or payload for the `section_id` value → copy it.

- [ ] **Step 5: Add the Methods filter app block**

Still in the theme customizer, on the shop-all collection page → sidebar → Add block → Apps → **Methods filter**. In its settings, paste the section ID copied in Step 4. Set which filter types to expose (Membership, Calendar, or all) per what LMS actually offers today — check `docs/superpowers/specs/2026-07-10-shop-all-search-page-design.md` §3 if unsure, and confirm with the user if LMS's current Supercycle setup only has some method types live. Save.

- [ ] **Step 6: Identify the native availability filter's DOM selector**

With the Methods filter block now live and both it and the native "Rental availability" checkbox filter visible in the sidebar, open DevTools → Elements, find the native filter's `<details id="Facet-Details-{{ section.id }}-{{ filter.param_name }}">` element (search the DOM for `Facet-Details-`), and read off the `filter.param_name` portion of that ID (the part after the section ID).

- [ ] **Step 7: Hide the native filter with scoped CSS**

In `theme/lms-redesign-v4/blocks/filters.liquid`, in the same `{% stylesheet %}` block edited in Task 5 Step 1, add a rule using the exact ID fragment found in Step 6 above (replace `REPLACE_WITH_PARAM_NAME` with that value):

```css
  .facets--vertical [id*='Facet-Details-'][id*='REPLACE_WITH_PARAM_NAME'] {
    display: none;
  }
```

- [ ] **Step 8: Push and verify**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
```

In the theme editor preview, confirm the native "Rental availability" checkbox filter is gone from the sidebar, and the Supercycle Methods filter block is the only availability UI shown, positioned above Format (per the design spec's sidebar order).

- [ ] **Step 9: Commit**

```bash
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Hide native availability filter in favor of Supercycle Methods filter block"
```

---

### Task 8: Manual QA pass

**Files:** None.

**Interfaces:** None.

- [ ] **Step 1: Desktop filter + grid check**

On the shop-all collection page (desktop viewport), check each: Format checkbox filters the grid and shows a count per value; Genre same; Boutique label same; New-arrivals toggle visually reads as a pill switch and filters to only `new-arrival`-tagged products; combining two filters (e.g. Format + Genre) narrows correctly (AND, not OR, across facet groups — this is Shopify's default facet behavior, confirm it holds here too); the sort dropdown defaults to "Date, new to old" without the customer having to select it.

- [ ] **Step 2: Search handoff + filter carryover**

With Format = "Blu-ray" active, type a query into the sidebar search box and submit. Confirm the resulting URL is `/search?q=<query>&filter.p.m.custom.format=Blu-ray` (or equivalent param) and that `search-results.liquid`'s vertical filter sidebar shows Format still active.

- [ ] **Step 3: Zero-result state**

Combine filters to a combination with no matching products (e.g. an unused Genre + Label pair). Confirm the empty-state message renders instead of a blank grid.

- [ ] **Step 4: Infinite scroll**

On a filter combination with more than one page of results, scroll to the bottom and confirm the next page loads automatically with no button click required.

- [ ] **Step 5: Mobile**

At a mobile viewport width, confirm the filters collapse into the existing drawer UI (tap "Show filters" opens the drawer with the same Format/Genre/Label/New-arrivals/Availability filters and the "See results" / "Clear all" footer buttons), and the search input is reachable (either in the drawer or above it, whichever the vertical-style layout resolves to — check both and note if it's missing on mobile, since Task 4's search form was inserted only in the shared desktop-and-mobile-triggering markup path, not drawer-only markup, so confirm it renders in both surfaces or flag as a follow-up).

- [ ] **Step 6: Other collections unaffected**

Visit a different collection page still using `collection.json` (e.g. any existing tagged collection). Confirm it still shows the horizontal filter bar, native product cards, and no search box — proving none of Tasks 3–5's shared-file changes leaked into other templates.

---

## Self-Review Notes

- Spec §1 (template scope) → Task 2. §1 (search handoff) → Task 4. §2 (data model) → Task 1. §3 (filter composition, Supercycle setup) → Tasks 1, 7. §4 (card, grid density, infinite scroll, sort default) → Tasks 2, 3. §5 (styling, mobile drawer, zero-result) → Tasks 5, 8.
- Sort default ("Date, new to old") requires no code change — it's the native `results.default_sort_by` already used by `filters.liquid`; verified in Task 8 Step 1.
- No task invents a `filter.p.tag` param name literal — Task 4's hidden-input carryover uses `value.param_name` generically for all filter types, so it works regardless of Shopify's actual generated param name for the tag filter.
