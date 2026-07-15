# In-stock/out-of-stock filter + back-in-stock notify waitlist — Design Spec

**Date:** 2026-07-15
**Status:** Design only — implementation begins once Supercycle setup (Section 1) is complete. No code in this spec.

## Goal

1. Let customers filter the search page and collection pages by whether a title currently has a rentable copy available.
2. Let a member on an out-of-stock title's PDP ask to be emailed once it's back — one-shot notification, member-only, no purchase involved (this store is rental-only via Supercycle Membership; see `CLAUDE.md` and `[[supercycle-rental-only-scope]]`).

Both features depend on products actually being live in Supercycle with membership enabled, which isn't true yet — Section 1 is the prerequisite work.

## Context established during brainstorming

- Supercycle is rental-only: Membership method only, item-based credits, allowance = 1 (one movie at a time), swap allowance unlimited (same-day swaps). No Calendar/Subscription/Resale. Confirmed 2026-07-15, see `[[supercycle-rental-only-scope]]`.
- Supercycle returns are **separate from Shopify's native return/inventory system** (confirmed via Supercycle docs) — this rules out any third-party back-in-stock app that watches native Shopify inventory quantity; they will never fire.
- Supercycle writes `supercycle.uncommitted_inventory` (variant boolean) and `supercycle.uncommitted_inventory_count` (variant integer) automatically once a product is imported and has active, available items. These are read-only from the theme's perspective — reading them is the intended integration pattern and does not conflict with CLAUDE.md's "never hand-create the `supercycle` namespace" rule (that rule is about writing/creating definitions, not reading Supercycle's own data).
- The theme's `blocks/filters.liquid` is a generic Search & Discovery filter renderer — it loops over `results.filters` and switches on `filter.type` (`price_range`, `boolean`, `list`, etc.) with no per-filter custom code. It's used identically by `sections/search-results.liquid` (the search page) and the collection template. Adding a filter to Search & Discovery's config makes it appear on both surfaces for free.
- Supercycle's Membership plan settings support `orderAllowance`/`returnAllowance` = `null` for **unlimited**, confirmed via the `Membership created`/`Membership updated` Flow trigger payload schema (`membership.orderAllowance`, `membership.remainingOrders`, etc., each documented as "(`null` if unlimited)"). This is a literal, supported setting, not an approximation via a large number.
- Supercycle's `Return created`/`Return updated` Flow triggers are native and documented, with payload fields including `returnOrder.receivalStatus` (`pending` | `received` | `overdue`) and `returnOrder.rentals[]` (array of cycles, each with `rental.item`, `rental.lineItemId`, etc.).
- **Open conflict to reconcile before implementation:** `docs/superpowers/specs/2026-07-15-rental-scoped-catalogue-and-filters-design.md` (same day, separate spec) restricts the inventory/search page to **exactly four** filter criteria (New Arrivals, Community Picks, Format, Genre) and states "everything else currently on that page not in this list goes away." The availability filter in this spec is a fifth criterion not covered by that list. This needs an explicit decision — either extend that spec's filter set to five, or treat availability as a distinct, later addition to the same page — before the filter half of this spec is implemented. Not resolved here; flagging so it isn't silently contradicted.

## Section 1 — Prerequisite: Supercycle setup

Blocks everything below. Steps, in order:

1. **Set Shopify inventory quantities** on rentable-movie SKUs before import, if auto-creation of serialized items on import is desired (optional — items can also be created manually after import).
2. **Import products into Supercycle**: Shopify admin → Products → select all rentable movies → Bulk actions → **Include in Supercycle**. This hands inventory/pricing control for each imported product to Supercycle (Shopify's own inventory management turns off for it).
3. **Create serialized items** per physical copy (serial `LMS-NNNNNNN`, condition, location, status `Active`) — bulk from the product page, CSV import, or the Supercycle Scanner app.
4. **Enable the Membership method** on each imported product (Supercycle → Products → product → Membership toggle on). Item-based credit system means no per-title credit cost to configure.
5. **Create the membership plan** (Supercycle → Settings → Methods → Membership → Add plan): $100/yr purchase option, credit/item allowance = 1, order allowance = unlimited (`null`), return allowance = unlimited (`null`).
6. **Mount the Methods app block** on the PDP (the `_product-details` block already allow-lists an `@app` block type — no theme-code change needed, just placing it via the theme editor) and the **Membership plans app block** on the membership page.
7. **Enable "Automatically recredit returns on request"** (Supercycle → Settings → Membership rental) so a member's credit and the item's availability state update without a manual admin step per return.

## Section 2 — Availability filter (search + collection pages)

**Data source:** `supercycle.uncommitted_inventory` (variant boolean), read directly. No `custom.*` stand-in — by the time this work starts, Supercycle will already be live and populating this metafield the moment a title is imported (Section 1, step 2).

**Setup (admin config, not code):** enable `supercycle.uncommitted_inventory` as a Search & Discovery filter (boolean type — e.g. labeled "In stock now" on the storefront). No new Liquid/JS is needed to render it: `blocks/filters.liquid` already renders any filter Search & Discovery is configured to expose, and it's shared by both the search page and collection pages.

**Caveat carried over from the original feature plan:** Search & Discovery's dedicated "availability filter" app block (a different, Supercycle-specific mechanism) is in beta with known limitations. This design deliberately avoids it — a plain boolean-metafield-as-filter is the standard, non-beta Search & Discovery mechanism, and is sufficient for "is there a copy available right now."

**Dependency:** see the open conflict noted above regarding the four-filter restriction on the search page.

## Section 3 — Back-in-stock notify button + waitlist

Native Shopify Flow + a product metafield. No custom app.

### Data model

One metafield per product: `custom.waitlist_emails` (`list.single_line_text_field`). Product-level (not variant-level) since these titles are effectively single-variant ("Default Title").

### Capture: PDP → waitlist

- When a title's `supercycle.uncommitted_inventory` is `false`, the buy-buttons area on the PDP shows a "Notify me when back in stock" button in place of add-to-cart.
- Visible and functional only for logged-in members (`customer.tags contains 'Has active subscription'`) — matches the confirmed model that only members can act on the notification anyway. The member's email comes from `customer.email`; there is no free-text email field.
- Clicking submits a `{% form 'contact' %}` with hidden fields carrying the product ID and the member's email.
- A Flow workflow triggered on **"Contact form submitted"** reads the submission and appends the email to that product's `custom.waitlist_emails`, with a dedup check (skip if already present).
- **Verify before building:** this design relies on the standard Shopify behavior that a `{% form 'contact' %}` submission fires Flow's "Contact form submitted" trigger. That pairing wasn't confirmed against a doc citation during this design session (general Shopify dev-docs search didn't surface the specific trigger name/payload). First implementation step: confirm the exact trigger name and payload shape in the Flow trigger picker on the dev store before building the rest of the workflow on top of it.

### Notify: return → email → clear

- Flow workflow triggered on **Return updated** (native Supercycle trigger, confirmed).
- Condition: `returnOrder.receivalStatus == "received"` — fire only once the item is physically back and available, not merely when a return was requested.
- For each cycle in `returnOrder.rentals`, resolve the product via `rental.item` → variant → product.
  - **Verify before building:** the exact join path from `rental.item` to a Shopify product/variant ID needs confirming against Supercycle's full Item property schema — this design only had the top-level Cycle/Return field list in front of it, not the nested Item property table.
- Read that product's `custom.waitlist_emails`. If non-empty: send one email per address (Flow's native "Send email" action), then clear the metafield (one-shot — per decision, members do not stay on a persistent watch).

### Known edge case (not solved, intentionally)

Multiple members can be waitlisted against the same single returned copy. All get emailed; only the first to complete an add-to-cart actually gets it. This is inherent to a single-copy-per-title pool at LMS's scale and is not something this design attempts to fix (e.g., no reservation hold). Email copy should not imply the item is reserved for the recipient.

## Testing / verification plan

- **Filter:** rent out a test title's only available copy via a test membership account → confirm it drops off the "in stock now" filter on both search and collection pages → process the return through to `received` → confirm it reappears.
- **Waitlist:** as a member, click "Notify me" on an out-of-stock title → confirm the email lands in `custom.waitlist_emails` (inspect via Shopify admin custom data) → process the return through to `received` → confirm the email sends and the metafield is cleared afterward → confirm a second return on the same title does *not* re-email that member (one-shot behavior holds).

## Out of scope

- Any UI for a member to see or manage what they're waitlisted for (e.g., an account-page "your waitlist" section) — email is the only surface, per decision.
- Non-member waitlist capture.
- Persistent/repeating waitlist entries.
- Resolving the four-filter-vs-five-filter conflict with the 2026-07-15 rental-scoped-catalogue spec — flagged, not decided, here.
