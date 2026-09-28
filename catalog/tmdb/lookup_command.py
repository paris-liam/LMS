"""`python3 -m catalog tmdb-lookup --tag <tag>` — TMDB matching only, for the
products carrying one tag, over the latest audit's snapshot.

Read-only: writes one CSV into the run folder and the shared TMDB cache.
"""

import argparse
from collections import Counter
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.handles import slugify
from catalog.core.runs import resolve_run
from catalog.errors import InputShapeError
from catalog.shopify.snapshot import load_snapshot
from catalog.tmdb.cache import TmdbCache
from catalog.tmdb.client import make_fetcher
from catalog.tmdb.lookup import LOOKUP_COLUMNS, has_tag, lookup


def register(subparsers) -> None:
    p = subparsers.add_parser("tmdb-lookup", help="TMDB matching only, for products with one tag (read-only)")
    p.add_argument("--tag", required=True, help="Shopify tag to look up, e.g. 'Staff Picks'")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--no-cache", action="store_true", help="bypass the TMDB cache (re-fetch everything)")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def run_command(args, fetch_fn=None) -> int:
    runs_dir = Path(args.runs_dir)
    run_dir = resolve_run(runs_dir, args.run)
    log.setup_logging(None, log.verbosity(args))
    log.header(f"tmdb-lookup — tag {args.tag!r}, audit run {run_dir.name}")

    rows = load_snapshot(run_dir / "snapshot.json")
    if not any(has_tag(r, args.tag) for r in rows):
        raise InputShapeError(f"no movie in run {run_dir.name} carries the tag {args.tag!r}")

    raw_fetch = fetch_fn or make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))
    cache = None if args.no_cache else TmdbCache(runs_dir / config.TMDB_CACHE_FILENAME)
    fetch = raw_fetch if cache is None else cache.wrap(raw_fetch)
    try:
        results = lookup(rows, args.tag, fetch)
    finally:
        if cache is not None:
            cache.save()

    out = run_dir / f"tmdb-lookup-{slugify(args.tag)}.csv"
    write_csv(out, LOOKUP_COLUMNS, results)
    counts = Counter(r["Match"] for r in results)
    log.summary(f"products:  {len(results)} tagged {args.tag!r}")
    log.summary("matches:   " + ", ".join(f"{k} {counts[k]}" for k in ("confident", "ambiguous", "none", "error")
                                          if counts[k]))
    if cache is not None:
        log.summary(f"tmdb:      {cache.hits} cache hits, {cache.misses} fetches")
    log.summary(f"-> {out}")
    return 0
