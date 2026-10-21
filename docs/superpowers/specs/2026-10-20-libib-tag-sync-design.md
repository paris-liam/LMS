# Libib tag sync — design

**Date:** 2026-10-20
**Store:** production (`p0wkgv-wy.myshopify.com`) and the client's Libib account (`Rental Library`, published at `libib.com/u/littlemoviestore`).

## Intent

Customers see tags in two places: the Shopify homepage/shop-all page and the public Libib library page. Shopify already keeps `new-arrival` current through two Flows. Libib has no item API, so its tags are edited by hand and drift. The client asked for the Libib side to follow automatically, and for Community Picks to show up in Libib too.

Shopify is the source of truth. A daily job makes Libib (and the Shopify `community-pick` product tag) match it.

## Goals

1. **New arrivals: the job decides, in both Shopify and Libib (revised 2026-10-20).** The newest `count` *titles* (default **50**) are new arrivals. All their copies get `new-arrival` in Shopify and `new arrival` in Libib, and every other product and item loses the tag. As new titles come in, the oldest drop out. Details are in "New arrivals" below. This replaces the original goal of mirroring the two Flows.
2. **`community pick` in Libib.** A Libib item carries `community pick` exactly when one of its Shopify products is the `product` of an **Active** `community_pick` metaobject entry. Draft entries, and entries with no product, don't count.
3. **`community-pick` on Shopify products.** The same rule sets the Shopify product tag: products referenced by an Active Community Pick entry get `community-pick`, and every other product loses it. This replaces step 7 of "Client steps: adding a Community Pick" in `claudedocs/lms-admin-instructions.md`, which should be updated to say the tag is automatic (within a day).
4. Runs once a day without anyone doing anything. A failed or skipped run is fixed by the next one, because each run compares the full current state. It never replays a list of events.

## Non-goals

- ~~Changing the Shopify `new-arrival` Flows or the 7-day rule.~~ Reversed 2026-10-20: the job now owns the `new-arrival` tag, and the 7-day expiry sweep Flow is turned off at rollout (see "New arrivals").
- Triggering anything from the rental sync app (`lms-rental-sync.vercel.app`). A new rental gets its Libib tag on the next daily run. **Up to a day of lag is accepted.**
- A "7 days after the last sync" timer. This was considered and dropped: items in one sync can be added on different days, and Shopify already knows the right answer.
- A Shopify Flow for Community Picks. The daily job reads the metaobjects directly.
- Touching any other Libib tag (genre and format tags like `blu-ray, drama` must be left exactly as they are), or any other Libib field.
- Floor Sale or retail products. They aren't in Libib, so Community Picks that point at them only get the Shopify tag.

## Anti-goals (this would be a failure even if it ran)

- Changing more than the two tags on any Libib item, or wiping an item's other tags.
- Re-importing items through Libib CSV import. Import is create-only, so it would create duplicates (`claudedocs/2026-09-14-libib-bulk-upload-plan.md` (removed 2026-10-20; in git history)).
- Failing silently. If Libib's pages change and the job breaks, someone has to find out.
- Making a large number of edits because of a bad read. Example: Shopify returns zero `new-arrival` products because of an API error, and the job strips every tag.

## New arrivals (decided 2026-10-20)

- **Who's eligible:** a Shopify product tagged `Rental` whose variant barcode matches exactly one Libib copy. A product that isn't a rental, or isn't in Libib, never carries `new-arrival`; the job removes the tag if it finds it there.
- **Counted by title, not by copy.** The user asked for this so that 3 copies of one new movie take one slot, not 3. A title is a movie + format.
  - **My call:** the key is `(normalize_title(Title), title_year(Title), canonical format of Vendor)`, reusing `catalog/duplicates/match.py`. Edition words are ignored and the year is kept, so *Halloween (1978)* and *Halloween (2018)* stay apart. It's an exact key match, with no fuzzy matching.
- **Newest:** a title's arrival date is the earliest Shopify `createdAt` among its eligible copies. The newest `count` titles by that date are tagged, ties broken by key. A new copy of an older title doesn't make the title new. A new copy of a title already in the top `count` does get the tag, like its siblings. This covers the earlier "extra copies aren't new arrivals" requirement.
- **Settings, all adjustable** (the user and the client are still working out the specifics). They live in `catalog/libib/tag_settings.json`:

  | Setting | Now | Meaning |
  |---|---|---|
  | `new_arrivals.count` | `50` | how many titles are new arrivals at once |
  | `new_arrivals.max_age_days` | `null` (off) | optional: a title stops being new this many days after it arrived, even if it's still in the newest `count`. Setting it makes a whole batch drop out together. |
  | `max_changes` | `125` | the unattended run's limit on **Libib edits** (Shopify tag writes aren't counted: Flow 1 tags every upload, so trims grow with volume, and the next run corrects a bad one; final review 2026-10-20): about 2 × `count` (a full rotation out and in) plus room for Community Picks. Raise it with `count`. |

  Rotating versus dropping out together is covered by `count` plus `max_age_days`. A separate mode setting would only be added if the client wants something those can't express.
- **Flows (my call):** at rollout, turn off "New Arrival tag auto-expiry (daily sweep)". Otherwise it removes tags from titles that are still in the newest 50 after 7 days, and fights the job. "New Arrival auto-tag" can stay on: it tags a rental the moment it's created, the homepage gets it straight away, and the daily job trims to `count`.
- **Bad-read guard:** the run fails before writing anything if Shopify returns zero `Rental` products, because that's never real. With at most `count` titles tagged, a wrong run can mistag at most about `count` titles' copies, and the next run fixes them.
- **Runtime:** a full rotation is about 100 Libib edits at roughly 20–30 s each, so the workflow timeout is 2 hours.

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
- **Joining Shopify to Libib: one to one, by barcode.** Libib is one item per physical copy, like Shopify. The 2026-10-20 export has 3,962 items, each with `copies` = 1 and one barcode row, and 314 titles appear on more than one item. A Shopify rental's variant barcode equals exactly one Libib copy barcode, and the barcode export maps it to that item's `id`. **Decided: tags go only on the matched copy.** A Community Pick tags the one copy the client picked, not other copies of the same movie. For new arrivals, the copies of one title are grouped (revised 2026-10-20, see "New arrivals"). Community Picks have no sibling grouping.
- **Opening an item: by barcode, not call number.** Items created through the rental sync app have a `201…` barcode and an empty `call_number`. As of 2026-10-20 that's 3: The Curse, Bottoms, Nouvelle Vague (see `catalog/core/barcodes.py:is_new_flow_item`). They are exactly the items `new arrival` targets, and `browser.open_item` only searches `call:<call_number>`. **My call:** the job opens items by searching their barcode in the Libib web app. It requires exactly one hit, otherwise it reports the item and skips it. It never writes `call_number`. Before building, confirm on the live account that the admin search matches copy barcodes, both legacy 8-digit and `201…`. The public `/search` endpoint does (`claudedocs/2026-10-13-libib-item-links-join-id.md`). Then add that step to the selftest. If the admin search doesn't match barcodes, stop and bring it back. Writing `call_number` = barcode is an option but needs approval.
- **Future rework, out of scope:** the client is moving Shopify to one product per movie + format with an inventory count (memory `inventory-per-movie-format`). Rentals haven't moved yet. When they do, one Shopify product will no longer map to one Libib copy, and this join must be revisited at that point. **Requirement for that rework (decided 2026-10-20):** an additional copy of a movie + format that already exists must **not** get `new-arrival`, in Shopify or Libib. Only a movie + format new to the shop counts as a new arrival. The "Product created" Flow trigger probably gives this for free, since an extra copy becomes an inventory increase on the existing product rather than a new product. The rework should confirm that, and make sure the Libib side doesn't tag the new copy's item on its own. Since 2026-10-20 this already holds before the move, because new arrivals are counted by title (see "New arrivals").
- **Shopify access:** the job needs read products, write products (tags), and read metaobjects. The rental sync app already authenticates with `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` and has those scopes (`tools/rental-sync/README.md`).
- **Can't run on Vercel.** A Playwright run with 30s page waits across several items is too long and too fragile for a function.
- **The repo is public.** Credentials only go in Actions secrets or equivalent, never in files.

## Decided

- One daily reconciliation job covers all three goals.
- It runs against production and the client's Libib account.
- The rental sync app is not modified.

## Left to the builder

- **Where it runs.** My call: GitHub Actions on a daily schedule plus a manual "Run workflow" button, following a since-deleted selftest-on-Actions draft (now `.github/workflows/libib-tags.yml`) (secrets `LIBIB_EMAIL`, `LIBIB_PASSWORD`, plus the Shopify client credentials, and `concurrency: libib` so it never overlaps another Libib login). Use the existing scheduled cloud session if Actions turns out to be blocked.
- **Time of day.** It should run after the Flow daily expiry sweep, so check that Flow's scheduled time on production.
- **Selftest first.** My call: run the selftest steps at the start of each job and stop before any edit if they fail.
- **Safety limit.** My call: if a run wants to make more than `max_changes` Libib edits, it does nothing and fails loudly. This started at 25, which the dry run showed is too low for the client's upload volume (20–180 rentals per upload day). It's now set in the settings file, at 125. A manual run with `--approve` covers a first backfill or a deliberate large change.
- **First run.** Today no Libib item carries either tag (checked in the 2026-10-20 export). The first run trims Shopify's ~391 `new-arrival` products down to the newest 50 titles and tags those in Libib. That's well over the limit, so it's a manual `--approve` run.
- **Failure notice.** My call: GitHub's default email on a failed workflow run is enough. A run that hits items it can't match (no Libib item for a barcode, or several) still succeeds, but lists them in its log/summary.
- **Dry run.** A `--dry-run` that prints the planned adds and removes without opening the Edit form, to use while building and before the first real run.
- **Code location.** It's a `catalog` subcommand alongside the other `libib` commands, with the comparison logic pure and unit-tested apart from Playwright, following how `transfer.py` keeps the checks separate from `browser.py`.
- **Worth checking, optional:** whether the public Libib page can sort by date added. If it can, that's a no-code complement to the `new arrival` tag. It doesn't change this design.
- **Worth checking:** whether editing an item's tags keeps its `join_id` (`claudedocs/2026-10-13-libib-item-links-join-id.md` expected yes, unverified). If it doesn't, stored Libib links would break.
