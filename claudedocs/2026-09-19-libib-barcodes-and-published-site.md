# Libib barcodes & published site — decisions & configuration

**Date:** 2026-09-19
**Scope:** Areas #4 (Barcodes; Kiosk ruled out) and #5 (Published site) of the Libib Pro setup. Lending is in `claudedocs/2026-09-19-libib-lending-setup.md`.
**Sources:** support.libib.com — `libib/website/barcodes`, `getting-started/quickstart-barcodes`, `libib/website/publish`, `libib/website/publish/published-site`, `kiosk/website`. Fetched 2026-09-19.
**Related:** `docs/superpowers/specs/2026-09-17-libib-migration-master-design.md` (barcode = call_number migration), memory `barcode-driven-upload-model` (Shopify Retail Barcode Labels app prints the shelf labels).

---

## 1. Decisions (confirmed 2026-09-19)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Published-site role | **Availability lookup page**, public, linked from the Shopify PDP. **May later replace the movie PDP entirely** — see §4.3. |
| 2 | Alias | **Proposed `littlemoviestore`** — pending confirmation. |
| 3 | Patron barcodes / member cards | **None for now** — staff look members up by name/email at the desk. Printed QR cards via Libib's generator is a possible later addition. |
| 4 | Patron Account Page | **ON** (members can log in and see their own checkouts/history). Self-renewal sub-toggle **OFF**. |
| 5 | Light/Dark mode | **Light**. |
| 6 | Kiosk | **OFF** — desk-only checkouts make it unused. |
| 7 | Item labels | **Existing Shopify shelf labels are the scan target.** No Libib label printing. |

---

## 2. Barcodes — facts

- Libib auto-assigns every **copy** a 13-digit SKU: prefix `201` + 9-digit counter + Mod-10 checksum (e.g. `2010000000014`). Every **patron** gets the same with prefix `202`.
- Custom barcodes may be overridden (lock icon on the field); accepted format is 5–15 digits, numeric only. Docs warn the value "must be in the correct format for Libib to guarantee recognition."
- Exports: `Settings → Collections → Export Barcodes` (items), `Settings → Lending → Export Patrons` (patrons). Numbers only — no symbol rendered.
- Printing options: Libib's built-in **QR** generator (subset of Avery templates; 25-page sets; margin adjustment; print a test page first), Avery's own generator from the export, or pre-printed PDFs (QR 1–9000, Avery 5160).
- Date filter on the label generator refers to when a *copy* was added/updated, not the item.

## 3. Barcodes — how LMS uses them

### 3.1 Items
- The shelf label (Shopify Retail Barcode Labels app, 1D Code 128) carries the 8-digit `variant.barcode`. The migration writes that same number into the Libib copy `barcode` field (`formatting-scripts/libib_barcode_update.py`), so **the label already on the case is what gets scanned** at the desk.
- Libib's own `201…` SKU is discarded per copy once overwritten. Do not print Libib item labels.
- Duplicate 8-digit values across distinct products (13 pairs as of 2026-09-19, tracked in the migration's `duplicate-barcode.csv`) must be relabelled on one side, otherwise a scan is ambiguous.

**Verification owed on the live account (not yet done):**
1. `Lending → Lending` → scan an 8-digit shelf label → the correct copy queues in one hit (no ambiguity prompt).
2. `Check In Mode` → scan the same label → checks in without a copy-selection prompt.
3. Scan a shelf label whose product had a duplicate barcode → confirm the failure mode (wrong copy vs. prompt).

### 3.2 Patrons
- Flow → `POST /patrons` returns the `202…` barcode; it's stored as a Shopify customer metafield (membership spec) but **not printed**.
- Desk lookup: search by name / email / patron ID on the Lending page.
- If member cards are added later: `Barcodes → Patrons → Generate QR` on an Avery template. **The desk scanner must then read 2D (QR)** — shelf labels are 1D; confirm the store's scanner supports both before buying label stock.

### 3.3 Scanner
- Any USB HID scanner that reads Code 128 works for items today. 2D capability only matters if patron QR cards are introduced.

---

## 4. Published site

### 4.1 Facts
- URL: `https://www.libib.com/u/[alias]`. Alias is set in `Publish → Site`; the kiosk URL (`/kiosk/[alias]`) and patron login hang off the same alias.
- Default (free) view is a cover grid. Pro unlocks search, item expansion, tags, metadata display, logo, theme colour, social links, website link, holds, self-checkout, availability, patron login, account page, announcement, contact email.
- **No custom domain and no embed/iframe are documented.** Theme control = logo, one colour, light/dark, social links.
- Each Admin/Manager/Lender has their **own** `/u/[alias]` public site showing only their collections — leave those unpublished.
- Collections are published individually (`Select Collections to Publish`).

### 4.2 Configuration steps

`Publish → Site`
1. **Public Site URL / alias** → `littlemoviestore` (pending confirmation).
2. **Select Collections to Publish** → the Rental collection only.
3. **Detail Level** → `cover` (poster grid; matches the Shopify catalogue feel). Revisit to `list` if search-first browsing is preferred.

`Publish → Display Options`

| Option | Setting | Why |
|---|---|---|
| Display item type | OFF | Everything is a movie |
| Display Search Bar | **ON** | Needed for tags to be searchable too |
| Display Tags | **ON** | Genre lives in tags |
| Display Notes | OFF | Internal |
| Display Availability | **ON** | The whole point of the page — shows copies / out per title |
| Display Date Added | ON | Cheap "new arrivals" signal |
| Display Additional Fields | OFF | All-or-nothing; nothing customer-facing there today |
| Display ISBN/UPC | **OFF** | Field holds internal serials on force-imported rows |
| Display Call # | **OFF** | Call number **is** the 8-digit serial — never surface serials |
| Display LCC / LCCN / DDC / OCLC / Lexile | OFF | Book-only |

`Publish → Theme` (owner sets)
4. **Upload Logo** → 400×400 square brand mark.
5. **Website Link** → `https://littlemoviestore.com`.
6. **Color Theme** → brick `#973123`.
7. **Light/Dark Mode** → Light.
8. **Instagram Link** → `instagram.com/littlemoviestore`. Others blank.

`Publish → Settings`
9. **Require Patron Login** → OFF (public availability page).
10. **Allow Patron Holds** → **OFF**.
11. **Allow Patron Self-checkouts** → **OFF**.
12. **Patron Account Page** → **ON**; sub-options: self-renewals OFF, account editing ON (lets members fix their own email/notification addresses).
13. **Your Email Notification for Patron Holds** → n/a while holds are off.
14. **Contact Email** → store inbox.

`Publish → Announcement`
15. Subject + message: how renting works (members only, in-store at the desk, 14-day loans, "ask staff to hold a title for you"). Dismissible.

`Settings → Kiosk`
16. **Web Kiosk** → leave OFF.

### 4.3 Role 1 vs. replacing the PDP

**Role 1 (adopted now):** Shopify stays the catalogue; each movie PDP gets a "Check availability" link to the Libib site — ideally a search deep-link on the title (verify the URL pattern on the live site once published; the docs don't document query params). Libib is the only source of live availability (no API), so this is the cheapest way to get it onto the storefront.

**If Libib replaces the movie PDP later**, note before deciding:
- No custom domain / embed → the customer leaves littlemoviestore.com for libib.com.
- Theme is logo + one colour; no control over layout, typography, or the design system.
- Poster art, description and genre must be complete in Libib (the migration's `reverify-posters` step becomes customer-facing quality, not back-office).
- The read-only Shopify PDP (`templates/product.json`, `sections/main-movie.liquid`) would become redundant for the Rental subset; Floor Sale products still need a Shopify PDP (they aren't in Libib).
- Shopify collections/search & discovery would then only serve Floor Sale + retail.

---

## 5. Open items

| Item | Needed from | Notes |
|---|---|---|
| Alias | store | `littlemoviestore` proposed |
| 8-digit label scan verification (§3.1) | dev, on live account | Blocks the front-desk procedure |
| Duplicate-barcode relabelling | store ops | 13 pairs; list in migration `duplicate-barcode.csv` |
| Scanner model / 2D support | store | Only matters if patron cards are added |
| PDP "Check availability" link pattern | dev | Confirm whether `/u/[alias]` supports a search query param |
| Logo asset 400×400 | store / design | |
| Announcement copy | store | |
| PDP replacement decision | store | Revisit after the availability page has been live a while |
