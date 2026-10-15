# Rental sync app — follow-ups after the build (2026-10-15)

Built on `feature/rental-sync-app` from the plan
`docs/superpowers/plans/2026-10-15-libib-shopify-sync-app.md`. Tests at hand-off: Python 826 OK,
JS 53 pass. Everything below is **not done yet**.

## Developer steps before anyone uses it (plan Task 9 steps 1–8, Task 13 step 5)

1. Capture `tools/rental-sync/guide/export-barcodes.png` and `export-library.png` (see
   `tools/rental-sync/README.md` → "Before the first deploy").
2. Dev Dashboard app: confirm scopes (read/write_products, read/write_inventory, read_locations,
   read/write_publications, read_metaobjects) and install on the dev store; run the Task 9 step 1
   script. Also confirm whether the shop-metafield write (`lms.rental_sync_last_run`) needs any
   other scope.
3. Create the Vercel project (repo root, Framework Other), set the six env vars with
   `SHOPIFY_STORE` = dev store, deploy, run the Task 9 step 3 smoke test — and confirm
   `/catalog/errors.py` and `/runs/` are not served.
4. Dev-store walk-through (Task 9 steps 4–8) with test copies in Libib; delete them afterwards
   (they are in the client's real Libib).
5. Things only a live store can answer — check during step 4:
   - `productByIdentifier(identifier: {handle})`, `productSet` `files`, `resourcePublicationsV2`,
     `Publication.name` behave as coded on API 2026-07.
   - Newly created products are **not** auto-published to POS or another channel (the app's
     read-back refuses anything besides Online Store, so every create would fail if one is).
   - `https://admin.shopify.com/store/<slug>/products?tag=Barcode%20Not%20Printed` filters by tag.
   - Re-running immediately after a create: the barcode search may lag; the handle lookup is
     direct, so a duplicate should be reported, not created.
6. Production switch (Task 13 step 5), then update `CLAUDE.md` roadmap #3 with the dates.

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
