# Catalogue formatting scripts

One command turns a movie CSV into a file Shopify can import, and puts
everything it could not resolve into files you fix and re-run.

Design: `docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md`

## Run it

```bash
export TMDB_API_KEY=...          # omit to normalize only
python3 formatting-scripts/run.py <input.csv> [--outdir OUTDIR] [--skip-tmdb] [--no-cache]
```

Input can be a batch from the upload template, a Shopify product export, or
any file this script produced earlier. Output lands in `out-<inputname>/`
(or `--outdir` if given).

| File | What to do with it |
|---|---|
| `upload.csv` | Import it: Shopify admin → Products → Import |
| `issues.csv` | Fix the rows, then `run.py out-<name>/issues.csv` |
| `review-picker.html` | Open it, pick the right poster, Export picks (only written when at least one row was ambiguous) |
| `tmdb-picks.json` | `python3 formatting-scripts/apply_picks.py <picks> <upload.csv>` → `picks-applied.csv` |
| `tmdb-unmatched.csv` | Same columns as `upload.csv`, no Reason column — fix the title (see the run's console output for why each row didn't match) or paste a description/poster, then re-run it |
| `run-report.txt` | Counts for the run |
| `.tmdb-cache.json` | TMDB query cache for this output directory. Not an input file — don't feed it to `run.py`. |

The TMDB cache is only saved to disk once at the end of the fill stage
(and again after the picker stage, if one runs). If a long run is
interrupted partway through — killed, crashed, network drops — every TMDB
fetch that run made is lost, not just the rows still pending; re-running
re-fetches from scratch.

Two copies of the same movie in the same format and type, uploaded in one
template batch, land in `issues.csv` as a `duplicate handle` — both rows
would otherwise generate identical handles and collide on import. Fix it
by hand-editing one copy's `Handle` cell to something distinct before
re-running.

Flags:

- `--skip-tmdb` — stop after normalization; no network calls, no cache file
  touched at all. Use this to check the data cleans up correctly before
  spending TMDB API calls.
- `--no-cache` — bypass the TMDB query cache (`.tmdb-cache.json` in the
  output directory) and re-fetch every query from TMDB, without deleting or
  modifying the existing cache file. Zero-result TMDB responses are cached
  indefinitely, so this is the escape hatch when TMDB later gains a film or
  a matching bug gets fixed and you need those queries re-checked.
- `--outdir` — write to a directory other than the default `out-<inputname>/`.

## The loop

1. Run the script.
2. Import `upload.csv`.
3. **Run `scripts/set-movie-template.sh`** — imported movies otherwise land
   on the default product template, which shows a $0.00 Buy Now button on
   rentals.
4. Open the picker, choose posters, export, apply, import `picks-applied.csv`.
5. Fix `issues.csv` and `tmdb-unmatched.csv`, run the script on each, import
   what comes out. Repeat until both files come back empty.

   **Opening `issues.csv` in Excel (export runs only):** these files carry a
   `Variant Barcode` column, and some of our barcodes start with a `0`
   (`06662394`, for example). If you just double-click the file to open it,
   Excel reads that column as a number and drops the leading zero — the file
   will save with `6662394` instead, silently shortening a barcode whose
   printed shelf label still reads `06662394`. You won't see an error; the
   mismatch only shows up later, if at all. To fix it, don't double-click:
   in Excel use **Data → From Text/CSV**, and when the import dialog shows
   the column list, set `Variant Barcode`'s data type to **Text** before
   loading.

## Before the first full-catalogue import

Import ~20 reformatted products to the **dev store**, re-export them, and
diff `Variant Barcode` and inventory against the input. Reformatting changes
`Option1 Value` on the 669 ex-`Condition` products, and Shopify matches
variants by option value; the script carries barcodes through so a rebuilt
variant keeps its printed label, but this has not been verified against a
live store.

## Rules the code enforces

- Handles on export rows are never rewritten — a handle is a live product's
  identity.
- Genre is never inferred from a title; type is never inferred from price.
- Existing descriptions and posters are never overwritten.
- Nothing is ever written to product tags except `Type, Format, Genre…, extras, Formatted`.
- The export output omits every column it does not set, so Shopify leaves
  those fields alone.

## Tests

```bash
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" -v
```

Standard library only. No venv, no install step.
