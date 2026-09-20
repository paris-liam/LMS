# Libib lending setup — decisions & configuration

**Date:** 2026-09-19
**Scope:** Libib Pro account for LMS. Area #2 (Lending) of the Libib setup; areas #4 (Kiosk/Barcodes) and #5 (Published site) to follow.
**Sources:** support.libib.com — `libib/website/lending`, `libib/website/settings`, `libib/website/publish`, `getting-started/quickstart-for-patrons`, `libib/mobile-app/lending/*`, `faqs`. Fetched 2026-09-19.
**Related:** `docs/superpowers/specs/2026-09-13-membership-system-design.md` (patron creation via Flow → REST API), `claudedocs/2026-09-12-libib-vs-supercycle-assessment.md`.

---

## 1. Decisions (confirmed 2026-09-19)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Loan length | **14 days** |
| 2 | Reminder cadence (pre-due / past-due) | **OPEN** — see §5 |
| 3 | Overdue handling | No fines. Staff **Freeze** the patron manually after overdue (threshold TBD, see §5). Freeze blocks self-service only; staff can still lend to a frozen patron, so it's a flag, not a hard block. |
| 4 | 3-item allowance | **Manual.** Libib has no per-patron checkout limit; staff read the "active checkouts" count on the patron card at checkout. |
| 5 | Collections | **Rental library only** is in Libib. Floor Sale stock is not imported. No "disallow checkouts" collection needed. |
| 6 | Online reservations | **None.** Members cannot place holds or self-checkout online. All checkouts happen at the front desk, handled by an employee. |
| 7 | Back-in-stock alerts | Staff-placed holds only (see §2). |

---

## 2. Back-in-stock alerts without online reservation

**Libib has no "notify-only" feature.** The "item is available" email is sent exclusively to patrons with an **active hold**, and a hold reserves the copy (checkout to another patron is blocked until the hold is released or overridden).

**Policy adopted:**
- `Publish → Settings → Allow Patron Holds` = **OFF** → members cannot reserve online.
- When a member asks to be told when a title is back, **staff place the hold** from `Lending → Lending` (queue the item → select patron → **Place Hold**).
- On check-in Libib emails the patron automatically (batched through the day; only when no other hold is ahead of them).
- The copy stays reserved for that patron. House rule to decide: how long a staff-placed hold survives before staff **Release** it (`Lending → Holds → Release`). Suggest 3–7 days after the availability email.
- If a walk-in wants a held copy, staff can `Release` or override; note the emailed patron will then arrive to nothing — prefer releasing only after the pickup window lapses.
- `Publish → Display Options → Display Availability` = **ON** so the public site shows "copies / out" per title (no reservation needed to see if something is in).

---

## 3. Facts that constrain the setup (from docs)

- **One global due-date length** — owner-only; no per-collection or per-format loan period. Editable per transaction at checkout (click the date).
- **Reminders** — pre-due: 1 value, 1–14 days before due, **must be strictly less than the due-date value** or it never sends. Past-due: up to 3 values, 1–14 days after due; blank = off. Templates editable via *View/Edit Email*. Global across all collections.
- **Renew** — documented in the staff mobile app (`Checkouts → ⋯ → Renew`). Not documented on the web Checkouts page. **Verify on the live account** before writing the counter procedure.
- **No fees/fines.** Overdue = red highlight + past-due emails.
- **No per-patron checkout limit.** Kiosk cannot enforce one either.
- **Holds** auto-release after 4 years; a held item with no spare copy blocks checkout to anyone else.
- **Patron fields** — first/last (required), email (unique, login credential), notification emails ×3 (override login email), phone, address, patron ID (non-unique, searchable), tags, barcode (auto 5–15 digits, overridable), Freeze.
- **Freeze** — blocks patron self-checkout, self-hold, published-site and kiosk access; staff can still lend/hold for them.
- **Timezone** — set in Account Settings; drives due-date math.
- **History** — 2-year window on Checkouts / Holds / Reports.
- **Check In Mode** — scan returns one after another; needs custom barcodes for single-scan (ISBN/UPC prompts for copy choice).

---

## 4. Configuration steps

### 4.1 Account
1. `Account Menu → Account Settings` → set **Timezone** to the store's zone.

### 4.2 Lending settings (owner login required)
`Settings → Lending`
1. **Lending Due Date** → `14`.
2. **Patron Email Reminder** (before due) → value from §5 (must be < 14). Click *View/Edit Email* → brand the template (store name, hours, how to return).
3. **Past Due Reminders** 1/2/3 → values from §5, or blank to disable. Edit templates.
4. **Patron Hold Emails** → **ON**. Edit template: state the pickup window from §2 and that the copy is held at the desk.

### 4.3 Publish settings (lending-relevant only — rest belongs to area #5)
`Publish → Settings`
1. **Allow Patron Holds** → **OFF**.
2. **Allow Patron Self-checkouts** → **OFF**.
3. **Patron Account Page** → decide in area #5 (lets members see their own checkouts/history; self-renewal sub-toggle should stay **OFF** given desk-only policy).
4. **Your Email Notification for Patron Holds** → irrelevant while holds are off.

`Publish → Display Options`
5. **Display Availability** → **ON**.

### 4.4 Kiosk (area #4, noted here because it's a lending surface)
`Settings → Kiosk`
- With desk-only checkouts, the **Web Kiosk should stay OFF**. Revisit only if self-checkout policy changes.

### 4.5 Managers
`Managers`
- Add each front-desk employee as **Lender** (lending + patrons only, scoped to the Rental collection). +$2/mo or $24/yr per manager slot.
- Owner keeps the only login that can change lending settings.

### 4.6 Patrons
- New members: created automatically by Shopify Flow → `POST /patrons` (see membership spec). Barcode returned → Shopify customer metafield.
- Existing/legacy members, if any: `Lending → Patrons → CSV Import` (`first_name`, `last_name`, `email` minimum; UTF-8; duplicate email rows are skipped).
- Lapsed membership: Flow → `POST /patrons/{email}` with freeze. Staff can also toggle **Freeze** manually on the patron edit form.

---

## 5. Open items

| Item | Needed from | Notes |
|------|-------------|-------|
| Pre-due reminder day | store | 1–13 (must be < 14). Suggest **2**. |
| Past-due reminder days ×3 | store | Suggest **1 / 7 / 14**; blank any not wanted. |
| Freeze threshold | store | e.g. freeze at 14 days overdue; who unfreezes and when. |
| Staff-hold pickup window | store | days a staff-placed hold survives after the availability email before Release. |
| Renew on web | verify on account | Docs only show Renew in the mobile app. |
| Email template copy | store + dev | 5 templates: pre-due, past-due ×3, hold-available. |
| Patron Account Page on/off | area #5 | Read-only member view of own checkouts; keep self-renewal off. |

---

## 6. Front-desk procedure (draft — finalize after Renew is verified)

**Checkout**
1. `Lending → Lending`. Scan each copy's barcode (custom 8-digit) → items queue.
2. Scan the member's patron barcode (or search name/email).
3. Check the patron card: **active checkouts + queued items ≤ 3** (manual rule). Frozen patron → resolve before lending.
4. Adjust due date only if needed (click the date). Click **Checkout**.

**Return**
1. `Lending → Lending → Check In Mode`. Scan each returned copy. Confirm the title flashes below the input.

**"Tell me when it's back"**
1. `Lending → Lending`. Search the title → queue → select patron → **Place Hold**.
2. Libib emails them on check-in. Pull the copy to the hold shelf.
3. After the pickup window (§5) → `Lending → Holds → Release`.

**Overdue**
1. `Lending → Checkouts` — red rows. Libib sends past-due emails automatically.
2. Past the freeze threshold → `Lending → Patrons → edit → Freeze`.
