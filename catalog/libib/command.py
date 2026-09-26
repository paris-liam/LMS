"""`python3 -m catalog libib <diff|prepare|mark-imported|fix|status>` — keep
Libib 1:1 with the Shopify snapshot's rentals.

diff writes its run folder and libib-sync/_state.json (promotions, one-time
poster_src migration; a pre-change copy is kept in the run folder) and asks
nothing. prepare / mark-imported / fix show a plan and ask first.
"""

import argparse
import csv
import shutil
import urllib.request
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.core.runs import resolve_run
from catalog.errors import NoRunError
from catalog.libib.diff import BLOCKED_COLUMNS, DRIFT_COLUMNS, ELIGIBLE_COLUMNS, ORPHAN_COLUMNS, diff
from catalog.libib.exports import DEFAULT_COLLECTION, load_libib
from catalog.libib.prepare import download_posters, next_batch_id, write_batch
from catalog.libib.state import (
    IN_FLIGHT, counts_by_status, load_state, migrate_poster_src, save_state, set_status, state_path,
)
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

    p = sub.add_parser("prepare", help="build the next Libib import batch from the diff's eligible rentals")
    p.add_argument("--size", type=int, default=200, help="rentals per batch (default 200)")
    _common(p)
    add_approval_args(p)
    p.set_defaults(func=run_prepare_command)

    p = sub.add_parser("mark-imported", help="record that a batch's import.csv was force-imported into Libib")
    p.add_argument("batch", help="batch id, e.g. batch-0017")
    _common(p, needs_run=False)
    add_approval_args(p)
    p.set_defaults(func=run_mark_imported_command)

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


def _read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_prepare_command(args, download=None, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    eligible_path = run_dir / "libib" / "eligible.csv"
    if not eligible_path.exists():
        raise NoRunError(f"no libib diff for run {run_dir.name} — run `python3 -m catalog libib diff …` first")
    log.setup_logging(run_dir / "libib" / "prepare.log", log.verbosity(args))
    log.header(f"libib prepare — audit run {run_dir.name}")

    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    rows_by_handle = {r["Handle"]: r for r in load_snapshot(run_dir / "snapshot.json")}
    eligible = _read_csv(eligible_path)
    chosen = [e for e in eligible if (state.get(e["handle"]) or {}).get("status") not in IN_FLIGHT][: args.size]
    batch_id = next_batch_id(sync_dir)
    batch_dir = sync_dir / batch_id

    plan = Plan(
        title="libib prepare",
        count=len(chosen),
        summary=[f"{batch_id}: {len(chosen)} rentals (of {len(eligible)} eligible)",
                 f"downloads {len(chosen)} posters and writes {batch_dir}/import.csv + ready.csv",
                 f"state: {len(chosen)} -> queued"],
        samples=[f"{e['call_number']} {e['title']}" for e in chosen],
    )
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0

    rows = [rows_by_handle[e["handle"]] for e in chosen]
    posters, failed = download_posters(rows, batch_dir, download or urllib.request.urlretrieve)
    write_batch(batch_dir, rows, posters)
    for e in chosen:
        set_status(state, e["handle"], "queued", batch=batch_id, call_number=e["call_number"])
    save_state(sync_dir, state)

    if failed:
        log.summary(f"{len(failed)} poster(s) failed to download (ready.csv leaves image_path blank): {', '.join(failed)}")
    log.summary(f"Next: in Libib, Add Items -> CSV -> {batch_dir / 'import.csv'} with Force Import Mode on, then")
    log.summary(f"  python3 -m catalog libib mark-imported {batch_id}")
    log.summary(f"  .venv-libib/bin/python -m catalog libib fix {batch_id}")
    return 0


def run_mark_imported_command(args, stdin=None) -> int:
    log.setup_logging(None, log.verbosity(args))
    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    handles = sorted(h for h, e in state.items() if e.get("batch") == args.batch and e.get("status") == "queued")
    plan = Plan(title="libib mark-imported", count=len(handles),
                summary=[f"{args.batch}: {len(handles)} handles queued -> imported"], samples=handles)
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0
    for handle in handles:
        set_status(state, handle, "imported")
    save_state(sync_dir, state)
    log.summary(f"Next: .venv-libib/bin/python -m catalog libib fix {args.batch}")
    return 0
