# Availability filter + back-in-stock waitlist — Shopify Admin runbook

**Companion to the code plan:** `docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist.md`
**Design rationale:** `docs/superpowers/specs/2026-07-15-availability-filter-and-backinstock-waitlist-design.md`

This is the by-hand work in Shopify Admin, the Supercycle app, Search & Discovery, and Flow. **No code changes here** — the theme code lives in the companion plan. Everything runs on the **dev store `lms-sandbox-lutsfahz.myshopify.com`** unless you are explicitly told otherwise. Do this on production only on a per-operation instruction.

Work top to bottom — later phases depend on earlier ones. Section A (Supercycle setup) blocks literally everything else; do not start Section B, C, or the code plan until A is done and verified.

> **⚠️ Known caveat — proceeding on Supercycle's guidance (2026-07-16).** Live testing found `supercycle.uncommitted_inventory` (variant) did **not** flip after a rental was created and fulfilled — it stayed `1` while Supercycle's internal inventory read "0 uncommitted / 1 on order". Supercycle **support confirmed** this metafield is the right availability signal and that it updates on **fulfillment state** (once the item is with the customer), recommending it as a condition on an **automatic (smart) Shopify collection**. Their claim contradicts our observed result (likely a write-lag or a store-side issue support is still reconciling). **Decision: build Sections B & C now as if the metafield is correct and current** — support will close the gap on their side. If the write is never fixed, the fallback is the **Methods filter app block** (beta) / **Storefront Product Availability API** for the filter and PDP OOS state. See `[[supercycle-uncommitted-inventory-integer]]`. (Also confirmed: an item commits at **fulfillment**, not order creation. Support calls the metafield "boolean"; it's actually integer `1` — logic unchanged.)

> **✅ Filter-count decision (settled 2026-07-15).** The availability filter is added as a **fifth** filter on the search/shop-all page, on top of the four in the sibling spec `docs/superpowers/specs/2026-07-15-rental-scoped-catalogue-and-filters-design.md` (New Arrivals, Community Picks, Format, Genre). That spec's "exactly four" restriction described the state *before* this work; the fifth "In stock now" filter is an intentional addition here. Section B builds it.

---

## Section A — Supercycle setup (prerequisite; blocks everything)

None of the availability data or the waitlist return-trigger exists until movies are actually live in Supercycle. Do this first.

### A1 — (Optional, PRE-IMPORT ONLY) Set Shopify inventory quantities before import

This step only does anything **before** A2 — its sole purpose is to let Supercycle auto-generate items at import time. **Once you've imported (A2), skip it entirely** and create items in A3 instead. Per Supercycle docs, items should be created *inside the Supercycle product, not the Shopify product* ("Supercycle is responsible for inventory management after import"), so A3 is the correct path regardless.

- (Pre-import only) **Admin → Products** → for each rentable movie SKU, set an inventory quantity equal to the number of physical copies you hold.

### A2 — Import rentable movies into Supercycle

1. **Admin → Products.**
2. Filter/select the rentable movies. (These carry the `Rental` tag per the rental-scoped spec — filter by `tag:Rental` if that scoping is already applied, otherwise select the titles you intend to rent.)
3. **Bulk actions → Include in Supercycle.**
4. Confirm.

**What this does:** hands inventory + pricing control for each imported product to Supercycle. Shopify's own inventory management turns **off** for those products.

**Verify:** open one imported product in Supercycle (**Apps → Supercycle → Products**). It should list under Supercycle-managed products. Back in **Admin → Products**, that product's inventory should now read as managed by Supercycle rather than Shopify.

### A3 — Create items (one per physical copy)

For each imported title, create one item per physical disc you own, **inside Supercycle** (not the Shopify product). Navigation:

**Apps → Supercycle → Products → [the movie] → variants table → current-quantity dropdown → Add inventory**, then choose one:

- **Fastest (recommended to unblock the build):** click **"Add without serials"** → enter the number of physical copies → **Review → Add inventory**. Creates `Active` items with no serials — enough for the availability filter and waitlist, which only need an item to be `Active` and not in a cycle. Serials can be added later per item.
- **Traceable:** add one serial per line using the `LMS-NNNNNNN` scheme.
- **Alternatives at scale:** CSV import (columns: Item ID, Variant Shopify ID, SKU, Visibility, Status; optional Condition) or the Supercycle Scanner (scanning an unknown tag opens "Create item").

**On barcodes:** the barcode shown in Shopify's inventory section is the Shopify *variant* barcode (one per title/SKU, shared by every copy) — it is **not** a per-item Supercycle serial and generally can't be used as one (two copies of a title share the same barcode and would collide). It's only useful as a Scanner lookup handle, or as the serial for a title where you hold exactly one copy.

**Availability gotcha:** an item counts as available only when Visibility = **`Active`** *and* it isn't currently in a cycle. Make sure new items land as `Active`, not `Draft` — otherwise `supercycle.uncommitted_inventory` won't reflect them.

**Verify:** a title with 2 physical copies shows 2 `Active` items in Supercycle.

> Reminder from CLAUDE.md: never surface `LMS-NNNNNNN` serials on the storefront. They stay admin-side.

### A4 — Enable the Membership method per product

- **Apps → Supercycle → Products → [product] → select the Membership rental method → toggle on → Save.**
- Item-based credits mean there is **no per-title credit cost** to configure — the credit-cost fields are greyed out; that's expected.
- Repeat for every imported rentable title.

**No confirmed bulk-enable path (as of 2026-07-15, dev store).** The docs describe a Products-list ••• → "Bulk update options" → Membership → CSV flow, but on this store the Products-list ••• only shows "Block dates," and the Membership options-table bulk menu (rename / update credit cost / update checkout price / apply to markets / apply to item conditions / delete) only edits *existing* options — nothing there *adds* the method to products that lack it. Doc-clarity feedback filed with Supercycle. Until resolved, enable per-product. You only need a handful for the rent-out test and to build/test the filter + waitlist, so don't block on doing all ~50.

**Verify:** the product shows Membership enabled in Supercycle.

### A5 — Create the membership plan

- **Apps → Supercycle → Settings → Methods → Membership → Add plan.**
- Purchase option: **$100/yr**.
- Credit / item allowance: **1** (one movie out at a time).
- Order allowance: **unlimited** — set to `null`/blank (the "unlimited" option, not a large number). This is a literal supported setting; confirmed via the `Membership created/updated` Flow payload where `orderAllowance` is documented as "(`null` if unlimited)".
- Return allowance: **unlimited** — same, `null`/blank.
- Save.

**Verify:** the plan shows allowance 1, unlimited orders, unlimited returns.

### A6 — Mount the app blocks (theme editor, no code)

The theme already allow-lists an `@app` block in the product section (`_product-details`), so this is placement only.

1. **Online Store → Customize** → open a **product** template on the working theme (`140918915134`).
2. In the product section, **Add block → Apps → [Supercycle] Methods** block. Position it where the buy button sits.
3. Open the **Membership page** template (`page.membership`) → **Add block → Apps → Membership plans** block. Save.

**Verify:** on a rentable PDP preview, the Methods block renders. On the membership page, the plans block renders and offers the $100/yr plan.

> Integration contract (CLAUDE.md): the Methods block **reuses the theme's single add-to-cart button** — do not add any dynamic-checkout / "Buy now" / express-checkout button to a movie PDP. The companion code plan's notify-me button must not break this; that interaction is a verification gate in the code plan (Task 1).

### A7 — Enable automatic recredit on return

- **Apps → Supercycle → Settings → Membership rental → "Automatically recredit returns on request" → on.**
- So a member's credit and the item's availability state update without a manual admin step per return.

**Verify:** setting shows enabled.

### A8 — Gate check before proceeding

Do not continue until **all** are true:
- [ ] At least one rentable title is imported into Supercycle with ≥1 Active item.
- [ ] Membership is enabled on that title.
- [ ] The $100/yr plan exists (allowance 1, unlimited orders/returns).
- [ ] The Methods block is mounted on the PDP.
- [ ] On that title's PDP, `variant.metafields.supercycle.uncommitted_inventory` is now populated. **How to check:** Admin → Products → [title] → scroll to **Metafields → View all** (or Admin API) → confirm a `supercycle.uncommitted_inventory` boolean value exists on the variant. This is the signal the availability filter and the notify-me button both read; if it's absent, Supercycle hasn't finished wiring the product and neither feature will work.

---

## Section B — Availability filter (Search & Discovery)

**Only after Section A.** This assumes decision (a) from the top-of-file callout (a fifth filter is acceptable). No code — `blocks/filters.liquid` already renders any filter Search & Discovery exposes, on both the search page and collection pages.

### B1 — Make `supercycle.uncommitted_inventory` filterable

1. **Admin → Settings → Custom data → Variants → View unstructured/all metafields.** ⚠️ It's under **Variants, NOT Products** — `uncommitted_inventory` is a *variant* metafield. (The Products page only shows the product-level `supercycle.total_uncommitted_inventory`, which is a different, count-based field.)
2. Find `supercycle.uncommitted_inventory` (variant metafield, created by Supercycle) → **Add definition** for it.

   > **Fallback if variant metafields aren't filterable in your Search & Discovery:** use the product-level **`supercycle.total_uncommitted_inventory`** (visible under Custom data → Products) instead — support confirmed it also updates on fulfillment. It's an integer *count* (`0` = none available, `≥1` = available) rather than a `1`/`0` flag, so in B2 you'd relabel each count value or, more simply, treat "any value ≥ 1" as in-stock. Prefer the variant flag when available; this is the backup.
   - Type: **Boolean** — confirmed 2026-07-16 when adding the definition, Shopify auto-detected the stored value as boolean, and Supercycle support independently called it a boolean. (An earlier admin read showed "1", which we took for integer — that was a misread; the definition-detection + support are authoritative. `true` = a copy is available/uncommitted, `false`/absent = none.)
   - Enable **"Filter on the product list and in the Admin API."**
   - Save.

> This mirrors the earlier `supercycle.methods` runbook step: you're **only enabling filtering** on a Supercycle-owned metafield, not creating data under it. Do **not** create anything else under the `supercycle` namespace (CLAUDE.md).

### B2 — Add the Search & Discovery filter

1. **Apps → Search & Discovery → Filters → Add filter.**
2. Source: **Uncommitted inventory** (the `supercycle.uncommitted_inventory` metafield).
3. Relabel the filter for the storefront: **"In stock now"** (use the filter group's "Filter label" rename field — see `[[search-discovery-filter-customization]]`). Because the metafield is a **boolean**, the value list will show **True/False** — relabel the **True** value to **"Available"** via the value-rename workaround (create a group of one; see that same memory). Products with `false`/no value simply won't carry the True value, so selecting "Available" filters to in-stock titles.
4. Save all changes before leaving the app.

> **Avoid the beta block:** do **not** use Search & Discovery's dedicated Supercycle "availability filter" app block — it's in beta with known limitations. A plain boolean-metafield-as-filter (what you just did) is the standard, non-beta mechanism and is enough for "is a copy available right now."

### B3 — Verify on both surfaces

1. **Search page** (`sections/search-results.liquid`) and **shop-all collection page** (`templates/collection.shop-all.json`): confirm an **"In stock now"** filter now appears in the sidebar on both.
2. Live test: with a test membership account, rent out a title's only Active copy → its `supercycle.uncommitted_inventory` flips to `false` → confirm the title **drops off** results when "In stock now" is active, on **both** search and collection pages.
3. Process that rental's return through to **received** (Section A7 auto-recredit, or manually) → confirm the title **reappears** under the filter.

---

## Section C — Back-in-stock waitlist (metafield + two Flows)

> **⏸️ DEFERRED (decision 2026-07-16).** The waitlist is paused. It's blocked on **two** independent problems, neither a quick fix: (1) the metafield write — the notify-me button can't detect "out of stock" until `supercycle.uncommitted_inventory` actually flips off on rental (the open Supercycle support item), and (2) the capture mechanism — the design's contact-form → Flow trigger **does not exist** (C2 finding); a rebuild via **Shopify Forms → metaobject → Flow** (or app-proxy / 3rd-party app) is required and unverified for per-product context. Since the availability *filter* is the higher-value, nearly-done half and shares blocker (1), effort refocuses there and on finishing Supercycle setup (Section A). **Done and retained:** C1 (`custom.waitlist_emails` metafield exists — harmless to leave). **To resume:** pick a capture mechanism (see C2 finding + the deferred-decision options), confirm blocker (1) is resolved, then build C3–C6 and the companion code plan.

**Only after Section A.** The theme-side notify-me button is in the companion code plan; this section builds the data model and the two Flow workflows it depends on. Do **C1 first** — the code plan writes to this metafield.

### C1 — Create the waitlist metafield

1. **Admin → Settings → Custom data → Products → Add definition.**
2. Definition:
   - Name: **Waitlist emails**
   - Namespace and key: **`custom.waitlist_emails`**
   - Type: **List of single line text** (`list.single_line_text_field`)
   - Product-level (these titles are single-variant "Default Title").
   - Leave storefront filtering **off** — this is internal data, not a facet.
   - Save.

**Verify:** the definition exists and is editable from a product's Metafields panel.

### C2 — VERIFY-BEFORE-BUILD: confirm the contact-form → Flow trigger

The capture path relies on a `{% form 'contact' %}` submission firing Flow's **"Contact form submitted"** trigger. That pairing was **not** confirmed against a doc citation during design. Confirm it before building C3.

1. **Apps → Flow → Create workflow → Trigger.**
2. In the trigger picker, search for a **"Contact form submitted"** (or similarly named storefront-contact) trigger.
3. Note the **exact trigger name** and inspect its **payload shape** — specifically whether it exposes the submitted fields (you'll need to read the product ID and email the button sends).
4. **If the trigger exists and exposes submission fields:** proceed to C3.
5. **If it does not exist or can't read custom fields:** stop and report back — the capture mechanism needs rethinking (e.g. a different form type or a small app/proxy), and the code plan's Task 2 changes accordingly.

Record what you find here: **FINDING (2026-07-16): the assumed "Contact form submitted" Flow trigger does NOT exist.** Shopify Flow has no storefront contact-form trigger, and Supercycle offers no waitlist/back-in-stock capture (its notifications are rental-lifecycle only). The supported native, no-backend path is: **Shopify Forms** (first-party app) saves each submission as a **metaobject entry** → Shopify Flow's **"Metaobject entry created"** trigger fires. So capture must go through Shopify Forms (or an app-proxy/Admin-API write, or a 3rd-party back-in-stock app), NOT a raw `{% form 'contact' %}`. Open risk with the Forms path: confirming per-product context (the product ID) can be attached to the submission metaobject — the per-product `custom.waitlist_emails` model needs it. **Capture mechanism decision pending (see below); C3 blocked until chosen + verified.**

### C3 — Flow: capture (contact form → append to waitlist)

Build only after C2 confirms the trigger.

1. **Apps → Flow → Create workflow.**
2. **Trigger:** the contact-form trigger confirmed in C2.
3. **Condition (dedup):** load the target product's `custom.waitlist_emails`; check whether the submitted email is **already present**. If present → stop (do nothing).
4. **Action:** append the submitted email to that product's `custom.waitlist_emails` list metafield (update-metafield action).
   - The product ID and email come from the hidden fields the notify-me button submits (defined in the code plan, Task 2). Field names to expect: `contact[product_id]` and the member email in the contact email field.
5. Name it **"Waitlist — capture"**, turn it **on**, save.

**Verify:** manually submit a test notify-me (once the code plan's button is live) → confirm the email lands in that product's `custom.waitlist_emails` (Admin → product → Metafields). Submit the same email again → confirm it is **not** duplicated.

### C4 — VERIFY-BEFORE-BUILD: confirm the `rental.item` → product join path

The notify Flow (C5) must resolve, for each returned cycle, which Shopify product to email against. Design only had the top-level Return/Cycle field list, **not** the nested Item property table. Confirm the join before building C5.

1. **Apps → Flow → Create workflow → Trigger → "Return updated"** (native Supercycle trigger).
2. Inspect the payload: `returnOrder.rentals[]` → each `rental.item`. Drill into `rental.item`'s properties.
3. Identify the exact field that maps an item to a **Shopify product or variant ID** (e.g. an item → variant → product reference).
4. Record the exact path: `_______________________________________`
5. If no such field is exposed on the trigger payload, note what lookup/step is needed to resolve it, and report back before building C5.

### C5 — Flow: notify (return received → email waitlist → clear)

Build only after C4 confirms the join path.

1. **Apps → Flow → Create workflow.**
2. **Trigger:** **Return updated** (Supercycle, native — confirmed in the spec).
3. **Condition:** `returnOrder.receivalStatus == "received"` — fire only when the item is physically back and available, not on return *request*.
4. **For each** cycle in `returnOrder.rentals`: resolve the product via the join path recorded in C4 (`rental.item` → variant → product).
5. Read that product's `custom.waitlist_emails`.
   - **If empty:** do nothing for that product.
   - **If non-empty:**
     a. **Send email** (Flow's native "Send email" action) — one per address. **Copy must not imply the item is reserved for the recipient** (see edge case below).
     b. **Clear** `custom.waitlist_emails` on that product (set to empty list). One-shot: members do not stay on a persistent watch.
6. Name it **"Waitlist — notify & clear"**, turn it **on**, save.

**Known edge case (intentionally not solved):** multiple members can be waitlisted on the same single returned copy. All get emailed; only the first to add-to-cart gets it. This is inherent to single-copy-per-title at LMS scale — no reservation hold. Keep the email copy honest about that ("a copy is back" — not "we're holding it for you").

### C6 — End-to-end waitlist verification

Once the code plan's button is live **and** C3/C5 are on:

1. As a member, on an **out-of-stock** title, click **"Notify me when back in stock."**
2. Confirm the email lands in `custom.waitlist_emails` (Admin → product → Metafields).
3. Process a return on that title through to **received.**
4. Confirm the email **sends** and the metafield is **cleared** afterward.
5. Process a **second** return on the same title → confirm that member is **not** re-emailed (one-shot holds).

---

## When you're done

Report back with:
- Section A8 gate results (is `supercycle.uncommitted_inventory` populating?).
- C2 finding — exact contact-form trigger name + whether it reads submission fields.
- C4 finding — the exact `rental.item` → product/variant ID path.

Those three answers unblock / correct the companion code plan (Tasks 1–2) and Flows C3/C5.
