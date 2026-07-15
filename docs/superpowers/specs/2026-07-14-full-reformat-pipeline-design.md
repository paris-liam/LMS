# Full reformat pipeline — design

## Context

Two reformatting scripts already exist and are approved/merged to `main`:
- `data-cleanup/reformat_movies.py` — reformats the plain resale batch (`Option1 Name == "Genre"`).
- `data-cleanup/circaos_reformat.py` — reformats the serialized-rental/CircaOS batch (`Option1 Name == "Condition"`).

Both were run against the dev store's export and their outputs manually combined into a single upload file, along with tagging the flagged "needs review" products from both batches so nothing gets lost. This spec turns that manual process into a repeatable script, so the same work can be re-run against a different store's export (e.g. production) without redoing it by hand.

## Scope

A new orchestrator script, `data-cleanup/run_full_reformat.py`, that wires together the two existing modules' already-tested `build_output()` functions. Neither existing module needs any changes — both already accept `(rows, fieldnames)` as parameters rather than hardcoding file paths, so the orchestrator can call them directly.

Out of scope: fixing the wrong CircaOS descriptions (a separate, future step), and any change to the reformatting logic itself (genre/format resolution, multi-copy splitting, etc.) — this spec is purely about orchestration and combining outputs.

## CLI

```
python3 data-cleanup/run_full_reformat.py <input_csv> [--outdir DIR]
```

- `input_csv`: path to the full product export (positional, required).
- `--outdir`: directory to write the four output files. Defaults to the input file's own directory.

## Pipeline

1. Read `input_csv` once (`fieldnames`, `rows`).
2. Call `reformat_movies.build_output(rows, fieldnames)` → `(resale_fieldnames, resale_output_rows, resale_review_rows)`.
3. Call `circaos_reformat.build_output(rows, fieldnames)` → `(circaos_fieldnames, circaos_output_rows, circaos_review_rows)`.
4. Both calls independently decide whether to insert the `Media format` column into `fieldnames`; since both start from the same `fieldnames` and apply the same insertion rule, `resale_fieldnames == circaos_fieldnames`. This becomes the shared output header.
5. Merge review rows: `resale_review_rows` tagged with `Batch: "resale"`, `circaos_review_rows` tagged with `Batch: "circaos"`, combined into one list.
6. Build the combined upload:
   - All `resale_output_rows` (already fully reformatted).
   - All `circaos_output_rows` (already fully reformatted).
   - For every review-flagged handle (both batches): the handle's **full original row(s)** from the input export, every field preserved at its real current value (no blanking — Shopify's CSV import clears any column present in the file when a row's cell for that column is blank, so passthrough rows must carry real values, not omit them), with `Tags` updated to append `Needs Review` (resale-batch handles) or `CircaOS Import` + `Needs Review` (circaos-batch handles), without duplicating a tag that's already present. Multi-row handles (a review-flagged product with bonus image rows) bring all their rows along; only the first row's `Tags` changes.
7. Write four files to `--outdir`:
   - `reformatted-resale.csv` — `resale_output_rows` with the shared header.
   - `reformatted-circaos.csv` — `circaos_output_rows` with the shared header.
   - `needs-review.csv` — the merged review report: `Handle, Title, Batch, Reason`.
   - `combined-upload.csv` — the full combined upload from step 6, with the shared header.

## Field mapping and tagging — no new rules

This spec introduces no new reformatting rules. Genre/format resolution, multi-copy splitting, vendor/category fixing, and the review criteria are exactly what `reformat_movies.py` and `circaos_reformat.py` already do. The only new logic is:
- Combining two review-row lists into one with a `Batch` column.
- Building passthrough rows for review-flagged handles and appending the appropriate tag(s) without touching any other field.

## Testing

- Unit tests for the review-merge function (adds `Batch` correctly, preserves `Reason`/`Handle`/`Title`) and the passthrough-row builder (preserves every original field, appends the correct tag(s) without duplication, carries multi-row handles' bonus rows unchanged).
- One integration test against a new fixture CSV (`tests/data_cleanup/fixtures/full_export_sample.csv`) containing representative rows from both batches together: a resale in-scope row, a resale review row, a CircaOS in-scope row, a CircaOS review row with a bonus image row (mirroring `conan-the-barbarian`), and the Supercycle Plan skip row — verifying all four output files end to end.

## Assumptions / caveats (not solved by this script)

- The target store must already have the `shopify.genre` and `shopify.media-format` metafields/metaobject entries set up with matching handles, exactly as verified on the dev store before the first reformat pass. This script doesn't check or create them — that's a manual pre-flight step, same as it was for the dev store.
- The existing `VENDOR_TO_FORMAT`/`GENRE_VALUE_MAP` tables were built from the dev store's exact set of raw values. If a different store's export contains vendor or genre values outside those tables, the existing classification logic already handles this safely (unmapped genre values route to review, not silently mishandled; unmapped vendors resolve to a blank format, not an error) — but the review report may be larger for a dataset with different messiness than the dev store's.
