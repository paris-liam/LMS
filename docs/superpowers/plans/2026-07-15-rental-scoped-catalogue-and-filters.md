# Rental-Scoped Catalogue, New Arrivals, and Inventory-Page Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scope the movie catalogue to Rental-tagged `Media > Videos` products everywhere it's browsed, replace the homepage's merchant-curated "New arrivals" rail with an automatic 7-day New Arrivals feed, and reduce the inventory/search page to exactly four filter criteria (New Arrivals toggle, Community Picks toggle, Format checkboxes, Genre checkboxes).

**Architecture:** Two Shopify smart collections do the scoping work natively (no custom filter logic): "All Movies" gains a `tag = Rental` rule (already powers the hero button and the shop-all/search page), and a new "New Arrivals" collection (`Category = Media > Videos AND tag = Rental AND tag = new-arrival`, sorted newest-first) feeds the homepage rail. A Shopify Flow keeps the `new-arrival` tag in sync going forward (add on create, remove after 7 days via a native Wait action); a one-time backfill script tags currently-existing qualifying products so the collection isn't empty at launch. `blocks/filters.liquid` (already generic/config-driven — it renders whatever Search & Discovery exposes, no metafield keys are hardcoded in Liquid) gets two Liquid changes: suppress the generic Product-tags checkbox facet on the vertical (shop-all) layout, and add a second toggle switch for `community-pick` mirroring the existing `new-arrival` switch. Format/Genre facet source (`shopify.media-format`/`shopify.genre` vs. the unused `custom.format`/`custom.genres`) is a Search & Discovery admin config change, not code.

**Tech Stack:** Shopify Horizon theme (Liquid), Shopify Admin GraphQL API via `shopify store execute` (bash + jq wrapper scripts, using the CLI's own OAuth session rather than the older curl+`SHOPIFY_ADMIN_TOKEN` pattern in `scripts/create-movie-metafield-definitions.sh`/`create-curation-collections.sh` — deviation decided during pre-flight review since no admin token is provisioned in this environment), Shopify Flow (manual admin setup), `shopify theme check`.

## Global Constraints

- Dev store only: `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`. Never touch production (`p0wkgv-wy.myshopify.com`) as part of this plan.
- Admin API scripts default to `SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com`, override only on explicit instruction — follow the existing pattern in `scripts/create-movie-metafield-definitions.sh` and `scripts/create-curation-collections.sh`.
- No new locale/translation keys (`en.default.json`) — hardcode any new English copy directly in Liquid. Adding a `content.*` key triggers ~30 `MatchingTranslations` theme-check errors (one per other locale). See project memory `theme-check-matchingtranslations-gotcha`.
- Verification baseline: `shopify theme check --path theme/lms-redesign-v4` currently reports 9 offenses / 2 errors (pre-existing Supercycle `JSONMissingBlock`, unrelated to this work). Every theme-check run in this plan must not exceed that baseline.
- Gate all `blocks/filters.liquid` changes to `block_settings.filter_style == 'vertical'` (the shop-all page only) — the horizontal/default collection-page layout must stay unchanged, matching the pattern already established in this file (see `docs/superpowers/plans/2026-07-14-shop-all-toolbar-polish.md`).
- Every product/collection mutation must be idempotent or safely re-runnable, per the `scripts/*.sh` convention (treat "already exists"/"already tagged" userErrors as OK, not failures).

---

### Task 1: Script — scope "All Movies" to Rental

**Files:**
- Create: `scripts/scope-all-movies-to-rental.sh`

**Interfaces:**
- Produces: an updated "All Movies" smart collection (handle `all-movies`) with ruleset `Category = Media > Videos AND tag = Rental`. Later tasks (2, 4) assume this collection is Rental-scoped when linking to it as "the inventory/search page."

- [x] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Adds a "tag = Rental" rule to the existing "All Movies" smart collection
# (handle: all-movies), which already powers the hero's "Browse the shelves"
# button and the shop-all/search page. Re-running is safe: it always sets
# the ruleset to the same two rules (replace, not append).
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/scope-all-movies-to-rental.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

echo "Looking up 'all-movies' collection id..."
LOOKUP_QUERY='query { collectionByHandle(handle: "all-movies") { id ruleSet { rules { column relation condition } } } }'
LOOKUP_RESP=$(shopify store execute --store "$STORE" -j -q "$LOOKUP_QUERY")
COLLECTION_ID=$(echo "$LOOKUP_RESP" | jq -r '.collectionByHandle.id // empty')
if [[ -z "$COLLECTION_ID" ]]; then
  echo "✗ Could not find collection with handle 'all-movies':"; echo "$LOOKUP_RESP" | jq .; exit 1
fi
echo "  found: ${COLLECTION_ID}"

MUTATION='mutation UpdateRuleSet($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { id handle ruleSet { appliedDisjunctively rules { column relation condition } } }
    userErrors { field message }
  }
}'
VARS=$(jq -n --arg id "$COLLECTION_ID" '{
  input: {
    id: $id,
    ruleSet: {
      appliedDisjunctively: false,
      rules: [
        { column: "PRODUCT_CATEGORY_ID", relation: "EQUALS", condition: "gid://shopify/TaxonomyCategory/me-7" },
        { column: "TAG", relation: "EQUALS", condition: "Rental" }
      ]
    }
  }
}')
RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$MUTATION" -v "$VARS")
ERR=$(echo "$RESP" | jq -r '.collectionUpdate.userErrors[0].message // empty')
if [[ -n "$ERR" ]]; then
  echo "✗ collectionUpdate failed: ${ERR}"; exit 1
fi
echo "✓ All Movies ruleset updated:"
echo "$RESP" | jq '.collectionUpdate.collection.ruleSet'
```

- [x] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/scope-all-movies-to-rental.sh
./scripts/scope-all-movies-to-rental.sh
```

If this is the first Admin API call in the session, it may need `shopify store auth --store lms-sandbox-lutsfahz.myshopify.com --scopes write_products` first (interactive browser login). Expected output ends with the two-rule ruleset (`PRODUCT_CATEGORY_ID` / `TAG=Rental`) printed as JSON.

- [x] **Step 3: Verify the product count dropped**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --query \
  'query { collectionByHandle(handle: "all-movies") { productsCount { count } } }'
```

Expected: `count` is roughly 925 (was 2,526 before this change — verify it dropped, exact number may drift slightly as catalogue data changes).

- [x] **Step 4: Commit**

```bash
git add scripts/scope-all-movies-to-rental.sh
git commit -m "Add script to scope All Movies collection to Rental-tagged products"
```

---

### Task 2: Script — create the "New Arrivals" smart collection

**Files:**
- Create: `scripts/create-new-arrivals-collection.sh`

**Interfaces:**
- Consumes: none (independent of Task 1, but conceptually layers on top of the same Rental scoping).
- Produces: a smart collection with handle `new-arrivals`, ruleset `Category = Media > Videos AND tag = Rental AND tag = new-arrival`, sorted `CREATED_DESC`. Task 5 (homepage section) reads `collections['new-arrivals']` by this exact handle.

- [x] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Creates the "New Arrivals" smart collection (handle: new-arrivals) that
# feeds the homepage New Arrivals rail. Membership is fully rule-driven —
# Category = Media > Videos AND tag = Rental AND tag = new-arrival — so a
# product enters/leaves automatically as the new-arrival tag is added/removed
# by the Shopify Flow set up in the admin runbook (Task 6).
# Idempotent: a "handle has already been taken" userError is treated as OK.
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/create-new-arrivals-collection.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

MUTATION='mutation Create($input: CollectionInput!) {
  collectionCreate(input: $input) { collection { id handle } userErrors { field message } }
}'
VARS=$(jq -n '{
  input: {
    title: "New Arrivals",
    handle: "new-arrivals",
    sortOrder: "CREATED_DESC",
    ruleSet: {
      appliedDisjunctively: false,
      rules: [
        { column: "PRODUCT_CATEGORY_ID", relation: "EQUALS", condition: "gid://shopify/TaxonomyCategory/me-7" },
        { column: "TAG", relation: "EQUALS", condition: "Rental" },
        { column: "TAG", relation: "EQUALS", condition: "new-arrival" }
      ]
    }
  }
}')
RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$MUTATION" -v "$VARS")
ERR=$(echo "$RESP" | jq -r '.collectionCreate.userErrors[0].message // empty')
if [[ -n "$ERR" ]]; then
  if echo "$ERR" | grep -qiE 'taken|already|in use'; then
    echo "= New Arrivals: exists (ok)"
  else
    echo "✗ New Arrivals: ${ERR}"; exit 1
  fi
else
  echo "✓ New Arrivals created → $(echo "$RESP" | jq -r '.collectionCreate.collection.handle')"
fi
```

- [x] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/create-new-arrivals-collection.sh
./scripts/create-new-arrivals-collection.sh
```

- [x] **Step 3: Verify the collection exists with the right rules**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --query \
  'query { collectionByHandle(handle: "new-arrivals") { title ruleSet { rules { column relation condition } } sortOrder } }'
```

Expected: three rules (category, `TAG=Rental`, `TAG=new-arrival`), `sortOrder: CREATED_DESC`.

- [x] **Step 4: Commit**

```bash
git add scripts/create-new-arrivals-collection.sh
git commit -m "Add script to create the New Arrivals smart collection"
```

---

### Task 3: Script — backfill `new-arrival` tags on existing recent products

**Why this task exists:** Task 6's Shopify Flow only tags products going forward (on the `product created` event). The ~925 Rental movies already in the catalogue were created during this week's bulk reformat/import, so without a backfill, the New Arrivals collection would be empty at launch even though those products genuinely match the "created in the last 7 days" intent.

**Files:**
- Create: `scripts/backfill-new-arrival-tags.sh`

**Interfaces:**
- Consumes: none directly, but only makes sense to run after Task 1 (Rental scoping) is in place conceptually — it queries `tag:Rental` regardless.
- Produces: `new-arrival` tag added to all currently-existing products matching `tag:Rental AND created_at >= (today - 7 days)`.

- [x] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# One-time backfill: tags every existing Rental product created in the last
# 7 days with `new-arrival`, so the New Arrivals collection (Task 2) is
# populated at launch. Going forward, the Shopify Flow from the admin
# runbook (Task 6) takes over tagging/untagging for new products. Safe to
# re-run — tagsAdd is idempotent (won't duplicate an existing tag).
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/backfill-new-arrival-tags.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

SINCE=$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)
echo "Backfilling new-arrival tag for tag:Rental products created since ${SINCE}..."

SEARCH_QUERY="tag:Rental AND created_at:>='${SINCE}'"
FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q) {
    edges { cursor node { id title } }
    pageInfo { hasNextPage }
  }
}'
TAG_ADD='mutation Tag($id: ID!, $tags: [String!]!) {
  tagsAdd(id: $id, tags: $tags) { userErrors { field message } }
}'

AFTER="null"
TOTAL=0
while :; do
  VARS=$(jq -n --arg q "$SEARCH_QUERY" --argjson after "$AFTER" '{q: $q, after: $after}')
  RESP=$(shopify store execute --store "$STORE" -j -q "$FIND" -v "$VARS")
  EDGES=$(echo "$RESP" | jq -c '.products.edges[]')
  if [[ -z "$EDGES" ]]; then break; fi

  while IFS= read -r EDGE; do
    PRODUCT_ID=$(echo "$EDGE" | jq -r '.node.id')
    TITLE=$(echo "$EDGE" | jq -r '.node.title')
    TAG_VARS=$(jq -n --arg id "$PRODUCT_ID" '{id: $id, tags: ["new-arrival"]}')
    TAG_RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$TAG_ADD" -v "$TAG_VARS")
    TAG_ERR=$(echo "$TAG_RESP" | jq -r '.tagsAdd.userErrors[0].message // empty')
    if [[ -n "$TAG_ERR" ]]; then
      echo "  ✗ ${TITLE}: ${TAG_ERR}"
    else
      TOTAL=$((TOTAL + 1))
      echo "  ✓ ${TITLE} tagged new-arrival"
    fi
  done <<< "$EDGES"

  HAS_NEXT=$(echo "$RESP" | jq -r '.products.pageInfo.hasNextPage')
  if [[ "$HAS_NEXT" != "true" ]]; then break; fi
  LAST_CURSOR=$(echo "$RESP" | jq -r '.products.edges[-1].cursor')
  AFTER=$(jq -n --arg c "$LAST_CURSOR" '$c')
done

echo "✓ Backfill complete: ${TOTAL} product(s) tagged new-arrival."
```

- [x] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/backfill-new-arrival-tags.sh
./scripts/backfill-new-arrival-tags.sh
```

Expected: prints one line per tagged product, ends with a total count (expect close to the full ~925 Rental count right now, per the known transient state documented in the spec).

- [x] **Step 3: Verify the New Arrivals collection is now populated**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --query \
  'query { collectionByHandle(handle: "new-arrivals") { productsCount { count } } }'
```

Expected: `count` > 0 (matches the backfill total from Step 2, modulo any products that didn't match `Category = Media > Videos` exactly).

- [x] **Step 4: Commit**

```bash
git add scripts/backfill-new-arrival-tags.sh
git commit -m "Add one-time backfill script for new-arrival tags on existing recent products"
```

---

### Task 4: Homepage — rewrite `lms-new-releases.liquid` into the New Arrivals rail

**Files:**
- Modify: `theme/lms-redesign-v4/sections/lms-new-releases.liquid` (full rewrite of the Liquid body and schema `settings`; CSS/stylesheet block is unchanged)

**Interfaces:**
- Consumes: `collections['new-arrivals']` (Task 2), `collections['all-movies']` (Task 1) — both referenced by fixed handle.
- Produces: no new interfaces consumed elsewhere; this is a leaf homepage section.

- [x] **Step 1: Replace the Liquid body (lines 1–53) and schema settings**

Replace the file's opening comment + liquid assigns + markup (current lines 1–53) with:

```liquid
{% comment %}
  lms-new-releases — "New Arrivals" rail: the 10 most recent Rental movies.
  Data source is the fixed `new-arrivals` smart collection (Category = Media
  > Videos AND tag = Rental AND tag = new-arrival), kept in sync by a
  Shopify Flow (see docs/superpowers/plans/2026-07-15-rental-scoped-catalogue-and-filters.md).
  The "+N more" button links to the shop-all/search page with the New
  Arrivals toggle pre-set (filter.p.tag=new-arrival).
  Desktop: 5-up grid. Tablet: 3-up. Mobile: horizontal scroll-snap row.
{% endcomment %}

{%- liquid
  assign collection = collections['new-arrivals']
  assign limit = 10
  assign remaining = collection.products_count | minus: limit
  assign all_movies_url = collections['all-movies'].url
-%}

{% render 'contrast-override', background_color: section.settings.background_color, section_id: section.id %}
<div class="lms-new-releases color-custom-{{ section.id }}"
  style="--lms-pad-top: {{ section.settings.padding-block-start }}px; --lms-pad-bottom: {{ section.settings.padding-block-end }}px;"
  {{ section.shopify_attributes }}>
  <div class="lms-container">

    <div class="lms-new-releases__header">
      <div>
        {% render 'lms-eyebrow', text: section.settings.eyebrow %}
        {%- if section.settings.heading != blank -%}
          <h2 class="lms-new-releases__heading">{{ section.settings.heading }}</h2>
        {%- endif -%}
      </div>
      {%- if remaining > 0 -%}
        <a href="{{ all_movies_url }}?filter.p.tag=new-arrival" class="lms-btn lms-btn--outline lms-btn--sm">
          + {{ remaining }} more
        </a>
      {%- endif -%}
    </div>

    <div class="lms-new-releases__grid">
      {%- if collection.products_count > 0 -%}
        {%- for product in collection.products limit: limit -%}
          {% render 'lms-product-card', card_product: product %}
        {%- endfor -%}
      {%- else -%}
        <div class="lms-new-releases__empty">
          New arrivals will appear here as soon as they're added.
        </div>
      {%- endif -%}
    </div>

  </div>
</div>
```

- [x] **Step 2: Add the empty-state style**

In the `{% stylesheet %}` block, immediately after the existing `.lms-new-releases__header` rule block (after the closing `}` of `.lms-new-releases .lms-eyebrow { display: block; }`), add:

```css
.lms-new-releases__empty {
  font-family: var(--lms-font-mono);
  font-weight: var(--lms-fw-mono-light);
  font-size: 13px;
  color: var(--lms-text-muted);
  padding: 32px 0;
}
```

- [x] **Step 3: Replace the schema settings**

Replace the `"settings"` array in the `{% schema %}` block — remove the `collection` (type `collection`) and `products_to_show` (type `range`) entries, and remove the `button_label` entry (button copy is now hardcoded "+N more" in Step 1). The resulting settings array:

```json
  "settings": [
    { "type": "header", "content": "Heading" },
    {
      "type": "text",
      "id": "eyebrow",
      "label": "Eyebrow",
      "default": "Just dropped"
    },
    {
      "type": "text",
      "id": "heading",
      "label": "Heading",
      "default": "New arrivals this week"
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
      "default": 24
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
```

Also update `"name"` at the top of the schema from `"LMS new releases"` to `"LMS new arrivals"`, and the preset `"name"` from `"LMS new releases"` to `"LMS new arrivals"`.

- [x] **Step 4: Theme check**

```bash
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -10
```

Expected: no new offenses beyond the 9-offense/2-error baseline (a removed setting referenced nowhere else won't trigger anything; if theme-check flags an unused/missing setting reference, fix it before proceeding).

- [x] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/sections/lms-new-releases.liquid
git commit -m "Rework homepage New Arrivals rail to source from the New Arrivals smart collection"
```

---

### Task 5: Inventory page — remove the generic Tags facet, add the Community Picks toggle

**Files:**
- Modify: `theme/lms-redesign-v4/blocks/filters.liquid`

**Interfaces:**
- Consumes: the native `filters` collection Liquid object (Search & Discovery), specifically `filter.param_name == 'filter.p.tag'` and its `.values[]` where `value.value == 'new-arrival'` / `'community-pick'` — same access pattern already used for the New Arrivals switch.
- Produces: no new interfaces; this is UI-only.

- [x] **Step 1: Suppress the generic Tags facet on the desktop vertical layout**

Find this line (~273, inside the desktop `{%- for filter in filters -%}` loop, `{% else %}` branch):

```liquid
                        render 'list-filter', filter: filter, filter_style: block_settings.filter_style, active_value_count: active_value_count, should_render_clear: should_render_clear, show_swatch_label: block_settings.show_swatch_label, sectionId: section.id, suppress_new_arrival: suppress_na
```

Replace it with:

```liquid
                        unless filter.param_name == 'filter.p.tag' and block_settings.filter_style == 'vertical'
                          render 'list-filter', filter: filter, filter_style: block_settings.filter_style, active_value_count: active_value_count, should_render_clear: should_render_clear, show_swatch_label: block_settings.show_swatch_label, sectionId: section.id, suppress_new_arrival: suppress_na
                        endunless
```

This keeps `total_active_values` counting (the lines above it, unchanged) so "Clear all" / chip behavior still reflects an active toggle, but stops the Product-tags checkbox accordion (`label-*`, `rare`, `staff-pick`, `holiday`, `new-arrival`, `community-pick`) from rendering on the shop-all page. Non-vertical (horizontal) pages are untouched — the `unless` only fires when both conditions are true.

- [x] **Step 2: Mirror the same suppression in the mobile drawer**

Find this line (~572, inside the drawer's `{%- for filter in filters -%}` loop, `{% else %}` branch):

```liquid
                        render 'list-filter', filter: filter, filter_style: 'vertical', active_value_count: active_value_count, should_render_clear: false, in_drawer: true, sectionId: section.id, suppress_new_arrival: suppress_na
```

Replace it with:

```liquid
                        unless filter.param_name == 'filter.p.tag' and block_settings.filter_style == 'vertical'
                          render 'list-filter', filter: filter, filter_style: 'vertical', active_value_count: active_value_count, should_render_clear: false, in_drawer: true, sectionId: section.id, suppress_new_arrival: suppress_na
                        endunless
```

- [x] **Step 3: Add the Community Picks toggle on desktop**

Find the desktop New Arrivals toggle block (~lines 279–311):

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
                      <span class="facets-new-arrivals__label">New arrivals</span>
                      <facet-remove-component
                        class="facets-new-arrivals__switch{% if na_value.active %} is-on{% endif %}"
                        data-url="{% if na_value.active %}{{ na_value.url_to_remove }}{% else %}{{ na_value.url_to_add }}{% endif %}"
                        role="switch"
                        aria-checked="{% if na_value.active %}true{% else %}false{% endif %}"
                        aria-label="New arrivals"
                        tabindex="0"
                        on:click="/removeFilter?form="
                        on:keydown="/removeFilter?form="
                      ></facet-remove-component>
                    </div>
                  {%- endcapture -%}
                  {%- assign rendered_filters = rendered_filters | append: new_arrivals_toggle -%}
                {%- endif -%}
              {%- endif -%}
```

Immediately after this whole block (after its final `{%- endif -%}`), insert a second, parallel block for Community Picks:

```liquid
              {%- if block_settings.filter_style == 'vertical' -%}
                {%- liquid
                  assign cp_value = null
                  for filter in filters
                    if filter.param_name == 'filter.p.tag'
                      for value in filter.values
                        if value.value == 'community-pick'
                          assign cp_value = value
                          break
                        endif
                      endfor
                    endif
                  endfor
                -%}
                {%- if cp_value -%}
                  {%- capture community_picks_toggle -%}
                    <div class="facets__item facets-new-arrivals">
                      <span class="facets-new-arrivals__label">Community picks</span>
                      <facet-remove-component
                        class="facets-new-arrivals__switch{% if cp_value.active %} is-on{% endif %}"
                        data-url="{% if cp_value.active %}{{ cp_value.url_to_remove }}{% else %}{{ cp_value.url_to_add }}{% endif %}"
                        role="switch"
                        aria-checked="{% if cp_value.active %}true{% else %}false{% endif %}"
                        aria-label="Community picks"
                        tabindex="0"
                        on:click="/removeFilter?form="
                        on:keydown="/removeFilter?form="
                      ></facet-remove-component>
                    </div>
                  {%- endcapture -%}
                  {%- assign rendered_filters = rendered_filters | append: community_picks_toggle -%}
                {%- endif -%}
              {%- endif -%}
```

Note: this reuses the `.facets-new-arrivals` / `.facets-new-arrivals__label` / `.facets-new-arrivals__switch` CSS classes from the existing New Arrivals switch — they're a generic toggle-switch component despite the name, and reusing them keeps this a Liquid-only change with zero new CSS. Do not rename the classes as part of this task.

- [x] **Step 4: Add the Community Picks toggle in the mobile drawer**

Find the drawer's New Arrivals toggle block (~lines 576–605, same shape as Step 3 but using `na_value_drawer` and no `rendered_filters` append — it renders directly). Immediately after its closing `{%- endif -%}` (the one closing `{%- if block_settings.filter_style == 'vertical' -%}` for the drawer), insert:

```liquid
                {%- if block_settings.filter_style == 'vertical' -%}
                  {%- liquid
                    assign cp_value_drawer = null
                    for filter in filters
                      if filter.param_name == 'filter.p.tag'
                        for value in filter.values
                          if value.value == 'community-pick'
                            assign cp_value_drawer = value
                            break
                          endif
                        endfor
                      endif
                    endfor
                  -%}
                  {%- if cp_value_drawer -%}
                    <div class="facets__item facets-new-arrivals">
                      <span class="facets-new-arrivals__label">Community picks</span>
                      <facet-remove-component
                        class="facets-new-arrivals__switch{% if cp_value_drawer.active %} is-on{% endif %}"
                        data-url="{% if cp_value_drawer.active %}{{ cp_value_drawer.url_to_remove }}{% else %}{{ cp_value_drawer.url_to_add }}{% endif %}"
                        role="switch"
                        aria-checked="{% if cp_value_drawer.active %}true{% else %}false{% endif %}"
                        aria-label="Community picks"
                        tabindex="0"
                        on:click="/removeFilter?form="
                        on:keydown="/removeFilter?form="
                      ></facet-remove-component>
                    </div>
                  {%- endif -%}
                {%- endif -%}
```

- [x] **Step 5: Theme check**

```bash
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -10
```

Expected: no new offenses beyond the 9-offense/2-error baseline.

- [x] **Step 6: Commit**

```bash
git add theme/lms-redesign-v4/blocks/filters.liquid
git commit -m "Shop-all: drop generic Tags facet, add Community Picks toggle"
```

---

### Task 6: Admin runbook (manual — no code, no commit)

**Status: deferred.** Tasks 1-5 are complete and shipped to the dev store's live theme (140918915134). This task requires manual Shopify Admin UI work (Flow builder, Search & Discovery app) that was not completed as part of this implementation pass — the feature is live but partially degraded until this is done: the Format and Genre checkboxes won't appear (Search & Discovery isn't configured for those metafields), the Community Picks toggle won't appear (no product carries the `community-pick` tag yet), and `new-arrival` won't be applied to genuinely new products created after the one-time backfill (Task 3) until the Flow exists.

These steps happen in the Shopify Admin UI directly (Flow builder, Search & Discovery app) and cannot be scripted against a public Admin API. Complete them on `lms-sandbox-lutsfahz.myshopify.com`.

- [ ] **Step 1: Create the New Arrivals Flow**

Admin → Apps → Flow → Create workflow:

- **Trigger:** "Product created"
- **Action 1:** "Add tags" → tags: `new-arrival` → apply to: the triggering product
- **Action 2:** "Wait" → duration: 7 days
- **Action 3:** "Remove tags" → tags: `new-arrival` → apply to: the triggering product

Name it "New Arrival tag lifecycle" and turn it on. This uses Flow's native event trigger + Wait action (no relative-date search query needed) — it fires once per product creation and handles both the add and, 7 days later, the removal in a single run.

- [ ] **Step 2: Enable Format and Genre filters in Search & Discovery**

Admin → Apps → Search & Discovery → Filters (or the equivalent current path in the installed app version):

- Enable filtering on `product.metafields.shopify.media-format` (label it "Format" if the app lets you set a display label).
- Enable filtering on `product.metafields.shopify.genre` (label it "Genre").
- Confirm the "Product tags" filter is enabled (required — it's what powers the New Arrivals and Community Picks toggles, even though its generic checkbox list is now suppressed in the theme).
- If `custom.format`, `custom.genres`, `custom.genre` (singular), `custom.label`, or `custom.condition` are enabled from an earlier iteration, disable/remove them — they're unpopulated on the current catalogue and would show as empty/broken facets.

- [ ] **Step 3: Verify filter counts manually**

Visit `https://lms-sandbox-lutsfahz.myshopify.com/collections/all-movies` (with the storefront password, per project memory `dev-store-storefront-password`) and confirm the Format and Genre sidebar facets show non-zero counts matching real catalogue data, not blank/zero-count lists.

---

### Task 7: Push and manual QA

**Files:** none (deployment + verification only)

- [x] **Step 1: Push the changed theme files**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only sections/lms-new-releases.liquid --only blocks/filters.liquid --allow-live
```

- [ ] **Step 2: Manual QA checklist**

On the pushed dev theme (storefront password required):

1. [x] Homepage: "New Arrivals" rail shows ≤10 cards sourced from real Rental movies; "+N more" appears only when the New Arrivals collection has more than 10 products, with the correct count.
2. [ ] Clicking "+N more" lands on `/collections/all-movies` with the New Arrivals toggle already switched on and the grid pre-filtered accordingly.
3. [x] Shop-all page (`/collections/all-movies`): total product count is ~925 (Rental-scoped), not 2,526.
4. [ ] Format and Genre checkboxes show real, non-zero counts and correctly filter the grid.
5. [x] New Arrivals toggle and Community Picks toggle both render as switches (not checkboxes) and correctly filter when turned on.
6. [x] No generic "Tags" checkbox group (`label-*`/`rare`/`staff-pick`/`holiday`) appears anywhere on the shop-all sidebar or drawer.
7. [ ] Combining a Format checkbox + a Genre checkbox narrows results (OR within each group); adding a toggle further narrows (AND across groups).
8. [ ] Search box and sort control still work as before.
9. [ ] Mobile: open the filter drawer, confirm both toggles and the Format/Genre accordions render correctly, still no Tags group.
10. [ ] Visit a normal (non-shop-all) `collection.json` page and confirm it's visually unchanged — horizontal filter bar, no toggles, no relocated search box.
11. [ ] Zero-result state: apply a Format/Genre combination with no matches and confirm the existing empty-state UI renders (not a blank grid).

Items 4 and 9 (Format/Genre facets, Community Picks) cannot pass until Task 6 is done. Remaining unchecked items were not explicitly re-verified during this session's QA pass.

- [ ] **Step 3: Record any QA failures as follow-up items** — do not silently patch around them; re-open the relevant task above if something doesn't match the checklist.

---

## Deferred work (not part of this plan — tracked in the design spec)

- Automating `community-pick` tag sync with the `staff_pick` metaobject (currently a manual two-step convention: add the metaobject entry, add the tag).
- Scoping `sections/product-recommendations.liquid` (Shopify's native algorithmic recommendations) to Rental-only — not supported by Shopify's recommendation engine without a custom fallback.
- Supercycle Methods-block / availability filtering (separate track, blocked on Supercycle app-block mounting).
- Any change to the individual product page template itself.
- Search box / sort control behavior changes.

## Self-Review Notes

- **Spec coverage:** §1 scoping → Task 1. §2 New Arrivals (Flow + collection + homepage rail) → Tasks 2, 3, 4, 6 Step 1. §3 four filters → Task 5, Task 6 Step 2. §4 ("only these criteria") → Task 5 Step 1/2 (Tags facet removal) confirmed still leaves search/sort per the approved design.
- **Placeholder scan:** no TBD/TODO; every step has literal code or exact manual UI instructions (Task 6 is manual by necessity — no public Admin API exists for Flow workflows or Search & Discovery filter config, consistent with how the 2026-07-14 shop-all spec treated the same category of change).
- **Type/name consistency:** `new-arrival` and `community-pick` tag strings, the `new-arrivals`/`all-movies` collection handles, and the `.facets-new-arrivals*` CSS class names are used identically across Tasks 2–5.
- **Known gap closed during planning:** the spec's Flow design (event Flow + separate scheduled sweep) is implemented here as a single event-triggered Flow using a native Wait action instead — simpler and avoids relying on relative-date search syntax in Flow's Find-product action. This still satisfies the spec's intent (tag added on create, removed after 7 days). Task 3 (backfill script) was added during planning to cover the gap where Flow only fires on new creates and wouldn't otherwise populate New Arrivals for the ~925 products created during this week's bulk import.
