# Libib stage — acceptance (2026-09-26)

Plan: `docs/superpowers/plans/2026-09-25-catalog-pipeline-3-libib.md` (Task 11).
Snapshot: production audit run `2026-09-25-2`. Libib exports (Rental Library):
`exports/2026-09-26/barcodes_20260927_000214.csv` (item/barcode) and
`exports/2026-09-26/library_20260927_000207.csv` (collection), 2,996 items each.

## Smoke run first (old 9.20 exports, scratch copy of `_state.json`)

3,000 items · 2,436 in sync · 80 drift (79 copy barcodes) · 489 eligible · 484 orphans · 2 blocked.
Real `_state.json` untouched. Most orphans came from pre-9.23-reprint call numbers — why fresh exports mattered.

## `libib diff` on the fresh exports

```
libib items:  2996 (Rental Library)
in sync:      2676 rentals
drift:        29 rentals, 33 fields -> drift.csv
eligible:     302 rentals missing from Libib -> eligible.csv
incomplete:   242 rentals missing from Libib but not complete in Shopify
orphans:      291 Libib items (no rental / duplicates) -> orphans.csv
blocked:      2 rentals with a bad or shared barcode -> blocked.csv
```
State: 165 handles promoted to `done` and 2,522 `poster_confirmed` entries migrated to `poster_src` (first diff; a pre-change copy is `runs/2026-09-25-2/libib/state-before.json`, and the original is in git history). State after: 2,677 done · 300 needs-review · 3 imported.

### Bug found and fixed during acceptance

The first diff reported `dazed-and-confused-vhs-rental-sci-fi` tags as drift: Shopify's `VHS, comedy; sci-fi` vs Libib's `comedy, sci-fi, vhs`. Libib splits the genre metafield's `;` into separate tags; the comparison only split on commas (the old `libib_fields.py` had the same bug). Fixed (`normalized_tag_set` splits on `;`), test `test_multi_genre_semicolons_split_like_libib_does`; drift dropped from 30 to 29 rentals.

### Spot-checks — all real

Drift (Shopify is authoritative):
- `cinderella-vhs-rental-kids-family` — Libib description blank; tags `4k, kids-family` (Shopify: VHS).
- `rear-window-vhs-rental-thriller` — Libib description `Temporary!!`; tags `4k, thriller` (Shopify: VHS).
- `the-thin-blue-line-vhs-rental-documentary` — description blank; tags `blu-ray, documentary` (Shopify: VHS).
- `compromising-position-vhs-rental-drama` — Libib genre `drama`, Shopify genre `comedy`.
- `baywatch-the-movie-vhs-rental-action` — title case (`Baywatch the movie`) and no tags in Libib.
- 24 barcode drifts: copy barcode still Libib's auto-generated `2010000…` value instead of the call number (e.g. 35275770 ↔ 2010000001271).

Orphans:
- 276 carry old-style call numbers (`191-DVDVIL-001A`, `191-DVDTH2-001A`, …) that no Shopify product has — items to re-barcode or remove in Libib by hand.
- 14 are duplicate call numbers (e.g. `47927546` on both "Taken 2" and "No Contest").
- 1 is `08873722` "Frances", whose rental is blocked (shares its barcode with `swashbuckler-dvd-rental-action`).

## Dry runs

- `libib prepare --dry-run` — `batch-0017`: 200 of 302 eligible rentals; nothing written.
- `libib fix --drift --dry-run` — 29 items (24 barcode, plus tags/description/title fixes); nothing written.

## One-item browser fix (run with the user's approval)

`.venv-libib/bin/python -m catalog libib fix --drift --limit 1 --yes` (credentials from the gitignored `.env`).
First attempt stopped before any edit: the venv's Playwright had no Chromium for its version; installed with `.venv-libib/bin/python -m playwright install chromium`.

Result: `95306746,updated,skipped,barcode: ok | content: title/description/tags/poster already correct` — "A Fool and His Money"'s copy barcode set to its call number and verified after a fresh reload; state `imported` (the next diff promotes it to `done`).

No rule looked wrong apart from the tag-split bug above.

## Correction after the final review (2026-09-26)

The final review found that `needs-review` rentals were offered for import. On the real data **293 of the 302 "eligible" rentals were `needs-review`**, and 255 of them are already in Libib under their **pre-reprint call numbers** (the `191-…` "orphans" above are the same copies). The `batch-0017: 200 of 302` preview above was therefore mostly duplicates — it was only a dry run; nothing was imported.

Fixed (tests `test_needs_review_missing_rental_is_held_not_eligible`, `test_rental_found_under_its_old_call_number_is_matched_not_eligible`, `test_prepare_never_offers_a_needs_review_rental`):
- a rental missing by barcode is also looked up under the call number recorded in its state entry; a match is reported as `call_number` drift (manual fix), not as missing;
- `needs-review` rentals are never eligible and never prepared — they go to `held.csv` for a person;
- a tracked rental whose poster was never confirmed is poster drift (`fix --drift` uploads it); no poster drift when Shopify has no image;
- `--collection` naming a collection the export doesn't have now stops with the list of real collection names.

Re-run on the same exports:

```
in sync:      2511 rentals
drift:        440 rentals, 935 fields  (poster 411 · barcode 269 · call_number 246 · tags 5 · description 3 · title 1)
eligible:     9 rentals missing from Libib
incomplete:   242
orphans:      45 (31 no Shopify rental · 14 duplicate call numbers)
blocked:      2
held:         47 needs-review rentals not found in Libib
```

- `libib prepare --dry-run` → `batch-0017: 9 rentals (of 9 eligible)`.
- `libib fix --drift --dry-run` → 194 items the fixer can edit; **246 need a manual call-number fix** in Libib (their call number is still the old `191-…` value; the fixer finds items by call number, so it can't reach them).
