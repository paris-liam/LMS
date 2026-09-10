# Supercycle, explained (for LMS)

A living reference for how Supercycle actually works, written up as we learn it and tailor it to Little Movie Store. Each section has a **high-level explanation** (architecture/concepts) followed by **step-by-step instructions** for the specific thing we set up.

See also: `CLAUDE.md` (store/theme reference, integration contract) and `claudedocs/2026-09-08-supercycle-scope-rebuild.md` (canonical current scope). The old `supercycle-progress.md` was retired into this file's build log on 2026-09-10.

Supercycle is installed and live on **production** (`p0wkgv-wy.myshopify.com`) — **not** the dev store. Verified 2026-09-10 via Admin API: production carries the app's `supercycle.*` product and variant metafields with real values; the dev store has no Supercycle products at all (only a leftover variant metafield *definition* named "In-Stock" from July's availability work). Any doc telling you to do Supercycle work on `lms-sandbox-lutsfahz` is stale.

The Supercycle app embed in the live theme is **enabled** as of 2026-09-10 (it was explicitly disabled on 2026-09-08).

---

## 1. Memberships — core architecture

Supercycle's membership system ("Methods > Membership") is built out of a few pieces:

- **Plan = a Shopify product.** When you create a membership plan in Supercycle's admin, it auto-creates a linked Shopify product ("plan product") purely to carry billing via a Shopify **selling plan** (native Shopify subscriptions, minimum 1-month interval — there is no separate custom billing engine). **Never sell this product directly** through a normal Buy Button or direct link — it processes an order without activating membership properly and needs a manual refund to undo. The only supported enrollment path is Supercycle's own "Membership plans" app block.
- **Entitlements live in metafields, not the plan itself.** Per-product/variant settings (which items are rentable via membership, credit cost) live in the app-reserved `supercycle.*` product/variant metafield namespace. Customer-side state (their current plan, credit balance, quotas) lives in `customer.metafields.supercycle.membership` (JSON) plus a set of Shopify customer **tags**.
- **Two levers only for plan limits** — this is the important constraint to design around:
  - **Credit / item allowance** — the max number of items a member can hold *concurrently*. Ours is **allowance = 3** (three movies at a time), revised 2026-09-03 from an earlier "one at a time" design.
  - **Swap allowance** — how often the member can *order and return* (i.e. swap out) within a billing period. This throttles *frequency*, aligned to the billing anniversary by default.
  - **There is no native "max N days per rental" setting on the Membership method.** A 7-day hold cap is a different concept, more associated with the Calendar rental method or return-trigger automation — not something a membership plan enforces on its own.

  > **Open item — revisit later:** we are *not* enforcing a per-rental hold duration for v1. Credit allowance (3) caps how many items are out at once, but nothing caps how long; the target 2-week window has to be handled operationally (reminder emails, honour system) or via return-trigger automation. Flagged here so we come back to it.

- **Checkout & tags.** The member picks a plan through the Membership Plans app block on the storefront (its own add-to-cart flow, not a generic product form). On successful signup, Supercycle activates the membership and Shopify applies tags automatically: `Has membership`, `Has {status} subscription` (active/paused/canceled), `{plan name} subscriber`, `Recurring order #N`, `Supercycle member`. Credits deduct when a member checks a rental out, and restore when it's returned.
- **Methods block gating vs. our tag gating.** The **Methods** app block on the PDP (the one that reuses our theme's add-to-cart button, per the integration contract in CLAUDE.md) does its own client-side check against `customer.metafields.supercycle.membership.value.quotas.credits.allowance` to enable/disable the add-to-cart button when credits are insufficient. This is a *lower-level, more precise* check than our theme's `customer.tags contains 'Has active subscription'` gating (used for things like hiding the header/hero "Join the club" button). Both checks matter, at different points in the flow — the tag check is coarse ("are they a member at all"), the metafield check is what actually governs whether they can check out an item right now.

---

## 2. Setting up the $160/yr membership plan — step by step

**Goal for v1:** yearly membership, $160/yr, lets the member hold **3 items at a time**, with **no enforced hold-duration cap** (target is 2 weeks per item, but see open item above — Supercycle Membership has no native field for this) and **effectively unlimited swaps** over the year.

### A. Create the plan in Supercycle admin

1. In Shopify admin, go to **Supercycle > Settings > Methods > Membership**.
2. Click **Add plan**.
3. Set the plan title (this becomes the linked Shopify product's title — use something customer-facing, e.g. "LMS Annual Membership").
4. Set the **credit/item allowance to 3** (three items held at a time).
5. Set the **swap allowance** high enough to be effectively unlimited for a year of normal use (check what the actual field/max value is when you get to this screen — the docs don't give a hard number, so this needs eyeballing in the UI).
6. Set the **purchase option / pricing tier**: yearly billing, $160/yr. (If the UI offers multiple intervals per plan — e.g. monthly vs. yearly tiers on the same plan — decide whether we want *only* yearly for now, or scaffold monthly too and hide it. Default to yearly-only for v1 unless you want both.)
7. Save the plan.

### B. Enable membership on rentable products

1. Go to **Supercycle > Products**.
2. For each product that should be rentable via membership, select rental method **Membership** and toggle it on.
3. At the **variant level**, set the credit cost (for a simple "1 credit = 1 movie" model, this should just be `1` on every rentable variant, so allowance-of-1 cleanly means "one movie out").
4. Save.

### C. Build the storefront membership page

1. Create a new Shopify **collection** containing the plan product(s) we want to surface for purchase (just the one $160/yr plan for now, but a dedicated collection keeps this extensible for future tiers).
2. Create a new Shopify **page** (do not reuse the existing `theme/lms-redesign-v4/templates/page.json` block from earlier experimentation — build fresh, per your call above).
3. In the theme customizer, add the **"Supercycle - Membership plans"** app block to the new page.
4. Point the block's **collection** setting at the plan collection from step 1.
5. Configure the block's display settings (pricing card template, colors, button label, etc. — it pulls title/price/description from the linked Shopify product, styleable via the block's own settings plus a `custom_css` field).
6. Preview and confirm: plan card shows correct price/interval/credit allowance, and clicking through completes a real signup (tags get applied, credit balance populates on the test customer).

### D. Verify end-to-end

- [ ] Tag/metafield check: after a test signup, confirm the test customer has `Has active subscription` + related tags, and `customer.metafields.supercycle.membership` shows credit allowance = 3.
- [ ] PDP check: on a membership-enabled product, confirm the Methods block reflects credit availability (button enabled while any of the 3 credits are free, disabled/messaged once all 3 are checked out).
- [ ] Header/hero check: confirm "Join the club" buttons hide correctly for this now-active member (existing gating logic in `sections/header.liquid` / `sections/lms-hero.liquid`).

---

## Open questions / follow-ups log

- **2-week hold duration**: no native membership-plan setting for this (updated from the earlier 7-day target). Decided 2026-09-03: not enforcing for v1 — record plan settings now (allowance=3, $160/yr) and revisit enforcement (return-trigger automation vs. reminder emails / honor system) later.
- **Swap allowance ceiling**: need to check the actual UI to see what counts as "unlimited enough" for a year of normal single-item swapping.
- **Monthly vs. yearly pricing tiers**: decide if the plan should ever offer more than the one yearly option.

---

## Build log

Absorbed from the retired `supercycle-progress.md` on 2026-09-10. Newest first.

### 2026-09-10 — production audit, PDP availability label, metafield incident

**Where Supercycle actually lives.** Verified by Admin API that the app runs on **production**, not dev. `CLAUDE.md`, this file, and the availability-filter runbook all said dev; all three were corrected.

**Current production state** (re-verify before citing — it moves):
- 79 titles imported into Supercycle; only **3** carry `supercycle.methods` (Zack Parker's Proxy, Fatal Attraction, Rear Window).
- `supercycle.uncommitted_inventory` (variant, boolean) is populated on **81 variants** — 34 `true`, 18 `false` across the 57 products in All Movies.
- Membership plan exists and is Active; app embed enabled.

**Unresolved: the product-level sync bug.** Enabling the Membership method reliably writes `supercycle.membership_configuration`, but `supercycle.methods`, `supercycle.total_uncommitted_inventory`, and the `Supercycle product` tag are written for only *some* products. A controlled test on six titles (identical off→save→on→save toggle) succeeded on two and failed on four. Ruled out: missing Supercycle items, and Shopify inventory tracking (007: Tomorrow Never Dies was switched to tracked with `totalInventory: 1` and still failed). Cause unknown — raised with Supercycle support; see `claudedocs/2026-09-10-supercycle-support-ticket.md`.

**Unresolved: the storefront availability filter returns nothing.** `?filter.p.m.supercycle.methods=Membership` correctly returns the 3 products. `?filter.v.m.supercycle.uncommitted_inventory=1` *and* `=true` both return **No products**, despite 81 populated values. Re-tested 54 minutes later with no change, so it is not an indexing delay. Note Shopify **rejects** the admin-filterable capability on a variant metafield (`INVALID_CAPABILITY`) — the July runbook's Section B1 step is impossible as written.

**⚠️ Incident — never delete a `supercycle.*` metafield definition.** Deleting the `supercycle.methods` product definition wiped its value from all 79 products in a ~4-second sweep. Re-creating the definition did **not** restore them (`metafieldsCount: 0`). The only recovery found is toggling the method off/on per product — which only works on products that aren't hit by the sync bug above. One upside: the definition had been the wrong type (`single_line_text_field`); re-created correctly as `list.single_line_text_field`, which is what the filter actually needs.

**Shipped: the PDP availability label.** `sections/main-movie.liquid` reads the variant metafield directly in Liquid, which bypasses the broken Search & Discovery index entirely — it works on all 52 of 57 All Movies products that carry the metafield, including titles the filter can't see. Fixed a false-negative where a product with `supercycle_enabled` but no availability metafield rendered "Currently out": an absent metafield (nil) and a genuine `false` are both falsy once Liquid unwraps the boolean, so `uncommitted_inventory_count` is used as a presence probe (`| default: -1`). Note `== blank` cannot be used — in Liquid, `false == blank` is true.

Label states: `true` → "Available now" · `false` → "Currently out" · metafield absent or not `supercycle_enabled` → "Available in-store".

### 2026-07-05 — "Join the club" buttons (header + hero), gated on membership status

Added the header schema settings (`enable_membership_gating`, `join_club_url`, `join_club_label`) that `snippets/header-actions.liquid` already had gating logic for, plus a `hide_if_member` checkbox on the hero's generic `button` block. Both gate on `customer.tags contains 'Has active subscription'`. Hero visibility uses a manual counting loop rather than `where_exp`, which `shopify theme check` flagged as unsupported in this theme.

**Still open from that session:** only `Has active subscription` hides the buttons — a customer with `Has paused subscription` still sees "Join the club". Undecided whether a paused member should count as "already a member".
