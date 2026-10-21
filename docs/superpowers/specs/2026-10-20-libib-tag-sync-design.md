# Libib tag sync — design

**Date:** 2026-10-20
**Store:** production (`p0wkgv-wy.myshopify.com`) and the client's Libib account (`Rental Library`, published at `libib.com/u/littlemoviestore`).

## Intent

Customers see tags in two places: the Shopify homepage/shop-all page and the public Libib library page. Shopify already keeps `new-arrival` current through two Flows. Libib has no item API, so its tags are edited by hand and drift. The client asked for the Libib side to follow automatically, and for Community Picks to show up in Libib too.

Shopify is the source of truth. A daily job makes Libib (and the Shopify `community-pick` product tag) match it.

## Goals

1. **`new arrival` in Libib.** A Libib item carries the tag `new arrival` exactly when at least one of its Shopify rental products currently carries `new-arrival`. The job does not decide what is new: the existing Flows ("New Arrival auto-tag" and the 7-day "auto-expiry" sweep) stay as they are, and the job mirrors their result.
2. **`community pick` in Libib.** A Libib item carries `community pick` exactly when one of its Shopify products is the `product` of an **Active** `community_pick` metaobject entry. Draft entries, and entries with no product, don't count.
3. **`community-pick` on Shopify products.** The same rule sets the Shopify product tag: products referenced by an Active Community Pick entry get `community-pick`, and every other product loses it. This replaces step 7 of "Client steps: adding a Community Pick" in `claudedocs/lms-admin-instructions.md`, which should be updated to say the tag is automatic (within a day).
4. Runs once a day without anyone doing anything. A failed or skipped run is fixed by the next one, because each run compares the full current state. It never replays a list of events.

## Non-goals

- Changing the Shopify `new-arrival` Flows or the 7-day rule.
- Triggering anything from the rental sync app (`lms-rental-sync.vercel.app`). A new rental gets its Libib tag on the next daily run. **Up to a day of lag is accepted.**
- A "7 days after the last sync" timer. This was considered and dropped: items in one sync can be added on different days, and Shopify already knows the right answer.
- A Shopify Flow for Community Picks. The daily job reads the metaobjects directly.
- Touching any other Libib tag (genre and format tags like `blu-ray, drama` must be left exactly as they are), or any other Libib field.
- Floor Sale or retail products. They aren't in Libib, so Community Picks that point at them only get the Shopify tag.

## Anti-goals (this would be a failure even if it ran)

- Changing more than the two tags on any Libib item, or wiping an item's other tags.
- Re-importing items through Libib CSV import. Import is create-only, so it would create duplicates (`claudedocs/2026-09-14-libib-bulk-upload-plan.md`).
- Failing silently. If Libib's pages change and the job breaks, someone has to find out.
- Making a large number of edits because of a bad read. Example: Shopify returns zero `new-arrival` products because of an API error, and the job strips every tag.

## Tag wording

| Where | Tag |
|---|---|
| Shopify (unchanged) | `new-arrival`, `community-pick` |
| Libib (new) | `new arrival`, `community pick` (lowercase, spaced, matching existing Libib tags like `blu-ray, drama`) |

**My call (Liam approved the guess):** use the lowercase spaced form in Libib.

## Constraints and known facts

- **No Libib item API.** Item edits go through the Libib web app with Playwright. `catalog/libib/browser.py` already does this: login with retry for Libib's "One moment, please" holding page, forcing the `Rental Library` scope, opening an item by `call:<call_number>` search, editing the Tags field in the Edit form (`input.tags-autocomplete[name='tags']`, inside a collapsed section), and reload-to-verify. The new job reuses those steps. `fix_content` currently writes title, description, tags and poster together, so the job needs a tags-only path that reads the current tags, adds or removes only our two, and verifies after reload.
- **Libib changes its UI without notice.** That happened twice in the week of 2026-09-21. `python3 -m catalog libib selftest` (read-only) exists to catch this and already runs daily as a scheduled Claude Code cloud session.
- **Reading Libib state:** the existing export step (`catalog/libib/transfer.py` / `exports.py`) downloads the collection export (item `id`, `tags`, `call_number`, …) and the barcode export (item `id` → copy `barcode`).
- **Joining Shopify to Libib: one to one, by barcode.** Libib is one item per physical copy, like Shopify. The 2026-10-20 export has 3,962 items, each with `copies` = 1 and one barcode row, and 314 titles appear on more than one item. A Shopify rental's variant barcode equals exactly one Libib copy barcode, and the barcode export maps it to that item's `id`. **Decided: tags go only on the matched copy.** A Community Pick tags the one copy the client picked, not other copies of the same movie. `new arrival` likewise mirrors Shopify product by product. No sibling grouping.
- **Opening an item: by barcode, not call number.** Items created through the rental sync app have a `201…` barcode and an empty `call_number`. As of 2026-10-20 that's 3: The Curse, Bottoms, Nouvelle Vague (see `catalog/core/barcodes.py:is_new_flow_item`). They are exactly the items `new arrival` targets, and `browser.open_item` only searches `call:<call_number>`. **My call:** the job opens items by searching their barcode in the Libib web app. It requires exactly one hit, otherwise it reports the item and skips it. It never writes `call_number`. Before building, confirm on the live account that the admin search matches copy barcodes, both legacy 8-digit and `201…`. The public `/search` endpoint does (`claudedocs/2026-10-13-libib-item-links-join-id.md`). Then add that step to the selftest. If the admin search doesn't match barcodes, stop and bring it back. Writing `call_number` = barcode is an option but needs approval.
- **Future rework, out of scope:** the client is moving Shopify to one product per movie + format with an inventory count (memory `inventory-per-movie-format`). Rentals haven't moved yet. When they do, one Shopify product will no longer map to one Libib copy, and this join must be revisited at that point.
- **Shopify access:** the job needs read products, write products (tags), and read metaobjects. The rental sync app already authenticates with `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` and has those scopes (`tools/rental-sync/README.md`).
- **Can't run on Vercel.** A Playwright run with 30s page waits across several items is too long and too fragile for a function.
- **The repo is public.** Credentials only go in Actions secrets or equivalent, never in files.

## Decided

- One daily reconciliation job covers all three goals.
- It runs against production and the client's Libib account.
- The rental sync app is not modified.

## Left to the builder

- **Where it runs.** My call: GitHub Actions on a daily schedule plus a manual "Run workflow" button, following the draft in `claudedocs/2026-09-29-libib-selftest-github-actions.md` (secrets `LIBIB_EMAIL`, `LIBIB_PASSWORD`, plus the Shopify client credentials, and `concurrency: libib` so it never overlaps another Libib login). Use the existing scheduled cloud session if Actions turns out to be blocked.
- **Time of day.** It should run after the Flow daily expiry sweep, so check that Flow's scheduled time on production.
- **Selftest first.** My call: run the selftest steps at the start of each job and stop before any edit if they fail.
- **Safety limit.** My call: if a run wants to change more than a set number of items (start around 25), it does nothing and fails loudly. A manual run with an override flag lets you do a first backfill or a deliberate large change.
- **First run.** Today no Libib item carries either tag (checked in the 2026-10-20 export). The first run adds `new arrival` to whatever is currently new, which is likely more than the safety limit, so it's a manual run with the override flag.
- **Failure notice.** My call: GitHub's default email on a failed workflow run is enough. A run that hits items it can't match (no Libib item for a barcode, or several) still succeeds, but lists them in its log/summary.
- **Dry run.** A `--dry-run` that prints the planned adds and removes without opening the Edit form, to use while building and before the first real run.
- **Code location.** It's a `catalog` subcommand alongside the other `libib` commands, with the comparison logic pure and unit-tested apart from Playwright, following how `transfer.py` keeps the checks separate from `browser.py`.
- **Worth checking, optional:** whether the public Libib page can sort by date added. If it can, that's a no-code complement to the `new arrival` tag. It doesn't change this design.
- **Worth checking:** whether editing an item's tags keeps its `join_id` (`claudedocs/2026-10-13-libib-item-links-join-id.md` expected yes, unverified). If it doesn't, stored Libib links would break.
