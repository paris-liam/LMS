# Shop-All Toolbar & Sidebar Polish (items 3 & 4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Bring the shop-all page's search + toolbar in line with the mockup (`docs/search-a.dc.html`): (3) move the search box into the left sidebar, and (4) render Sort as a pill and the active-filter chips + "Clear all" in the top toolbar, drop the sidebar "Filters" heading, and label the count "N films".

**Architecture:** All changes are in `blocks/filters.liquid` (the shared filters block), gated to the shop-all page via `block_settings.filter_style == 'vertical'`. The vertical top bar is `.facets-controls-wrapper` (currently: `Filters` H4 + count + Sort). The search `<form>` currently renders *outside* the sidebar column; the active-filter chips (`filter-remove-buttons.liquid` → `.facets-remove__pill`) currently render *inside* the sidebar. We relocate both and restyle to the mockup.

**Tech Stack:** Shopify Horizon theme (Liquid), `shopify theme check`, manual QA on dev theme `140918915134`.

**Design source:** `docs/search-a.dc.html` (Direction A). **Mockup target:** top toolbar row = LEFT `Filters: [4K UHD ×][Drama ×] Clear all`, RIGHT `49 films  [Sort: Just landed ⌄]`; sidebar leads with the search box, then facet accordions.

## Global Constraints

- **Gate to shop-all only:** every change activates only when `block_settings.filter_style == 'vertical'`. A normal `collection.json` (horizontal) page must be visually unchanged.
- **No new locale keys.** The count label "films" must be **hardcoded** in Liquid — do NOT add a `content.*` key to `en.default.json` (it triggers ~30 `MatchingTranslations` errors, one per other locale). See memory `theme-check-matchingtranslations-gotcha`.
- **Preserve mobile drawer + horizontal behavior:** the sidebar/drawer chip and search paths for non-vertical pages must keep working.
- Edit only `theme/lms-redesign-v4/blocks/filters.liquid`. Dev store / theme `140918915134`. Never production.
- Verification = `shopify theme check` (no new offenses beyond the baseline 9 offenses / 2 pre-existing Supercycle `JSONMissingBlock`) + manual QA on a pushed dev theme.

---

### Task 1: Move the search box into the sidebar column (item 3)

The search `<form>` at `filters.liquid` ~line 147 renders as a sibling *outside* `.facets-block-wrapper--vertical`, so it has no grid cell and doesn't appear in the sidebar. Relocate it to the top of the sidebar column.

**Files:** Modify `theme/lms-redesign-v4/blocks/filters.liquid`

- [ ] **Step 1: Cut the search form from its current (outside-sidebar) location**

Delete this whole block (currently ~lines 147–178) — the `{% if … show_search_input %}<form class="facets-search-form">…</form>{% endif %}`:

```liquid
  {% if block_settings.filter_style == 'vertical' and block_settings.show_search_input %}
    <form
      method="get"
      action="{{ routes.search_url }}"
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
```

- [ ] **Step 2: Paste it as the first child of the vertical facets container**

Find the sidebar column's inner facets container (currently ~line 204):

```liquid
    <div
      class="facets facets--{{ block_settings.filter_style }} spacing-style"
      style="{% render 'spacing-style', settings: block_settings %}{% if block_settings.text_label_case == 'uppercase' %} --facet-label-transform: uppercase;{% endif %}"
      aria-label="{{ 'accessibility.filters' | t }}"
    >
```

Immediately **after** that opening `<div …>` tag, paste the exact `{% if … show_search_input %}…{% endif %}` block from Step 1. It now lives inside `.facets--vertical` (the sidebar column), above the facets form, matching the mockup. (Its existing `.facets-search-form` / `__input` CSS is unchanged.)

- [ ] **Step 3: Theme check + commit**

```bash
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Shop-all: move search box into the sidebar column (item 3)"
```
Expected: no new offenses. Manual QA (after push): the search input renders at the top of the left sidebar, above Availability/Format/etc.

---

### Task 2: Restyle the Sort control as a pill (item 4a)

The sort control (`sorting.liquid`) already renders a `Sort` label + a `<select class="sorting-filter__select">` (showing the selected option, e.g. "Just landed") + a caret, inside `.facets-controls-wrapper`. This is a **CSS-only** task to make it read as the mockup's pill "Sort: Just landed ⌄".

**Files:** Modify `theme/lms-redesign-v4/blocks/filters.liquid` (its `{% stylesheet %}` — the "LMS shop-all" section, near the `.facets-search-form` rules ~line 1440).

- [ ] **Step 1: Add pill styling scoped to the vertical controls bar**

Insert these rules in the LMS shop-all stylesheet section (e.g. right after the `.facets-search-form__input:focus-visible` rule):

```css
  /* Sort as a pill in the shop-all top bar */
  .facets-controls-wrapper .sorting-filter__container {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1.5px solid var(--lms-ink-300);
    border-radius: 999px;
    padding: 7px 14px;
    font-family: var(--lms-font-mono, monospace);
  }

  .facets-controls-wrapper .sorting-filter__container .facets__label {
    font-size: 13px;
    letter-spacing: 0;
    text-transform: none;
    color: var(--lms-text-strong, var(--color-foreground));
  }

  /* "Sort" -> "Sort:" */
  .facets-controls-wrapper .sorting-filter__container .facets__label::after {
    content: ':';
  }

  .facets-controls-wrapper .sorting-filter__select {
    appearance: none;
    border: none;
    background: transparent;
    padding: 0 18px 0 0;
    font-family: var(--lms-font-mono, monospace);
    font-size: 13px;
    color: var(--lms-text-strong, var(--color-foreground));
    cursor: pointer;
  }
```

- [ ] **Step 2: Theme check + commit**

```bash
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Shop-all: style the Sort control as a pill (item 4a)"
```
Expected: no new offenses. Manual QA: Sort reads "Sort: <current option> ⌄" as a bordered pill top-right; changing it re-sorts.

---

### Task 3: Chips + Clear all in the top toolbar; drop the "Filters" heading; count reads "films" (item 4b)

Restructure the vertical `.facets-controls-wrapper` into a left group (active-filter chips + "Clear all", with a "Filters:" prefix) and a right group (count + Sort); remove the `Filters` H4; hardcode the count as "N films"; suppress the sidebar chip instance for vertical; restyle the chips to the mockup's brick pills.

**Files:** Modify `theme/lms-redesign-v4/blocks/filters.liquid`

- [ ] **Step 1: Rebuild the vertical controls-wrapper markup**

Replace the current vertical controls block (currently ~lines 108–144, the `<div class="facets facets--horizontal facets-controls-wrapper …">…</div>`) with this two-group layout (drops the `Filters` H4, adds the chips-left group, hardcodes "films"):

```liquid
    <div
      class="facets facets--horizontal facets-controls-wrapper spacing-style"
      style="{% render 'spacing-style', settings: block_settings %}{% if block_settings.text_label_case == 'uppercase' %} --facet-label-transform: uppercase;{% endif %}"
    >
      <div class="facets-controls-wrapper__left">
        {% if block_settings.enable_filtering and total_active_values > 0 %}
          <span class="facets-controls__filters-label">{{ 'content.filters' | t }}:</span>
          {% render 'filter-remove-buttons',
            filters: filters,
            results_url: results_url,
            show_filter_label: block_settings.show_filter_label,
            should_show_clear_all: true
          %}
        {% endif %}
      </div>

      <div class="facets-controls-wrapper__right">
        <div class="products-count-wrapper" data-testid="products-count">
          <span role="status">{{ products_count }} films</span>
        </div>

        {% if block_settings.enable_sorting %}
          {% render 'sorting',
            results: results,
            sort_by: sort_by,
            filter_style: block_settings.filter_style,
            suffix: 'desktop',
            sort_position: 'desktop',
            should_use_select_on_mobile: false,
            section_id: section.id
          %}
        {% endif %}

        {% if block_settings.enable_grid_density %}
          {% render 'grid-density-controls', viewport: 'desktop' %}
        {% endif %}
      </div>
    </div>
```

Notes: `total_active_values` is already computed above (lines ~41–55). The count is hardcoded `{{ products_count }} films` — **do not** reintroduce `content.item_count` or add a locale key. Singular ("1 films") is acceptable for v1; optionally guard with `{% if products_count == 1 %}1 film{% else %}{{ products_count }} films{% endif %}`.

- [ ] **Step 2: Suppress the sidebar chip instance on vertical**

The desktop facets form still renders `filter-remove-buttons` inside the sidebar (currently ~line 224, `{% render 'filter-remove-buttons', … should_show_clear_all: true %}` right after `{% if should_show_pane %}`). Wrap that render so it does not fire for vertical (chips now live in the top bar):

```liquid
            {% unless block_settings.filter_style == 'vertical' %}
              {% render 'filter-remove-buttons',
                filters: filters,
                results_url: results_url,
                show_filter_label: block_settings.show_filter_label,
                should_show_clear_all: true
              %}
            {% endunless %}
```

(Leave the drawer's own `filter-remove-buttons` render, ~line 529, untouched — mobile keeps its chips in the drawer.)

- [ ] **Step 3: Add toolbar-layout + brick-chip CSS**

Add to the LMS shop-all stylesheet section:

```css
  /* Shop-all top toolbar: chips left, count+sort right */
  .facets-controls-wrapper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }

  .facets-controls-wrapper__left {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .facets-controls-wrapper__right {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
  }

  .facets-controls__filters-label {
    font-family: var(--lms-font-mono, monospace);
    font-size: 13px;
    color: var(--lms-text-muted, var(--color-foreground-subdued));
  }

  /* Brick active-filter chips (mockup .lms-chip-on) */
  .facets-controls-wrapper__left .facets-remove__pill {
    font-family: var(--lms-font-mono, monospace);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 6px 12px;
    border-radius: 999px;
    background: var(--lms-brick);
    border: 1.5px solid var(--lms-brick);
    color: var(--lms-parchment);
  }

  .facets-controls-wrapper__left .facets__clear-all-link {
    font-family: var(--lms-font-mono, monospace);
    font-size: 12px;
    color: var(--lms-sage-dark, var(--lms-sage));
    cursor: pointer;
  }
```

Note: `.facets-remove:has(facet-remove-component)` (from `filter-remove-buttons.liquid`) sets `display:flex` and its own margins; the pill restyle above overrides appearance. If the inherited `margin-block` pushes the row out of vertical-center, zero it with `.facets-controls-wrapper__left .facets-remove { margin: 0; }`.

- [ ] **Step 4: Theme check + commit**

```bash
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -3
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Shop-all: chips+clear-all in top toolbar, drop Filters heading, count as films (item 4b)"
```
Expected: no new offenses.

- [ ] **Step 5: Push + manual QA**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134
```
Confirm on the shop-all page:
1. No "Filters" heading above the sidebar; sidebar leads with the search box.
2. Selecting facet values shows brick chips + "Clear all" in the **top toolbar left**; count reads "N films"; Sort pill on the right.
3. Removing a chip / "Clear all" updates results.
4. Mobile drawer still shows its own chips and controls.
5. A normal `collection.json` page is unchanged (horizontal bar, native count, no relocation).

---

## Self-Review Notes

- **Item 3** → Task 1 (relocate search into `.facets--vertical`). **Item 4a** → Task 2 (sort pill, CSS). **Item 4b** → Task 3 (chips top-left + drop heading + "films" + suppress sidebar chip + brick styling).
- **Locale trap avoided:** count is hardcoded "films" (Task 3 Step 1), no `content.*` key added — per the MatchingTranslations gotcha.
- **Gating:** every change keys on `block_settings.filter_style == 'vertical'`; the horizontal desktop bar, the mobile drawer chips, and non-shop-all pages are untouched (Task 3 Step 2 leaves the drawer render; the controls-wrapper markup only renders in the `filter_style == 'vertical'` branch at line 106).
- **Decisions applied:** chips → top toolbar; sidebar "Filters" heading dropped; count reads "films" (confirmed 2026-07-14).
- **Open/optional:** singular "1 film" guard (noted, optional); the `filters-label` uses the existing `content.filters` key (already present — safe, not a new key).
