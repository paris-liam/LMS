"""`python3 -m catalog audit` — read Shopify, run every rule, write a run folder.

Read-only toward Shopify. Writes only its own run folder, the shared TMDB
cache, and registry promotion (applied -> resolved), so it asks for no approval.
"""

import argparse
from datetime import date
from pathlib import Path

from catalog import config
from catalog.audit.run import build_report, run_audit, write_outputs
from catalog.core import log
from catalog.core.registry import load_registry, save_registry
from catalog.core.runs import new_run
from catalog.shopify.export_reader import read_export
from catalog.shopify.reader import read_products
from catalog.shopify.snapshot import filter_catalogue
from catalog.tmdb.cache import TmdbCache
from catalog.tmdb.client import make_fetcher


def register(subparsers) -> None:
    p = subparsers.add_parser("audit", help="audit the Shopify movie catalogue (read-only)")
    p.add_argument("--store", default=config.DEFAULT_STORE, help=f"store domain (default {config.DEFAULT_STORE})")
    p.add_argument("--from-export", metavar="CSV", help="read a Shopify product export instead of the API")
    p.add_argument("--skip-tmdb", action="store_true", help="no TMDB lookups; missing content is listed only")
    p.add_argument("--no-cache", action="store_true", help="bypass the TMDB cache (re-fetch everything)")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def run_command(args, fetch_fn=None, read_api=read_products, today: date | None = None) -> int:
    runs_dir = Path(args.runs_dir)
    # Fail fast on a missing key: before creating a run folder or reading Shopify.
    raw_fetch = None
    if not args.skip_tmdb:
        raw_fetch = fetch_fn or make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))

    run_dir = new_run(runs_dir, today or date.today())
    log.setup_logging(run_dir / "audit.log", log.verbosity(args))
    log.header(f"audit — run {run_dir.name}")

    if args.from_export:
        source = f"export {args.from_export}"
        log.summary(f"reading {args.from_export}")
        raw_rows = read_export(args.from_export)
    else:
        source = f"api {args.store}"
        log.summary(f"reading products from {args.store} (read-only)")
        raw_rows = read_api(args.store)
    rows, excluded = filter_catalogue(raw_rows)
    log.summary(f"{len(rows)} movies to audit; excluded {sum(excluded.values())} ({excluded or 'none'})")

    registry = load_registry(args.picker_dir)
    cache = None
    if raw_fetch is None:
        fetch, tmdb_status = None, "skipped (--skip-tmdb)"
    elif args.no_cache:
        fetch, tmdb_status = raw_fetch, "cache bypassed (--no-cache)"
    else:
        cache = TmdbCache(runs_dir / config.TMDB_CACHE_FILENAME)
        fetch = cache.wrap(raw_fetch)

    try:
        result = run_audit(rows, registry, fetch)
    finally:
        if cache is not None:
            cache.save()
    if cache is not None:
        tmdb_status = f"{cache.hits} cache hits, {cache.misses} fetches"

    if result.promoted:
        save_registry(args.picker_dir, registry)

    report = build_report(result, source=source, audited=len(rows), excluded=excluded, tmdb_status=tmdb_status)
    write_outputs(run_dir, rows, result, report)
    log.summary(report.rstrip())
    log.summary(f"-> {run_dir}")
    return 0
