# Membership System — Remaining Tasks

Status snapshot for the Shopify-native membership build (dev store `lms-sandbox-lutsfahz.myshopify.com`, branch `membership-setup`). Full plan and spec:

- Design spec: `docs/superpowers/specs/2026-09-13-membership-system-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-13-membership-system-implementation.md`

## Done

Tasks 1–7, 10, 12 from the implementation plan, plus three ad-hoc additions requested mid-build:

- Stale leftover product archived; customer metafield definitions created (`custom.libib_barcode`, `custom.birthday`)
- Membership product template built (terms checkbox + birthday capture, both as line-item properties)
- Membership Terms page created (`/pages/membership-terms` — **draft placeholder body, not final legal text**)
- "Little Movie Club Membership" product created, $160.00, published to Online Store + POS
- Shopify Subscriptions app installed, Yearly selling plan configured, cancellation policy (Shopify's automatic default), POS smart-grid tile, renewal-reminder email branded
- 10% automatic discount for the `Active Member` customer segment
- "Join the Club" CTA button added to the membership marketing page
- Single-button checkout: dynamic checkout ("Buy it now") hidden on this product (bypassed the terms checkbox), Add to Cart now redirects straight to `/checkout`
- Terms link opens as an in-page dialog instead of same-tab navigation, with a new-tab fallback if JS fails
- Birthday field made optional; its character counter hidden
- POS staff terms-acceptance checklist written (`docs/pos-membership-terms-checklist.md`)
- Stale theme-ID references in `CLAUDE.md` corrected

## Remaining

### 1. Task 9 — Email blast capability (on you, ready now)

No dependencies. Steps:

1. Confirm Shopify Email is installed (Admin → Apps).
2. Create a test campaign (Admin → Marketing → Create campaign → Shopify Email), audience = the `Active Member` segment.
3. Confirm the campaign's audience count matches the number of customers tagged `Active Member`, then discard the draft without sending.

### 2. Task 8 — Membership Flow automation (on you, blocked on Libib credentials)

**Prerequisite:** the Libib API key and API user value (Libib account → Account → API settings). Not yet retrieved as of this doc.

Once you have them, this is a manual build in Shopify Flow's visual editor (trigger: Subscription contract created → tag customer `Active Member` → call Libib `POST /patrons` → write `custom.libib_barcode` + `custom.birthday` metafields, with a retry-then-tag-for-manual-follow-up path on Libib failure). Full step-by-step is in the implementation plan, Task 8 — I'll walk through it with you when you're ready.

**Note:** since the birthday field is now optional (see above), Task 8's metafield-write step needs a check to skip writing `custom.birthday` when the line-item property is blank, rather than overwriting a real value with nothing on a repeat purchase.

### 3. Task 11 — End-to-end testing (depends on Task 8)

Online test purchase, POS test purchase (needs a real POS device signed into the dev store), an induced Libib-failure test, pause/cancel test via the customer account portal, and cleanup of test data. Can't start until Task 8 is built.

## Known open items (not blockers, just flagged)

- `/pages/membership-terms` still has placeholder legal text marked "DRAFT — pending final legal review" — needs real copy before this goes live to real customers.
- Three early commits (`27d6127`, `6f8be7a`, `191b29e`) have a cosmetic attribution mismatch (say "Claude Haiku 4.5" instead of the session convention "Claude Sonnet 5"). Left alone per this repo's no-history-rewrite-without-consent rule — let me know if you want them corrected via rebase.
