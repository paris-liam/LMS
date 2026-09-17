# Libib migration master — fresh-start design (2026-09-17)

Supersedes the `libib-batches/` + `libib_batch.py` registry-based system from
2026-09-16. That system's own bookkeeping drifted from reality twice in one
session (batch-0001's barcode step falsely reported 25/25 success when 2
hadn't persisted; the registry still said batch-0001 was "uploaded" after
the user wiped Libib). This design replaces "trust our own state" with
"always re-derive from the two real exports."

## Goal

Get every Shopify rental-library product into Libib, with the Shopify
product's barcode and the Libib item's physical barcode matching exactly,
in 8-digit format. Track progress as a set of flat CSVs that always reflect
current reality, not an internal status flag that can drift.

## Working directory

`Libib_Migration_Master/` is the only folder this process reads or writes
going forward. Nothing outside it is touched. The old `libib-batches/`,
`libib_batch.py`, `libib_batch_state.py`, and `LIBIB_FINAL_IMPORT/*.csv`
(other than the two cache files, see below) are left on disk as history,
unread by anything new.

### Inputs (dropped in by hand, untouched by scripts)

- `shopify_rental_current_9.16.csv` — full Shopify rental-library export
- `libib_current_9.16.csv` — full Libib export (re-dropped in whenever the
  user wants to reconcile against current reality)

Both are re-droppable at any time under a new date-stamped name; scripts
always take the current filename as an argument rather than hardcoding it.

### Reused from the old system

`.tmdb-cache.json` and `.upcmdb-cache.json` move from `LIBIB_FINAL_IMPORT/`
into `Libib_Migration_Master/`. Both cache by content (`TmdbCache` keys on
`(title, year)`, `UpcmdbCache` keys on IMDb ID), not by which batch or row
they were populated from, so every one of the 816 already-resolved-UPC
rows and 1994 already-confirmed-no-UPC rows from the old `libib-batches/`
work is a free cache hit going forward — no new API calls for anything
already looked up. `libib_pipeline.enrich_rows()` is reused unchanged,
just pointed at the new cache location.

### Working files (all in Libib_Migration_Master/, full Shopify-column
schema unless noted)

| File | Contents |
|---|---|
| `master.csv` | Rows not yet fully resolved one way or another. Starts as an exact copy of `shopify_rental_current_9.16.csv`. |
| `incorrect-barcode.csv` | Rows whose `Variant Barcodes` isn't exactly 8 digits. |
| `duplicate-barcode.csv` | Rows whose 8-digit barcode is shared by another distinct product (by Handle) elsewhere in the *original* Shopify export. |
| `imported.csv` | Rows confirmed present in Libib (barcode matched against Libib's `call_number`) but whose Libib `barcode` field doesn't yet equal `call_number`. |
| `done.csv` | Rows confirmed present in Libib **and** `barcode == call_number`. Fully complete, nothing left to do. |
| `batches/batch-0001.csv`, ... | Libib import-format CSVs (not Shopify columns) pulled from whatever remains in `master.csv`, for manual upload. |

Row-count invariant, checked after every `reconcile` run: `len(master) +
len(incorrect-barcode) + len(duplicate-barcode) + len(imported) +
len(done)` always equals the row count of the original
`shopify_rental_current_*.csv` (minus header). Rows only ever move between
these files, never get dropped or duplicated.

## Script: `reconcile`

Run any time after dropping in a fresh Libib export. Idempotent — safe to
re-run on the same state.

1. **Format split.** From `master.csv`, pull every row whose
   `Variant Barcodes` isn't exactly 8 numeric characters into
   `incorrect-barcode.csv`.
2. **Duplicate split.** Using the *original, untouched*
   `shopify_rental_current_*.csv` as the source of truth (not the mutating
   `master.csv`, so a duplicate that's half-already-imported is still
   caught), find every 8-digit barcode value shared by 2+ distinct
   Handles. Pull any such row still sitting in `master.csv` into
   `duplicate-barcode.csv`.
3. **Libib match.** For what's left in `master.csv`, match each row's
   `Variant Barcodes` against the current `libib_current_*.csv`'s
   `call_number` column:
   - no match → stays in `master.csv`
   - match, and Libib's `barcode == call_number` → move to `done.csv`
   - match, but `barcode != call_number` → move to `imported.csv`
4. Print a summary: how many rows moved into each file this run, and the
   row-count invariant check.

## Script: `build-batch`

Pulls the next chunk of `master.csv` rows that are ready to hand-upload.

1. Run `enrich_rows()` (unchanged, from `libib_pipeline.py`) against
   whatever's currently in `master.csv`, pointed at the relocated cache
   files. Previously-seen titles resolve instantly from cache; only rows
   never searched before spend fresh TMDB/UPCMDB calls.
2. Filter to rows that got a real `upc_isbn10`.
3. Take the next N (default 100, overridable) such rows, write them to
   `batches/batch-000N.csv` in Libib's movie-import column format.
4. **Does not** remove these rows from `master.csv`. They only move to
   `imported.csv`/`done.csv` once a subsequent `reconcile` confirms
   against a real, fresh Libib export that they actually landed. This is
   the fix for the false-success problem: nothing is ever marked done
   based on our own intent, only on re-observed reality.

## Barcode-setting

Unchanged: `formatting-scripts/libib_barcode_update.py` runs as-is against
any CSV with a `call_number` column — a `batches/batch-000N.csv`, or
`imported.csv` directly to sweep up everything still needing its physical
barcode set. Its known bugs (stale search-index false-ambiguity, false-
positive save verification) were already fixed in this same session and
carry forward unchanged.

## Explicitly out of scope for this pass

- Merging a newer `shopify_rental_current_*.csv` into an
  already-in-progress `master.csv` (what happens to rows added/changed
  since master was built). Not asked for; `master.csv` is the working set
  once created.
- Any UI/automation for the manual "upload this batch to Libib" step —
  still a human action, same as before.
- Retrying `upcmdb`-lookup-failed rows on a schedule. `enrich_rows`
  already treats a confirmed no-UPC-records result as a stable cached
  answer (not retried) per `upcmdb_cache.py`'s existing policy; changing
  that policy isn't part of this design.
