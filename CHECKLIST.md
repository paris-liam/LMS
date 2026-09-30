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

- [ ] **2. Swashbuckler and Frances share barcode `08873722`.**
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
  21 barcodes each sit on more than one product (42 products). Every
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

- [ ] **10. Finish the ~226 rentals that are incomplete in Shopify.**
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
    workflow first; if it can't log in, the scheduled Claude cloud session is
    the fallback.
  - Don't upload screenshots/exports as public artifacts.

---

## Notes

- 2026-09-30 — checklist created. Tag cleanup finished (see
  `claudedocs/2026-09-28-shopify-manual-fixes.md`).
