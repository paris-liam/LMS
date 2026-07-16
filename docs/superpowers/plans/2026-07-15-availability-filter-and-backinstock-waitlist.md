# Availability filter + back-in-stock waitlist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠️ Known caveat — proceeding on Supercycle's guidance (2026-07-16).** In live testing `supercycle.uncommitted_inventory` did not flip after a rental was created + fulfilled (stayed `1`). Supercycle **support confirmed** this metafield is the correct availability signal and that it updates on **fulfillment state**; the observed staleness is a write-lag / store-side issue they're reconciling. **Decision: build this plan now as if the metafield is correct and current.** The Task 2 Liquid (`is_available` from the metafield) is written to be find-and-replace-ready if the source ever changes. Fallback if support can't fix the write: detect availability via the **Storefront Product Availability API** or the Methods PDP block's own OOS state. See `[[supercycle-uncommitted-inventory-integer]]`.

**Goal:** Add a member-only "Notify me when back in stock" button to out-of-stock rental PDPs that feeds a Flow-backed email waitlist, without breaking Supercycle's add-to-cart takeover.

**Architecture:** The only theme code in this feature is one new snippet (`snippets/notify-me-waitlist.liquid`) and a conditional wrapper in the shared `blocks/buy-buttons.liquid`. The availability *filter* (spec Section 2) is 100% Search & Discovery config with **no code** — it lives entirely in the admin runbook. The waitlist's data plumbing (metafield + two Flows) is also admin — this plan only covers the PDP capture UI. Everything downstream (append-to-metafield, email, clear) is Flow, built in the runbook.

**Tech Stack:** Shopify Liquid (Horizon 4.1.1 theme blocks), Shopify `{% form 'contact' %}`, Supercycle variant metafield `supercycle.uncommitted_inventory` (read-only), Shopify Flow. No JS build step, no test framework.

## Global Constraints

- **Prerequisites — this plan is blocked until the admin runbook's Section A is done and verified.** No `supercycle.uncommitted_inventory` value exists on any product until movies are live in Supercycle. Runbook: `docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist-admin-runbook.md`. Also do runbook **C1** (create `custom.waitlist_emails`) and **C2** (confirm the contact-form Flow trigger) before Task 2 here.
- **Default target: dev store `lms-sandbox-lutsfahz.myshopify.com`, working theme `140918915134`.** Never production unless explicitly instructed per-operation (CLAUDE.md).
- **No dynamic checkout on movie PDPs.** Do not add "Buy now" / express / accelerated-checkout buttons anywhere in this work (CLAUDE.md integration contract). The notify-me path renders *instead of* add-to-cart when it fires; it never introduces a checkout button.
- **Read, never create, the `supercycle` namespace.** This plan only *reads* `supercycle.uncommitted_inventory` (variant integer) and `supercycle.supercycle_enabled` (product boolean). Mark the read site with `{# STAND-IN NOTE: reading Supercycle-owned metafields, do not create #}` for greppability. Do not add any `supercycle.*` definition in code.
- **Member gate string is exactly** `Has active subscription` — `{% if customer.tags contains 'Has active subscription' %}`. (Grep confirms this is the *first* member-gate in the theme; there's no existing pattern to copy.)
- **Hardcode bespoke English button/label copy — do NOT add new keys to `en.default.json`.** Adding a locale key errors theme-check ~30× (one per other locale). See `[[theme-check-matchingtranslations-gotcha]]`. `t` has no `default:` param.
- **Theme-check baseline (do not regress):** the tree currently reports **9 offenses / 2 errors** (2 pre-existing Supercycle `JSONMissingBlock` errors). Capture the real baseline yourself in Task 2 Step 1 rather than trusting this number. "Passing" = no *new* offenses vs. that captured baseline.
- **No Liquid unit-test framework exists in this repo.** Per the sibling rental-scoped spec's own testing section, the test cycle here is: `shopify theme check` (no new offenses) + manual QA on the pushed dev theme. Steps below reflect that honestly.

---

### Task 1: Spike — confirm notify-me won't break Supercycle's Methods-block button reuse

**Depends on:** runbook Section A complete (Methods block mounted on a rentable PDP, `supercycle.uncommitted_inventory` populating).

**Why this is a task, not an assumption:** the CLAUDE.md integration contract says Supercycle's Methods app block **reuses the theme's single add-to-cart button** once mounted. Task 2 conditionally *replaces* that button (with notify-me) when a title is out of stock for a member. If the Methods block manages the out-of-stock state itself, or breaks when the add-to-cart markup is absent, Task 2's approach is wrong. Confirm the interaction on a live mounted block before writing the button.

**Files:** none (investigation only).

**Interfaces:**
- Produces: a go/no-go decision + the observed behavior, recorded at the bottom of this task. Task 2 assumes **go** (Methods block tolerates add-to-cart being conditionally replaced on OOS titles).

- [ ] **Step 1: Reproduce a member + OOS state on a live PDP**

On the dev store, with the Methods block mounted (runbook A6): use a test membership customer tagged `Has active subscription`, rent out a title's only Active copy so `supercycle.uncommitted_inventory` is `false` for it. Confirm via Admin → product → Metafields.

- [ ] **Step 2: Observe how the Methods block renders on that OOS PDP**

Load the PDP as that member. Note: does the Methods block show its own out-of-stock/unavailable state? Does it render the add-to-cart button at all when no copy is available? Does it depend on the theme's `<product-form-component>` / the `[name="id"]` input existing in the DOM?

- [ ] **Step 3: Decide and record**

- If the Methods block **still needs** the theme's add-to-cart button present even when OOS → Task 2 must *not* remove it; instead render notify-me *alongside/below* rather than *in place of*. Update Task 2 accordingly and note it here.
- If the Methods block is **independent** of the theme button when OOS (or the button is safe to replace) → proceed with Task 2 as written.

Record finding here: `_______________________________________`

- [ ] **Step 4: Commit the finding**

```bash
git add docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist.md
git commit -m "docs: record Methods-block/notify-me interaction spike finding"
```

---

### Task 2: Notify-me waitlist snippet + conditional wiring in buy-buttons

**Depends on:** Task 1 = go; runbook A (Supercycle live), C1 (`custom.waitlist_emails` exists), C2 (contact-form Flow trigger confirmed).

**Files:**
- Create: `theme/lms-redesign-v4/snippets/notify-me-waitlist.liquid`
- Modify: `theme/lms-redesign-v4/blocks/buy-buttons.liquid` (around the add-to-cart / accelerated-checkout `content_for` calls, currently lines 223–235)

**Interfaces:**
- Consumes: `supercycle.uncommitted_inventory` (variant **boolean**; `true` = a copy is on the shelf, `false`/absent = none — confirmed 2026-07-16 via definition detection + support), `supercycle.supercycle_enabled` (product boolean; `true` = product is in Supercycle), `customer.tags`, `customer.email`.
- Produces: an out-of-stock, member-only `{% form 'contact' %}` submission carrying hidden fields **`contact[product_id]`** (the product's numeric ID) and **`contact[email]`** (the member's email), plus an identifiable **`contact[body]`**. Runbook Flow "Waitlist — capture" (C3) reads these. If these field names change, C3 must change with them.

- [ ] **Step 1: Capture the theme-check baseline**

Run: `shopify theme check --path theme/lms-redesign-v4`
Record the exact offense/error counts (expected ≈ 9 offenses / 2 errors). This is the number Step 6 must not exceed.

- [ ] **Step 2: Create the notify-me snippet**

Create `theme/lms-redesign-v4/snippets/notify-me-waitlist.liquid`:

```liquid
{%- doc -%}
  Member-only "Notify me when back in stock" waitlist form.
  Rendered by blocks/buy-buttons.liquid in place of add-to-cart when a rental
  title has no available copy (supercycle.uncommitted_inventory == false) and
  the customer is a member. Submits a Shopify contact form; Flow workflow
  "Waitlist — capture" appends contact[email] to
  product.metafields.custom.waitlist_emails (deduped).

  Rental-only store: this is a notification request, NOT a purchase — no
  add-to-cart, no checkout button is introduced here.

  @param {object} product - the current product
{%- enddoc -%}

{%- assign notify_form_id = 'NotifyMe-' | append: product.id -%}

<div class="notify-me-waitlist">
  {%- form 'contact', id: notify_form_id, class: 'notify-me-waitlist__form' -%}
    {%- if form.posted_successfully? -%}
      <p
        class="notify-me-waitlist__success"
        tabindex="-1"
        autofocus
      >
        Thanks — we'll email you when a copy is back on the shelf.
      </p>
    {%- else -%}
      {# STAND-IN NOTE: contact[product_id] is read by Flow "Waitlist — capture" #}
      <input type="hidden" name="contact[product_id]" value="{{ product.id }}">
      <input type="hidden" name="contact[email]" value="{{ customer.email }}">
      <input
        type="hidden"
        name="contact[body]"
        value="Back-in-stock waitlist request for product {{ product.id }} ({{ product.title }})"
      >
      <p class="notify-me-waitlist__note">
        No copies are available right now. We'll email you once one is returned — a copy isn't reserved, it's first to check out.
      </p>
      <button
        type="submit"
        class="button notify-me-waitlist__button"
      >
        Notify me when back in stock
      </button>
    {%- endif -%}
  {%- endform -%}
</div>

{%- style -%}
  .notify-me-waitlist__note {
    font-size: 0.85em;
    margin-block: 0 var(--spacing, 8px);
  }
  .notify-me-waitlist__button {
    width: 100%;
  }
{%- endstyle -%}
```

Copy is hardcoded English on purpose (no new `en.default.json` keys — see Global Constraints). Email copy is deliberately honest that the item is not reserved (spec's known edge case).

- [ ] **Step 3: Wire the conditional into `blocks/buy-buttons.liquid`**

The block already computes `variant` (line 9) and renders the add-to-cart + accelerated-checkout `content_for` calls at lines 223–235. Replace exactly this existing block:

```liquid
          {% content_for 'block',
            type: 'add-to-cart',
            id: 'add-to-cart',
            can_add_to_cart: can_add_to_cart,
            add_to_cart_text: add_to_cart_text
          %}

          {% content_for 'block',
            type: 'accelerated-checkout',
            id: 'accelerated-checkout',
            can_add_to_cart: can_add_to_cart,
            form_obj: form
          %}
```

with:

```liquid
          {%- liquid
            # STAND-IN NOTE: reading Supercycle-owned metafields, do not create the supercycle namespace
            # supercycle.uncommitted_inventory is a BOOLEAN: true = a copy is available, false/absent = none (confirmed 2026-07-16 via metafield-definition detection + Supercycle support)
            assign sc_enabled = product.metafields.supercycle.supercycle_enabled
            assign is_rental = false
            if sc_enabled != blank and sc_enabled.value == true
              assign is_rental = true
            endif
            assign sc_uncommitted = variant.metafields.supercycle.uncommitted_inventory
            assign is_available = false
            if sc_uncommitted != blank and sc_uncommitted.value == true
              assign is_available = true
            endif
            assign is_rental_oos = false
            if is_rental and is_available == false
              assign is_rental_oos = true
            endif
            assign is_member = false
            if customer and customer.tags contains 'Has active subscription'
              assign is_member = true
            endif
          -%}

          {%- if is_rental_oos and is_member -%}
            {% render 'notify-me-waitlist', product: product %}
          {%- else -%}
            {% content_for 'block',
              type: 'add-to-cart',
              id: 'add-to-cart',
              can_add_to_cart: can_add_to_cart,
              add_to_cart_text: add_to_cart_text
            %}

            {% content_for 'block',
              type: 'accelerated-checkout',
              id: 'accelerated-checkout',
              can_add_to_cart: can_add_to_cart,
              form_obj: form
            %}
          {%- endif -%}
```

**Why this is safe on non-rental products:** `is_rental` is gated on `supercycle.supercycle_enabled == true`, which is only set on products imported into Supercycle. Merch, gift cards, snacks, and titles pulled *out* of Supercycle all have it `blank`/`false`, so `is_rental_oos` stays `false` and they get the unchanged add-to-cart path. Using `supercycle_enabled` (rather than just "is `uncommitted_inventory` absent") is what lets us distinguish "rental title, 0 available" from "not a rental product at all" — both of which could otherwise look like an absent inventory metafield.

**Verify-before-build (needs one live rental-out):** confirm that when a Supercycle title's only copy is rented, `supercycle.uncommitted_inventory` actually changes away from `true` (to `false` or absent). The `is_available` check (`== true`) treats `false`/blank/absent all as not-available, so it's robust to which of those Supercycle writes — but you must confirm the value *does* flip off on commit, or the button will never appear. Test during Task 2 Step 7 state 1.

**If Task 1 recorded "Methods block needs the button present even when OOS":** do NOT replace the `content_for` calls — instead render `{% render 'notify-me-waitlist', product: product %}` *after* them (still inside the `is_rental_oos and is_member` guard), and keep the add-to-cart calls unconditional.

- [ ] **Step 4: Sanity-check the Liquid parses (no member/OOS state needed yet)**

Run: `shopify theme check --path theme/lms-redesign-v4 --category liquid`
Expected: no *new* Liquid syntax/parse errors introduced by the two changed files.

- [ ] **Step 5: Run full theme-check against baseline**

Run: `shopify theme check --path theme/lms-redesign-v4`
Expected: offense/error counts **equal to the Step 1 baseline** (≈ 9 offenses / 2 errors). If the count went up, the new snippet/edit introduced an offense — fix before continuing. Watch specifically for `MatchingTranslations` (means a stray translation key crept in) and `UnusedAssign`.

- [ ] **Step 6: Push to the dev working theme**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only snippets/notify-me-waitlist.liquid --only blocks/buy-buttons.liquid
```

(Narrow `--only` push so merchant-managed files aren't touched.)

- [ ] **Step 7: Manual QA — the four states**

Get past the storefront password with the dev-store password (see `[[dev-store-storefront-password]]`) for browser checks. On a rentable PDP:

1. **Member + out of stock** (`uncommitted_inventory` false, customer tagged `Has active subscription`): the "Notify me when back in stock" button shows **in place of** add-to-cart (or below it, per Task 1). **No** checkout/express button is present.
2. **Member + in stock** (`uncommitted_inventory` true): normal add-to-cart / Methods block shows; no notify-me.
3. **Non-member + out of stock** (logged out or untagged): notify-me does **not** show; existing behavior only.
4. **Non-rental product** (a merch/gift-card product with no `supercycle` metafield): completely unchanged add-to-cart.

- [ ] **Step 8: Manual QA — capture round-trips to the metafield**

With runbook C3 ("Waitlist — capture" Flow) live: as the member in state 1, click the button. Confirm the success message renders, then check Admin → that product → Metafields → `custom.waitlist_emails` now contains the member's email. Click again with the same account → confirm it is **not** duplicated (dedup is in the Flow, but this confirms the field wiring end-to-end).

- [ ] **Step 9: Commit**

```bash
git add theme/lms-redesign-v4/snippets/notify-me-waitlist.liquid theme/lms-redesign-v4/blocks/buy-buttons.liquid
git commit -m "feat: member-only back-in-stock notify button on out-of-stock rental PDPs"
```

---

## Coverage note (what this plan does NOT cover — by design)

- **Spec Section 2 (availability filter):** no code — entirely Search & Discovery config in runbook Section B. Nothing to build here.
- **Spec Section 3 downstream (append / email / clear):** Flow, built in runbook C3 + C5. This plan stops at the PDP capture UI.
- **The 4-vs-5-filter conflict** with the rental-scoped spec: flagged in the runbook's top callout; it's a config decision, no code either way.

## Self-review against the spec

- **§2 availability filter** → runbook Section B (no code). ✅ Covered (out of this plan's code scope by design).
- **§3 capture UI (member-only, OOS-only, `customer.email`, hidden product-id, contact form)** → Task 2 snippet. ✅
- **§3 "verify contact-form fires Flow trigger"** → runbook C2 (gate before Task 2). ✅
- **§3 append/dedup** → runbook C3. ✅ (downstream, not code)
- **§3 notify/clear + `rental.item` join verify** → runbook C4/C5. ✅ (downstream, not code)
- **Integration contract (Methods block button reuse; no dynamic checkout)** → Task 1 spike + Global Constraints + Task 2 guard. ✅
- **Type consistency:** `sc_uncommitted` / `is_rental_oos` / `is_member` used consistently; hidden field names `contact[product_id]` / `contact[email]` / `contact[body]` match the runbook C3 "Interfaces" note. ✅
- **Known edge case (no reservation)** → reflected in the honest email copy. ✅
