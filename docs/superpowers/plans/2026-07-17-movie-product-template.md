# Dedicated Movie Product Template — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated, read-only movie product template that shows only poster, title, curated genre/format chips, an in-store availability indicator, an out-of-stock notify-me capture, and the description — no price, variant picker, add-to-cart, or online transaction path.

**Architecture:** A new Shopify OS 2.0 JSON template (`templates/product.movie.json`) points at one new purpose-built Liquid section (`sections/main-movie.liquid`) that renders the whole page directly. Retail keeps the default `product.json`/`product-information` untouched. Availability is decided in a single, greppable, swappable Liquid block so it can flip from Shopify inventory to the Supercycle signal later.

**Tech Stack:** Shopify Horizon theme (Liquid, section schema, `{% stylesheet %}`), Shopify CLI (`shopify theme check`, `shopify theme dev`/`push`), native `{% form 'contact' %}`.

## Global Constraints

- **Target:** dev store `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`. Never production.
- **Read-only movie page.** No price, no variant picker, no quantity, no add-to-cart, no dynamic/express checkout, and **no Supercycle Methods-block slot** (`[name="id"]` form intentionally absent). This is a scoped, intentional override of the Methods-slot reservation rule in `CLAUDE.md`, for this template only.
- **Single availability check.** Exactly one Liquid block decides `movie_in_stock`, marked `{# STAND-IN: … swap to scf.avf / supercycle.* on install #}`. Indicator and notify-me both read that one variable.
- **Curated attributes only.** Chips come from `shopify.genre` and `shopify.media-format` metafields. Never render raw internal tags (`Rental`, `Floor Sale`).
- **Hardcode English UI strings.** Do NOT add new keys to `locales/en.default.json` (adding one key errors ~30× across other locales — see `theme-check MatchingTranslations` gotcha). Use literal English text.
- **Reuse existing design system:** `.lms-badge` / `.lms-badge--muted` chip classes (already used in `snippets/lms-product-card.liquid`) and `--lms-*` tokens from `assets/lms-tokens.css`.
- **Chip links:** `/collections/all-movies?filter.p.m.shopify.genre=<handle>` and `…?filter.p.m.shopify.media-format=<handle>`.
- **Lint gate:** `shopify theme check --path theme/lms-redesign-v4` must not introduce new offenses over baseline.

---

## File Structure

- **Create `theme/lms-redesign-v4/sections/main-movie.liquid`** — the entire movie PDP: media, title, chips, availability, in-store notice, notify-me, description, plus its `{% stylesheet %}` and `{% schema %}`. One file, one responsibility.
- **Create `theme/lms-redesign-v4/templates/product.movie.json`** — minimal JSON template referencing the `main-movie` section.
- **Unchanged:** `templates/product.json`, `sections/product-information.liquid` (retail path).

All paths below are relative to repo root `/Users/liamparis/web-projects/personal/LMS-sandbox/`.

### Verification note (applies to every task)

This is a Liquid theme with no unit-test runner. Each task's "test" is: (1) `shopify theme check` stays clean, and (2) a **manual browser check** on the dev store. To view changes, in **your own terminal** (interactive password prompt) run:

```bash
shopify theme dev --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com
```

…or push the two files to the dev working theme and open the product URL:

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only sections/main-movie.liquid --only templates/product.movie.json
```

You need **one movie product assigned to the `movie` template** to see anything (Task 1, Step 4).

---

## Task 1: Section scaffold + template + assignment (poster, title, description)

Delivers a working read-only page with poster, title, and description — and the complete stylesheet the later tasks' markup will use. No commerce UI exists in the code.

**Files:**
- Create: `theme/lms-redesign-v4/sections/main-movie.liquid`
- Create: `theme/lms-redesign-v4/templates/product.movie.json`

**Interfaces:**
- Produces: a section `type: "main-movie"`; a Liquid variable `movie_in_stock` is added in Task 3. Later tasks insert markup at the marked anchors inside `.lms-movie__details` (`{# ANCHOR: chips #}`, `{# ANCHOR: availability #}`, `{# ANCHOR: notify #}`).

- [ ] **Step 1: Create the section file**

Create `theme/lms-redesign-v4/sections/main-movie.liquid`:

```liquid
{% comment %}
  main-movie — dedicated read-only PDP for rental/movie products.
  Spec: docs/superpowers/specs/2026-07-17-movie-product-template-design.md
  Shows poster, title, curated genre/format chips, in-store availability,
  out-of-stock notify-me, and description. NO price / variant / add-to-cart /
  dynamic checkout / Supercycle Methods slot — all transactions are in-store.
{% endcomment %}

<section class="lms-movie page-width">
  <div class="lms-movie__grid">
    <div class="lms-movie__media">
      {%- if product.featured_image -%}
        {{ product.featured_image
          | image_url: width: 900
          | image_tag:
            widths: '450, 675, 900',
            sizes: '(max-width: 749px) 100vw, 45vw',
            loading: 'eager',
            alt: product.featured_image.alt | default: product.title }}
      {%- else -%}
        <div class="lms-movie__placeholder">{{ 'product-1' | placeholder_svg_tag }}</div>
      {%- endif -%}
    </div>

    <div class="lms-movie__details">
      <h1 class="lms-movie__title">{{ product.title }}</h1>

      {# ANCHOR: chips #}
      {# ANCHOR: availability #}
      {# ANCHOR: notify #}

      {%- if product.description != blank -%}
        <div class="lms-movie__description rte">{{ product.description }}</div>
      {%- endif -%}
    </div>
  </div>
</section>

{% stylesheet %}
.lms-movie { padding-block: 32px; }
.lms-movie__grid {
  display: grid;
  grid-template-columns: minmax(0, 45%) minmax(0, 1fr);
  gap: 48px;
  align-items: start;
}
.lms-movie__media img,
.lms-movie__placeholder svg {
  width: 100%;
  height: auto;
  display: block;
  border: var(--lms-border-width) solid var(--lms-border-default);
  border-radius: var(--lms-radius-xs);
}
.lms-movie__details { display: flex; flex-direction: column; gap: 20px; }
.lms-movie__title { font-family: var(--lms-font-display); color: var(--lms-text-strong); margin: 0; }
.lms-movie__chips { display: flex; gap: 8px; flex-wrap: wrap; }
.lms-movie__chips a { text-decoration: none; }
.lms-movie__availability { font-family: var(--lms-font-mono); font-size: 14px; }
.lms-movie__stock--in { color: var(--lms-sage); }
.lms-movie__stock--out { color: var(--lms-text-muted); }
.lms-movie__instore { font-family: var(--lms-font-mono); font-size: 13px; color: var(--lms-text-muted); margin: 0; }
.lms-movie__description { color: var(--lms-text-default); }
.lms-movie__notify-label { display: block; font-family: var(--lms-font-mono); font-size: 13px; margin-bottom: 6px; }
.lms-movie__notify-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.lms-movie__notify-success { color: var(--lms-sage); font-family: var(--lms-font-mono); }
@media (max-width: 749px) {
  .lms-movie__grid { grid-template-columns: 1fr; gap: 24px; }
}
{% endstylesheet %}

{% schema %}
{
  "name": "Movie details",
  "tag": "section",
  "settings": [],
  "presets": [{ "name": "Movie details" }]
}
{% endschema %}
```

- [ ] **Step 2: Create the template file**

Create `theme/lms-redesign-v4/templates/product.movie.json`:

```json
{
  "sections": {
    "main": {
      "type": "main-movie",
      "settings": {}
    }
  },
  "order": ["main"]
}
```

- [ ] **Step 3: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`
Expected: completes with no NEW offenses attributable to `main-movie.liquid` or `product.movie.json` (compare total offense count against the pre-change baseline; the known baseline is small — investigate any increase).

- [ ] **Step 4: Assign a movie to the template and view it**

1. Push the two files to the dev working theme:
   `shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only sections/main-movie.liquid --only templates/product.movie.json`
2. In Shopify Admin (dev store) → Products → pick a movie (e.g. "Muppets Treasure Island") → in the **Theme template** selector choose **movie** → Save.
3. Open that product's storefront URL (via `shopify theme dev` in your terminal, or the dev preview). Get past the storefront password if prompted.

Expected: the page shows the poster on the left, the title and the TMDB description on the right, and **nothing else** — no price, no "Genre" variant dropdown, no Add to cart, no Buy now.

- [ ] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/sections/main-movie.liquid theme/lms-redesign-v4/templates/product.movie.json
git commit -m "feat: dedicated read-only movie product template scaffold"
```

---

## Task 2: Clickable genre + format chips

Adds the curated attribute chips below the title, linking into the shop-all catalogue with the matching facet.

**Files:**
- Modify: `theme/lms-redesign-v4/sections/main-movie.liquid` (replace the `{# ANCHOR: chips #}` line)

**Interfaces:**
- Consumes: `product.metafields.shopify.genre` and `product.metafields.shopify.media-format` (list.metaobject_reference; `.value.first.label.value` = display label, `.value.first.system.handle` = facet handle — same access pattern as `snippets/lms-product-card.liquid:25`).

- [ ] **Step 1: Replace the chips anchor with the chip markup**

In `sections/main-movie.liquid`, replace this line:

```liquid
      {# ANCHOR: chips #}
```

with:

```liquid
      {%- liquid
        assign genre_label = product.metafields.shopify.genre.value.first.label.value
        assign genre_handle = product.metafields.shopify.genre.value.first.system.handle
        assign format_label = product.metafields.shopify.media-format.value.first.label.value
        assign format_handle = product.metafields.shopify.media-format.value.first.system.handle
      -%}
      {%- if genre_label != blank or format_label != blank -%}
        <div class="lms-movie__chips">
          {%- if genre_label != blank -%}
            <a class="lms-badge lms-badge--muted" href="/collections/all-movies?filter.p.m.shopify.genre={{ genre_handle | url_encode }}">{{ genre_label }}</a>
          {%- endif -%}
          {%- if format_label != blank -%}
            <a class="lms-badge lms-badge--muted" href="/collections/all-movies?filter.p.m.shopify.media-format={{ format_handle | url_encode }}">{{ format_label }}</a>
          {%- endif -%}
        </div>
      {%- endif -%}
```

- [ ] **Step 2: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`
Expected: no new offenses.

- [ ] **Step 3: View it**

Push (`--only sections/main-movie.liquid`) and reload the movie product page.
Expected: two chips under the title — a genre chip (e.g. "Kids & Family") and a format chip (e.g. "VHS"). Click the genre chip → lands on `/collections/all-movies` with the genre filter applied; click the format chip → same collection with the format filter applied. A product missing one metafield shows only the other chip; a product missing both shows no chip row.

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/sections/main-movie.liquid
git commit -m "feat: clickable genre/format chips on movie template"
```

---

## Task 3: Availability indicator + swappable check + in-store notice

Adds the single availability decision and its indicator, plus the in-store transaction notice.

**Files:**
- Modify: `theme/lms-redesign-v4/sections/main-movie.liquid` (replace the `{# ANCHOR: availability #}` line)

**Interfaces:**
- Produces: Liquid variable `movie_in_stock` (boolean), read here and by the notify-me block in Task 4.

- [ ] **Step 1: Replace the availability anchor**

In `sections/main-movie.liquid`, replace this line:

```liquid
      {# ANCHOR: availability #}
```

with:

```liquid
      {# STAND-IN: inventory qty now; swap to scf.avf / supercycle.* on install #}
      {%- assign movie_in_stock = false -%}
      {%- if product.available -%}{%- assign movie_in_stock = true -%}{%- endif -%}

      <div class="lms-movie__availability">
        {%- if movie_in_stock -%}
          <span class="lms-movie__stock lms-movie__stock--in">● Available in-store</span>
        {%- else -%}
          <span class="lms-movie__stock lms-movie__stock--out">● Currently out</span>
        {%- endif -%}
      </div>
      <p class="lms-movie__instore">Rent or buy this title in-store.</p>
```

- [ ] **Step 2: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`
Expected: no new offenses (in particular no `UnusedAssign` for `movie_in_stock` — it is read by the indicator now and by Task 4).

- [ ] **Step 3: View both states**

Push and reload. With the product in stock (inventory qty ≥ 1): indicator reads "● Available in-store" in sage. In Admin set that variant's inventory to 0 and reload: indicator reads "● Currently out" in muted grey. The "Rent or buy this title in-store." line shows in both states.

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/sections/main-movie.liquid
git commit -m "feat: swappable availability indicator + in-store notice on movie template"
```

---

## Task 4: Out-of-stock notify-me form + full verification

Adds the notify-me capture (visible only when out of stock) and runs the full acceptance matrix.

**Files:**
- Modify: `theme/lms-redesign-v4/sections/main-movie.liquid` (replace the `{# ANCHOR: notify #}` line)

**Interfaces:**
- Consumes: `movie_in_stock` (Task 3), `product.title`, `product.handle`.

- [ ] **Step 1: Replace the notify anchor**

In `sections/main-movie.liquid`, replace this line:

```liquid
      {# ANCHOR: notify #}
```

with:

```liquid
      {%- unless movie_in_stock -%}
        <div class="lms-movie__notify">
          {%- form 'contact', class: 'lms-movie__notify-form' -%}
            {%- if form.posted_successfully? -%}
              <p class="lms-movie__notify-success">Thanks — we'll let you know when it's back in.</p>
            {%- else -%}
              <input type="hidden" name="contact[Movie]" value="{{ product.title | escape }} ({{ product.handle }})">
              <input type="hidden" name="contact[body]" value="Back-in-stock request for {{ product.title | escape }} ({{ product.handle }})">
              <label class="lms-movie__notify-label" for="lms-notify-email">Notify me when it's back</label>
              <div class="lms-movie__notify-row">
                <input id="lms-notify-email" type="email" name="contact[email]" placeholder="you@email.com" required>
                <button type="submit" class="button">Notify me</button>
              </div>
            {%- endif -%}
          {%- endform -%}
        </div>
      {%- endunless -%}
```

- [ ] **Step 2: Run theme check**

Run: `shopify theme check --path theme/lms-redesign-v4`
Expected: no new offenses.

- [ ] **Step 3: Full acceptance verification**

Push and verify the whole matrix on the dev store:

1. **In-stock movie:** poster, title, genre+format chips, "● Available in-store", in-store notice, description. **No** notify-me form. No price/variant/buy UI anywhere.
2. **Out-of-stock movie** (inventory 0): indicator "● Currently out" and the notify-me form appears. Submit a valid email → page reloads showing "Thanks — we'll let you know when it's back in." Confirm the submission arrives in Shopify Admin → Settings → Notifications / the store contact email, and that it names the movie title + handle.
3. **Chips:** genre and format chips each deep-link to `/collections/all-movies` with the correct facet applied.
4. **Retail regression:** open any non-movie product (still on `product.json`) — it renders the normal PDP unchanged.
5. **Responsive:** at ≤749px the layout stacks (poster above details).

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/sections/main-movie.liquid
git commit -m "feat: out-of-stock notify-me capture on movie template"
```

---

## Self-review notes

- **Spec coverage:** dedicated template (Task 1) · poster/title/description (Task 1) · genre+format chips, clickable, curated (Task 2) · availability indicator + single swappable check + in-store notice (Task 3) · out-of-stock-only native notify-me capture (Task 4) · no price/variant/buy/Methods slot (enforced by omission across all tasks, stated in Global Constraints) · retail untouched (Task 1 creates a separate template; verified Task 4 Step 3.4).
- **Deferred, not in this plan (per spec):** automated back-in-stock send, `scf.avf`/Supercycle signal swap, online member-rental via Methods block.
- **Type consistency:** `movie_in_stock` defined in Task 3, consumed in Task 4; metafield access `.value.first.label.value` / `.value.first.system.handle` matches `snippets/lms-product-card.liquid`; anchors `{# ANCHOR: chips/availability/notify #}` created in Task 1 and each consumed once.
