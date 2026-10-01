# Back-in-stock notifications & Libib holds — feasibility

_Researched 2026-10-01. Libib and Shopify capabilities below come from their public docs (sources at the end); nothing has been tested against the LMS Libib account or production store yet. Items marked **unverified** need a hands-on check before committing._

## The question

Can we email a customer when an out-of-stock rental becomes available again — built in Shopify, Libib, or both — given that rentals happen at the counter (checked out in Libib) and customers currently can't hold or rent anything themselves?

Two directions are covered:

- **Part 1 — "Notify me" with no holds** (the current policy). Shopify-side, fed by Libib availability.
- **Part 2 — Let customers place holds in Libib** (a policy change to pitch to the client). Libib does the notifying natively.

---

## Part 1 — "Notify me" without holds

### What each system can and can't do

**Libib**

- The REST API (Pro) covers only **accounts, managers, and patrons**. There is no items, checkouts, or loans endpoint — availability can't be read through the API.
- Neither export `catalog/libib` already drives (barcode export + collection export) includes checkout state. The `status` column there is Libib's personal reading status, not loan status.
- The Lending section has a **Checkouts** page and **Reports**. Getting availability out means scraping one of them with the existing Playwright tooling. **Unverified:** whether either offers a downloadable export.

**Shopify**

- Flow's **"Send internal email"** action is for staff only: the recipient can't be a variable, and Shopify's docs direct customer email to Messaging marketing automations instead.
  - ⚠️ This means Section C5 of the old Supercycle-era runbook (`docs/superpowers/plans/2026-07-15-availability-filter-and-backinstock-waitlist-admin-runbook.md`) — "Flow sends one email per waitlisted address" — would not have worked as written.
- **Messaging marketing automations** only reach customers who opted in to marketing. A community report says product details passed in from Flow arrive empty in the template (**unverified**).
- Flow has **no trigger for a storefront contact form** (found 2026-07-16). Storing waitlist signups natively means **Shopify Forms → metaobject entry → Flow "Metaobject entry created"**. It was never confirmed that the form can carry which product was clicked.
- Flow **does** have inventory triggers ("Product variant inventory quantity changed" and a back-in-stock trigger). So if Shopify inventory reflects Libib, anything keyed on inventory just works.

### Recommended architecture

1. **Daily Libib → Shopify inventory sync (the only custom build).**
   - Scrape the checked-out copies from Libib.
   - Set each rental's Shopify inventory to `0` if it's out and `1` if it's in.
   - Side benefit: an accurate "in stock" indicator on the product page, which is worth having even without notifications.
2. **A back-in-stock app for the button and the emails** (e.g. Klaviyo, Amp, STOQ, Appikon).
   - These fire on Shopify inventory going 0 → 1.
   - They store many subscribers per product, remove duplicates, handle marketing consent, and send the email.
   - This also answers the "many users click the button" problem.

### Why not fully native Shopify

A native build needs four pieces, none of them verified:

1. Shopify Forms → metaobject to store subscribers.
2. A Flow inventory trigger.
3. A lookup of everyone waiting on that product.
4. A way to send the email: either a Messaging automation (opted-in customers only, product details possibly blank) or an HTTP request to an outside email service (SendGrid, etc. — another account to run).

All of that rebuilds what a low-cost app already does.

### Risks

- **Scraper reliability.** It runs against a site that requires a login. It breaks if Libib changes its page or the session expires. It also needs a machine that runs every day (a local cron job or the cloud setup `catalog/` already supports).
- **Latency.** With a daily sync, an email can be up to about a day late. That's probably acceptable for rentals.
- **One product per physical copy.** A title with three copies is three Shopify products. A customer who clicks "notify me" on copy A isn't told when copy B returns. Apps work per product, so the waitlist has to work per *title*. That means consolidating copies into one product (inventory = number of copies) or building something custom.
- **No holds means a race.** Everyone on the list is emailed and whoever reaches the counter first gets the copy. The email has to say "a copy is back", never "we're holding one for you".

### To verify before committing

1. Can Libib's Checkouts page or Reports export a list of checked-out items?
2. Are copies still one Shopify product each on production? If yes, solve the per-title problem first.

---

## Part 2 — Letting customers place holds in Libib

Libib Pro already has a full lending system with patron-facing holds, including the "email me when it's back" behaviour. If the client is willing to let customers reserve titles, most of Part 1's custom work goes away. Below is how each piece works.

### Plans

| Plan | Price | Lending / holds | Patrons | Published site | API |
|------|-------|-----------------|---------|----------------|-----|
| Basic | Free | ✗ | ✗ | Read-only publish | ✗ |
| **Pro** | $9/mo or $99/yr (+$2/mo per extra manager) | ✓ | Unlimited | Interactive (holds, self-checkout, patron login) | Accounts, managers, patrons |
| Ultimate | $900/yr | ✓ | Unlimited | Same as Pro, plus the **Patron App** | Same as Pro |

Everything below needs **Pro**. Ultimate adds the mobile Patron App (holds, checkouts, and renewals in Libib's app via a QR code), SSO, and priority support — it isn't needed here. **Unverified:** which plan the LMS account is on now. If staff already check items out in Libib, it's Pro or higher.

### Patrons (customer accounts in Libib)

- A **patron** is someone who borrows: they have items checked out to them, place holds, and log in to the published site. There's no limit on the number of patrons.
- **How patrons are created:**
  - A manager adds them one at a time.
  - A manager imports a CSV (minimum columns: `first_name`, `last_name`).
  - Through the **REST API** (`POST /patrons`).
  - Per Libib's patron quickstart, someone whose email isn't in the system "can request that your library administrators create an account". There's **no documented open self-sign-up**.
- **Passwords:** a manager can set one at creation, or the patron clicks **"Need Password?"** on the login dialog and Libib emails temporary credentials.
- **Freeze:** a manager can freeze a patron. A frozen patron can't self-checkout or place holds (staff can still check items out to them), and their history is kept. Useful for lapsed members.
- **Patron history** page: a single patron's current and past checkouts and holds, with activity stats.
- **API:** `GET /patrons`, `GET/POST/DELETE /patrons/{id}` (id = barcode or email), `PATCH` to restore a deleted patron within 30 days. Patrons are the only borrowing-related data the API exposes.

> **Integration hook:** Shopify membership signup could create the Libib patron automatically. A Flow "Send HTTP request" on the membership order/subscription would call `POST /patrons`, so members never wait for a manual account. **Unverified:** Libib API auth details, and whether Flow can send the required headers.

### The published library (the patron-facing site)

- Lives at `libib.com/u/<alias>`. It's Libib's own site, separate from the Shopify storefront.
  - **Unverified:** custom domain or embedding options. The docs don't mention either, so assume a link-out from the Shopify product page.
- Settings that matter here (exact names):
  - **"Require Patron Login"** — only logged-in patrons can view the site.
  - **"Display Availability"** — shows checkout status as a fraction (e.g. 1/2 available).
  - **"Display Search Bar"** — patrons can search collections.
  - **"Allow Patron Holds"** — patrons can place holds and are emailed when the item becomes available.
  - **"Allow Patron Self-checkouts"** — patrons can check out available items themselves. **LMS would leave this OFF** so checkout stays at the counter.
  - **"Patron Account Page"** — patrons see active checkouts/holds and their history, and can edit their profile, password, and notification preferences. There are optional sub-toggles for **self-renewals** and **profile editing**.
  - **"Your Email Notification for Patron Holds"** — staff are emailed whenever a patron places a hold.
  - **Announcement** — a message visitors can dismiss.
- Collections can be marked **"Disallow Checkouts"** (reference only). That's useful if Floor Sale stock is ever published alongside rentals.

### How a hold works, end to end

1. **Patron places a hold.** On the published site they open the title and click **"Add Hold"**. They can queue several titles, then click **"Complete"**. Alternatively, staff place the hold for them from the Lending page (e.g. over the phone or at the counter).
2. **Staff are told** if "Your Email Notification for Patron Holds" is on. The hold appears on the **Holds** list (item, patron, collection, date placed).
3. **While the copy is out:** nothing happens until it's checked back in.
4. **On check-in:** the copy becomes available *for the patron who holds it*. **Patron Hold Emails** sends an "item is available" email. Libib batches these through the day and sends them only once the item is "available and unencumbered by other holds".
5. **The copy is locked to the hold.** Per Libib: "When an item is placed on hold, and there are no additional copies to lend out, you will not be able to check out the item without first releasing the hold — or overriding the hold by making the item available." Staff can't accidentally rent it to a walk-in.
6. **Pickup:** the patron comes in and staff check the copy out to them, which fulfils the hold. Or staff release the hold if it's no longer wanted.
7. **Expiry:** holds expire automatically after **4 years**. There is **no documented pickup window** (e.g. "collect within 3 days or it goes to the next person"). Staff would have to release stale holds by hand.

**Unverified (test on the real account before pitching hard):**

- Whether **several patrons can hold the same title**, and if so whether they're served first-come-first-served. "Unencumbered by other holds" suggests a queue exists, but the order isn't documented.
- Whether a hold attaches to the **title** (any copy) or to a **specific copy**. This interacts with how LMS models copies in Libib (`catalog/libib/columns.py` defaults `copies` to `1`, which suggests one Libib item per physical copy). If each copy is its own Libib item, a customer would have to pick a copy, much like the Shopify per-copy problem in Part 1.
- What the hold email looks like, and whether it can be branded. Custom templates are documented for due-date reminders, not hold emails.

### Other lending capabilities

- **Checkout / check-in (staff):** scan or search by title, creator, ISBN/UPC, or custom barcode → items go into a queue → pick the patron → **Checkout**. Checkout and due dates can be edited per checkout. **Check-in mode** is a scan box.
- **Lending Due Date:** the default loan length in days. Changing it only affects new checkouts.
- **Patron Email Reminder:** one "coming due" email 1–14 days before the due date, plus up to **three** past-due emails 1–14 days after. Custom templates are supported.
- **Self-renewals:** optional, from the Patron Account Page.
- **Kiosk (web and app):** in-store self-checkout by barcode scanner at `libib.com/kiosk/<alias>`, with three password modes (Low / High / Absolute trust). This is **not needed** for LMS, where staff do checkout.
- **Checkouts page / reports:** sorted by due date, overdue items shown in red, up to 2 years of history.
- **Export Patrons:** patron list as CSV.
- **Not documented anywhere:** fines/fees, per-patron borrowing limits, patron groups/types. Assume Libib has none of these — fees and limits stay on the Shopify membership side.

### What the pitch amounts to

**What the client gets**

- Customers reserve a title online and are emailed automatically when it's back.
- The copy is locked for them, so there's no race and no "it was gone by the time I arrived".
- Coming-due and overdue reminder emails come free, sent to the actual borrower.
- Almost no custom code. The Part 1 scraper and back-in-stock app aren't needed for holds. The optional extra is auto-creating Libib patrons from Shopify memberships through the API.

**What it costs or changes**

- **Policy change:** customers can now reserve. The client needs to decide who can hold (members only, enforced by creating patrons only for members and freezing lapsed ones), how many holds each customer gets (no documented limit setting, so this is honor system plus freezing), and how long a held copy waits (manual release).
- **Two customer accounts:** a Shopify account (membership and purchases) and a Libib patron login (holds). This is the biggest friction point. Auto-creating patrons and linking out from each product page softens it but doesn't remove it.
- **A second, Libib-branded website** for browsing and holding, unless custom domain or embedding turns out to exist.
- Staff have to keep an eye on the Holds list and release abandoned holds.

**Hybrid option:** keep Part 1's sync so the Shopify product page shows accurate availability, and have its "Reserve" button link to the title on the Libib published site. Shopify stays the browsing site and Libib handles holds and notifications.

---

## Sources

- [Libib — Lending](https://support.libib.com/libib/website/lending.html)
- [Libib — Publish (published library settings)](https://support.libib.com/libib/website/publish.html)
- [Libib — Settings (lending due date, reminders, hold emails, kiosk password mode)](https://support.libib.com/libib/website/settings.html)
- [Libib — Holds](https://support.libib.com/support/holds/)
- [Libib — Lending Settings](https://support.libib.com/support/lending-settings/)
- [Libib — Quickstart for Patrons](https://support.libib.com/getting-started/quickstart-for-patrons.html)
- [Libib — Kiosk Website](https://support.libib.com/kiosk/website.html)
- [Libib — REST API: Patrons](https://support.libib.com/rest-api/patrons.html)
- [Libib — Pricing](https://www.libib.com/pricing)
- [Libib Blog — Patron freeze](https://blog.libib.com/2023/02/28/patron-freeze-prevent-self-checkoutsholds/)
- [Libib — FAQs](https://support.libib.com/faqs.html)
- [Shopify — Send internal email action](https://help.shopify.com/en/manual/shopify-flow/reference/actions/send-email)
- [Shopify Community — Back in Stock trigger with Flow](https://community.shopify.com/t/back-in-stock-trigger-with-flow/592157)
- [STOQ — Back in stock with Shopify Flow](https://help.stoqapp.com/back-in-stock/back-in-stock-with-shopify-flow/)
- [Amp Back in Stock (Shopify App Store)](https://apps.shopify.com/back-in-stock)
- [Omnisend — Shopify back-in-stock email flow](https://www.omnisend.com/blog/shopify-back-in-stock-email/)
