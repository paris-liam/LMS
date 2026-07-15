# TMDB review picker — design

## Context

The TMDB auto-fill run (`data-cleanup/tmdb_fill.py`) produced a `tmdb-needs-review.csv` with >450 entries: ambiguous matches, no-matches, and matched-but-incomplete TMDB records. Resolving these by hand-searching TMDB per title is slow. This adds a two-step manual-review workflow:

1. **`data-cleanup/tmdb_review_page.py`** — re-queries TMDB for every review entry with no confidence threshold, and generates a self-contained HTML picker page showing each product's top 5 candidates (poster, title, year, overview). The user clicks the right candidate — or "Not filling this one" — per product and exports their picks as a JSON file.
2. **`data-cleanup/apply_review_picks.py`** — applies the exported picks to a product CSV (normally the run's `tmdb-filled.csv`), producing an upload-ready CSV.

## Picker page (`tmdb_review_page.py`)

```
TMDB_API_KEY=... python3 data-cleanup/tmdb_review_page.py <needs-review.csv> [--outdir DIR]
```

- Dedupes review entries by Handle (a product can appear twice, e.g. "no poster" + "no overview").
- Per handle: cleans the title (reusing `clean_title_and_year` from `tmdb_fill`), searches TMDB once (year filter + no-year fallback, reusing `search_tmdb`), keeps the top 5 results as candidates `{id, title, year, overview, poster_path}`.
- Same 250ms pacing and per-product progress printing as `tmdb_fill`.
- Writes `tmdb-review-picker.html`: self-contained, candidate data embedded as JSON (with `</` escaped so overview text can't break out of the script tag), poster thumbnails loaded from TMDB's CDN (`w185`).

Page behavior (vanilla JS, no dependencies):
- One card per product: title, handle, review reason, TMDB + Google search links for manual research, and radio options — each candidate, **"Not filling this one — tag 'needs data'"**, and a default **"Decide later"**.
- Selections persist to `localStorage` on every change, so a 450-item session can be resumed after closing the page.
- A progress counter (decided / total) and an **Export picks** button that downloads `tmdb-picks.json` containing only decided products: `[{handle, choice: "tmdb", poster_path, overview} | {handle, choice: "needs_data"}]`. Partial exports are fine — apply, re-open, continue later.

JSON (not CSV) for the picks file: overviews contain commas/quotes/newlines, and `JSON.stringify`/`json.load` round-trips them without a hand-rolled CSV writer in JS.

## Apply step (`apply_review_picks.py`)

```
python3 data-cleanup/apply_review_picks.py <tmdb-picks.json> <base.csv> [--outdir DIR]
```

- `base.csv` is normally the run's `tmdb-filled.csv`, so picks layer on top of the auto-filled output.
- `choice == "tmdb"`: fills fields on the handle's primary row using the **same need rules as the auto-fill** (imported from `tmdb_fill`): image only if the product has none (`needs_image`), description only if short/empty or CircaOS-tagged (`needs_description` / `has_circaos_tag`), and each field only if the pick actually carries data. An already-good field is never clobbered.
- `choice == "needs_data"`: appends the tag `needs data` to the primary row's Tags without duplicating (reusing `add_tags` from `run_full_reformat`).
- Handles in the picks file that don't exist in the base CSV are counted and reported, not fatal.
- Writes `picks-applied.csv` (full CSV) and prints counts: applied, tagged, unknown handles.

## Testing

Same pattern as `tmdb_fill`: injectable `fetch_fn`, `unittest`, no network. Cover: candidate mapping/capping, handle dedupe, JSON embedding safety (`</script>` in an overview), needs-data option present in HTML, picks application for both choice types, need-rule gating (good image not replaced), tag dedup, unknown-handle handling.
