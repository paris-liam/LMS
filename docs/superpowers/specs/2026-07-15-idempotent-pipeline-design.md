# Idempotent catalogue pipeline — design

## Context

The reformat scripts (`reformat_movies.py`, `circaos_reformat.py`, `run_full_reformat.py`) classify work by row *shape* and were built for the raw store export. Run against an already-reformatted file they flag ~2,500 finished products as needing review and would re-tag them all `Needs Review`. Separately, the TMDB fill re-refreshes every CircaOS description on every run, and nothing chains the stages together. This spec makes the whole flow idempotent and adds a single pipeline command, while keeping `tmdb_fill.py` independently runnable.

## Structure changes

```
data-cleanup/
  catalog_common.py      NEW — shared helpers: load_export, write_csv,
                         split_tags, add_tags, has_tag, group_rows_by_handle
  genre_format_mapping.py  + "kids-family" entry in GENRE_VALUE_MAP
  reformat_movies.py       transform functions only; stale main() removed
  circaos_reformat.py      transform functions only; stale main() removed
  run_pipeline.py        NEW — replaces run_full_reformat.py (deleted)
  tmdb_fill.py             standalone CLI kept; three behavior changes below
  tmdb_review_page.py      import updates only
  apply_review_picks.py    imports add_tags from catalog_common
```

`group_rows_by_handle` moves from `reformat_movies` to `catalog_common`; all importers (both reformat modules, `tmdb_fill`, `apply_review_picks`, tests) update. Tag helpers consolidate: `run_full_reformat.add_tags` and `circaos_reformat.build_tags` become `catalog_common.add_tags`; ad-hoc tag splits become `split_tags`/`has_tag`.

## Workflow tags

| Tag | Meaning | Applied by | Consumed by |
|---|---|---|---|
| `Needs Review` | Reformat couldn't classify genre/format | pipeline | pipeline (skip; auto-remove when resolved) |
| `CircaOS Import` | Product originated from the CircaOS import | reformat transforms | tmdb_fill (description distrust) |
| `TMDB Filled` | tmdb_fill has filled/refreshed this product | tmdb_fill | tmdb_fill (don't force-refresh again) |
| `needs data` | Human declined to fill in the picker | apply_review_picks | tmdb_fill (skip entirely) |

## `run_pipeline.py`

```
python3 data-cleanup/run_pipeline.py <export.csv> [--outdir DIR] [--skip-tmdb]
```

### Stage 1 — reformat (idempotent classification, per handle group)

1. `Type == "Supercycle Plan"` → passthrough unchanged ("skipped").
2. `Option1 Name == "Genre"` → resale transform (existing `transform_group`). Unmappable/corrupt values → review.
3. `Option1 Name == "Condition"` → CircaOS transform (existing `transform_circaos_group`, incl. multi-copy split). No genre-like tag → review.
4. Anything else (reformatted `Title` shape):
   - genre metafield **filled** → done; if tagged `Needs Review`, remove the tag (resolved) and count it.
   - genre metafield **empty** → **recovery**: look for a mappable genre tag in Tags (`extract_genre_from_tags`). Found → fill genre metafield; fill format metafield if empty (`resolve_circaos_format`: barcode prefix, then 4K tag, then vendor); fix Vendor → `Little Movie Store` and Product Category → `Media > Videos`; remove `Needs Review` tag if present. Not found → review.
5. "Review" outcome: product passes through with all original values, `Tags` gains `Needs Review` (no duplicate), and a row goes in the review report. A product already tagged `Needs Review` that still can't be classified stays tagged, passes through, and is reported as "still flagged" (not re-flagged).

Output: full catalogue (every product, in original order) — reformatted, recovered, passthrough alike — so the TMDB stage and the Shopify import both see a complete file.

### Stage 2 — TMDB fill + picker (skipped with `--skip-tmdb` or when `TMDB_API_KEY` unset)

Runs in-process on stage 1's output rows: `tmdb_fill.build_output` with the same pacing/progress, writing the usual five files, then `tmdb_review_page.collect_products` + `build_picker_html` on the fill's review rows → `tmdb-review-picker.html`. Stage 2 skipped ⇒ the upload file is stage 1's output; otherwise it's `tmdb-filled.csv`.

### Outputs (all in `--outdir`, default input's directory)

- `reformatted.csv` — full catalogue after stage 1
- `reformat-review.csv` — `Handle, Title, Reason, Status(new|still-flagged)`
- stage 2: `tmdb-filled.csv`, `tmdb-needs-review.csv`, `tmdb-changed.csv`, `tmdb-changed-before.csv`, `tmdb-changes.html`, `tmdb-review-picker.html`
- printed summary: reformatted / recovered / resolved-tag-removed / newly flagged / still flagged / done-skipped counts, then the TMDB counts, then next-step instructions (open picker → export → `apply_review_picks.py`)

## `tmdb_fill.py` changes (standalone CLI unchanged otherwise)

1. **Skip `needs data`**: products carrying the tag are passed through untouched (progress: "skipped (needs data)"), never queried.
2. **Idempotent CircaOS refresh**: forced description refresh applies only to products tagged `CircaOS Import` **without** `TMDB Filled`.
3. **`TMDB Filled` marker**: whenever the fill changes a product (image or description), append `TMDB Filled` to the primary row's Tags.
4. **Honest summary**: CLI prints total rows written and actual changed-product count distinctly (counts dict already has both).

## Logging

Every stage narrates to stdout as it runs:

- Stage banners (`== Stage 1: reformat ==`, `== Stage 2: TMDB fill ==`) with input/output paths.
- Stage 1 prints one line per product it **acts on** — reformatted, recovered, tag-removed, newly flagged (`[handle] recovered genre 'drama' from tags`, `[handle] flagged: no genre-like tag`) — but not per untouched product (thousands of "skipped" lines would bury the signal); untouched products are summarized in the counts.
- Stage 2 keeps `tmdb_fill`'s existing per-product `[i/total]` progress (network-paced, so per-product lines double as a liveness indicator).
- Both stages end with a counts summary; the pipeline ends with explicit next-step instructions.
- All logging goes through injectable `log_fn`/`progress_fn` parameters defaulting to no-ops in library functions and wired to `print` in `main()`, so tests stay silent.

## Testing

- `test_catalog_common.py` — tag helpers, grouping, CSV round-trip.
- `test_run_pipeline.py` — one fixture CSV containing every classification bucket: done row (genre filled), done-but-tagged row (tag removed), raw Genre row, raw Condition row (+ multi-copy), recovery row (genre in Tags, metafield empty, old vendor), unrecoverable row (new flag), already-flagged unrecoverable row (still-flagged, no duplicate tag), Supercycle Plan row. End-to-end `run()` test with fake `fetch_fn` covering stage 2 chaining and `--skip-tmdb`.
- `test_tmdb_fill.py` — new cases: needs-data skip, CircaOS + TMDB Filled not re-refreshed, marker tag appended on change; existing 53 tests keep passing (marker changes some expectations).
- `test_run_full_reformat.py` deleted with its module; transform-level tests in `test_reformat_movies.py` / `test_circaos_reformat.py` keep covering the transforms (minus deleted `main()`s).
- Full suite green before and after; no network in any test.

## Non-goals

- No change to the picker/apply flow beyond the import path.
- No automatic re-run of the picker loop — it's inherently manual.
- `reformat_movies.py`/`circaos_reformat.py` stay as separate modules (their transforms differ genuinely); only their duplicated scaffolding is removed.
