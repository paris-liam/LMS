"""End-to-end: Shopify export -> IMDb ID (TMDB) -> UPC/EAN (UPCMDB) -> Libib
movie-import CSV.

    python3 formatting-scripts/libib_pipeline.py \\
        products_9.14_rental.csv claudedocs/libib-import.csv [--limit 20]

TMDB_API_KEY / UPCMDB_API_KEY are hardcoded below at the user's request --
this repo has a GitHub remote (paris-liam/LMS), so this commits both keys
to git history there.

Writes:
  - <output>            the Libib movie-import CSV (libib_export.py's columns)
  - <output>.review.csv rows that couldn't be fully resolved (no confident
                         TMDB match, no imdb_id, or no UPCMDB record) with a
                         reason, so they can be handled by hand before import
  - .tmdb-cache.json     TMDB search cache (see tmdb_cache.py), beside the
                         input file, reused across runs/limits so repeated
                         tries on the same file don't repay the full API cost
  - .upcmdb-cache.json   UPCMDB lookup cache (see upcmdb_cache.py), keyed by
                         IMDb ID -- UPCMDB quota is limited, so this is on
                         by default and a 404 is cached too (it's a stable
                         answer, not a transient failure); a handle whose
                         IMDb ID was already looked up never re-spends quota

Use --skip-upcmdb while iterating on TMDB/matching behavior (e.g. tuning
the ambiguous rate) -- it runs the IMDb-ID step and reports would-be
match rates without touching UPCMDB at all.

See claudedocs/2026-09-14-libib-bulk-upload-plan.md for the Libib import
mechanics and claudedocs/2026-09-16-* (this session) for why upc_isbn10/
ean_isbn13 are now filled instead of left blank.
"""

import argparse
import time
from pathlib import Path

from catalog_common import load_export, write_csv
from imdb_upc_fill import build_output, make_external_ids_fetcher, make_upcmdb_fetcher, print_progress
from libib_export import LIBIB_MOVIE_COLUMNS, map_row
from tmdb_cache import TmdbCache
from tmdb_fill import make_tmdb_fetcher
from upcmdb_cache import UpcmdbCache

TMDB_API_KEY = "259d3aaf7c2a60737d754042363eb5a6"
UPCMDB_API_KEY = "fcb6284d00fd953b484d30dfcbe13736"


def enrich_rows(rows: list[dict], cache_dir: Path, no_cache: bool = False, skip_upcmdb: bool = False):
    """Shopify export rows -> (libib_rows, review_rows). TMDB/UPCMDB caches
    live in cache_dir, shared across calls so repeated/retried runs over
    the same source data don't repay API cost."""
    tmdb_fetch_fn = make_tmdb_fetcher(TMDB_API_KEY)
    tmdb_cache = None
    if not no_cache:
        tmdb_cache = TmdbCache(cache_dir / ".tmdb-cache.json")
        tmdb_fetch_fn = tmdb_cache.wrap(tmdb_fetch_fn)

    external_ids_fetch_fn = make_external_ids_fetcher(TMDB_API_KEY)

    upcmdb_cache = None
    upc_fetch_fn = None
    if not skip_upcmdb:
        upc_fetch_fn = make_upcmdb_fetcher(UPCMDB_API_KEY)
        if not no_cache:
            upcmdb_cache = UpcmdbCache(cache_dir / ".upcmdb-cache.json")
            upc_fetch_fn = upcmdb_cache.wrap(upc_fetch_fn)

    enriched_rows, review_rows = build_output(
        rows,
        tmdb_fetch_fn,
        external_ids_fetch_fn,
        upc_fetch_fn,
        sleep_fn=time.sleep,
        progress_fn=print_progress,
        skip_upc=skip_upcmdb,
    )

    if tmdb_cache is not None:
        tmdb_cache.save()
        print(f"TMDB cache: {tmdb_cache.hits} hits, {tmdb_cache.misses} misses")
    if upcmdb_cache is not None:
        upcmdb_cache.save()
        print(f"UPCMDB cache: {upcmdb_cache.hits} hits, {upcmdb_cache.misses} misses (quota only spent on misses)")

    parents = [row for row in enriched_rows if row.get("Title", "").strip()]
    libib_rows = [map_row(row) for row in parents]
    return libib_rows, review_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Shopify product export CSV")
    parser.add_argument("output", help="Libib movie-import CSV to write")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows (for trying it out)")
    parser.add_argument("--no-cache", action="store_true", help="Skip both on-disk caches (TMDB and UPCMDB)")
    parser.add_argument(
        "--skip-upcmdb", action="store_true",
        help="Run TMDB/IMDb-ID matching only -- never calls UPCMDB. Use this while tuning match behavior.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    fieldnames, rows = load_export(input_path)
    if args.limit:
        rows = rows[: args.limit]
    print(f"== {input_path.name}: {len(rows)} rows ==")

    libib_rows, review_rows = enrich_rows(rows, input_path.parent, no_cache=args.no_cache, skip_upcmdb=args.skip_upcmdb)

    write_csv(output_path, LIBIB_MOVIE_COLUMNS, libib_rows)
    print(f"wrote {len(libib_rows)} rows to {output_path}")

    resolved = sum(1 for r in libib_rows if r["upc_isbn10"])
    print(f"{resolved}/{len(libib_rows)} rows got a real UPC")

    if review_rows:
        review_path = output_path.with_suffix(output_path.suffix + ".review.csv")
        write_csv(review_path, ["Handle", "Title", "Vendor", "Kind", "Reason"], review_rows)
        print(f"{len(review_rows)} rows need review -> {review_path}")


if __name__ == "__main__":
    main()
