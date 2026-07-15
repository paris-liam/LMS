# TMDB image/description auto-fill — design

## Context

The movie catalogue reformat pipeline (`reformat_movies.py`, `circaos_reformat.py`, `run_full_reformat.py`) fixes structural issues (format-in-Vendor, fake-variant genre) but doesn't touch missing content. A scan of `movies-reformatted.csv` found **1,458 of 1,846 products (79%)** missing an image and/or a real description — mostly stub rows created with title/tags/pricing but never given copy or photos.

This spec covers a script to auto-fill those gaps from [TMDB](https://www.themoviedb.org/) (The Movie Database), using an existing TMDB API key.

**Sequencing**: the user is currently re-exporting the full catalogue after uploading recent reformat work. The missing-image-or-description scan will be re-run against that fresh export, and this script will consume both the fresh export and the scan's flagged list. The script itself doesn't depend on the exact input filename — it operates on any Shopify product CSV.

## Scope

A new module, `data-cleanup/tmdb_fill.py`, following the same pattern as `reformat_movies.py`: a testable `build_output(rows, fieldnames, api_key, fetch_fn=...)` function plus a thin CLI wrapper. `fetch_fn` is injectable so unit tests supply canned TMDB responses instead of hitting the network.

Out of scope: downloading/re-hosting images (TMDB's CDN URL is written directly into `Image Src`; Shopify fetches and re-hosts it on import, same as existing Image Src values in the CSVs), site-wide TMDB attribution notice (a separate, later concern), and any change to the existing reformat scripts.

## CLI

```
TMDB_API_KEY=... python3 data-cleanup/tmdb_fill.py <input_csv> [--outdir DIR]
```

- `input_csv`: path to a Shopify product export/CSV (positional, required).
- `--outdir`: directory for the two output files. Defaults to the input file's own directory.
- API key is read from the `TMDB_API_KEY` environment variable; the script exits with a clear error if it's unset.

## Determining what needs filling

Rows are grouped by `Handle` (existing `group_rows_by_handle` pattern). For each group, checked against the **primary (first) row**:

- **Needs image** if no row in the group has a non-empty `Image Src`.
- **Needs description** if `Body (HTML)` on the primary row, with HTML tags stripped, is empty OR under 40 characters.

A product needing neither is left completely untouched and passed through unchanged. A product needing only one of the two only gets that field touched.

## Title cleaning & TMDB matching

1. **Extract year**: strip a trailing `(YYYY)` from the title (`"Warriors (1994)"` → title `"Warriors"`, year `1994`). No parenthetical year → no year filter.
2. **Strip known noise patterns**: a small, extensible list (module-level constant, same style as `genre_format_mapping.py`'s tables) of packaging/edition noise that isn't part of the movie's real title — e.g. `[Steelbook]`, `(Free Gift)`, `Widescreen Set`, `Full Screen`, `Special/Collector's/Anniversary Edition`, `Remastered`, `Director's Cut`, `Uncut`, `Unrated`, `Extended Cut`. Patterns not on the list are left as-is; any resulting mismatch just falls through to the review file rather than being silently guessed.
3. **Search**: call TMDB `/search/movie` with the cleaned title and, if present, `primary_release_year`.
4. **Fallback**: if that returns zero results and a year was set, retry once without the year filter (old VHS/DVD release-year metadata is often off by a year from TMDB's theatrical date).
5. **Confidence check**: normalize (lowercase, strip punctuation) both the cleaned search title and the top result's title, compare with `difflib.SequenceMatcher` ratio. Accept as a confident match at or above a fixed threshold (0.9); exact match after normalization always passes.
6. **No match** (zero results after both attempts) → review, reason `"no TMDB match"`.
7. **Low-confidence match** (top result below threshold) → review, reason `"ambiguous match (best candidate: '<title>' (<year>))"`.

One TMDB search call per product needing at least one field (search results already include `overview` and `poster_path`, so no second detail-lookup call is needed).

## Writing fields

On a confident match, only for the field(s) the product actually needed:

- `Image Src` ← `https://image.tmdb.org/t/p/w500{poster_path}`, only if the match has a poster. If the match is confident but has no poster, the image is left blank and the handle is separately flagged in the review file: `"matched but no TMDB poster"`.
- `Body (HTML)` ← `<p>{overview}</p>`, only if the match has a non-empty overview. Same partial-flag treatment (`"matched but no TMDB overview"`) if not.

A single product can appear in the review file for a genuine no-match/ambiguous-match reason, OR purely for a partial-fill note while still having its other field(s) written into `tmdb-filled.csv`.

## Output files

Written to `--outdir`:

- `tmdb-filled.csv` — the full input CSV, same header/row structure, with matched fields filled in. Rows needing nothing pass through unchanged.
- `tmdb-needs-review.csv` — `Handle, Title, Reason` for every handle that got a no-match/ambiguous-match/partial-fill flag.

## Error handling & rate limiting

- A fixed small delay between requests (e.g. 250ms) to stay well under TMDB's rate limits over a ~1,450-item run.
- A single failed/errored TMDB request (network error, non-200, timeout) does not abort the run — that product is routed to `tmdb-needs-review.csv` with the error message as its reason, and the script continues.
- No resumable cache/checkpoint file: a full run completes in a few minutes at the polite request pace, and reruns are idempotent since rows that already have good data are left untouched regardless of what the CSV started as.

## Testing

- Unit tests for `clean_title_and_year` (year extraction, noise-pattern stripping, titles with neither).
- Unit tests for the matching logic against a fake `fetch_fn` returning canned TMDB responses: confident match, no results, low-similarity top result, year-filtered-then-fallback path.
- Unit tests for `build_output`: needs-image-only, needs-description-only, needs-both, needs-neither (untouched), partial match (poster but no overview and vice versa), and a failed fetch routed to review without aborting the batch.
- No integration test against the live TMDB API (would require network access and a real key in CI); the injectable `fetch_fn` is the seam that makes the above testable without one.

## Assumptions / caveats

- Requires `TMDB_API_KEY` to be set in the environment before running; the script does not read or write any key-storage file.
- Writes TMDB's own CDN URL into `Image Src` rather than downloading/re-hosting; if TMDB ever removes/moves an image after import, Shopify's own copy (created at import time) is unaffected since Shopify re-hosts on fetch.
- The 0.9 similarity threshold and 40-character description threshold are fixed constants in this first pass, not tuned against the real dataset yet — worth revisiting once the review file's size/contents are seen against the actual fresh export.
- TMDB attribution ("This product uses the TMDB API but is not endorsed or certified by TMDB") is a site-wide requirement per TMDB's API terms and is not addressed by this script — flagging as a follow-up, not blocking this work.
