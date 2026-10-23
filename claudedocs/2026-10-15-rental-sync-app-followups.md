# Rental sync app — follow-ups after the build (2026-10-15)

Built from the plan `docs/superpowers/plans/2026-10-15-libib-shopify-sync-app.md` (removed 2026-10-20; in git history).

## Status: live on production (2026-10-16)

All developer steps are done (plan Task 9 steps 1–8 and Task 13 step 5): guide screenshots
captured, app scopes checked and installed, Vercel project created (repo root, Framework Other),
smoke-tested, verified end-to-end on the dev store, then switched to production
(`SHOPIFY_STORE=p0wkgv-wy.myshopify.com`) at `https://lms-rental-sync.vercel.app`.

Found during deployment and fixed in `374fee0`: Vercel's Python builder detects `/api`
functions by reading the source for a top-level `class handler`, so the entry files must use a
class statement, not `handler = make_handler(...)` (a test now pins this). `/catalog/**` is served
as static files — expected, since the repo is public.

What's left is optional: the minor issues and later phases below.

## Duplicates and copies (built 2026-10-21, not live)

Spec `docs/superpowers/specs/2026-10-21-rental-sync-duplicates-design.md`, plan
`docs/superpowers/plans/2026-10-21-rental-sync-duplicates.md`. **Go-live waits on the separate
duplicate-cleanup project** (dedupe production and the real Libib first). Tested on the dev store only.

### Dev-store test (2026-10-22/23, plan Task 10)

Preview `https://rental-sync-git-libib-sync-duplicates-liam-paris-projects.vercel.app` (Vercel
project `rental-sync`), pointed at the dev store through a separate Dev Dashboard app ("LMS Rental
Sync (dev)", the developer's own account; the production app belongs to the client's account and
can't be installed on the dev store). Preview-only `SHOPIFY_STORE` / `SHOPIFY_CLIENT_ID` /
`SHOPIFY_CLIENT_SECRET`; Production untouched.

Every scenario passed, each product checked in admin (variants, barcodes, Copy values, qty 1,
untaxed, Online Store only, tags) and the storefront PDP showing no Copy option:

| Scenario | Test title | Result |
|---|---|---|
| New movie | GODFATHER: CODA | one product, one variant |
| New item, two copies | The Godfather Part II | one product, Copy 1 / Copy 2 |
| New copy of an item whose old copy is 8-digit | Fences (`79859194` + new `2010000000045`) | added to the existing Fences product; old variant became Copy 1 (`productOptionsCreate` `LEAVE_AS_IS` works) |
| Second Libib item, different title | Mario Puzo's THE GODFATHER, Coda: The Death of Michael Corleone | flagged against GODFATHER: CODA; Skip this run created nothing |
| Not a duplicate | same item | created as its own product |
| Re-run | same exports | nothing new |

Retail Barcode Labels prints a single variant, and the label shows the genre, not `Copy N`
(plan Task 1, recorded in the spec). Not checked: the results page's print list and browser
console errors (the Playwright walk-through was skipped).

Two changes came out of the test, both in the spec:
- **Legacy siblings (decision 3 revised):** a new copy matches the old 8-digit copies of its Libib
  item, because the client keeps those barcodes. A mixed product's old copy stays first, so the
  legacy tools still see a legacy product. The old copy keeps its own settings (Fences' is still
  taxable and on POS/Shop); the cleanup project should normalize those.
- **Contained titles:** a Libib item is also flagged when every word of the shorter title (2+
  words) is in the longer one. It flags sequels too (about 4 in 5 of the extra flags on the
  2026-10-19 export), which the client clears with Not a duplicate.

Test data left on the dev store and in the test Libib account: the products above.
`vercel curl` also created a deployment protection bypass token for the `rental-sync` project
(revocable under Settings → Deployment Protection).

## Known minor issues (reviewed, deliberately left)

- `prepare.py` `_header`: a wrong file whose first line is over 128 KB raises a raw `csv.Error`
  (shows as a setup error).
- A new-flow copy given a Call # by mistake is silently out of scope (counted in `not_new_flow`,
  not shown on the page). Consider listing it as set aside ("clear Call #").
- Cached Shopify token isn't dropped on 401/403/ACCESS_DENIED — redeploy after changing scopes
  (documented in the README). App-not-installed / bad-secret errors show "Shopify didn't respond"
  rather than the setup message.
- A barcode hit that reaches `create` (race only) is verified with the full tag set, so a product
  whose tags were edited in admin or that is rented out (qty 0) would show "needs attention".
- "It may have been created anyway" also appears on productSet validation errors.
- On a setup stop the progress bar reads "N of N done".
- Front end: poster-failed products appear in both the "poster didn't load" and "Created" groups;
  image-load error note isn't kept in state; empty store name if `status` failed; `admin_url`
  href not prefix-checked; accessibility (dialog role, focus on step change, aria-current, live
  region, ✓ contrast); login error says "wrong password" for any non-OK response; the 401 retry
  is unbounded (relies on login resolving only on success); duplicate-barcode rows share one
  checkbox.
- Misspelling rule skips tags under 4 characters; alias hits like `4K UHD` / `laser` are always
  set aside (worth a line in the client guide).
- `_finish` accepts negative/float counts; poster `alt` and item fields have no length cap
  (authenticated only).
- `create`: a title with no letters/digits gives a handle starting with `-`.
- `audit/rules.py`: `row.get("Handle", "")` would fail on a `None` handle (loaders give `""`).
- Test gaps: zero locations, two Online Store channels, `shop_from_env`, several set-aside reasons
  at once, Library-box wrong-file message, exact 5 MB boundary, `diff()` with call == barcode.
- Commit trailers on agent-made commits name the model each agent ran on.

## Later phases (from the spec, not started)

- Auto-export from Libib through a GitHub Action (needs the spike: does Libib accept a login from
  GitHub's runners?), replacing the manual upload.
- A CSV template so the client can bulk-add rentals to Libib — **drafted 2026-10-18** as a Google
  Sheet in `catalog/client_sheet/template/libib-rental/` (mirror `catalog/client_sheet/libib_rental.py`);
  live sheet built and seam-tested 2026-10-19; still needs the developer test import in its guide.
- Pushing later Libib edits to products that already exist (the app is create-only).
- Bringing the last ~50 legacy 8-digit rentals into this flow; deciding whether `libib sync`
  retires.
- Removing legacy rentals from POS (separate bulk action).
