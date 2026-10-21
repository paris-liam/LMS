# Libib tags job — overview for the next session (2026-10-20)

Start here if you're building on the daily tag job. The design and its reasons are in `docs/superpowers/specs/2026-10-20-libib-tag-sync-design.md`. This page covers what was built, how it runs, the current state of production, and what to keep in mind when extending it.

## What it does

Libib has no item API, but customers see tags both on its public page (`libib.com/u/littlemoviestore`) and on the Shopify storefront. Once a day, `python3 -m catalog libib tags` sets four tags from Shopify data:

| Tag | Shopify | Libib | Rule |
|---|---|---|---|
| New arrival | `new-arrival` | `new arrival` | The **newest 50 titles**. A title is a movie + format, keyed by `normalize_title` + `title_year` + canonical Vendor format from `catalog/duplicates/match.py`. Its age is the earliest `createdAt` among its copies. Only products tagged `Rental` whose barcode matches exactly one Libib copy qualify. Every copy of a chosen title gets the tag, everything else loses it, and old titles rotate out as new ones arrive. |
| Community pick | `community-pick` | `community pick` | The product of every **Active** `community_pick` metaobject entry. In Libib, only that exact copy is tagged. A non-rental pick gets only the Shopify tag. |

The job adds or removes only these tags and never touches any other Libib tag or field. It writes Shopify with `tagsAdd`/`tagsRemove` and writes Libib through the item Edit form in a Playwright browser.

## How a run works

`catalog/libib/tags_command.py:run_tags_command`, in order:

1. **Load settings** from `catalog/libib/tag_settings.json` (`--settings` overrides the file).
2. **Read Shopify** (`tags_shopify.read_state`): every `Rental` product (title, vendor, `createdAt`, tags, barcodes), products tagged `new-arrival` or `community-pick`, and Community Pick entries. A GraphQL error, or **zero rentals**, stops the run before Libib is opened.
3. **Export Libib** (both CSVs, into a temp dir) and load the `Rental Library` items. An empty export stops the run.
4. **Compute the changes** with `tags.plan_tags(items, state, settings, now)`, which is pure and has no I/O. It returns `TagPlan(libib, shopify, unmatched, new_arrival_titles)`.
5. **Approve.** One `Plan` lists every change, and `catalog/core/plan.confirm` gates it. The options:
   - `--dry-run` prints the changes and an approval code.
   - `--approve <code>` makes exactly those changes.
   - `--unattended` is the daily run. It skips the prompt but refuses more than `max_changes` **Libib edits** (Shopify writes aren't counted), exiting 2 without changing anything.
6. **Write Shopify tags, then edit Libib** (`tag_editor.run_tag_editor` → `browser.set_item_tags`). Each Libib item is found by **copy-barcode search**: rental-sync items have no call number. The job then:
   - checks that the opened item's copy barcode really matches
   - reads the live tags and changes only ours (`tags.apply_tag_change`)
   - saves, reloads and checks the result
   - retries failed items 3 times
7. **Report.** It writes the report to `libib-tags/<timestamp>.csv` (gitignored, no barcode column). It exits 1 if anything errored.

## Settings (`catalog/libib/tag_settings.json`)

The user and client are still deciding how many titles, rotate versus batch drop-out, and how long titles stay, so these are meant to change:

| Key | Now | Meaning |
|---|---|---|
| `new_arrivals.count` | 50 | How many titles are new at once |
| `new_arrivals.max_age_days` | `null` | If set, a title stops being new after this many days, even if it's still in the top `count`. This makes a whole batch drop out together. |
| `max_changes` | 125 | The unattended limit on Libib edits. A full rotation is about 2 × `count`, so raise this together with `count`. |

`tag_settings.load_settings` validates the file. A bad value stops the run with a message naming the key.

## Files

| File | Role |
|---|---|
| `catalog/libib/tags.py` | Pure logic: `Product`, `ShopifyState`, `LibibChange`, `ShopifyChange(product_id, title, tag, action)`, `TagPlan`, `title_key`, `plan_tags`, `apply_tag_change` |
| `catalog/libib/tags_shopify.py` | GraphQL reads and writes, `store_from_env(store)` (client credentials grant) |
| `catalog/libib/tag_settings.py` + `.json` | Settings |
| `catalog/libib/tags_command.py` | CLI `libib tags`, `TagDeps` (injectable for tests), the approval and limit logic |
| `catalog/libib/tag_editor.py` | Browser loop and CSV report |
| `catalog/libib/browser.py` | `open_item_by_barcode` (`BARCODE_SEARCH = "{barcode}"`) and `set_item_tags`, alongside the older fixer steps |
| `catalog/libib/selftest.py` | Read-only health check of every Libib page step, including "search by barcode" (`--barcode` to try a specific copy) |
| `.github/workflows/libib-tags.yml` | Daily 12:00 UTC and on demand: `libib selftest --skip-import-matching`, then `libib tags --unattended --headless`. 2 h timeout, `concurrency: libib`. |
| Tests | `tests/catalog/test_libib_tags*.py`, `test_libib_tag_settings.py`, plus selftest tests in `test_libib_transfer.py`. Run `python3 -m unittest discover -s tests/catalog -p "test_*.py"` (975 passing at merge). |

## Hard constraints

- **The repo is public, and so are its Actions logs.** Never print a barcode or call number: they're the internal shelf serials. Items are identified by title + Libib item id. Tests check this (`test_output_never_contains_barcodes`, `TestSelftestFailureMessages`). Don't upload screenshots as artifacts.
- **No Libib CSV re-import.** It only creates items, so a re-import makes duplicates. Edit through the browser.
- **Both New Arrival Flows are OFF on production.** That's "New Arrival auto-tag" and the 7-day expiry sweep. The job owns the tag, so don't turn them back on. Hand edits to these four tags are undone the next day: change the settings instead.
- **Libib changes its UI without notice.** That happened twice in one week in September. The selftest runs first in every workflow run. When a selector breaks, fix it in `browser.py` and add it to `selftest.build_checks`.
- **Every write needs approval** (`Plan`/`confirm`, no `--yes`). The only exception is `--unattended`, which is capped.
- **Branch work happens in a git worktree** (`.worktrees/<name>`), never with `git checkout` in the main folder: other sessions share it.

## Running it

```bash
.venv-libib/bin/python -m catalog libib tags --dry-run --headless      # read-only preview + approval code
.venv-libib/bin/python -m catalog libib tags --approve <code> --headless
.venv-libib/bin/python -m catalog libib selftest --skip-import-matching
```

Secrets come from `.env` locally and from Actions secrets on GitHub: `LIBIB_EMAIL`, `LIBIB_PASSWORD`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`. The Shopify app needs `read_products`, `write_products` and `read_metaobjects`.

The local `gh` CLI's active account is the user's work account, which can't dispatch workflows on `paris-liam/LMS`. Use the personal login for single commands only: `GH_TOKEN=$(gh auth token --user paris-liam) gh workflow run libib-tags.yml -R paris-liam/LMS --ref main`.

## Production state (2026-10-20)

- **First real run:** 401 changes, 0 errors.
  - Libib: 50 items got `new arrival`, 4 got `community pick`.
  - Shopify: 341 products lost `new-arrival`, 6 gained `community-pick`.
- **Afterwards:** a dry run showed nothing to change. The first Actions run (`39534673002`) passed: selftest 10/10 and "Nothing to change", with no serials in the log.
- **Libib links survive tag edits:** Bottoms' `join_id` (170093045) was unchanged.
- **Revert kit (local only, gitignored):** `libib-tags/revert/` holds the pre-run Shopify snapshot (391 `new-arrival` products) and `shopify_tags.py revert [--apply]`. The Libib items tagged are listed in `libib-tags/2026-10-20-221433.csv`. A revert also means disabling the workflow and turning the Flows back on.

## Known limitations (deferred)

- Titles rarely include a year, so a same-name remake in the same format shares a title with the original and doesn't count as new.
- A product with a missing or invalid `createdAt` stops the run with a traceback (nothing is written).
- Products with a blank title or blank Vendor can group together (none exist today).
- A product whose barcodes match two different Libib items is skipped without a warning.
- After saving, the item is re-opened without re-checking it's the same item.
- The copy-barcode check uses a broad selector: a stray table row costs a 30 s wait, then fails safely.
- Plain barcode search could be ambiguous for legacy 8-digit items (`call:` search would avoid that).
- The approval code includes counts, so it can go stale between a dry run and the approve run. Just re-run the dry run.
- `community-pick` matching in Shopify is case-sensitive.
- The homepage rail also requires Category = Videos, which the job doesn't check, so the rail can show fewer than 50.
- The job matches one Shopify product per Libib copy. When rentals move to one product per movie + format (memory `inventory-per-movie-format`), matching must be redone.

## Extending it

- **A new tag or rule:** add the decision to `plan_tags`, keeping it pure and testing it in `test_libib_tags.py` with `plan(...)` and `state(...)` helpers. Emit `LibibChange` / `ShopifyChange` with the new tag, and add the Libib tag to `MANAGED_LIBIB_TAGS`, or the job won't remove it. The approval, report and limit logic work unchanged.
- **New Shopify data:** add fields to `PRODUCTS` / `COMMUNITY_PICKS` in `tags_shopify.py` and to `Product`, with defaults so existing tests keep working.
- **New Libib page steps:** put them in `browser.py`, never print serials, and add a read-only check to the selftest.
- **New settings:** extend `TagSettings`, `load_settings` validation and its tests, the JSON file, and the settings table in the spec, the README and `claudedocs/lms-admin-instructions.md` (New Arrivals → "Current rule").
- **Before touching production:** run a read-only dry run and review the change list with the user.
