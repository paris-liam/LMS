# Supercycle, explained (for LMS)

A living reference for how Supercycle actually works, written up as we learn it and tailor it to Little Movie Store. Each section has a **high-level explanation** (architecture/concepts) followed by **step-by-step instructions** for the specific thing we set up.

See also: `CLAUDE.md` (store/theme reference, integration contract), `lms-supercycle-feature-plan.md` (full feature plan), `supercycle-progress.md` (running build log).

Supercycle is confirmed **installed** on the dev store (`lms-sandbox-lutsfahz.myshopify.com`) — the `Has active subscription` customer tag is already applied live by the app, and a `templates/page.json` in `theme/lms-redesign-v4` already has a Supercycle "Membership plans" app block wired up (from earlier experimentation — we're building a fresh page rather than reusing it).

---

## 1. Memberships — core architecture

Supercycle's membership system ("Methods > Membership") is built out of a few pieces:

- **Plan = a Shopify product.** When you create a membership plan in Supercycle's admin, it auto-creates a linked Shopify product ("plan product") purely to carry billing via a Shopify **selling plan** (native Shopify subscriptions, minimum 1-month interval — there is no separate custom billing engine). **Never sell this product directly** through a normal Buy Button or direct link — it processes an order without activating membership properly and needs a manual refund to undo. The only supported enrollment path is Supercycle's own "Membership plans" app block.
- **Entitlements live in metafields, not the plan itself.** Per-product/variant settings (which items are rentable via membership, credit cost) live in the app-reserved `supercycle.*` product/variant metafield namespace. Customer-side state (their current plan, credit balance, quotas) lives in `customer.metafields.supercycle.membership` (JSON) plus a set of Shopify customer **tags**.
- **Two levers only for plan limits** — this is the important constraint to design around:
  - **Credit / item allowance** — the max number of items a member can hold *concurrently*. Our "one movie at a time" maps directly to this: allowance = 1.
  - **Swap allowance** — how often the member can *order and return* (i.e. swap out) within a billing period. This throttles *frequency*, aligned to the billing anniversary by default.
  - **There is no native "max N days per rental" setting on the Membership method.** A 7-day hold cap is a different concept, more associated with the Calendar rental method or return-trigger automation — not something a membership plan enforces on its own.

  > **Open item — revisit later:** we are *not* enforcing the "one week per checkout" rule for v1. Credit allowance (1) covers "one at a time"; the 7-day return window will need to be handled operationally (reminder emails, honor system) or via return-trigger automation once we've looked at that piece. Flagged here so we come back to it.

- **Checkout & tags.** The member picks a plan through the Membership Plans app block on the storefront (its own add-to-cart flow, not a generic product form). On successful signup, Supercycle activates the membership and Shopify applies tags automatically: `Has membership`, `Has {status} subscription` (active/paused/canceled), `{plan name} subscriber`, `Recurring order #N`, `Supercycle member`. Credits deduct when a member checks a rental out, and restore when it's returned.
- **Methods block gating vs. our tag gating.** The **Methods** app block on the PDP (the one that reuses our theme's add-to-cart button, per the integration contract in CLAUDE.md) does its own client-side check against `customer.metafields.supercycle.membership.value.quotas.credits.allowance` to enable/disable the add-to-cart button when credits are insufficient. This is a *lower-level, more precise* check than our theme's `customer.tags contains 'Has active subscription'` gating (used for things like hiding the header/hero "Join the club" button). Both checks matter, at different points in the flow — the tag check is coarse ("are they a member at all"), the metafield check is what actually governs whether they can check out an item right now.

---

## 2. Setting up the $100/yr membership plan — step by step

**Goal for v1:** yearly membership, $100/yr, lets the member hold **1 item at a time**, with **no enforced hold-duration cap** (see open item above) and **effectively unlimited swaps** over the year.

### A. Create the plan in Supercycle admin

1. In Shopify admin, go to **Supercycle > Settings > Methods > Membership**.
2. Click **Add plan**.
3. Set the plan title (this becomes the linked Shopify product's title — use something customer-facing, e.g. "LMS Annual Membership").
4. Set the **credit/item allowance to 1** (one item held at a time).
5. Set the **swap allowance** high enough to be effectively unlimited for a year of normal use (check what the actual field/max value is when you get to this screen — the docs don't give a hard number, so this needs eyeballing in the UI).
6. Set the **purchase option / pricing tier**: yearly billing, $100/yr. (If the UI offers multiple intervals per plan — e.g. monthly vs. yearly tiers on the same plan — decide whether we want *only* yearly for now, or scaffold monthly too and hide it. Default to yearly-only for v1 unless you want both.)
7. Save the plan.

### B. Enable membership on rentable products

1. Go to **Supercycle > Products**.
2. For each product that should be rentable via membership, select rental method **Membership** and toggle it on.
3. At the **variant level**, set the credit cost (for a simple "1 credit = 1 movie" model, this should just be `1` on every rentable variant, so allowance-of-1 cleanly means "one movie out").
4. Save.

### C. Build the storefront membership page

1. Create a new Shopify **collection** containing the plan product(s) we want to surface for purchase (just the one $100/yr plan for now, but a dedicated collection keeps this extensible for future tiers).
2. Create a new Shopify **page** (do not reuse the existing `theme/lms-redesign-v4/templates/page.json` block from earlier experimentation — build fresh, per your call above).
3. In the theme customizer, add the **"Supercycle - Membership plans"** app block to the new page.
4. Point the block's **collection** setting at the plan collection from step 1.
5. Configure the block's display settings (pricing card template, colors, button label, etc. — it pulls title/price/description from the linked Shopify product, styleable via the block's own settings plus a `custom_css` field).
6. Preview and confirm: plan card shows correct price/interval/credit allowance, and clicking through completes a real signup (tags get applied, credit balance populates on the test customer).

### D. Verify end-to-end

- [ ] Tag/metafield check: after a test signup, confirm the test customer has `Has active subscription` + related tags, and `customer.metafields.supercycle.membership` shows credit allowance = 1.
- [ ] PDP check: on a membership-enabled product, confirm the Methods block reflects credit availability (button enabled when a credit is free, disabled/messaged when the member's 1 credit is already checked out).
- [ ] Header/hero check: confirm "Join the club" buttons hide correctly for this now-active member (existing gating logic in `sections/header.liquid` / `sections/lms-hero.liquid`).

---

## Open questions / follow-ups log

- **7-day hold duration**: no native membership-plan setting for this. Revisit once we've looked at return-trigger automation or decide it's purely operational (reminder emails / honor system).
- **Swap allowance ceiling**: need to check the actual UI to see what counts as "unlimited enough" for a year of normal single-item swapping.
- **Monthly vs. yearly pricing tiers**: decide if the plan should ever offer more than the one yearly option.
