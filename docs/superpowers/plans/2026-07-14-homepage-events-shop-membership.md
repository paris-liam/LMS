# Homepage Events + Shop/Membership Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the homepage's events+membership split tile with a shop(online-store)+membership tile, give events their own full-width homepage section, and add a dedicated Events page with the complete upcoming calendar — without deleting or modifying the two retired section files.

**Architecture:** Three new section files (`lms-shop-membership`, `lms-events-full`, `lms-events-calendar`) plus one new shared snippet (`lms-events-list`) that centralizes the existing event-sort logic so it isn't duplicated a second and third time. One new page template (`page.events.json`). `templates/index.json` is rewired to swap the old sections for the new ones.

**Tech Stack:** Shopify Horizon theme (Liquid, OS 2.0 JSON templates), `shopify theme check` for static validation, `shopify theme dev`/`shopify theme push` for the dev store (`lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`).

## Global Constraints

- Working directory for all file paths below: `theme/lms-redesign-v4/` (repo root is `LMS-sandbox/`).
- Do **not** delete or modify `sections/lms-events-membership.liquid` or `sections/lms-promo-pair.liquid` — only remove their instances from `templates/index.json`.
- All new sections follow the existing LMS pattern: `render 'contrast-override', background_color: section.settings.background_color, section_id: section.id` at the top, a `color-custom-{{ section.id }}` wrapper div with `--lms-pad-top`/`--lms-pad-bottom` CSS vars driven by `padding-block-start`/`padding-block-end` range settings, and a standard "Section style" settings group (`background_color`, `padding-block-start`, `padding-block-end`).
- No automated test suite exists in this theme repo. The verification cycle for every task is: `shopify theme check --path theme/lms-redesign-v4` (baseline: 9 offenses / 2 errors, all pre-existing Supercycle-block warnings unrelated to this work — confirm no *new* offenses), plus a manual push + visual check on the dev store.
- Dev store: `lms-sandbox-lutsfahz.myshopify.com`, theme id `140918915134` (this is the **live** theme on that store, so pushes need `--allow-live`).
- The "online-store" product collection already exists on the dev store (confirmed earlier in this session).

---

### Task 1: Shared event list snippet + full-width homepage events section

**Files:**
- Create: `theme/lms-redesign-v4/snippets/lms-events-list.liquid`
- Create: `theme/lms-redesign-v4/sections/lms-events-full.liquid`

**Interfaces:**
- Consumes: `shop.metaobjects.event.values` (fields: `name`, `date`, `description`, `audience`, `link` — same metaobject used by the existing `lms-events-membership.liquid`).
- Produces: `{% render 'lms-events-list', limit: <integer, 0 = unlimited>, style: 'cards' | 'rows' %}` — renders a `<div class="lms-events-cards">...</div>` for `style: 'cards'` or a `<ul class="lms-events">...</ul>` for `style: 'rows'`, sorted soonest-first, filtered to today-or-later. Task 3 depends on this snippet's `rows` style; this task's own section depends on the `cards` style.

- [ ] **Step 1: Create the shared snippet**

Create `theme/lms-redesign-v4/snippets/lms-events-list.liquid`:

```liquid
{% comment %}
  lms-events-list — shared upcoming-events renderer.

  Events are driven by an `event` metaobject (Admin → Content):
    - name        Single-line text
    - date        Date
    - description Single-line text
    - audience    Single-line text with preset choices: Members | Public
    - link        URL (optional)
  Only events on or after today are shown, soonest first. Metaobject value
  lists aren't reliably index-able, so each event's markup is captured,
  prefixed with its ISO date, joined into one string, and the strings are
  sorted (ISO dates sort correctly as strings) — this is the same technique
  originally used in lms-events-membership.liquid, centralized here so it
  isn't re-implemented by every new consumer.

  Accepts:
  - limit: {Number} optional. 0 or blank shows every upcoming event.
  - style: {String} required. 'cards' (full-width card row) or 'rows'
    (vertical list with description — used by the full calendar page).

  Usage:
  {% render 'lms-events-list', limit: 4, style: 'cards' %}
  {% render 'lms-events-list', limit: 0, style: 'rows' %}
{% endcomment %}

{%- liquid
  assign today = 'now' | date: '%Y-%m-%d'
  assign event_values = shop.metaobjects.event.values
  assign sortable = ''
  assign list_limit = limit | default: 0

  for event in event_values
    assign event_date = event.date.value | date: '%Y-%m-%d'
    if event_date >= today
      capture event_html
        if style == 'cards'
          echo '<div class="lms-event-card"><div class="lms-events__date"><div class="lms-events__month">'
          echo event.date.value | date: '%b'
          echo '</div><div class="lms-events__day">'
          echo event.date.value | date: '%d'
          echo '</div></div><div class="lms-event-card__body"><div class="lms-events__name">'
          if event.link.value != blank
            echo '<a href="'
            echo event.link.value
            echo '">'
            echo event.name.value
            echo '</a>'
          else
            echo event.name.value
          endif
          echo '</div>'
          if event.audience.value != blank
            assign is_members = event.audience.value | downcase
            if is_members == 'members'
              echo '<span class="lms-badge lms-badge--brick">'
            else
              echo '<span class="lms-badge lms-badge--sage">'
            endif
            echo event.audience.value
            echo '</span>'
          endif
          echo '</div></div>'
        else
          echo '<li class="lms-events__item"><div class="lms-events__date"><div class="lms-events__month">'
          echo event.date.value | date: '%b'
          echo '</div><div class="lms-events__day">'
          echo event.date.value | date: '%d'
          echo '</div></div><div class="lms-events__body"><div class="lms-events__name">'
          if event.link.value != blank
            echo '<a href="'
            echo event.link.value
            echo '">'
            echo event.name.value
            echo '</a>'
          else
            echo event.name.value
          endif
          echo '</div>'
          if event.description.value != blank
            echo '<div class="lms-events__desc">'
            echo event.description.value
            echo '</div>'
          endif
          echo '</div>'
          if event.audience.value != blank
            assign is_members = event.audience.value | downcase
            if is_members == 'members'
              echo '<span class="lms-badge lms-badge--brick">'
            else
              echo '<span class="lms-badge lms-badge--sage">'
            endif
            echo event.audience.value
            echo '</span>'
          endif
          echo '</li>'
        endif
      endcapture
      assign sortable = sortable | append: event_date | append: '@@EVENTFIELD@@' | append: event_html | append: '@@EVENTSPLIT@@'
    endif
  endfor

  assign event_records = sortable | split: '@@EVENTSPLIT@@' | sort
  assign shown = 0
-%}

{%- if style == 'cards' -%}
  <div class="lms-events-cards">
{%- else -%}
  <ul class="lms-events">
{%- endif -%}

{%- for record in event_records -%}
  {%- if record == blank -%}{%- continue -%}{%- endif -%}
  {%- if list_limit > 0 and shown >= list_limit -%}{% break %}{%- endif -%}
  {%- assign shown = shown | plus: 1 -%}
  {%- assign record_html = record | split: '@@EVENTFIELD@@' | last -%}
  {{ record_html }}
{%- endfor -%}

{%- if shown == 0 -%}
  {%- if style == 'cards' -%}
    <div class="lms-events__empty">No upcoming events yet. Add events under Admin → Content → Events and they'll appear here automatically.</div>
  {%- else -%}
    <li class="lms-events__empty">No upcoming events yet. Add events under Admin → Content → Events and they'll appear here automatically.</li>
  {%- endif -%}
{%- endif -%}

{%- if style == 'cards' -%}
  </div>
{%- else -%}
  </ul>
{%- endif -%}

{% stylesheet %}
.lms-events {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: var(--lms-border-width) solid var(--lms-border-default);
}
.lms-events__item {
  display: flex;
  gap: 20px;
  align-items: center;
  padding: 18px 0;
  border-bottom: var(--lms-border-width) solid var(--lms-border-default);
}
.lms-events__date { text-align: center; min-width: 46px; flex-shrink: 0; }
.lms-events__month {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-med);
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--lms-brick);
}
.lms-events__day {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-semi);
  font-size: 28px;
  line-height: 1;
  color: var(--lms-text-strong);
}
.lms-events__body { flex: 1; min-width: 0; }
.lms-events__name {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 16px;
  color: var(--lms-text-strong);
  line-height: 1.25;
  margin-bottom: 3px;
}
.lms-events__name a { color: inherit; text-decoration: none; }
.lms-events__name a:hover { text-decoration: underline; }
.lms-events__desc {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 12px;
  color: var(--lms-text-muted);
}
.lms-events__empty {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 13px;
  color: var(--lms-text-muted);
  padding: 18px 0;
}

/* --- Card style (full-width homepage row) --- */
.lms-events-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
}
.lms-event-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 20px;
  border: var(--lms-border-width) solid var(--lms-border-default);
  border-radius: var(--lms-radius-md);
  background: var(--lms-bg, var(--lms-parchment));
}
.lms-event-card .lms-events__date { text-align: left; }
.lms-event-card__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
@media screen and (max-width: 989px) {
  .lms-events-cards { grid-template-columns: repeat(2, 1fr); }
}
@media screen and (max-width: 549px) {
  .lms-events-cards {
    display: flex;
    overflow-x: auto;
    gap: 14px;
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
  }
  .lms-events-cards > .lms-event-card { flex: 0 0 78%; scroll-snap-align: start; }
  .lms-events-cards > .lms-events__empty { flex: 0 0 100%; }
}
{% endstylesheet %}
```

- [ ] **Step 2: Create the full-width homepage section**

Create `theme/lms-redesign-v4/sections/lms-events-full.liquid`:

```liquid
{% comment %}
  lms-events-full — full-width "next N upcoming events" card row.
  Replaces lms-promo-pair on the homepage (that section's file is retired,
  kept but unreferenced — see templates/index.json).
  Event data + sort logic lives in snippets/lms-events-list.liquid.
{% endcomment %}

{% render 'contrast-override', background_color: section.settings.background_color, section_id: section.id %}
<div class="lms-events-full color-custom-{{ section.id }}"
  style="--lms-pad-top: {{ section.settings.padding-block-start }}px; --lms-pad-bottom: {{ section.settings.padding-block-end }}px;"
  {{ section.shopify_attributes }}>
  <div class="lms-container">

    <div class="lms-events-full__header">
      <div>
        {% render 'lms-eyebrow', text: section.settings.eyebrow %}
        {%- if section.settings.heading != blank -%}
          <h2 class="lms-events-full__heading">{{ section.settings.heading }}</h2>
        {%- endif -%}
      </div>
      {%- if section.settings.all_events_link_label != blank -%}
        <a href="{{ section.settings.all_events_link | default: '#' }}" class="lms-btn lms-btn--outline lms-btn--sm">
          {{- section.settings.all_events_link_label -}}
        </a>
      {%- endif -%}
    </div>

    {% render 'lms-events-list', limit: section.settings.events_to_show, style: 'cards' %}

  </div>
</div>

{% stylesheet %}
.lms-events-full {
  background: var(--color-background, var(--lms-parchment));
  padding-block: var(--lms-pad-top, 72px) var(--lms-pad-bottom, 72px);
}
.lms-events-full__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 34px;
}
.lms-events-full .lms-eyebrow { display: block; }
.lms-events-full__heading {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 32px;
  line-height: var(--lms-lh-tight);
  color: var(--lms-text-strong);
  margin: 10px 0 0;
}
{% endstylesheet %}

{% schema %}
{
  "name": "LMS events full",
  "tag": "section",
  "class": "lms-events-full-section",
  "settings": [
    { "type": "header", "content": "Heading" },
    { "type": "text", "id": "eyebrow", "label": "Eyebrow", "default": "Coming up" },
    { "type": "text", "id": "heading", "label": "Heading", "default": "Events & screenings" },
    { "type": "header", "content": "Events" },
    {
      "type": "paragraph",
      "content": "Events are managed under Admin → Content → Events. Upcoming events appear here automatically, soonest first."
    },
    {
      "type": "range",
      "id": "events_to_show",
      "label": "Events to show",
      "min": 2,
      "max": 8,
      "step": 1,
      "default": 4
    },
    { "type": "header", "content": "All events link" },
    {
      "type": "text",
      "id": "all_events_link_label",
      "label": "Link label",
      "default": "All events →",
      "info": "Leave blank to hide."
    },
    { "type": "url", "id": "all_events_link", "label": "Link" },
    { "type": "header", "content": "Section style" },
    {
      "type": "color",
      "id": "background_color",
      "label": "t:settings.background_color",
      "placeholder": "t:settings.default"
    },
    {
      "type": "range",
      "id": "padding-block-start",
      "label": "Top padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 72
    },
    {
      "type": "range",
      "id": "padding-block-end",
      "label": "Bottom padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 72
    }
  ],
  "presets": [
    { "name": "LMS events full" }
  ]
}
{% endschema %}
```

- [ ] **Step 3: Run theme-check**

Run: `cd /Users/liamparis/web-projects/personal/LMS-sandbox && shopify theme check --path theme/lms-redesign-v4`
Expected: Summary line still reads `9 total offenses found across 9 files. 2 errors.` (the pre-existing Supercycle-block errors/warnings) — no new offenses from the two new files. If theme-check reports anything in `snippets/lms-events-list.liquid` or `sections/lms-events-full.liquid`, fix it before continuing.

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
git add theme/lms-redesign-v4/snippets/lms-events-list.liquid theme/lms-redesign-v4/sections/lms-events-full.liquid
git commit -m "Add shared event list snippet and full-width events section"
```

---

### Task 2: Shop + membership split section

**Files:**
- Create: `theme/lms-redesign-v4/sections/lms-shop-membership.liquid`

**Interfaces:**
- Consumes: `render 'lms-product-card', card_product: product` (existing snippet, unchanged — see `snippets/lms-product-card.liquid`), `render 'lms-eyebrow', text: ...` (existing snippet), `render 'contrast-override', ...` (existing snippet).
- Produces: section type `lms-shop-membership` with settings `shop_eyebrow`, `shop_heading`, `shop_description`, `shop_collection` (collection picker), `shop_link_label`, plus the membership settings carried over unchanged from `lms-events-membership.liquid`: `membership_eyebrow`, `membership_heading`, `card_est_text`, `card_name_text`, `price_text`, `price_suffix`, `button_label`, `button_link`, and block type `perk` (`title`, `detail`). Task 4 (`templates/index.json`) depends on these exact setting/block IDs.

- [ ] **Step 1: Create the section file**

Create `theme/lms-redesign-v4/sections/lms-shop-membership.liquid`:

```liquid
{% comment %}
  lms-shop-membership — split card: online-store product showcase (left) +
  membership panel (right). Replaces lms-events-membership on the homepage
  (that section's file is retired, kept but unreferenced — see
  templates/index.json). The membership panel's settings, blocks, and
  markup are carried over unchanged from lms-events-membership.liquid.

  Shop panel is driven by a merchant-selected collection (same pattern as
  lms-new-releases.liquid) — no hardcoded collection handle.

  Perks are section-local blocks — ordered inline in the editor.
{% endcomment %}

{%- liquid
  assign shop_collection = section.settings.shop_collection
-%}

{% render 'contrast-override', background_color: section.settings.background_color, section_id: section.id %}
<div class="lms-split-section color-custom-{{ section.id }}"
  style="--lms-pad-top: {{ section.settings.padding-block-start }}px; --lms-pad-bottom: {{ section.settings.padding-block-end }}px;"
  {{ section.shopify_attributes }}>
  <div class="lms-container">
    <div class="lms-split">

      {%- comment -%} ---------- Left: shop ---------- {%- endcomment -%}
      <div class="lms-split__shop">
        {% render 'lms-eyebrow', text: section.settings.shop_eyebrow %}
        {%- if section.settings.shop_heading != blank -%}
          <h2 class="lms-split__heading">{{ section.settings.shop_heading }}</h2>
        {%- endif -%}
        {%- if section.settings.shop_description != blank -%}
          <div class="lms-split__desc rte">{{ section.settings.shop_description }}</div>
        {%- endif -%}

        <div class="lms-split__shop-grid">
          {%- if shop_collection != blank -%}
            {%- for product in shop_collection.products limit: 4 -%}
              {% render 'lms-product-card', card_product: product %}
            {%- endfor -%}
          {%- else -%}
            {%- comment -%} Onboarding state: no collection selected yet {%- endcomment -%}
            {%- for i in (1..4) -%}
              <div class="lms-product-card">
                <div class="lms-product-card__media">
                  <div class="lms-product-card__placeholder">{{ 'product-1' | placeholder_svg_tag }}</div>
                </div>
                <div class="lms-product-card__title">Example title</div>
              </div>
            {%- endfor -%}
          {%- endif -%}
        </div>

        {%- if section.settings.shop_link_label != blank and shop_collection != blank -%}
          <a href="{{ shop_collection.url }}" class="lms-split__textlink">
            {{- section.settings.shop_link_label -}}
          </a>
        {%- endif -%}
      </div>

      {%- comment -%} ---------- Right: membership ---------- {%- endcomment -%}
      <div class="lms-split__membership">
        {% render 'lms-eyebrow', text: section.settings.membership_eyebrow %}
        {%- if section.settings.membership_heading != blank -%}
          <h2 class="lms-split__heading">{{ section.settings.membership_heading }}</h2>
        {%- endif -%}

        <div class="lms-member-card">
          <div class="lms-member-card__top">
            <span class="lms-member-card__brand">Little Movie Club</span>
            <span class="lms-member-card__est">{{ section.settings.card_est_text }}</span>
          </div>
          <div class="lms-member-card__holder">
            <div class="lms-member-card__holder-label">Member</div>
            <div class="lms-member-card__holder-name">{{ section.settings.card_name_text }}</div>
          </div>
        </div>

        {%- if section.blocks.size > 0 -%}
          <ul class="lms-perks">
            {%- for block in section.blocks -%}
              <li class="lms-perks__item" {{ block.shopify_attributes }}>
                <span class="lms-perks__mark" aria-hidden="true">✦</span>
                <span class="lms-perks__text">
                  {{ block.settings.title }}
                  {%- if block.settings.detail != blank -%}
                    <span class="lms-perks__detail"> — {{ block.settings.detail }}</span>
                  {%- endif -%}
                </span>
              </li>
            {%- endfor -%}
          </ul>
        {%- endif -%}

        <div class="lms-split__price">
          <span class="lms-split__price-value">{{ section.settings.price_text }}</span>
          {%- if section.settings.price_suffix != blank -%}
            <span class="lms-split__price-suffix">{{ section.settings.price_suffix }}</span>
          {%- endif -%}
        </div>

        {%- if section.settings.button_label != blank -%}
          <a href="{{ section.settings.button_link | default: '#' }}" class="lms-btn lms-btn--primary lms-btn--lg">
            {{- section.settings.button_label -}}
          </a>
        {%- endif -%}
      </div>

    </div>
  </div>
</div>

{% stylesheet %}
.lms-split-section {
  /* Sunken parchment frames the bordered card (per mockup) */
  background: var(--lms-bg-sunken);
  padding-block: var(--lms-pad-top, 72px) var(--lms-pad-bottom, 72px);
}
.lms-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border: var(--lms-border-width) solid var(--lms-border-default);
  border-radius: var(--lms-radius-md);
  overflow: hidden;
  background: var(--lms-bg);
}
.lms-split__shop {
  padding: 44px;
  border-right: var(--lms-border-width) solid var(--lms-border-default);
  display: flex;
  flex-direction: column;
}
.lms-split__membership {
  padding: 44px;
  background: var(--lms-bg-sunken);
  display: flex;
  flex-direction: column;
}
.lms-split .lms-eyebrow { display: block; }
.lms-split__heading {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 32px;
  line-height: var(--lms-lh-tight);
  color: var(--lms-text-strong);
  margin: 12px 0 22px;
}
.lms-split__desc {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 13px;
  line-height: 1.7;
  color: var(--lms-text-muted);
  margin: -10px 0 22px;
}
.lms-split__desc p { margin: 0 0 1em; }
.lms-split__desc p:last-child { margin-bottom: 0; }

/* Shop grid */
.lms-split__shop-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  flex: 1;
}

.lms-split__textlink {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-med);
  font-size: 12px;
  letter-spacing: var(--lms-tracking-wide);
  text-transform: uppercase;
  color: var(--lms-brick);
  text-decoration: none;
  margin-top: 22px;
  align-self: flex-start;
}
.lms-split__textlink:hover { color: var(--lms-brick-dark); }

/* Member card */
.lms-member-card {
  position: relative;
  background: var(--lms-surface-inverse);
  border-radius: var(--lms-radius-sm);
  padding: 24px;
  box-shadow: var(--lms-shadow-md);
  overflow: hidden;
  margin-bottom: 24px;
}
.lms-member-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.lms-member-card__brand {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-med);
  font-size: 10px;
  letter-spacing: var(--lms-tracking-eyebrow);
  text-transform: uppercase;
  color: var(--lms-cyan);
}
.lms-member-card__est {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 11px;
  color: color-mix(in oklch, var(--lms-text-on-dark) 60%, transparent);
}
.lms-member-card__holder { margin-top: 26px; }
.lms-member-card__holder-label {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: color-mix(in oklch, var(--lms-text-on-dark) 55%, transparent);
  margin-bottom: 5px;
}
.lms-member-card__holder-name {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-med);
  font-size: 22px;
  color: var(--lms-text-on-dark);
  line-height: var(--lms-lh-tight);
}

/* Perks */
.lms-perks {
  list-style: none;
  margin: 0 0 24px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}
.lms-perks__item { display: flex; gap: 11px; align-items: flex-start; }
.lms-perks__mark {
  color: var(--lms-brick);
  font-size: 13px;
  line-height: 1.5;
  flex-shrink: 0;
}
.lms-perks__text {
  font-family: var(--lms-font-mono);
  font-size: 14px;
  line-height: var(--lms-lh-snug);
  color: var(--lms-text-strong);
}
.lms-perks__detail { color: var(--lms-text-muted); }

/* Price */
.lms-split__price {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 18px;
}
.lms-split__price-value {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-semi);
  font-size: 44px;
  line-height: 1;
  color: var(--lms-brick);
}
.lms-split__price-suffix {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 13px;
  color: var(--lms-text-muted);
}

@media screen and (max-width: 989px) {
  .lms-split { grid-template-columns: 1fr; }
  .lms-split__shop {
    border-right: none;
    border-bottom: var(--lms-border-width) solid var(--lms-border-default);
  }
}
@media screen and (max-width: 549px) {
  .lms-split__shop,
  .lms-split__membership { padding: 30px 26px; }
  .lms-split__shop-grid { grid-template-columns: repeat(2, 1fr); gap: 14px; }
}
{% endstylesheet %}

{% schema %}
{
  "name": "LMS shop + membership",
  "tag": "section",
  "class": "lms-shop-membership-section",
  "settings": [
    { "type": "header", "content": "Shop" },
    {
      "type": "text",
      "id": "shop_eyebrow",
      "label": "Eyebrow",
      "default": "Shop online"
    },
    {
      "type": "text",
      "id": "shop_heading",
      "label": "Heading",
      "default": "Can't make it in? Shop online."
    },
    {
      "type": "richtext",
      "id": "shop_description",
      "label": "Description",
      "default": "<p>The same curated shelves, shipped to your door.</p>"
    },
    {
      "type": "collection",
      "id": "shop_collection",
      "label": "Collection",
      "info": "Shows up to 4 products from this collection. To rotate stock, update the collection — this section follows automatically."
    },
    {
      "type": "text",
      "id": "shop_link_label",
      "label": "Link label",
      "default": "Shop now →",
      "info": "Links to the selected collection. Leave blank to hide."
    },
    { "type": "header", "content": "Membership" },
    {
      "type": "text",
      "id": "membership_eyebrow",
      "label": "Eyebrow",
      "default": "The Little Movie Club · $100/yr"
    },
    {
      "type": "text",
      "id": "membership_heading",
      "label": "Heading",
      "default": "Become a regular, not a customer."
    },
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
      "info": "Placeholder name shown on the sample member card."
    },
    { "type": "header", "content": "Price" },
    {
      "type": "text",
      "id": "price_text",
      "label": "Price",
      "default": "$100"
    },
    {
      "type": "text",
      "id": "price_suffix",
      "label": "After the price",
      "default": "/ year"
    },
    { "type": "header", "content": "Button" },
    {
      "type": "text",
      "id": "button_label",
      "label": "Label",
      "default": "Join the club →"
    },
    { "type": "url", "id": "button_link", "label": "Link" },
    { "type": "header", "content": "Section style" },
    {
      "type": "color",
      "id": "background_color",
      "label": "t:settings.background_color",
      "placeholder": "t:settings.default"
    },
    {
      "type": "range",
      "id": "padding-block-start",
      "label": "Top padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 72
    },
    {
      "type": "range",
      "id": "padding-block-end",
      "label": "Bottom padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 72
    }
  ],
  "blocks": [
    {
      "type": "perk",
      "name": "Perk",
      "settings": [
        {
          "type": "text",
          "id": "title",
          "label": "Perk",
          "default": "Full rental library access"
        },
        {
          "type": "text",
          "id": "detail",
          "label": "Detail",
          "default": "borrow anything, anytime"
        }
      ]
    }
  ],
  "max_blocks": 6,
  "presets": [
    {
      "name": "LMS shop + membership",
      "blocks": [
        {
          "type": "perk",
          "settings": { "title": "Full rental library access", "detail": "borrow anything, anytime" }
        },
        {
          "type": "perk",
          "settings": { "title": "10% off every purchase", "detail": "every single visit" }
        },
        {
          "type": "perk",
          "settings": { "title": "A free birthday movie", "detail": "on us, every year" }
        },
        {
          "type": "perk",
          "settings": { "title": "Members-only events", "detail": "first invites, always" }
        }
      ]
    }
  ]
}
{% endschema %}
```

- [ ] **Step 2: Run theme-check**

Run: `cd /Users/liamparis/web-projects/personal/LMS-sandbox && shopify theme check --path theme/lms-redesign-v4`
Expected: Same baseline as Task 1 (`9 total offenses ... 2 errors`) — no new offenses in `sections/lms-shop-membership.liquid`.

- [ ] **Step 3: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
git add theme/lms-redesign-v4/sections/lms-shop-membership.liquid
git commit -m "Add shop + membership split section"
```

---

### Task 3: Dedicated Events page

**Files:**
- Create: `theme/lms-redesign-v4/sections/lms-events-calendar.liquid`
- Create: `theme/lms-redesign-v4/templates/page.events.json`

**Interfaces:**
- Consumes: `render 'lms-events-list', limit: 0, style: 'rows'` (from Task 1).
- Produces: section type `lms-events-calendar`; page template `page.events` (selectable in Admin when creating a Page — the Page record itself still needs manual creation, noted in Task 5).

- [ ] **Step 1: Create the calendar section**

Create `theme/lms-redesign-v4/sections/lms-events-calendar.liquid`:

```liquid
{% comment %}
  lms-events-calendar — full upcoming event calendar for the dedicated
  Events page. Event data + sort logic lives in snippets/lms-events-list.liquid.
{% endcomment %}

{% render 'contrast-override', background_color: section.settings.background_color, section_id: section.id %}
<div class="lms-events-calendar color-custom-{{ section.id }}"
  style="--lms-pad-top: {{ section.settings.padding-block-start }}px; --lms-pad-bottom: {{ section.settings.padding-block-end }}px;"
  {{ section.shopify_attributes }}>
  <div class="lms-container">
    {% render 'lms-eyebrow', text: section.settings.eyebrow %}
    {%- if section.settings.heading != blank -%}
      <h1 class="lms-events-calendar__heading">{{ section.settings.heading }}</h1>
    {%- endif -%}
    {%- if section.settings.description != blank -%}
      <div class="lms-events-calendar__desc rte">{{ section.settings.description }}</div>
    {%- endif -%}

    {% render 'lms-events-list', limit: 0, style: 'rows' %}
  </div>
</div>

{% stylesheet %}
.lms-events-calendar {
  background: var(--color-background, var(--lms-parchment));
  padding-block: var(--lms-pad-top, 64px) var(--lms-pad-bottom, 72px);
}
.lms-events-calendar .lms-eyebrow { display: block; }
.lms-events-calendar__heading {
  font-family: var(--lms-font-display);
  font-weight: var(--lms-fw-head-extra-bold);
  font-size: clamp(36px, 4.4vw, 56px);
  line-height: var(--lms-lh-tight);
  color: var(--lms-text-strong);
  margin: 14px 0 0;
}
.lms-events-calendar__desc {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 15px;
  line-height: 1.65;
  color: var(--lms-text-body);
  max-width: 540px;
  margin: 20px 0 40px;
}
.lms-events-calendar__desc p { margin: 0 0 1em; }
.lms-events-calendar__desc p:last-child { margin-bottom: 0; }
.lms-events-calendar .lms-events { margin-top: 28px; }
{% endstylesheet %}

{% schema %}
{
  "name": "LMS events calendar",
  "tag": "section",
  "class": "lms-events-calendar-section",
  "settings": [
    { "type": "text", "id": "eyebrow", "label": "Eyebrow", "default": "The full calendar" },
    { "type": "text", "id": "heading", "label": "Heading", "default": "Events & screenings" },
    {
      "type": "richtext",
      "id": "description",
      "label": "Description",
      "default": "<p>Every upcoming screening, signing, and in-store event — soonest first.</p>"
    },
    { "type": "header", "content": "Section style" },
    {
      "type": "color",
      "id": "background_color",
      "label": "t:settings.background_color",
      "placeholder": "t:settings.default"
    },
    {
      "type": "range",
      "id": "padding-block-start",
      "label": "Top padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 64
    },
    {
      "type": "range",
      "id": "padding-block-end",
      "label": "Bottom padding",
      "min": 0,
      "max": 100,
      "step": 4,
      "unit": "px",
      "default": 72
    }
  ],
  "presets": [
    { "name": "LMS events calendar" }
  ]
}
{% endschema %}
```

- [ ] **Step 2: Create the page template**

Create `theme/lms-redesign-v4/templates/page.events.json`:

```json
{
  "sections": {
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
    "events_calendar": {
      "type": "lms-events-calendar",
      "settings": {
        "eyebrow": "The full calendar",
        "heading": "Events & screenings",
        "description": "<p>Every upcoming screening, signing, and in-store event — soonest first.</p>",
        "background_color": "",
        "padding-block-start": 64,
        "padding-block-end": 72
      }
    }
  },
  "order": [
    "main",
    "events_calendar"
  ]
}
```

- [ ] **Step 3: Run theme-check**

Run: `cd /Users/liamparis/web-projects/personal/LMS-sandbox && shopify theme check --path theme/lms-redesign-v4`
Expected: Same baseline as Task 1 — no new offenses in `sections/lms-events-calendar.liquid` or `templates/page.events.json`.

- [ ] **Step 4: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
git add theme/lms-redesign-v4/sections/lms-events-calendar.liquid theme/lms-redesign-v4/templates/page.events.json
git commit -m "Add dedicated Events page template and calendar section"
```

---

### Task 4: Homepage rewiring

**Files:**
- Modify: `theme/lms-redesign-v4/templates/index.json`

**Interfaces:**
- Consumes: section types `lms-shop-membership` (Task 2) and `lms-events-full` (Task 1).
- Produces: the live homepage section order, with `lms_events_membership` and `lms_promo_pair` instances removed (files untouched) and `lms_shop_membership` / `lms_events_full` instances added in their place.

- [ ] **Step 1: Remove the retired section instances and add the new ones**

In `theme/lms-redesign-v4/templates/index.json`, replace the `"lms_events_membership"` and `"lms_promo_pair"` entries (inside `"sections"`) with `"lms_shop_membership"` and `"lms_events_full"`:

Remove this whole block:

```json
    "lms_events_membership": {
      "type": "lms-events-membership",
      "blocks": {
        "perk_rental": {
          "type": "perk",
          "settings": {
            "title": "Full rental library access",
            "detail": "borrow anything, anytime"
          }
        },
        "perk_discount": {
          "type": "perk",
          "settings": {
            "title": "10% off every purchase",
            "detail": "every single visit"
          }
        },
        "perk_birthday": {
          "type": "perk",
          "settings": {
            "title": "A free birthday movie",
            "detail": "on us, every year"
          }
        },
        "perk_events": {
          "type": "perk",
          "settings": {
            "title": "Members-only events",
            "detail": "first invites, always"
          }
        }
      },
      "block_order": [
        "perk_rental",
        "perk_discount",
        "perk_birthday",
        "perk_events"
      ],
      "settings": {
        "events_eyebrow": "Coming up",
        "events_heading": "Events & screenings",
        "events_to_show": 3,
        "events_link_label": "All events →",
        "events_link": "",
        "membership_eyebrow": "The Little Movie Club · $100/yr",
        "membership_heading": "Become a regular, not a customer.",
        "card_est_text": "Est. 2026",
        "card_name_text": "— your name here —",
        "price_text": "$100",
        "price_suffix": "/ year",
        "button_label": "JOIN THE CLUB →",
        "button_link": "/pages/membership",
        "background_color": "",
        "padding-block-start": 72,
        "padding-block-end": 72
      }
    },
    "lms_promo_pair": {
      "type": "lms-promo-pair",
      "blocks": {
        "promo_rental": {
          "type": "lms-promo-card",
          "settings": {
            "eyebrow": "The rental library",
            "heading": "Not ready to commit? Rent it.",
            "body": "<p>A few bucks gets any film home for the week — players included if you need one. Take a chance on something weird, bring it back, tell us what you thought. Free for members, and most of the time, renters become buyers.</p>",
            "stat_label": "Rentals from",
            "stat_value": "$4",
            "stat_suffix": "/ week · free for members",
            "button_label": "Browse library →",
            "button_link": "/collections/all",
            "background_color": "#e4eee9",
            "background_glyph": ""
          },
          "blocks": {}
        },
        "promo_mystery": {
          "type": "lms-promo-card",
          "settings": {
            "eyebrow": "Online · Ships nationwide",
            "heading": "The mystery bag.",
            "body": "<p>We pick, you watch. A bag of films hand-selected by the crew — themed, random, or genre-driven. The best way to discover something you'd never have found on your own.</p>",
            "stat_label": "Starting at",
            "stat_value": "$35",
            "stat_suffix": "",
            "button_label": "Get a bag →",
            "button_link": "",
            "background_color": "#3a2018",
            "background_glyph": "?"
          },
          "blocks": {}
        }
      },
      "block_order": [
        "promo_rental",
        "promo_mystery"
      ],
      "settings": {
        "background_color": "",
        "padding-block-start": 36,
        "padding-block-end": 36
      }
    },
```

Replace it with:

```json
    "lms_shop_membership": {
      "type": "lms-shop-membership",
      "blocks": {
        "perk_rental": {
          "type": "perk",
          "settings": {
            "title": "Full rental library access",
            "detail": "borrow anything, anytime"
          }
        },
        "perk_discount": {
          "type": "perk",
          "settings": {
            "title": "10% off every purchase",
            "detail": "every single visit"
          }
        },
        "perk_birthday": {
          "type": "perk",
          "settings": {
            "title": "A free birthday movie",
            "detail": "on us, every year"
          }
        },
        "perk_events": {
          "type": "perk",
          "settings": {
            "title": "Members-only events",
            "detail": "first invites, always"
          }
        }
      },
      "block_order": [
        "perk_rental",
        "perk_discount",
        "perk_birthday",
        "perk_events"
      ],
      "settings": {
        "shop_eyebrow": "Shop online",
        "shop_heading": "Can't make it in? Shop online.",
        "shop_description": "<p>The same curated shelves, shipped to your door.</p>",
        "shop_collection": "online-store",
        "shop_link_label": "Shop now →",
        "membership_eyebrow": "The Little Movie Club · $100/yr",
        "membership_heading": "Become a regular, not a customer.",
        "card_est_text": "Est. 2026",
        "card_name_text": "— your name here —",
        "price_text": "$100",
        "price_suffix": "/ year",
        "button_label": "JOIN THE CLUB →",
        "button_link": "/pages/membership",
        "background_color": "",
        "padding-block-start": 72,
        "padding-block-end": 72
      }
    },
    "lms_events_full": {
      "type": "lms-events-full",
      "settings": {
        "eyebrow": "Coming up",
        "heading": "Events & screenings",
        "events_to_show": 4,
        "all_events_link_label": "All events →",
        "all_events_link": "/pages/events",
        "background_color": "",
        "padding-block-start": 36,
        "padding-block-end": 36
      }
    },
```

- [ ] **Step 2: Update the section order**

Replace the `"order"` array:

```json
  "order": [
    "lms_hero",
    "lms_ticker",
    "lms_new_releases",
    "lms_events_membership",
    "lms_promo_pair",
    "lms_staff_picks",
    "lms_newsletter_3dYbxn",
    "lms_social_bar_fiYNVL"
  ]
```

with:

```json
  "order": [
    "lms_hero",
    "lms_ticker",
    "lms_new_releases",
    "lms_shop_membership",
    "lms_events_full",
    "lms_staff_picks",
    "lms_newsletter_3dYbxn",
    "lms_social_bar_fiYNVL"
  ]
```

- [ ] **Step 3: Validate JSON syntax**

Run: `python3 -m json.tool theme/lms-redesign-v4/templates/index.json > /dev/null && echo "valid JSON"`
Expected: `valid JSON` (the file has a leading `/* ... */` comment block — `json.tool` will fail on that; if it does, instead run: `sed '1,/^\*\//d' theme/lms-redesign-v4/templates/index.json | python3 -m json.tool > /dev/null && echo "valid JSON"` to strip the header comment before parsing.)

- [ ] **Step 4: Run theme-check**

Run: `cd /Users/liamparis/web-projects/personal/LMS-sandbox && shopify theme check --path theme/lms-redesign-v4`
Expected: Same baseline as Task 1 — `templates/index.json` should report no new offenses (in particular, no `JSONMissingBlock` for `lms-shop-membership` or `lms-events-full`, confirming the section files from Tasks 1–2 are found).

- [ ] **Step 5: Commit**

```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
git add theme/lms-redesign-v4/templates/index.json
git commit -m "Rewire homepage: swap events+membership and promo-pair for shop+membership and full-width events"
```

---

### Task 5: Push to dev store and manual verification

**Files:** none (deployment + verification only).

**Interfaces:** none — this task validates Tasks 1–4 together on the live dev store.

- [ ] **Step 1: Full theme-check pass**

Run: `cd /Users/liamparis/web-projects/personal/LMS-sandbox && shopify theme check --path theme/lms-redesign-v4`
Expected: `9 total offenses found across 9 files. 2 errors.` — identical to the pre-existing baseline noted in the Global Constraints section (all in `templates/page.json` / `templates/page.membership.json` Supercycle blocks, `assets/lms-newsletter.css.liquid`/newsletter section, and `snippets/header-actions.liquid` — none in the files touched by this plan).

- [ ] **Step 2: Push to the dev store**

Run:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --allow-live \
  --only snippets/lms-events-list.liquid \
  --only sections/lms-events-full.liquid \
  --only sections/lms-shop-membership.liquid \
  --only sections/lms-events-calendar.liquid \
  --only templates/page.events.json \
  --only templates/index.json
```
Expected: `The theme 'lms-7/2' (#140918915134) was pushed successfully.`

- [ ] **Step 3: Manual visual check (run by the user — `shopify theme dev` prompts for the storefront password interactively and fails in non-interactive contexts)**

Ask the user to run, in their own terminal:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com
```
Then check:
1. Homepage shop+membership section: 4 products render from the `online-store` collection (or the 4-tile placeholder state if the collection setting didn't carry over); membership panel (member card, 4 perks, price, join button) looks and functions identically to the old events+membership section.
2. Homepage full-width events section: shows up to 4 upcoming events as a card row, soonest first, with correct Members/Public badges; "All events →" link points to `/pages/events` (will 404 until the manual page-creation follow-up below is done — expected until then).
3. `lms-events-membership.liquid` and `lms-promo-pair.liquid` sections no longer appear anywhere on the homepage, but both files still exist in `theme/lms-redesign-v4/sections/`.

- [ ] **Step 4: Note remaining manual follow-up**

Confirm with the user that the "Events" Page record still needs to be created manually in Admin → Online Store → Pages (title "Events", template suffix `events`) — this is a content operation the CLI's store-auth token can't perform (same limitation hit earlier this session for the nav-menu link and the `staff_link` metaobject field). Once created, `/pages/events` will resolve and the "All events →" links (from both the full-width homepage section and, if added later, elsewhere) will work.
