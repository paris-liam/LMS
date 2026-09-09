# Supercycle system — rebuilt scope & estimate basis

**Date:** 2026-09-08
**Purpose:** a from-scratch scope for "set up the entire Supercycle system," replacing the older 16-feature deck-driven plan (`lms-supercycle-feature-plan.md`), which bundled in a lot of work that never touches Supercycle. This document is the basis for a client price/timeline estimate — it is not itself a price.

**Store target:** production (`p0wkgv-wy.myshopify.com`) — the working store per the current TEMPORARY rule in `CLAUDE.md`. All state below was queried live against production on 2026-09-08 via Admin GraphQL (`shopify store execute`), not inferred from docs.

---

## 1. Confirmed scope boundary (decided this session)

- **Scope = Supercycle-touching work only.** Not the full 16-feature deck list — weekly drops, bundles, recommendations, loyalty, events/ticketing, space rental, and the retail catalogue are separate Shopify/app work with no Supercycle dependency, out of scope for this estimate.
- **Rental checkout stays in-store.** The movie PDP is deliberately read-only (poster, description, attribute chips, in-stock indicator, notify-me) per the 2026-07-17 design decision (`docs/superpowers/specs/2026-07-17-movie-product-template-design.md`) — no online add-to-cart, no Methods-block slot on the PDP. This is *not* being reversed. Physical rental checkout/return happens at the counter via Shopify POS + Supercycle.
- **Membership enrollment is dual-channel.** A customer can buy the $/yr plan **either** online (Membership Plans app block on the membership page) **or** in-store via POS. Both paths need to work.

This narrows "the entire Supercycle system" to five functional pieces:

1. Membership plan configuration
2. Catalogue import + per-title Membership-method enablement
3. Serialized item/inventory setup (one item per physical copy)
4. In-store rental checkout/return via POS (+ serial scanning)
5. Online membership enrollment (Membership Plans app block) + member-gating (tags/metafields) for discounts

---

## 2. Live production audit — what's actually there right now

Queried directly against `p0wkgv-wy.myshopify.com`, not assumed from docs (which turned out to understate how far along production is, and overstate how much of it is customer-visible).

| Area | Finding |
|---|---|
| **Supercycle installation** | Confirmed installed — the app-reserved `supercycle.methods` product metafield definition exists. |
| **Membership plan** | **Already exists and is real.** "Little Movie Club -- 1 Year" (status Active), linked to a genuine Shopify selling plan ("Yearly", 1-year billing interval). An earlier draft, "Little Movie Club" (no "-- 1 Year"), is Archived — leftover, not live. |
| **Plans collection** | Exists (`plans`), contains the 1 active plan product. Correctly scoped. |
| **Catalogue import** | **Only 52 of 3,130** rental-tagged/All-Movies products have been imported into Supercycle at all (i.e., carry the `supercycle.methods` metafield in any form). That's ~1.7% of the catalogue. |
| **Membership method enabled per-title** | Of those 52 imported, most show an **empty** methods array (`[]`) — imported but no rental method turned on. Spot-checked and confirmed only **2 titles** (*Avalanche*, *Fatal Attraction*) with Membership actively enabled (`["Membership"]`). Exact count needs a manual pass inside Supercycle's own Products view — JSON-array metafield search isn't reliably filterable via the generic Admin API. |
| **Availability data (`uncommitted_inventory`)** | Not present on production at all — this was dev-only work (from the 2026-07-15 availability-filter build) and was never migrated. No blocker for the in-store-only scope, since online availability filtering isn't in this scope. |
| **Storefront visibility** | **The Supercycle app embed is explicitly disabled** (`"disabled": true`) in the live theme's `settings_data.json` — same state found on dev (commit `d572857`, "hiding supercycle for now," 2026-09-02). Nothing Supercycle-related currently renders anywhere on the live storefront, even though the plan/product data exists behind the scenes. |
| **Membership Plans app block** | Present and configured on `templates/page.membership.json` (pointed at the `plans` collection), but inert while the app embed is off. Needs live re-verification once re-enabled — the checkout-redirect settings (`redirect_type: "custom"`) were flagged unverified in the 2026-08-28 dev-site audit and haven't been retested since. |
| **Serialized items (physical copies)** | **Not verifiable via generic Admin API** — Items are Supercycle-internal data, not a standard Shopify object. Needs a direct check inside Supercycle's own admin UI, or the client, to know how many (if any) items have been created. Treat as **unknown, assume zero** until confirmed. |
| **POS rental-checkout support** | **Unconfirmed** — this was flagged as an open question in the original feature plan (running question #6) and was never resolved. Given the confirmed scope is now in-store-only, this is the single most consequential unknown in this document — see §4. |
| **Customer / member counts** | 351 total customers on production. Tag-filtered counts (`Has active subscription`, `Supercycle member`) were **not reliably queryable** via this API path (the query filter was silently ignored, returning the total each time) — get an exact active-member count from Admin UI directly rather than trusting any number derived here. |

**Headline takeaway:** the membership *plan* itself is done. Almost everything else — catalogue import, per-title method enablement, item creation, POS rental flow, and turning the storefront pieces back on — is still ahead, at a scale (3,078 of 3,130 titles not yet imported) that's the dominant cost driver in this estimate, not any one integration puzzle.

---

## 3. Rebuilt work-item list

Flat list, each sized qualitatively (S/M/L) with the reasoning — no invented hour/dollar figures; translate sizes to your own rate once the open questions in §4 are resolved (POS depth in particular can swing size on item 4).

### A. Membership plan configuration — **Done, verify only**
- Plan exists, correct billing (yearly). Confirm allowance (1 item) and swap allowance (unlimited) match the intended design in `supercycle-explained.md` — not verifiable from outside Supercycle's settings screen.
- **Size: S** (a verification pass, not a build).

### B. Catalogue import + per-title Membership enablement — **Largest item**
- Import the remaining ~3,078 titles into Supercycle and enable the Membership method on each.
- No confirmed bulk-enable path as of the last check (2026-07-15 runbook note) — the Supercycle Products-list bulk actions didn't support adding the method to products that lack it. **Needs re-confirming with Supercycle support** whether a bulk/CSV path now exists (see §4, question 1) — this materially changes whether this is a scripted job or ~3,000 manual per-product toggles.
- **Size: L**, and the size band is wide specifically because of the bulk-path unknown — could be M with a working bulk tool, could be very L done by hand.

### C. Serialized item creation (one item per physical copy) — **Unknown scale, assume large**
- Assumed near-zero items exist on production today (unverifiable from outside Supercycle; confirm first).
- Supercycle supports "Add without serials" (fast, bulk quantity) or per-serial entry (`LMS-NNNNNNN`), or CSV import. Fastest path (bulk, no serials) is enough to unblock rental functionality; serials can be backfilled later.
- Depends on knowing physical copy counts per title — a data-gathering step in itself if that inventory count isn't already tracked centrally.
- **Size: L** (volume-driven, same root cause as B — most of the catalogue has never touched Supercycle).

### D. In-store rental checkout/return via POS + serial scanning — **Blocked on Supercycle's POS support depth**
- Confirm Supercycle's Shopify POS coverage: rental checkout, returns, counter-side serial scanning (Scanner app), and whether the member discount applies correctly at POS. This was an open question in the original plan (never resolved) and is now the load-bearing one, since rental is exclusively in-store.
- **Size: unknown until §4 question 2 is answered.** If POS support is solid and native, this is mostly staff training + verification (S/M). If it's partial or requires a workaround, this could be the most expensive single item in the whole estimate.

### E. Online membership enrollment — **Mostly built, needs re-activation + verification**
- Re-enable the Supercycle app embed on the live theme (currently `disabled: true`) — a one-line theme-settings change, but re-enabling surfaces the Methods/filter blocks too if they're mounted anywhere; confirm nothing unintended lights up (the movie PDP has no Methods slot by design, so this should be safe, but verify).
- Re-verify the Membership Plans block's checkout flow end-to-end (unverified since 2026-08-28; `redirect_type: "custom"` with a blank `redirect_url` was flagged then and never retested).
- Confirm the archived duplicate plan product ("Little Movie Club") isn't referenced anywhere and can stay archived.
- **Size: S/M** — most of the plumbing already exists; this is verification + cleanup, not new build.

### F. In-store membership enrollment via POS
- Confirm how a staff member rings up a new membership signup at the counter (does POS support the Supercycle plan product directly, does it need the same selling-plan purchase flow, is there a POS-specific Supercycle UI). Not documented anywhere in the existing plan — new territory.
- **Size: M** — likely folds into the same POS investigation as item D, but called out separately since it's enrollment, not rental.

### G. Member-gating for discounts (tag/metafield-based)
- Already partially built (header/hero "Join the club" gating logic exists and reads `Has active subscription`). Needs: confirming the automatic-discount-on-membership-fee question (does a Shopify automatic discount apply to the plan's own recurring charge, or only plain retail lines — open question from the original plan, still unresolved), and re-verifying gating still works correctly given the header-hiding changes made alongside the "hiding supercycle" commit.
- **Size: S/M**.

---

## 4. Questions to send Supercycle support (blocking parts of the estimate)

You confirmed a channel to Supercycle support exists — recommend sending these before finalizing price/timeline, since items B, C, and D above can't be sized precisely without them:

1. **Is there now a bulk/CSV path to enable the Membership method across many products at once?** (As of 2026-07-15 there wasn't, on this store.) Directly determines whether item B is a scripted job or ~3,000 manual toggles.
2. **What is the actual depth of Supercycle's Shopify POS support?** Specifically: rental checkout, returns, counter-side serial scanning (Scanner app), and whether the member discount applies correctly at POS. This is now the most consequential open question in the whole document, since rental is in-store-only.
3. **Is there a recommended/supported way to bulk-create items** (one per physical copy) beyond the documented "Add without serials" / per-serial / CSV paths — anything faster at ~3,000-title scale?
4. **Does a Shopify automatic discount apply to the membership plan's own recurring selling-plan charge**, or only to plain retail line items? (Affects whether "member discount" promises can include the membership fee itself — inherited from the original plan's unresolved question 4.)
5. *(Lower priority, doesn't block the estimate)* Is the Membership Plans app block's `redirect_type: "custom"` / blank `redirect_url` configuration expected to work as-is, or does it need a value set?

---

## 5. What this document is not

- Not a price. Sizes (S/M/L) are relative-effort labels based on what's confirmed vs. still unknown, not hours or dollars — translate against your own rate once §4 is answered, especially question 2 (POS depth), which has the widest cost swing in the whole scope.
- Not a claim about item/serial counts, exact active-member counts, or POS capability — those three are explicitly flagged above as unverifiable from outside Supercycle's own admin and need a direct look (by you or the client) rather than being estimated from the outside.
