# Shopify Flow: auto-cancel online orders for rental movies

**Store:** production (`p0wkgv-wy.myshopify.com`)
**Why:** Order #1074 (2026-09-20) bought two `Rental` movies online at $0.00 via Horizon's quick-add on `/collections/all`. Quick add is now off and the empty-cart link is fixed, but movies are still published to the Online Store at $0, so a cart permalink (`/cart/<variant-id>:1`) or `/cart/add.js` can still reach checkout. The store is on the Shopify plan (not Plus), so a custom-app checkout-validation Function isn't available. This Flow is the backstop: it cancels any such order the moment it's created.

It is reactive, not preventive — the customer still receives an order confirmation before the cancellation email. Treat it as a stopgap until the Shopify Subscriptions + Libib design decides how online rentals work.

---

## Build the workflow

Admin → **Apps → Flow → Create workflow**. Name it `Cancel online rental orders`.

### 1. Trigger

**Order created**

### 2. Condition

Add a condition with **two checks joined by AND**:

1. **Order / Source name** — `is equal to` — `web`
   Limits this to Online Store checkouts so POS sales of `Rental`-tagged copies at the counter are never touched.
2. **Order / Line items / Product / Tags** — set the list mode to **At least one of** (line items) → **At least one of** (tags) — `is equal to` — `Rental`
   Tag matching is exact and case-sensitive: `Rental`, capital R.

### 3. Actions (on the **Then** branch)

Add these in order:

1. **Add order tags** — `blocked-rental`
   Makes the orders easy to find later (Orders → filter by tag).
2. **Cancel order**
   - Reason: **Other**
   - Refund: **on** (no-op for $0 orders, but covers a movie that's ever priced above $0)
   - Restock inventory: **on** — otherwise the copy shows out of stock on the storefront
   - Notify customer: **on**
   - Staff note: `Auto-cancelled: rental movies can't be ordered online yet.`
3. **Send internal email** — to the store owner
   - Subject: `Online rental order auto-cancelled: {{order.name}}`
   - Body: include `{{order.name}}`, `{{order.customer.displayName}}`, `{{order.email}}`, and the line item titles so someone can follow up with the customer (they may be a new member who thought they were reserving titles).

Leave the **Otherwise** branch empty.

### 4. Turn it on

Click **Turn on workflow**.

---

## Test it

1. Pick an in-stock `Rental` movie and get its variant ID (admin product URL → variant, or the product JSON at `/products/<handle>.js`).
2. In a browser past the storefront password, visit `https://littlemoviestore.com/cart/<variant-id>:1` and complete checkout with a test email.
3. Confirm within a minute or two:
   - the order is **Cancelled**, tagged `blocked-rental`, and inventory is back to its previous count
   - the internal email arrived
   - Flow → the workflow → **Recent runs** shows the run with the condition evaluating true
4. Also confirm a normal online order (membership, retail) runs the workflow with the condition **false** and is left alone.

## Notes

- Flow does not run retroactively — orders placed before the workflow is turned on (e.g. #1074) must be handled manually.
- If a product ever legitimately needs to sell online while tagged `Rental`, this workflow will cancel it. Remove the tag or add an exception to the condition first.
- Retire this workflow once the rental checkout design (Subscriptions + Libib) replaces it with a real online flow or a preventive checkout rule.
