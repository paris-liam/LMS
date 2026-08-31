"""One-off: re-fetch TMDB descriptions for circa products whose Body (HTML)
was wrong. Unlike run.py, this skips normalize_rows entirely -- circa's
tagging/genre/format is already trusted, only the description is bad.

Usage: python3 formatting-scripts/circa_refill.py <input.csv> <outdir>
"""
import sys
import time
from pathlib import Path

import tmdb_fill
from catalog_common import load_export, write_csv
from columns import EXPORT_COLUMNS

API_KEY = "259d3aaf7c2a60737d754042363eb5a6"


def main():
    input_path = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = load_export(input_path)
    fetch_fn = tmdb_fill.make_tmdb_fetcher(API_KEY)

    filled_rows, review_rows = tmdb_fill.build_output(
        rows, fetch_fn, sleep_fn=time.sleep, progress_fn=tmdb_fill.print_progress,
    )

    write_csv(outdir / "circa-refilled.csv", fieldnames, filled_rows)

    ambiguous = [r for r in review_rows if r["Kind"] == "ambiguous"]
    unmatched = [r for r in review_rows if r["Kind"] == "unmatched"]

    by_handle = {}
    for row in filled_rows:
        by_handle.setdefault(row.get("Handle", ""), row)
    unmatched_rows = [by_handle[r["Handle"]] for r in unmatched if r["Handle"] in by_handle]
    write_csv(outdir / "circa-unmatched.csv", fieldnames, unmatched_rows)

    if ambiguous:
        from review_page import write_picker
        write_picker(ambiguous, outdir, fetch_fn, sleep_fn=time.sleep,
                     progress_fn=tmdb_fill.print_progress)

    print()
    print(f"filled:     {len(filled_rows)} rows -> {outdir / 'circa-refilled.csv'}")
    print(f"ambiguous:  {len(ambiguous)} -> {outdir / 'review-picker.html'}" if ambiguous else "ambiguous:  0")
    print(f"unmatched:  {len(unmatched)} -> {outdir / 'circa-unmatched.csv'}")


if __name__ == "__main__":
    main()
