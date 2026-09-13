# Libib vs. Supercycle — feasibility & migration estimate (2026-09-12)

**Question:** the client is considering dropping Supercycle and running rentals on Libib. What would it cost, what would it take, and what would they give up?

**Short answer:** feasible, and cheaper by roughly **$1,100+/yr**, but it is a *different product category*. Libib is a library circulation system (check-out / check-in / due dates / holds), not a commerce app. It does not bill members, does not enforce a "3 items at a time" allowance, does not integrate with Shopify or POS, and cannot feed live availability back to the Shopify storefront. Migration is **~8–12 dev days** plus client ops work (barcode relabelling is the wildcard).

Sources: libib.com/pricing, support.libib.com (lending, settings, publish, kiosk, add-items, item-overview, reports, rest-api/*), supercycle.com/pricing, shopify.dev subscription-contract migration docs. All fetched 2026-09-12.

---

## 1. What Libib is

| | Basic | **Pro** | Ultimate |
|---|---|---|---|
| Price | $0 | **$9/mo or $99/yr** | $900/yr |
| Items | 5,000 | 100,000 | 100,000 |
| Lending / holds / patrons | ✗ | ✓ (unlimited patrons) | ✓ + patron app |
| Extra staff logins ("managers") | ✗ | $2/mo ($24/yr) each | 50 included |
| REST API, barcodes, batch edit, CSV reports | ✗ | ✓ | ✓ |

**Circulation features (Pro):**
- Check out / check in / place hold from web or the staff mobile app, by scanning UPC or Libib's per-copy custom barcode. Custom barcodes are auto-generated per copy, overridable, **5–15 digits, numeric only**.
- One **global default due date** (N days after checkout) — this is the "2-week hold" that Supercycle's Membership method could not do. Patron reminder emails 1–14 days before due; up to 3 past-due reminders; editable templates.
- **Holds** with "item is available" emails — a working waitlist, which is what the broken Search & Discovery availability filter + back-in-stock plan was trying to build.
- Multiple **copies** per title (≤500), each with its own barcode and condition note.
- **Published library** at `libib.com/u/<alias>` — cover grid, search, tags, availability ("2/3 copies out"), patron login, patron holds, patron self-checkout, self-renewal, account page. Colour theme + logo only. **No custom domain, no embed/iframe documented.**
- **Kiosk** self-checkout (web page + scanner, or iOS/Android tablet app), three trust levels.
- Patron history page (May 2026), lending CSV reports (24-month window).
- CSV import per media type; movies match on UPC/EAN. "Force import" (Pro) lets title-only rows in.

**What Libib does NOT do (verified against docs):**
- **No payments, fees, fines, or membership billing.** Patrons are free records; money stays in Shopify.
- **No per-patron checkout limit** found anywhere in the settings, lending, or FAQ docs. Staff see a patron's "current checkouts" count on the lending screen and enforce by eye; kiosk self-checkout cannot enforce it at all. *Confirm on a Pro trial before committing — it's the single biggest functional loss.*
- **REST API = patrons, managers, accounts only.** No items, no checkouts, no holds, no webhooks. Rate limit 1 request / 2 s. So nothing can read "is this copy on the shelf" out of Libib programmatically.
- No Shopify / POS integration of any kind.

## 2. What Supercycle does today that would need a home

| Today (Supercycle, production) | Under Libib |
|---|---|
| Membership billing — $160/yr selling-plan product, Membership Plans app block | **Shopify Subscriptions** (free, first-party) selling plan on a membership product; standard product form on the membership page |
| `Has active subscription` tag → theme gating | Shopify Flow: subscription contract created → add tag; cancelled/expired → remove tag. Same theme check, different tag name if desired |
| Credit allowance = 3 items at a time, swap allowance | **Lost.** Staff enforce via patron card count. Kiosk can't enforce |
| POS takeover at the counter (rental rings through Shopify POS) | Rental checkout happens in Libib (web or staff app), **separately** from POS. Two screens at the counter |
| `supercycle.uncommitted_inventory` → PDP in-stock label | **Lost** (no items API). PDP shows "check availability" link to `libib.com/u/<alias>` search, or nothing |
| Storefront availability filter (currently broken) | Not possible on Shopify side; exists natively on the Libib published site |
| Waitlist / back-in-stock | Libib holds + availability emails — **gain** |
| Rental duration | Global due date + reminders — **gain** |
| Serialized inventory (`LMS-NNNNNNN`) | Libib per-copy barcodes, numeric 5–15 digits — see risk below |
| Return-trigger automation, shipping buffers | Not needed for in-store; n/a |

## 3. Ongoing cost

| | Supercycle (Super plan) | Libib Pro |
|---|---|---|
| Base | $100/mo = **$1,200/yr** | **$99/yr** |
| Variable | +1% of circular revenue (~$1.60/member/yr) | — |
| Extra staff logins | included | +$24/yr each |
| Membership billing app | included | Shopify Subscriptions: $0 |
| **Total (1 owner + 2 staff, 100 members)** | **≈ $1,360/yr** | **≈ $147/yr** |

Savings ≈ **$1,200/yr**. (Assumes LMS is on Supercycle's $100/mo Super tier — verify in the app's billing screen.)

## 4. Migration effort (dev)

| Work | Est. |
|---|---|
| **Catalogue export → Libib movie CSV.** Extend `formatting-scripts/` to emit Libib's movie template (UPC/EAN, title, copies, tags, group). Trial import of ~50 titles, measure match rate, decide on Force Import for no-UPC titles. Full import + spot-check. | 2–3 d |
| **Barcodes.** Map existing `LMS-NNNNNNN` labels to Libib copy barcodes. Only works if the printed barcode encodes a purely numeric value; otherwise every copy gets relabelled (client ops, not dev). Investigate first — this decides whether the project is a weekend or a month for the client. | 0.5 d dev + client ops |
| **Membership billing.** Install Shopify Subscriptions, create yearly selling plan on a new membership product, rebuild `page.membership.json` with the standard product form (the *only* product page allowed to have add-to-cart). Migrate existing Supercycle contracts: Supercycle-created subscription contracts stop renewing correctly once the app is uninstalled — they must be re-created under Shopify Subscriptions (contract import) or cancelled and re-sold before uninstall. Count current members first. | 1.5–2 d |
| **Tag + patron sync.** Shopify Flow: contract activated → tag customer + HTTP request to `POST api.libib.com/patrons`; contract cancelled → remove tag + `POST /patrons/{email}` with `freeze`. Flow's Send HTTP Request action covers this; no server needed. | 1 d |
| **Theme.** Disable Supercycle app embed (`settings_data.json`), strip `supercycle.*` reads from `sections/main-movie.liquid`, replace availability label with a Libib link or remove, retarget gating tag if renamed, remove Supercycle blocks from `page.membership.json`. Small footprint — 4 files reference it. | 1 d |
| **Libib setup + published site.** Alias, colour/logo, due date, reminder templates, holds on, self-checkout policy, kiosk, staff manager logins. Mostly client-facing config; dev assists. | 0.5–1 d |
| **Cutover + docs.** Uninstall Supercycle (metafields wiped — acceptable post-cutover), update CLAUDE.md / integration contract, staff runbook. | 1 d |
| **Total** | **≈ 8–10 dev days**, 12 with contingency |

Not counted: client time learning Libib, relabelling if needed, re-enrolling members.

## 5. What the client gives up / gains

**Gives up**
- Enforced 3-at-a-time allowance (the core of the current membership design).
- Rental transactions in Shopify — no rental line items, no POS ringing, no unified customer timeline. Reporting splits across two systems.
- Live availability on littlemoviestore.com PDPs and any future storefront filter.
- Branded catalogue browsing *with* availability — Libib's public site is libib.com-hosted, lightly themable, no custom domain.

**Gains**
- Due dates + automatic reminder emails (open item Supercycle couldn't solve).
- Working holds/waitlist with notifications.
- Self-checkout kiosk, staff scanning app, patron history, lending reports.
- ~$1,200/yr saved; simpler mental model for a video-store counter.

## 6. Recommendation

1. **Start a free Libib Pro trial and test two things before anything else:** (a) whether any per-patron checkout limit exists (docs say no); (b) whether an existing `LMS-` label scans as a numeric value Libib accepts. Those two answers decide the decision.
2. If the client can live with staff-enforced limits and a two-screen counter, Libib is the better fit for an in-store-only rental model — Supercycle is built for shipped rentals and online checkout, most of which LMS has already scoped out.
3. If online availability on the branded site matters, stay on Supercycle; Libib can't feed it.
