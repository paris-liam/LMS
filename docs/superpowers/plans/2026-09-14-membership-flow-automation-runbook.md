# Membership Flow Automation Runbook (Task 8)

Manual Shopify Flow build for the membership signup automation. This is Task 8 from `docs/superpowers/plans/2026-09-13-membership-system-implementation.md`, extracted as its own document since it's a manual admin-UI task (no Admin API mutation can build a Flow workflow), and to make it easy to repeat for production later — see `2026-09-14-membership-production-rollout-runbook.md` for the full repeat sequence.

**Where:** Admin → Apps → Flow, on the target store.

**Prerequisite:** the Libib API key and API user value (Libib account → Account → API settings). Enter them directly into Flow's HTTP request step in the browser — do not paste them into chat/Claude or commit them anywhere in this repo.

**Store-specific values below are for `lms-sandbox-lutsfahz.myshopify.com` (dev).** When repeating this for production, substitute production's own product ID (see the rollout runbook).

---

## Step 1 — Create workflow

Flow → Create workflow. Name it `Membership signup → Libib + tag`.

## Step 2 — Trigger

`Subscription contract created`.

## Step 3 — Condition: scope to the membership product

`Subscription contract > Line items > Product > ID` is `gid://shopify/Product/8263005667390` (dev store's "Little Movie Club Membership" product — this future-proofs the workflow in case another subscription product is ever added, so it won't misfire and create a Libib patron for it).

## Step 4 — Tag the customer

Action: `Add customer tag` → tag `Active Member`, customer = the contract's customer.

## Step 5 — Libib HTTP request

Action: `Send HTTP request`
- Method: `POST`
- URL: `https://api.libib.com/patrons`
- Headers:
  - `x-api-key`: (your Libib API key)
  - `x-api-user`: (your Libib API user value)
  - `Content-Type`: `application/json`
- Body (JSON, using Flow's data reference picker to insert these — the bracketed names are what you'll insert, not literal text):
```json
{
  "first_name": "{{customer first name}}",
  "last_name": "{{customer last name}}",
  "email": "{{customer email}}"
}
```

## Step 6 — Branch on response status

Add a `Condition` step: HTTP response status code is between `200` and `299`.

**Success path:**
1. `Set customer metafield` — namespace `custom`, key `libib_barcode`, value = the response's `barcode` field.
2. A second `Condition`: is the `Birthday (MM/DD/YYYY)` line-item property non-blank?
   - **Since the birthday field on the product is optional** (changed after the original spec — see `MEMBERSHIP-REMAINING-TASKS.md`), this check matters: don't overwrite a real birthday with blank on a repeat purchase.
   - **If non-blank:** `Set customer metafield` — namespace `custom`, key `birthday`, value = that line-item property.
   - **If blank:** skip — do nothing.

**Failure path (first attempt failed):**
1. `Wait` — 30 seconds.
2. Repeat the same `Send HTTP request` from Step 5 (duplicate the step).
3. `Condition` on the retry's response status, same 200–299 check.
   - **If true:** same two-step success path above (barcode metafield, then the birthday non-blank check).
   - **If false (final failure):** `Add customer tag` — tag `Libib Sync Failed` — so staff can create the patron manually in Libib and remove this tag once resolved. Do **not** add any action that blocks, cancels, or refunds the subscription contract — the sale stands regardless of Libib's availability.

## Step 7 — Turn it on

Toggle the workflow from Draft to On.

## Step 8 — Test it

Trigger a real test membership purchase (or Flow's own test-run feature if available). Verify:
- The test customer gets tagged `Active Member`.
- A patron actually appears in the real Libib account (**no Libib sandbox exists** — delete this test patron from Libib afterward).
- `custom.libib_barcode` is populated on the test customer.
- `custom.birthday` is populated **only if** you filled in a birthday on the test purchase.

Verification query:
```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { customer(id: "<CUSTOMER_ID>") { tags metafield(namespace: "custom", key: "libib_barcode") { value } birthdayField: metafield(namespace: "custom", key: "birthday") { value } } }'
```

## Step 9 — Induced-failure test (optional but recommended)

Temporarily point the HTTP request URL at an invalid endpoint (e.g. `https://api.libib.com/does-not-exist`), run a test purchase, and confirm:
- The sale completes normally (contract created, no block/refund).
- After the retry, the customer ends up tagged `Libib Sync Failed`.
- No Libib patron was created (nothing to clean up in Libib for this one).

Revert the URL to `https://api.libib.com/patrons` afterward and re-verify Step 8's test still succeeds.

---

No git commit applies to this task — Flow workflows live in Shopify Admin, not the repo.
