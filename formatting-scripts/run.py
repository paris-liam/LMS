"""One command: normalize a movie CSV, fill it from TMDB, and split out
everything that needs a human.

    python3 formatting-scripts/run.py <input.csv>

Writes to out-<inputname>/ beside the input, so re-running on that run's
issues.csv cannot clobber its upload.csv. Every output file is itself a
valid input file: fix the rows, run the same command on the fixed file,
import what comes out.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import tmdb_fill
from catalog_common import load_export, write_csv
from columns import REASON_COLUMN
from detect import UnknownShapeError, detect_shape, strip_reason
from normalize import normalize_rows, output_columns
from review_page import write_picker
from tmdb_cache import TmdbCache

NO_LOG = lambda message: None

CACHE_FILENAME = ".tmdb-cache.json"


def output_dir_for(input_path) -> Path:
    input_path = Path(input_path)
    return input_path.parent / f"out-{input_path.stem}"


def _unmatched_rows(review_rows, filled_rows, columns):
    """Build tmdb-unmatched.csv rows: Reason + the normalized output columns.

    These rows already passed normalization — the only thing missing is a
    description or a poster. Emitting them in the output shape (rather than
    the raw input shape) means the operator edits the same columns Shopify
    will read, and the file feeds straight back into run.py.
    """
    by_handle = {}
    for row in filled_rows:
        by_handle.setdefault(row.get("Handle", ""), row)

    out = []
    seen = set()
    for entry in review_rows:
        handle = entry["Handle"]
        if entry["Kind"] != "unmatched" or handle in seen or handle not in by_handle:
            continue
        seen.add(handle)
        source = by_handle[handle]
        out.append({REASON_COLUMN: entry["Reason"], **{c: source.get(c, "") for c in columns}})
    return out


def run(
    input_path,
    outdir=None,
    skip_tmdb=False,
    api_key=None,
    fetch_fn=None,
    sleep_fn=time.sleep,
    log_fn=NO_LOG,
    progress_fn=None,
    no_cache=False,
) -> dict:
    input_path = Path(input_path)
    outdir = Path(outdir) if outdir else output_dir_for(input_path)
    outdir.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = load_export(input_path)
    fieldnames, rows = strip_reason(fieldnames, rows)
    shape = detect_shape(fieldnames)
    log_fn(f"== {input_path.name}: {len(rows)} rows, detected shape: {shape} ==")

    clean_rows, issue_rows = normalize_rows(rows, shape)
    columns = output_columns(shape)

    write_csv(outdir / "issues.csv", [REASON_COLUMN] + fieldnames, issue_rows)
    log_fn(f"Stage 1: {len(clean_rows)} rows normalized, {len(issue_rows)} rows flagged")

    result = {
        "shape": shape,
        "clean": len(clean_rows),
        "issues": len(issue_rows),
        "ambiguous": 0,
        "unmatched": 0,
        "outdir": str(outdir),
    }

    if skip_tmdb or (fetch_fn is None and not api_key):
        reason = "--skip-tmdb" if skip_tmdb else "TMDB_API_KEY not set"
        log_fn(f"Stage 2: skipped ({reason})")
        write_csv(outdir / "upload.csv", columns, clean_rows)
        _write_report(outdir, input_path, result, log_fn)
        return result

    raw_fetch = fetch_fn or tmdb_fill.make_tmdb_fetcher(api_key)

    if no_cache:
        # Bypass the cache entirely: don't read the existing cache file, don't
        # write to it. The user's existing cache is left exactly as it was.
        cache = None
        cached_fetch = raw_fetch
        cache_status = "bypassed (--no-cache)"
        log_fn("Stage 2: TMDB cache bypassed (--no-cache) — re-fetching everything")
    else:
        cache = TmdbCache(outdir / CACHE_FILENAME)
        cached_fetch = cache.wrap(raw_fetch)
        cache_status = None  # filled in after the fetch below

    filled_rows, review_rows = tmdb_fill.build_output(
        clean_rows, cached_fetch, sleep_fn=sleep_fn,
        progress_fn=progress_fn or (lambda i, t, h, m: None),
    )
    if cache is not None:
        cache.save()
        cache_status = f"{cache.hits} hits, {cache.misses} fetches"

    write_csv(outdir / "upload.csv", columns, filled_rows)

    unmatched = _unmatched_rows(review_rows, filled_rows, columns)
    write_csv(outdir / "tmdb-unmatched.csv", [REASON_COLUMN] + columns, unmatched)

    ambiguous = [entry for entry in review_rows if entry["Kind"] == "ambiguous"]
    result["ambiguous"] = len({entry["Handle"] for entry in ambiguous})
    result["unmatched"] = len(unmatched)

    log_fn(
        f"Stage 2: {len(filled_rows)} rows written, "
        f"{result['ambiguous']} ambiguous, {result['unmatched']} unmatched "
        f"(cache: {cache_status})"
    )

    if ambiguous:
        write_picker(ambiguous, outdir, cached_fetch, sleep_fn=sleep_fn,
                     progress_fn=progress_fn or (lambda i, t, h, m: None))
        if cache is not None:
            cache.save()
        log_fn(f"Stage 3: picker page for {result['ambiguous']} products")

    _write_report(outdir, input_path, result, log_fn, cache_status=cache_status)
    return result


def _write_report(outdir: Path, input_path: Path, result: dict, log_fn, cache_status=None) -> None:
    lines = [
        f"input:      {input_path}",
        f"shape:      {result['shape']}",
        f"upload.csv: {result['clean']} products normalized",
        f"issues.csv: {result['issues']} rows need a fix",
        f"ambiguous:  {result['ambiguous']} products in review-picker.html",
        f"unmatched:  {result['unmatched']} products in tmdb-unmatched.csv",
    ]
    if cache_status is not None:
        lines.append(f"cache:      {cache_status}")
    (outdir / "run-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_fn(f"  -> {outdir}")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize and TMDB-fill a movie CSV for Shopify import."
    )
    parser.add_argument("input_csv", help="Upload-template batch, Shopify export, or a prior output")
    parser.add_argument("--outdir", default=None, help="Override the out-<inputname>/ directory")
    parser.add_argument("--skip-tmdb", action="store_true", help="Stop after normalization")
    parser.add_argument("--no-cache", action="store_true",
                         help="Bypass the TMDB query cache and re-fetch everything")
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not args.skip_tmdb and not api_key:
        print("Note: TMDB_API_KEY is not set — running normalization only.", file=sys.stderr)

    try:
        result = run(
            Path(args.input_csv),
            outdir=args.outdir,
            skip_tmdb=args.skip_tmdb,
            api_key=api_key,
            log_fn=lambda message: print(message, flush=True),
            progress_fn=tmdb_fill.print_progress,
            no_cache=args.no_cache,
        )
    except UnknownShapeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(result["outdir"])
    print()
    print(f"Import this:  {outdir / 'upload.csv'}")
    if result["issues"]:
        print(f"Fix and re-run: {outdir / 'issues.csv'} "
              f"({result['issues']} rows) — python3 formatting-scripts/run.py {outdir / 'issues.csv'}")
    if result["ambiguous"]:
        print(f"Pick posters: open {outdir / 'review-picker.html'}, export picks, then")
        print(f"  python3 formatting-scripts/apply_picks.py "
              f"{outdir / 'tmdb-picks.json'} {outdir / 'upload.csv'}")
    if result["unmatched"]:
        print(f"Fill by hand: {outdir / 'tmdb-unmatched.csv'} ({result['unmatched']} products)")
    print()
    print("After importing: run scripts/set-movie-template.sh so movies use the movie template.")


if __name__ == "__main__":
    main()
