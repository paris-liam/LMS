# Availability filter + back-in-stock waitlist — Shopify Admin runbook

**Companion to the code plan:** `docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist.md`
**Design rationale:** `docs/superpowers/specs/2026-07-15-availability-filter-and-backinstock-waitlist-design.md`

> **Rewritten 2026-09-10 to match reality.** This runbook was written in July against the **dev store** and against assumptions that have since been disproved. It has been corrected in place. Two things to know before reading: the store is now **production**, and **Section A is largely already done**. Sections of the original that were simply wrong (notably B1) are marked rather than silently deleted.

This is the by-hand work in Shopify Admin, the Supercycle app, Search & Discovery, and Flow. **No code changes here** — the theme code lives in the companion plan.

**Store: `p0wkgv-wy.myshopify.com` (production).** Supercycle is installed and live there, **not** on the dev store — every "dev store" reference in the July original was wrong. The dev store has no Supercycle products at all.

---

## Status at a glance (2026-09-10)

| Section | State |
|---|---|
| **A — Supercycle setup** | Mostly **done**. Plan exists and is Active; 79 titles imported; app embed enabled. Outstanding: Membership enabled on only 3 titles, and a **sync bug** blocks enabling it reliably. |
| **B — Availability filter** | **Blocked / broken.** The filter returns no products. B1 as written is impossible. |
| **C — Waitlist** | **Deferred** (unchanged, see below). |

**The two live blockers:**

1. **Product-level sync bug.** Enabling the Membership method reliably writes `supercycle.membership_configuration`, but `supercycle.methods`, `supercycle.total_uncommitted_inventory` and the `Supercycle product` tag land on only *some* products. A controlled six-title test succeeded on two and failed on four. Ruled out: missing items, and Shopify inventory tracking. Cause unknown — with Supercycle support (`claudedocs/2026-09-10-supercycle-support-ticket.md`).
2. **Storefront filter returns nothing.** See Section B.

---

## Section A — Supercycle setup

### A1 — (Pre-import only) Set Shopify inventory quantities

Only meaningful **before** A2 — it lets Supercycle auto-generate items at import. After importing, create items in A3 instead.

Per Supercycle's docs, importing sets the product to **"Inventory not tracked"** in Shopify and hands inventory management to Supercycle. Note that ~51 of the imported products are nonetheless `tracked: true`, most likely because a later client CSV upload switched tracking back on. **Tracking state does not affect whether the product-level metafields sync** — that was tested and disproved on 2026-09-10.

### A2 — Import rentable movies into Supercycle ✅ partly done (79 titles)

**Admin → Products** → select the rentable movies (they carry the `Rental` tag) → **Bulk actions → Include in Supercycle** → confirm.

**Verify:** the product gains `supercycle.supercycle_enabled = true`. Use **that** field, not `supercycle.methods`, to tell whether a product is imported — `methods` is unreliable (blocker 1).

### A3 — Create items (one per physical copy)

**Apps → Supercycle → Products → [movie] → variants table → quantity dropdown → Add inventory**, then:

- **Fastest:** **"Add without serials"** → enter the number of physical copies → Review → Add inventory.
- **Traceable:** one serial per line, `LMS-NNNNNNN` scheme.
- **At scale:** CSV import, or the Supercycle Scanner.

**Availability gotcha:** an item counts as available only when Visibility = **`Active`** and it isn't in a cycle.

> Never surface `LMS-NNNNNNN` serials on the storefront.

### A4 — Enable the Membership method per product ⚠️ blocked by the sync bug

**Apps → Supercycle → Products → [product] → Membership → toggle on → Save.** Item-based credits mean there is no per-title credit cost to set; those fields are greyed out.

**As of 2026-09-10 only 3 titles have a `supercycle.methods` value** (Zack Parker's Proxy, Fatal Attraction, Rear Window). Toggling off→save→on→save is the only known way to (re)write it, and it works on some products and not others — blocker 1. Do not assume a title is enabled because Supercycle's own Products view says so; check the Shopify metafield.

**No confirmed bulk-enable path.** Re-check **Supercycle → Products → ••• → Bulk update options** on production — the docs describe a CSV flow that wasn't available on the dev store in July.

### A5 — Create the membership plan ✅ done

**Apps → Supercycle → Settings → Methods → Membership.** The plan exists as **"Little Movie Club -- 1 Year"** (Active), linked to a real Shopify selling plan.

- Purchase option: **$160/yr** *(corrected — the July original said $100/yr)*
- Credit / item allowance: **3** *(corrected — the July original said 1)*
- Order and return allowance: **unlimited** (`null`/blank)

An earlier draft plan, "Little Movie Club" (no "-- 1 Year"), is Archived — leftover, not live.

### A6 — Mount the app blocks ⚠️ the PDP half is CANCELLED

**The Methods block is NOT mounted on the PDP, and must not be.** Reversed 2026-09-08: rental checkout stays **in-store** via Shopify POS, and the movie PDP is deliberately read-only — no product form, no add-to-cart, no app-block slot. See `CLAUDE.md` → integration contract §1. The July instruction to add a Methods block to the product template is void.

Still required: the **Membership plans** block on the membership page template (`page.membership`), pointed at the `plans` collection. Already present and configured; the app embed is enabled as of 2026-09-10.

### A7 — Enable automatic recredit on return

**Apps → Supercycle → Settings → Membership rental → "Automatically recredit returns on request" → on.**

### A8 — Gate check

- [x] Titles imported with items.
- [ ] Membership enabled on the titles you intend to rent — **blocked by the sync bug**.
- [x] The plan exists ($160/yr, allowance 3, unlimited orders/returns).
- [x] `supercycle.uncommitted_inventory` populates — **confirmed, 81 variants** (34 `true`, 18 `false`).
- [x] ~~Methods block mounted on the PDP~~ — cancelled, see A6.

---

## Section B — Availability filter (Search & Discovery)

> **⛔ Currently broken (2026-09-10).** The filter returns **No products** on the live storefront, in both value forms, despite 81 populated values. Re-tested 54 minutes after the last configuration change with no change, so it is **not** an indexing delay. This is unresolved and is Issue 3 in the support ticket.

### B1 — Make `supercycle.uncommitted_inventory` filterable

The metafield is a **variant** metafield, type **boolean**, display name "Rental availability", created by Supercycle. It already exists on production with 81 values.

> **❌ The July instruction here was impossible.** It said to enable **"Filter on the product list and in the Admin API."** Shopify **rejects** that capability on a variant metafield:
> ```
> INVALID_CAPABILITY: The capability admin_filterable is not valid for this definition.
> ```
> Admin-list filtering is product-level only. `smartCollectionCondition` *can* be enabled on it (done 2026-09-10) and made no difference to the storefront filter.

> **Do NOT delete this definition, or the `supercycle.methods` one.** Deleting a definition wipes its values catalogue-wide in seconds and re-creating it does not restore them. This happened on 2026-09-10 to `supercycle.methods`.

The product-level **`supercycle.methods`** definition (`Supercycle Methods`, type `list.single_line_text_field`, admin-filterable + smart-collection-condition enabled) **does** work as a storefront filter — `?filter.p.m.supercycle.methods=Membership` correctly returns its 3 products.

### B2 — Add the Search & Discovery filters

**Apps → Search & Discovery → Filters → Add filter.** Sources: **Rental availability** (the variant metafield) and **Supercycle Methods**.

Relabel for the storefront: "In stock now", with the `true` value relabelled "Available".

### B3 — Verify

Test each filter **in isolation** before combining — filters AND together, so one broken clause zeroes the whole result set. That is exactly what made the combined URL look empty when the `methods` half was fine.

Current results on `/collections/all-movies` (57 products):

| Filter | Result |
|---|---|
| `?filter.p.m.supercycle.methods=Membership` | ✅ 3 items |
| `?filter.v.m.supercycle.uncommitted_inventory=1` | ❌ No products |
| `?filter.v.m.supercycle.uncommitted_inventory=true` | ❌ No products |

**Note:** even once fixed, this filter can only ever surface titles that have a `methods` value — 3 today. Blocker 1 gates the useful scope of Section B.

**Working alternative, already shipped:** the PDP in-stock label in `sections/main-movie.liquid` reads the same variant metafield **directly in Liquid**, bypassing the Search & Discovery index entirely. It works on all 52 of 57 products that carry the metafield. If the filter stays broken, the same Liquid-read approach on product cards is the fallback for collection-level availability.

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
