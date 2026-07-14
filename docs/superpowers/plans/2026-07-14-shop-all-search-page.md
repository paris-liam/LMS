# Shop-All "Shop everything" Search Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the "Shop everything" catalog page — a vertical filter sidebar (search, Format, Genre, Tags, New-arrivals toggle) beside a poster-card grid — by reconciling the existing committed shop-all code to the finalized metadata model and polishing it to the mockup (`docs/search-a.dc.html`).

**Architecture:** The page is Horizon's native collection page rendered by the alternate template `templates/collection.shop-all.json`, driving the existing `main-collection` section and `filters` block (powered by Shopify Search & Discovery). Filter mechanics (facet counts, active-filter chips, clear-all, "+ N more", AND-across-groups, sort, result count, infinite scroll) are native. This plan (1) reconciles Search & Discovery config to the new field/tag model, (2) makes the intro copy theme-editor editable, (3) prettifies the combined Tags facet labels, and (4) renders `new-arrival` as a dedicated sidebar toggle. Every code change is gated to the shop-all template only.

**Tech Stack:** Shopify Horizon theme (Liquid, OS 2.0 JSON templates), Shopify CLI (`shopify theme check` / `theme push`), Shopify Search & Discovery app. No JS unit-test framework exists — "tests" mean `shopify theme check` (static lint) + JSON validation + manual verification in a pushed dev-theme preview.

**Design spec:** `docs/superpowers/specs/2026-07-14-shop-all-search-page-design.md`

## Global Constraints

- **Default store:** dev store `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`. **Never** target production (`p0wkgv-wy.myshopify.com`).
- **Edit only** `theme/lms-redesign-v4/`. Never touch `theme/lms-redesign/` or `theme/horizon-baseline-3.5.1/`.
- **Gate every code change to shop-all**: activation conditions are `filter_style == 'vertical'`, `product_card_style == 'poster'`, and CSS scoped under `.facets--vertical`. A normal `collection.json` page must be visually unchanged.
- **Metadata model (finalized 2026-07-14):** metafields `custom.format`, `custom.genres` (plural, list), `custom.media_condition`; tags `label-*`, `rare`, `staff-pick`, `holiday`, `new-arrival`. Genre is `custom.genres` — **not** `custom.genre`.
- **Never create the `supercycle` metafield namespace.**
- **Product tag filter param name** is `filter.p.tag` (used to detect the Tags facet in Liquid).
- **Interactive CLI** (`shopify theme dev`, `theme push`, admin steps) is run by the user in their own terminal — it prompts for the storefront password and fails non-interactively.

---

### Task 1: Reconcile Search & Discovery config and assign the template (admin runbook)

No repo changes — Shopify admin configuration on the dev store. This unblocks the manual QA in later tasks by making the four facets live against the new model and putting the page on a real collection.

**Files:** None (admin config).

**Interfaces:**
- Produces (consumed by Tasks 3–5): live storefront filters for `custom.format`, `custom.genres`, and Product tags; a catalog collection using the `collection.shop-all` template sorted newest-first; ≥3 products tagged `new-arrival`.

- [ ] **Step 1: Remove stale filters from the old model**

Shopify Admin (dev store) → **Apps → Search & Discovery → Filters**. If any of these exist (created by the retired 2026-07-10 plan), delete them: **`custom.genre`** (singular), **`custom.label`**, **`custom.condition`**. They reference fields that no longer back this page.

- [ ] **Step 2: Ensure the four correct filters exist**

Still in Search & Discovery → Filters → **Add filter** for any missing:
- `custom.format` → label "Format" (Source = Metafield)
- `custom.genres` → label "Genre" (Source = Metafield)
- **Product tags** → enable it (this is the combined Tags facet; label it "Tags")

Leave price/availability defaults as-is. Save.

- [ ] **Step 3: Create/confirm the catalog collection and assign the template**

Admin → **Products → Collections**. Create (or open) an "All films" smart collection with a condition that matches the whole catalogue (e.g. "Product price ≥ 0"), or reuse an existing all-products collection. Open it → **Theme template** dropdown → select **`shop-all`** → in **Sort**, choose **Newest first** (drives the "Just landed" default). Save.

- [ ] **Step 4: Tag demo products for New arrivals**

Open ≥3 products → **Organization → Tags** → add `new-arrival` → Save. (Genre/format/label/curation demo values already come from `scripts/backfill-mock-movies.sh`.)

- [ ] **Step 5: Verify the facets are live**

Open the collection in the theme editor preview (or storefront). Confirm the left sidebar shows **Format**, **Genre**, and a **Tags** group whose values include `label-…`, `rare`, `staff-pick`, and `new-arrival`. (Prettifying and pulling out `new-arrival` happen in Tasks 3–4; here we only confirm the raw facets render.)
Expected: all three facet groups appear with counts. Record completion in the PR notes (store-side config, no commit).

---

### Task 2: Make the intro copy theme-editor editable

Turn the shop-all template's heading into three editable text blocks — eyebrow, H1, subtitle — with literal default copy the client can overwrite in the theme editor (currently the H1/description are bound to `collection.title`/`collection.description`).

**Files:**
- Modify: `theme/lms-redesign-v4/templates/collection.shop-all.json`

**Interfaces:**
- Consumes: nothing. Produces: nothing consumed by later tasks (leaf change).

- [ ] **Step 1: Replace the Title block text with an editable literal H1**

In `theme/lms-redesign-v4/templates/collection.shop-all.json`, in block `text_tqQTNE`'s settings, change:

```json
            "text": "<h1>{{ closest.collection.title }}</h1>",
```

to:

```json
            "text": "<h1>Shop everything</h1>",
```

- [ ] **Step 2: Replace the Description block text with editable subtitle default copy**

In block `text_twGGkJ`'s settings, change:

```json
            "text": "{{ closest.collection.description }}",
```

to:

```json
            "text": "Every format, every shelf, every note we've left. Browse without pressure.",
```

- [ ] **Step 3: Add an eyebrow text block before the title**

In the `"section"` → `"blocks"` object, add this new block entry (a sibling of `text_tqQTNE` / `text_twGGkJ`):

```json
        "text_eyebrow": {
          "type": "text",
          "name": "Eyebrow",
          "settings": {
            "text": "The shelves",
            "width": "fit-content",
            "max_width": "normal",
            "alignment": "left",
            "type_preset": "rte",
            "font": "var(--font-primary--family)",
            "font_size": "12px",
            "line_height": "normal",
            "letter_spacing": "0.14em",
            "case": "uppercase",
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
```

Then update `block_order` in the `"section"` to put the eyebrow first:

```json
      "block_order": ["text_eyebrow", "text_tqQTNE", "text_twGGkJ"],
```

- [ ] **Step 4: Validate the JSON body**

Run (strips the leading `/* … */` comment, then parses — same caveat as other generated templates):

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
python3 -c "import json,re,pathlib; s=pathlib.Path('theme/lms-redesign-v4/templates/collection.shop-all.json').read_text(); json.loads(s[s.index('{'):]); print('VALID')"
```
Expected: `VALID`.

- [ ] **Step 5: Theme check**

Run: `shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3`
Expected: no new offenses referencing `collection.shop-all.json` (pre-existing Supercycle `JSONMissingBlock` errors are unrelated).

- [ ] **Step 6: Commit**

```bash
git add theme/lms-redesign-v4/templates/collection.shop-all.json
git commit -m "Make shop-all intro (eyebrow/H1/subtitle) theme-editor editable"
```

---

### Task 3: Prettify the combined Tags facet labels

In the shared filter-value renderer, compute a display label for values of the Product-tags facet only: strip a leading `label-`, turn hyphens into spaces, title-case each word (`label-criterion` → "Criterion", `kino-lorber` → "Kino Lorber", `rare` → "Rare"). Underlying values/params are untouched.

**Files:**
- Modify: `theme/lms-redesign-v4/snippets/list-filter.liquid`

**Interfaces:**
- Consumes (from Task 1): the live `filter.p.tag` facet. Produces: `display_label` variable used by the checkbox render in this file (and, in Task 4, the suppression of `new-arrival`).

- [ ] **Step 1: Add the `display_label` computation inside the value loop**

In `theme/lms-redesign-v4/snippets/list-filter.liquid`, find the per-value liquid block that opens the `{%- for value in filter.values -%}` loop (currently lines 202–215):

```liquid
              {% liquid
                assign input_id = 'Filter-' | append: filter.param_name | escape | append: '-' | append: forloop.index | replace: '.', '-' | append: '-' | append: filter_style | append: '-' | append: in_drawer
                assign is_disabled = false
                if value.count == 0 and value.active == false
                  assign is_disabled = true
                endif
                assign hidden_class = null
                if forloop.index > inital_visible_values and render_show_more
                  assign hidden_class = 'hidden'
                  if filter_style == 'horizontal'
                    assign hidden_class = 'mobile:hidden'
                  endif
                endif
              %}
```

Replace it with (adds tag detection + prettified `display_label` at the end):

```liquid
              {% liquid
                assign input_id = 'Filter-' | append: filter.param_name | escape | append: '-' | append: forloop.index | replace: '.', '-' | append: '-' | append: filter_style | append: '-' | append: in_drawer
                assign is_disabled = false
                if value.count == 0 and value.active == false
                  assign is_disabled = true
                endif
                assign hidden_class = null
                if forloop.index > inital_visible_values and render_show_more
                  assign hidden_class = 'hidden'
                  if filter_style == 'horizontal'
                    assign hidden_class = 'mobile:hidden'
                  endif
                endif

                # LMS shop-all: prettify Product-tags facet labels (label-criterion -> Criterion).
                assign is_tag_filter = false
                if filter.param_name == 'filter.p.tag'
                  assign is_tag_filter = true
                endif
                assign display_label = value.label
                if is_tag_filter
                  assign lms_raw = value.label | remove_first: 'label-' | replace: '-', ' '
                  assign lms_words = lms_raw | split: ' '
                  assign display_label = ''
                  for lms_w in lms_words
                    assign lms_cap = lms_w | capitalize
                    if forloop.first
                      assign display_label = lms_cap
                    else
                      assign display_label = display_label | append: ' ' | append: lms_cap
                    endif
                  endfor
                endif
              %}
```

- [ ] **Step 2: Use `display_label` in the checkbox render**

In the same file, find the checkbox render (currently lines 369–378):

```liquid
                    {% render 'checkbox',
                      name: value.param_name,
                      value: value.value,
                      label: value.label,
                      checked: value.active,
                      id: input_id,
                      disabled: is_disabled,
                      inputRef: 'facetInputs[]',
                      events: 'on:pointerenter="/prefetchPage" on:pointerleave="/cancelPrefetchPage" on:pointerdown="/prefetchPageImmediate"'
                    %}
```

Change `label: value.label,` to `label: display_label,`:

```liquid
                    {% render 'checkbox',
                      name: value.param_name,
                      value: value.value,
                      label: display_label,
                      checked: value.active,
                      id: input_id,
                      disabled: is_disabled,
                      inputRef: 'facetInputs[]',
                      events: 'on:pointerenter="/prefetchPage" on:pointerleave="/cancelPrefetchPage" on:pointerdown="/prefetchPageImmediate"'
                    %}
```

(The tags facet always uses this checkbox path — its labels exceed 3 chars, so `should_use_pills` is false, and it is neither swatch nor image. Metafield facets like Format/Genre keep `display_label == value.label` because `is_tag_filter` is false for them.)

- [ ] **Step 3: Theme check**

Run: `shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3`
Expected: no new offenses in `list-filter.liquid`.

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/snippets/list-filter.liquid
git commit -m "Prettify combined Tags facet labels on shop-all (strip label-, title-case)"
```

- [ ] **Step 5 (manual, after a dev push): verify prettified labels**

After Task 5's push, open the shop-all page. In the Tags facet, confirm values read as "Criterion", "Rare", "Staff Pick" — not `label-criterion`/`rare`/`staff-pick`. If they still show raw, the tag filter's `param_name` differs from `filter.p.tag`; inspect a Tags checkbox's `name` attribute in DevTools and update the `filter.param_name == 'filter.p.tag'` check in Step 1 to the observed value.

---

### Task 4: Render `new-arrival` as a dedicated sidebar toggle

Suppress the `new-arrival` value from the Tags list and render it as a standalone switch at the bottom of the vertical sidebar (reusing the pill CSS already in `filters.liquid`).

**Files:**
- Modify: `theme/lms-redesign-v4/snippets/list-filter.liquid`
- Modify: `theme/lms-redesign-v4/blocks/filters.liquid`

**Interfaces:**
- Consumes (from Task 3): the `is_tag_filter` variable in `list-filter.liquid`. Consumes (from Task 1): the `new-arrival` tag value on the `filter.p.tag` facet.
- Produces: a `<facet-inputs-component>` toggle in the desktop vertical sidebar bound to the `new-arrival` tag value's `param_name`/`value`.

- [ ] **Step 1: Suppress `new-arrival` from the Tags checkbox list**

In `theme/lms-redesign-v4/snippets/list-filter.liquid`, inside the `{%- for value in filter.values -%}` loop, immediately after the `%}` that closes the liquid block from Task 3 Step 1 (i.e. right before the `<li` element opens, currently near line 216), insert:

```liquid
              {%- if is_tag_filter and value.value == 'new-arrival' -%}{%- continue -%}{%- endif -%}
```

- [ ] **Step 2: Render the toggle in the desktop vertical sidebar**

In `theme/lms-redesign-v4/blocks/filters.liquid`, find the end of the desktop filter-capture (currently line 269, the `{% endcapture %}` closing `rendered_filters`):

```liquid
                {%- endfor -%}
              {% endcapture %}
```

Insert this block immediately after that `{% endcapture %}`:

```liquid
              {%- if block_settings.filter_style == 'vertical' -%}
                {%- liquid
                  assign na_value = null
                  for filter in filters
                    if filter.param_name == 'filter.p.tag'
                      for value in filter.values
                        if value.value == 'new-arrival'
                          assign na_value = value
                          break
                        endif
                      endfor
                    endif
                  endfor
                -%}
                {%- if na_value -%}
                  {%- capture new_arrivals_toggle -%}
                    <div class="facets__item facets-new-arrivals">
                      <span class="facets-new-arrivals__label">{{ 'content.new_arrivals' | t: default: 'New arrivals' }}</span>
                      <facet-inputs-component on:change="/updateFilters" class="facets-new-arrivals__control">
                        <input
                          type="checkbox"
                          name="{{ na_value.param_name }}"
                          value="{{ na_value.value }}"
                          aria-label="{{ 'content.new_arrivals' | t: default: 'New arrivals' }}"
                          id="Filter-new-arrivals-desktop"
                          {% if na_value.active %}checked{% endif %}
                          ref="facetInputs[]"
                        >
                      </facet-inputs-component>
                    </div>
                  {%- endcapture -%}
                  {%- assign rendered_filters = rendered_filters | append: new_arrivals_toggle -%}
                {%- endif -%}
              {%- endif -%}
```

- [ ] **Step 3: Add container CSS for the toggle row**

In `theme/lms-redesign-v4/blocks/filters.liquid`, find the existing new-arrival pill CSS anchor (currently line 1391):

```css
  .facets--vertical .checkbox:has(input[value='new-arrival']) {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
```

Insert the following rules immediately before it (the switch visual itself is already handled by the existing `.facets--vertical input[value='new-arrival']` rules below this anchor):

```css
  .facets--vertical .facets-new-arrivals {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1.5px solid var(--lms-border-default, rgb(var(--color-foreground-rgb) / 0.15));
    padding-top: 18px;
    margin-top: 8px;
  }

  .facets--vertical .facets-new-arrivals__label {
    font-family: var(--lms-font-mono, monospace);
    font-weight: 500;
    font-size: 14px;
    color: var(--lms-text-strong, var(--color-foreground));
  }

```

- [ ] **Step 4: Theme check**

Run: `shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3`
Expected: no new offenses in `filters.liquid` or `list-filter.liquid`.

- [ ] **Step 5: Confirm no stray `new-arrival` checkbox path remains in the Tags list logic**

Run:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
grep -n "new-arrival" theme/lms-redesign-v4/snippets/list-filter.liquid theme/lms-redesign-v4/blocks/filters.liquid
```
Expected: the `continue` guard in `list-filter.liquid`; the toggle markup + CSS in `filters.liquid`. No other unexpected references.

- [ ] **Step 6: Commit**

```bash
git add theme/lms-redesign-v4/snippets/list-filter.liquid theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Render new-arrival tag as a dedicated shop-all sidebar toggle"
```

---

### Task 5: Push to dev store and full manual QA

Push the reconciled theme and walk the spec's verification checklist on the real page.

**Files:** None (deploy + QA).

**Interfaces:** Consumes all prior tasks.

- [ ] **Step 1: Push to the dev working theme**

Run (your own terminal):
```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
```

- [ ] **Step 2: Facets, counts, chips**

On the shop-all collection page: Format, Genre, and Tags each filter the grid and show per-value counts; selecting values shows active-filter chips with `×`; "Clear all" resets; Genre shows "+ N more" when it has >10 values.

- [ ] **Step 3: Prettified Tags + New-arrivals toggle**

Confirm Tags values read prettified ("Criterion", "Rare", "Staff Pick"), and `new-arrival` is **absent** from the Tags list. Confirm the **New arrivals** row renders at the sidebar bottom as a switch, and toggling it filters the grid to `new-arrival`-tagged products (watch the result count / grid update). If the toggle renders but does **not** filter, the standalone `facet-inputs-component` isn't wiring to the form — fallback: remove the Task 4 suppression `continue` and instead style the in-list `new-arrival` checkbox as the switch via `.facets--vertical .checkbox:has(input[value='new-arrival'])` and `order`, leaving it inside the Tags group; re-push and re-verify. Note which path shipped in the PR.

- [ ] **Step 4: Search handoff + carryover**

With Format = one value active, type a query in the sidebar search box and submit. Confirm the URL is `/search?q=<query>&filter.p.m.custom.format=<value>` (or equivalent) and the search page keeps Format active.

- [ ] **Step 5: Empty state + infinite scroll**

Filter to a no-match combination → the empty-state message renders (not a blank grid). On a >1-page result, scroll to the bottom → the next page auto-loads with no button.

- [ ] **Step 6: Editable intro**

In the theme editor, open the shop-all collection → the heading blocks (Eyebrow / Title / Description) are editable; changing the subtitle text updates the page.

- [ ] **Step 7: Mobile + isolation**

At a mobile width, the filters collapse into the drawer with the same Format/Genre/Tags controls. Then open a different collection still on `collection.json` → it keeps the horizontal filter bar, native cards, and no search box (proving the gating held).

- [ ] **Step 8: Record completion**

No commit (deploy + config). Summarize in the PR: facets reconciled, intro editable, Tags prettified, New-arrivals toggle path shipped (primary or fallback).

---

## Self-Review Notes

- **Spec coverage:** reuse native foundation → Tasks 2–4 (edits, not rebuild); data/facet mapping + stale-filter removal → Task 1; combined Tags facet → Task 1; tag-label prettify → Task 3; New-arrivals dedicated toggle + suppression → Task 4; editable intro copy → Task 2; infinite scroll / poster cards / restyle → already committed (verified in Task 5); accepted divergences (no label-split, no accent) → not implemented by design; verification checklist → Task 5.
- **Placeholder scan:** every code step shows complete before/after Liquid/JSON/CSS; the subtitle default copy is intentional editable content, not a plan gap; the `filter.p.tag` param name and the toggle-wiring risk each carry an explicit verify + fallback step (Task 3 Step 5, Task 4 / Task 5 Step 3).
- **Type/name consistency:** `is_tag_filter` and `display_label` defined in Task 3 Step 1 are consumed in Task 3 Step 2 and Task 4 Step 1; `na_value` is local to Task 4 Step 2; `filter.p.tag`, `custom.genres`, `custom.format`, and the tag set (`label-*`/`rare`/`staff-pick`/`holiday`/`new-arrival`) are used identically across Tasks 1, 3, 4, 5 and match the Global Constraints.
