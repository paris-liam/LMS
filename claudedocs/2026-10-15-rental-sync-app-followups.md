# Rental sync app — follow-ups after the build (2026-10-15)

Built from the plan `docs/superpowers/plans/2026-10-15-libib-shopify-sync-app.md`.

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
- A CSV template so the client can bulk-add rentals to Libib.
- Pushing later Libib edits to products that already exist (the app is create-only).
- Bringing the last ~50 legacy 8-digit rentals into this flow; deciding whether `libib sync`
  retires.
- Removing legacy rentals from POS (separate bulk action).
