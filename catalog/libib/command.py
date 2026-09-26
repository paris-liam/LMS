"""`python3 -m catalog libib <diff|prepare|mark-imported|fix|status>` — keep
Libib 1:1 with the Shopify snapshot's rentals.

diff writes its run folder and libib-sync/_state.json (promotions, one-time
poster_src migration; a pre-change copy is kept in the run folder) and asks
nothing. prepare / mark-imported / fix show a plan and ask first.
"""

import argparse
import csv
import shutil
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.runs import resolve_run
from catalog.errors import NoRunError
from catalog.libib.diff import BLOCKED_COLUMNS, DRIFT_COLUMNS, ELIGIBLE_COLUMNS, ORPHAN_COLUMNS, diff
from catalog.libib.exports import DEFAULT_COLLECTION, load_libib
from catalog.libib.state import counts_by_status, load_state, migrate_poster_src, save_state, state_path
from catalog.shopify.snapshot import load_snapshot


def _common(p, needs_run: bool = True) -> None:
    if needs_run:
        p.add_argument("--run", help="audit run id (default: the latest complete run)")
        p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--sync-dir", default=str(config.LIBIB_SYNC_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)


def register(subparsers) -> None:
    libib = subparsers.add_parser("libib", help="compare and sync Libib with the Shopify snapshot")
    sub = libib.add_subparsers(dest="libib_command", required=True, metavar="<libib command>")

    p = sub.add_parser("diff", help="compare Libib's exports with the latest audit snapshot")
    p.add_argument("--barcode-export", required=True, help="Libib item/barcode export CSV")
    p.add_argument("--collection-export", required=True, help="Libib collection export CSV")
    p.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"Libib collection (default {DEFAULT_COLLECTION!r})")
    _common(p)
    p.set_defaults(func=run_diff_command)

    p = sub.add_parser("status", help="count tracked handles per state")
    _common(p, needs_run=False)
    p.set_defaults(func=run_status_command)


def _libib_dir(args) -> tuple[Path, Path]:
    run_dir = resolve_run(args.runs_dir, args.run)
    out = run_dir / "libib"
    out.mkdir(exist_ok=True)
    return run_dir, out


def run_diff_command(args) -> int:
    run_dir, out = _libib_dir(args)
    log.setup_logging(out / "diff.log", log.verbosity(args))
    log.header(f"libib diff — audit run {run_dir.name}")
    rows = load_snapshot(run_dir / "snapshot.json")
    items = load_libib(args.barcode_export, args.collection_export, args.collection)
    log.summary(f"{len(items)} Libib items in {args.collection or 'all collections'}")

    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    migrated = migrate_poster_src(state, {r["Handle"]: r for r in rows})
    result = diff(rows, items, state)

    write_csv(out / "drift.csv", DRIFT_COLUMNS, result.drift)
    write_csv(out / "eligible.csv", ELIGIBLE_COLUMNS, result.eligible)
    write_csv(out / "orphans.csv", ORPHAN_COLUMNS, result.orphans)
    write_csv(out / "blocked.csv", BLOCKED_COLUMNS, result.blocked)

    if migrated or result.promoted:
        if state_path(sync_dir).exists():
            shutil.copyfile(state_path(sync_dir), out / "state-before.json")
        save_state(sync_dir, state)

    drift_handles = {d["handle"] for d in result.drift}
    lines = [
        f"libib items:  {len(items)} ({args.collection or 'all collections'})",
        f"in sync:      {len(result.in_sync)} rentals",
        f"drift:        {len(drift_handles)} rentals, {len(result.drift)} fields -> drift.csv",
        f"eligible:     {len(result.eligible)} rentals missing from Libib -> eligible.csv",
        f"incomplete:   {len(result.incomplete)} rentals missing from Libib but not complete in Shopify",
        f"orphans:      {len(result.orphans)} Libib items (no rental / duplicates) -> orphans.csv",
        f"blocked:      {len(result.blocked)} rentals with a bad or shared barcode -> blocked.csv",
        f"state:        {len(result.promoted)} promoted to done, {migrated} poster_src migrated",
    ]
    (out / "libib-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        log.summary(line)
    log.summary(f"-> {out}")
    return 0


def run_status_command(args) -> int:
    log.setup_logging(None, log.verbosity(args))
    state = load_state(args.sync_dir)
    if not state:
        log.summary("No handles tracked yet.")
        return 0
    for status, count in sorted(counts_by_status(state).items()):
        log.summary(f"{status}: {count}")
    return 0
