# LMS catalogue checklist

Shared to-do list for the Little Movie Store catalogue (Shopify production +
Libib). Started 2026-09-30. Tick items off here and add a dated note when one
is finished, so either of us — or a fresh Claude session — can pick up where
we left off.

**Before starting any item (for a new Claude session):** read `CLAUDE.md`,
`catalog/README.md` and `claudedocs/2026-09-28-shopify-manual-fixes.md`.
Standing rules:

- Production (`p0wkgv-wy.myshopify.com`) is the working store.
- Nothing edits Shopify or Libib without first listing **every** change and
  getting approval (`--dry-run` prints an approval code; `--approve CODE` runs
  it). There is no `--yes`.
- Only one session in Libib at a time.
- The repo is public: never commit a password, token or key.

---

## Questions for the client

- [ ] **1. The 29 products that are neither Rental nor Floor Sale.**
  All are DVD / Blu-Ray priced $0, so they are probably rentals, but nobody
  tagged them. Every product needs exactly one type tag (`Rental` or
  `Floor Sale`) or it is left out of the rental catalogue, the Libib sync and
  the storefront collections. They still carry `Issue_Rental_Or_Sale`. 26 of
  them also still have old `191-…` call numbers as their barcode (tagged
  `Issue_Needs_New_Barcode`), so if they are rentals each needs a new 8-digit
  label, the new barcode in Shopify, and then a Libib sync. The other 3 (For
  the Boys, Legend of Zorro, Paradise Now) already have good barcodes.
  *Ask:* rental or floor sale, for all 29? *Then:* set the tag, remove
  `Issue_Rental_Or_Sale`; for the 26, get new labels printed and update
  barcodes. The list is the `manual` bucket of the latest audit
  (`runs/<latest>/`).

- [x] **2. Swashbuckler and Frances share barcode `08873722`.** *(Done
  2026-09-30 except printing the label — see the note of that date.)*
  Two different products carry the same barcode, so the Libib sync blocks
  both (it can't tell which Libib item belongs to which). Frances was entered
  first (2026-07-24) and the Libib item under `08873722` is Frances;
  Swashbuckler (`swashbuckler-dvd-rental-action`, Rental, created 2026-09-25)
  most likely got the number by mistake.
  *Ask:* what does the physical label on the Swashbuckler case say? If it
  reads `08873722`, it needs a new label; enter the new number on
  Swashbuckler in Shopify and the next `libib sync` adds it.

- [ ] **3. Floor Sale items at $0.**
  Earth Girls Are Easy and The Call are for sale but have no price (tagged
  `Issue_No_Price`). *Ask:* what should they cost? *Then:* set the price,
  remove the tag.

## Client upload sheet

- [ ] **4. Add the two new genres to the client's live Google Sheet.**
  Special Interest and Anime were added as genres on 2026-09-28/29 (in
  Shopify, the pipeline and the repo's template), but the client's live sheet
  is a separate copy. Without this, a product he uploads as Anime or Special
  Interest gets no genre.
  *Do:* in the sheet's `mappings` tab add the rows
  `Special Interest,special-interest` and `Anime,anime`, and add both options
  to the Genre dropdown(s). Reference copy:
  `catalog/client_sheet/template/genre-mappings.csv`.

- [ ] **5. Review the sheet, and have it also produce a Libib import CSV.**
  Today the sheet only produces the Shopify import (tab 2,
  `catalog/client_sheet/template/import-tab-formula.txt`), and rentals reach
  Libib later through `libib sync`. The idea is a second output tab so a new
  rental can go into Libib at the same time.
  *Things to know first:* Libib's CSV import only fills title, description,
  tags, price, copies and call number (`EXPECTED_MAPPINGS` in
  `catalog/libib/transfer.py`) — the barcode, poster and genre are set
  afterwards in the browser by `libib fix`. A rental is only ready for Libib
  once it has title, poster, barcode, description, genre, tags and format
  (`catalog/libib/fields.py`), and most uploads don't have a description or
  poster until the TMDB fill. So the sheet's Libib tab would give a partial
  item; decide whether that's worth it versus letting `libib sync` pick new
  rentals up (possibly on a schedule, item 12). Also review the sheet against
  the spec (`docs/superpowers/specs/2026-09-09-client-upload-template-rebuild-design.md`)
  and check a real filled export with `python3 -m catalog check-upload <csv>`.

## Catalogue clean-up

- [ ] **6. First pass through the picker queue before it goes to the client.**
  The audit sends products it can't fill automatically (no confident TMDB
  match, several same-titled films, etc.) to the hosted picker, where a
  person chooses the right film. About 943 are queued (2026-09-29). Many
  are obvious (one clear match, a well-known title), so Claude can propose
  picks for those and leave only the genuinely unclear ones for the client.
  *Do:* build the queue from the latest audit, sort into "obvious" /
  "needs the client", show the obvious picks for approval, apply them
  (`python3 -m catalog apply`), then `picker push` the rest.

- [ ] **7. Investigate the shared barcodes.**
  20 barcodes each sit on more than one product (40 products; was 21 / 42
  before Swashbuckler's fix on 2026-09-30). Every
  physical copy should have its own barcode, so each is either a real
  duplicate listing (same copy entered twice → merge/delete one), a second
  copy that was given the first copy's number (→ new label), or a typo.
  Rentals in this state are **blocked** from the Libib sync.
  *Do:* list them from the latest snapshot with titles, types, created dates
  and stock, sort into those three kinds, and bring back a proposal (the
  client may need to check labels).

- [ ] **8. Investigate the floor-sale quantities.**
  124 Floor Sale products have a quantity of 2 or more. The rule is **one
  product per physical copy**, so either these are several copies that
  should be split into separate products, or the stock number is wrong.
  *Do:* list them with quantity and created date, check whether they came
  from one upload batch (likely a sheet default), and propose a fix
  (correct the quantity, or split into copies).

- [ ] **9. Investigate the draft products.**
  94 products are drafts (not visible on the storefront). Some may be
  unfinished uploads, some duplicates, some deliberately hidden.
  *Do:* list them with type, barcode, price, created date and what's missing,
  group them, and propose publish / fix / delete for each group.

- [ ] **10. Finish the rentals that are incomplete in Shopify** (118 on
  2026-09-30 after the batch-0021/0022 sync; was ~226).
  These are rentals not yet in Libib that are missing one of the fields Libib
  needs (title, poster, barcode, description, genre, tags, format — see
  `catalog/libib/fields.py`), so `libib sync` skips them. Walkthrough and
  per-field breakdown started 2026-09-30 — see the dated note below once
  it's filled in.

## Setup

- [ ] **11. Narrow the Shopify app's permissions.**
  The Dev Dashboard app whose client ID/secret the pipeline uses was given
  ~150 scopes. If those credentials ever leaked, they could do far more than
  the pipeline needs. The pipeline only needs `read_products`,
  `write_products`, `read_inventory`, `read_metaobjects` (plus
  `write_inventory` and `write_metaobjects` only if we keep automating
  inventory changes / new genres).
  *Do:* in the Shopify Dev Dashboard, edit the app's scopes, release a new
  version, re-install it on production, then run `python3 -m catalog audit`
  and one small approved write to confirm nothing broke.

- [ ] **12. GitHub Actions that run the audit and the Libib sync on a schedule.**
  So the catalogue stays in step without anyone remembering to run it.
  Starting point: `claudedocs/2026-09-29-libib-selftest-github-actions.md`
  (the selftest workflow is written out there, not yet added).
  *Design questions:*
  - Secrets needed: `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, the TMDB
    key, `LIBIB_EMAIL`, `LIBIB_PASSWORD` (Actions secrets only — public repo).
  - Approval: the rule is that nothing changes without a person seeing the
    full list. So the scheduled job should run `audit` and
    `libib sync --dry-run`, and post the change list + approval code (e.g.
    as an issue or job summary); a second, manually triggered workflow takes
    the code and runs `libib sync --approve CODE`.
  - State: `libib-sync/_state.json` and the run folders are committed files,
    so the job has to commit its changes back (needs `contents: write`) and
    must never run at the same time as a person's session (`concurrency`).
  - Libib may challenge a login from GitHub's servers — try the selftest
    workflow first. Don't count on the Claude cloud session as the fallback:
    on 2026-09-30 it was far slower in Libib than a home connection (see the
    note of that date). The other fallback is an always-on machine on a home
    or shop connection.
  - Don't upload screenshots/exports as public artifacts.

## Picker

- [x] **13. Restructure the review picker: rentals in one group, floor sales
  in groups of 100.** (Planned 2026-09-30; can run in a cloud session — it
  doesn't touch Libib. Needs `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`,
  `TMDB_API_KEY`.) Do this before item 6, so item 6 works on the new groups.
  **Why:** the picker is split by *why* a product needs a person
  (`ambiguous-queue` 945, `unmatched-queue` 178), not by type. Rentals matter
  most, because they're held out of Libib until they're filled in, so the
  client should see them first and on their own.
  **Target:** one `rentals` group, then `floor-sale-01`, `floor-sale-02`, …
  of up to 100 each, plus an `untyped` group only if a flagged product is
  tagged neither `Rental` nor `Floor Sale` (don't guess its type). Group ids
  must match `BATCH_ID_PATTERN` (`catalog/picker/queues.py`, kept in sync
  with `tools/review-picker/api/_github.js`).
  **State on 2026-09-30:** no picks saved yet in either current queue (both
  `data/*.json` empty on `main`), so nothing the client did is lost.
  1,123 cards are queued. Against that day's audit, 900 are still flagged,
  **223 are no longer flagged** (probably fixed since), and **64 are flagged
  but were never queued** (they need TMDB candidates).
  **Steps:**
  1. `git pull`. Make sure no other session is using the picker or `apply`
     (both push to `main`).
  2. Run a full audit with TMDB: `python3 -m catalog audit` (no
     `--skip-tmdb`). In the cloud the TMDB cache starts empty, so it's slower.
  3. Change the code, with tests in `tests/catalog/`:
     - `catalog/picker/push.py`: file new products by type from the snapshot's
       `Tags`, not by `Kind`. Rentals go to `rentals`; floor sales go to the
       newest `floor-sale-NN` until it holds 100, then a new one starts.
     - Each card still shows its own reason (ambiguous / unmatched), so
       mixed groups need no page change. Check one of each kind renders.
  4. One-time regroup (a script under `scripts/`, with dry-run + approval
     like every other command):
     - Rebuild the groups from the new audit's picker products. Reuse each
       card's stored TMDB candidates from the old
       `data/*.products.json`, and fetch candidates only for the new ones.
     - **Drop cards no longer flagged** (default; confirm the list with the
       user in the dry run).
     - **Update `data/_handle-index.json` in the same step:** every moved
       handle's `batch` must become its new group id. `apply`
       (`catalog/apply/merge.py`) only accepts a pick from the group the index
       names; if the index still says `ambiguous-queue`, the client's picks
       are skipped as "superseded".
     - Write each group's `data/<id>.products.json`, empty `data/<id>.json`,
       `<id>/index.html` and its `batches.json` entry (reuse
       `append_to_queue` / `update_manifest` in `catalog/picker/queues.py`).
     - Take `ambiguous-queue`, `unmatched-queue` and the six old 8/31 and 9/2
       groups off the client's launcher, but **keep their `data/*.json`
       files**. `apply` still reads old picks.
  5. `picker push --dry-run`, then `--approve CODE`, to publish (pushes to
     `main`; Vercel deploys it). Open the hosted launcher and check the
     groups and counts.
  6. Update `catalog/README.md` (Stage 2 text still says the
     `ambiguous-queue` / `unmatched-queue` split) and add a dated note below
     with the final group counts.

---

## Notes

- 2026-09-30 — checklist created. Tag cleanup finished (see
  `claudedocs/2026-09-28-shopify-manual-fixes.md`).
- 2026-09-30 — item 10 breakdown (audit `runs/2026-09-30`): now **200**
  incomplete rentals (was ~226), all active and all with a valid 8-digit
  barcode. What they lack is only TMDB content: poster 191, description 173,
  genre metafield 20. Why they're stuck:
  - 20 have audit **auto-fixes** waiting (genre metafield from the genre tag,
    category, some poster/description) → `python3 -m catalog apply`; 12 of
    them are then complete.
  - ~131 are **ambiguous** (TMDB has several same-titled films) → picker
    choice; overlaps item 6.
  - ~57 have **no TMDB match** (box sets, compilations, obscure or oddly
    titled discs) → corrected search title, or a hand-written description +
    cover photo.
  Once a product has all fields, the next `libib sync` imports it.
- 2026-09-30 — **Libib sync batch-0020 DONE (finished locally).** 46 of 46
  fixed, 0 need review (commit `89530a1`). Every barcode, title, description
  and tag was already right; the run uploaded the 46 posters. A fresh export +
  `libib diff` then showed **3142 of 3143 Libib rentals in sync, 0 drift, 0
  eligible missing**; the 46 were promoted to `done`. Left over from that diff:
  1 orphan (`orphans.csv`), 2 blocked (item 2's shared barcode), 200
  incomplete (item 10).
  - The first local run failed every item with "image file not found":
    `ready.csv` stored the cloud box's absolute poster paths
    (`/home/user/LMS/...`). Fixed in `32ba525`: `libib fix` now uses the
    same-named poster beside `ready.csv`, so a batch prepared on one machine
    can be fixed on another. That failed run saved nothing in Libib.
  - The approval code locally was `29db6af269`, not `16bb2b0dc3`. The 184
    changes were the same, so expect the code to differ between machines.
- 2026-09-30 — **Libib sync batches 0021 + 0022 DONE (local), item 2 done.**
  - batch-0021: 15 drifted posters fixed, 82 new rentals imported and filled.
    The first `sync --approve` dropped mid-run (`ERR_INTERNET_DISCONNECTED` at
    the import login, before anything was uploaded); it was finished by hand
    with `libib import batch-0021` then `libib fix batch-0021`.
  - Item 2: not a typo. Both variant IDs end in `08873722`, so Retail Barcode
    Labels' last-8-digits rule gave both copies the same number. Frances keeps
    it; Swashbuckler got the next reprint number **`90000494`** (sequence was
    at `90000493`; lower gaps skipped in case a deleted product's label is
    still printed) and the `Reprint_These_Barcodes` tag, on production.
    batch-0022 imported it into Libib. **Still to do: print its label.**
  - Fresh audit `runs/2026-09-30-3` + diff: **3,226 of 3,226 Libib rentals in
    sync, 0 drift, 0 eligible, 0 orphans, 0 blocked, 0 held**; 118 incomplete
    (item 10). Manual bucket 31 = items 1 + 3.
  - For item 1: the next new barcode is `90000495`. A barcode collision like
    item 2 can happen again whenever two variant IDs share their last 8
    digits; the `blocked` line of `libib diff` is where it shows up.
  - Fixed: `export` / `import` / `selftest` run with the system `python3` now
    say to use `.venv-libib/bin/python` instead of a raw
    `ModuleNotFoundError`, and the "Next:" hint after `import` names the venv
    (`02d1cdb`).
- 2026-09-30 — **Cloud vs local speed (evidence for item 12).** Locally (home
  connection) `libib selftest` passed all steps: login 5.3s, search 5.1s,
  edit form 4.8s, export 4.3s. The batch-0020 fix ran at about 17s per item
  with no timeouts or retries. The cloud session hit repeated 30s timeouts
  waiting for the library search box on the same items. So Libib itself is
  fine; the likely causes are the cloud sandbox's HTTPS proxy, or Libib
  slowing traffic from data-center addresses (not yet confirmed). To tell them
  apart, run `libib selftest` in a cloud session and compare its step times
  with the local ones above. Options that don't depend on a personal laptop:
  an always-on machine on a home or shop connection, a rented server, or
  GitHub Actions. Check any new machine with `check-login` + `selftest` before
  giving it a real batch.
- 2026-09-30 — (history) **Libib sync batch-0020 IN PROGRESS — finish it locally.**
  46 new rentals (list: `libib-sync/batch-0020/ready.csv`; the full approved
  change list was 184 field changes, approval code `16bb2b0dc3`). All 46 are
  **imported** into Libib (each exactly once, verified). The browser fix step
  (barcode, title, description, tags, poster) only partly landed because Libib
  was very slow from the cloud all day: roughly 10–15 fully fixed, the rest
  missing some fields. The cloud run was stopped mid-batch on purpose; that's
  safe — every fix is idempotent (already-correct values are skipped) and the
  next run redoes the whole batch. `libib-sync/_state.json` shows 3 `imported`
  + 43 `needs-review` for this batch; the next fix run updates them.
  Code hardened today for slow Libib (all pushed): login waits out Libib's
  "One moment, please…" page and retries; page waits 8s → 30s; a failed item
  is retried twice.
  **To finish on a local machine:**
  1. `git pull origin main`
  2. Playwright for Python: `pip install playwright` then
     `python3 -m playwright install chromium` (or the `.venv-libib` from
     `catalog/README.md`).
  3. Environment: `LIBIB_EMAIL`, `LIBIB_PASSWORD`, `SHOPIFY_CLIENT_ID`,
     `SHOPIFY_CLIENT_SECRET` (never commit them).
  4. `python3 -m catalog audit --skip-tmdb` — `runs/` is not in git, and the
     fix step needs an audit run's snapshot to record results.
  5. `python3 -m catalog libib fix batch-0020 --dry-run` → the approval code
     should still be `16bb2b0dc3` (same 184 changes). If it is, run
     `python3 -m catalog libib fix batch-0020 --approve 16bb2b0dc3` (leave off
     `--headless` to watch it). Anything still `error` in
     `libib-sync/batch-0020/ready.sync-report.csv`: just run it again.
  6. Confirm: `python3 -m catalog libib sync --dry-run` (exports + diffs, changes
     nothing) should show **0 drift** for these 46. It may also list other
     rentals that became complete since — those are a new, separate approval.
  7. Commit `libib-sync/` and `exports/` and push.
  Don't run it while a cloud session is in Libib (one Libib session at a time).
- 2026-09-30 — **Item 13 DONE (picker regrouped and published to `main`).** Full
  audit with TMDB, then `scripts/regroup-picker.py` (approval `1e20df4511`):
  `rentals` 213, `floor-sale-01`..`07` 100 each, `floor-sale-08` 38 = 951 cards
  (51 new with fresh TMDB candidates). 223 no-longer-flagged cards dropped. No
  `untyped` group was needed. The old queues and six 8/31 + 9/2 groups are
  `"hidden": true` in `batches.json` (off the launcher; `apply` still reads their
  picks). `picker push` now files new products by type. Item 6 can work on these groups.
