# Membership System Design (Shopify-native)

**Status:** approved for planning
**Supersedes:** any earlier membership/checkout design based on Supercycle. Supercycle is out of scope for membership entirely — this is a fresh build on Shopify's own commerce primitives.
**Context:** membership checkout was deliberately removed from the live theme just before the 2026-09-20 launch (commit `80af052`) because membership products weren't sellable yet. This spec is what gets built to make them sellable, post-launch.

---

## 1. Requirements (as given)

- Membership renews yearly, $160/year, auto-renewing. Customers can pause or cancel. Customers get an email before renewal.
- Purchasable online or in-store via Shopify POS.
- Purchase requires reading and checkbox-acknowledging a membership agreement (no signature required).
- Membership grants 10% off all purchases, online and POS.
- Capture customer name and birthday at signup; schema may extend to more fields later.
- Client can send an email blast to all members.
- On membership creation, create a matching patron record in Libib (the library service that runs all rentals) via their REST API, using the same signup data.
- Libib returns a barcode on patron creation; store it as a Shopify customer metafield.
- All rentals and rental-related emails are handled by Libib, not Shopify — out of scope here.

## 2. Platform decision

**Shopify Subscriptions (native, free)**, not a third-party app (Appstle, Recharge, etc.), based on:

- Both native Shopify Subscriptions and Appstle now support selling subscriptions via POS (requires Shopify Payments + POS 10.13+, confirmed both in place).
- The native app has a built-in, customizable "upcoming order" customer notification — covers the renewal-reminder requirement without custom build.
- The store already uses **new customer accounts** (verified via Admin API: `customerAccountsV2.url` returns a `shopify.com/<id>/account` URL, not a classic `myshopify.com/account` URL), which is what's required for native self-serve pause/cancel in the customer portal.
- No extra recurring app cost. If some requirement below turns out not to be reliably achievable natively during implementation, fall back to Appstle for that specific gap — don't re-litigate the whole platform choice, just the piece that broke.

## 3. Product & selling plan setup

- One product: "Little Movie Club" (or similar), **subscription-only** (no one-time purchase option) — simpler checkout copy and logic; someone who doesn't want auto-renewal cancels via the portal instead of never enrolling.
- One selling plan: yearly interval, $160/charge, auto-renew on.
- Subscription cancellation policy set in admin (required for POS eligibility).
- Shopify Subscriptions tile added to the POS smart grid.

## 4. Terms acceptance & data capture

### Online
- On the membership product page: a required checkbox (linking to `/pages/membership-terms`) and a birthday date input, both as **line-item properties**, gated so "Add to cart" is disabled until the checkbox is checked.
- Fail closed if JS fails to load — don't silently allow purchase without the checkbox.
- **Open dependency, not yet done:** `/pages/membership-terms` is linked from the footer (see `sections/footer-group.json:149`) but the page doesn't exist with real content yet. Someone needs to write the actual agreement text before this ships — flagged here so it isn't missed.

### POS (in-store)
- No on-screen checkbox. Staff reads/hands over the terms, confirms verbal agreement, and types both the birthday and a note (e.g. "Terms agreed - verbal") into the POS order note field before completing the sale.
- A short staff script/checklist should be written and posted at the register (per the original draft plan's Phase 2, step 11) — this spec assumes that checklist gets written as part of implementation, not automated.
- **Evaluated and declined:** a paid app (TnC: Terms and Conditions Box, ~$8/month) offers a genuine on-screen POS "Agree to Terms" tile with timestamped consent logged to the order — more tamper-evident than a manual note, but not free. Decision: start with the free manual-note process; revisit only if staff compliance turns out to be a real problem in practice.

### Data storage: order line-item properties + customer metafield mirror
- Birthday and name are captured as line-item properties on the signup order (source of truth for "what did the customer type at signup").
- Additionally, a Flow step (see §5) mirrors birthday (and name, if useful) onto **customer metafields**. Reason: `sections/lms-perks-grid.liquid`, `lms-membership.liquid`, and `lms-shop-membership.liquid` already market "a free birthday movie, every year" as a real member perk — that has to be checkable at any point during the year (e.g. by staff at the counter, or a future automated segment), not just visible on the original signup order buried in order history.
- Update semantics: each new membership order **overwrites** the customer metafield value. Simplest rule; self-corrects if a birthday was mistyped at a prior signup.
- Libib has no birthday field (confirmed via their REST API docs — `POST /patrons` accepts `first_name`/`last_name` [required], `email`, `phone`, `address1/2`, `city`, `country`, `tags`, `patron_id`; no birthday). Birthday therefore stays Shopify-only.

## 5. Automation (Shopify Flow)

Trigger: **Subscription contract created** (fires on initial signup; using this rather than `Order created` scopes the automation specifically to membership signups, not just any order that happens to contain the product).

**Flow A — Tag + Libib sync + metafield mirror:**
1. Tag the customer `Active Member`. (No existing theme code currently checks any specific tag string — grepped the full theme, zero hits — so this name is free to pick and easy to rename before build.)
2. Call Libib `POST /patrons` with `first_name`, `last_name`, `email` from the order/customer.
3. On success: write the returned barcode to a Shopify customer metafield (namespace/key TBD at implementation time, e.g. `custom.libib_barcode`).
4. Mirror birthday (and name) from the line-item properties onto customer metafields.
5. On Libib API failure: retry a bounded number of times (Flow's built-in retry, or a short delay-and-retry sequence), then on final failure tag the customer `Libib Sync Failed` (or similar) so staff can create the patron manually in Libib and clear the tag once resolved. **The sale itself is never blocked or reversed by a Libib failure** — membership activates in Shopify regardless.

## 6. Member discount (10%)

- Automatic discount, 10% off, scoped to a customer segment defined by the `Active Member` tag.
- Applies store-wide, both online and POS, automatically once the tag is set — no separate POS-side build needed (Shopify automatic discounts apply at POS when the customer is attached to the sale).
- Default exclusions: the membership product itself, and gift cards. This is a default, not a hard requirement from the client — confirm before build in case they want a different scope (e.g. excluding already-discounted/sale items too).

## 7. Renewal reminder & cancellation

- **Renewal reminder:** Shopify Subscriptions' built-in "upcoming order" customer notification, template customized with LMS branding. No custom build.
- **Pause/cancel:** native self-serve via the customer accounts subscription portal (confirmed available — store uses new customer accounts). No custom build.

## 8. Email blast to members

- Shopify Email campaign targeting the `Active Member` segment (same segment used for the discount).

## 9. Migration / legacy data

None needed — confirmed zero existing members; membership checkout was never live (removed pre-launch, per commit `80af052`).

## 10. Testing plan

- One full online test purchase: checkbox + birthday entered, payment completes → confirm tag applied, Libib patron created, barcode metafield populated, birthday metafield populated, discount active on a subsequent test order, renewal-reminder email content/timing correct.
- One full POS test purchase: staff script followed, order note contains birthday + terms confirmation → confirm same downstream effects (tag, Libib sync, discount).
- One induced-failure test: point the Flow's Libib HTTP step at an invalid endpoint/credential to confirm the retry-then-tag-for-manual-follow-up path actually fires, and that the sale still completes normally.
- Confirm pause and cancel both work through the customer accounts portal for a test membership.

## 11. Explicitly out of scope for this spec

- Anything Supercycle-related (retired for membership entirely).
- Rental logistics, rental emails, serial/barcode scanning at the shelf — all Libib's domain.
- Writing the actual membership agreement text for `/pages/membership-terms` (a content task, not a technical one, but a hard blocker for online launch of this feature).
- The POS staff script/checklist content (should be written alongside implementation, not automated).
