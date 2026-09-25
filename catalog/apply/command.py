"""`python3 -m catalog apply` — turn the latest audit's auto-fixes plus the
client's picks into Shopify import CSVs (runs/<id>/import/*.csv).

Picks are read from the branch the hosted picker commits to (origin/main)
via git fetch + git show, so any local branch works; --local-picks reads the
working tree instead. Nothing is written to Shopify: you import the CSVs.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from catalog import config
from catalog.apply.csv_groups import build_import_files, warnings_for, write_import_files
from catalog.apply.merge import AUTO_FIX_SOURCE, CHANGE_COLUMNS, merge
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.git_sync import fetch_branch
from catalog.core.picks import load_picks, local_reader, remote_reader
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.core.registry import load_registry, mark_applied, mark_resolved, mark_skipped, save_registry
from catalog.core.runs import resolve_run
from catalog.errors import CatalogError
from catalog.shopify.snapshot import load_snapshot


def register(subparsers) -> None:
    p = subparsers.add_parser("apply", help="turn auto-fixes and client picks into Shopify import CSVs")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--local-picks", action="store_true",
                   help=f"read picks from the working tree instead of {config.PICKER_REMOTE}/{config.PICKER_BRANCH}")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    add_approval_args(p)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def _pick_reader(args, picker_dir: Path):
    if args.local_picks:
        return local_reader(picker_dir), f"working tree ({picker_dir})"
    ref = f"{config.PICKER_REMOTE}/{config.PICKER_BRANCH}"
    try:
        fetch_branch(config.REPO_ROOT, config.PICKER_REMOTE, config.PICKER_BRANCH)
    except RuntimeError as exc:
        raise CatalogError(f"{exc}\nRe-run with --local-picks to use the working tree's picks.") from None
    return remote_reader(config.REPO_ROOT, ref, config.PICKER_REL), ref


def run_command(args, read_text=None, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    log.setup_logging(run_dir / "apply.log", log.verbosity(args))
    log.header(f"apply — audit run {run_dir.name}")

    rows = load_snapshot(run_dir / "snapshot.json")
    autofix = json.loads((run_dir / "autofix.json").read_text(encoding="utf-8"))
    picker_dir = Path(args.picker_dir)
    if read_text is None:
        read_text, source = _pick_reader(args, picker_dir)
    else:
        source = "injected reader"
    picks = load_picks(read_text)
    log.summary(f"{len(picks)} picks read from {source}")

    registry = load_registry(picker_dir)
    result = merge(rows, autofix, picks, registry)
    files = build_import_files(result.changes, {r["Handle"]: r for r in rows})

    details = run_dir / "apply-plan.csv"
    write_csv(details, CHANGE_COLUMNS, [asdict(c) for c in result.changes])
    for handle, reason in result.ignored:
        log.detail(f"ignored {handle}: {reason}")

    from_picks = sum(1 for c in result.changes if c.source != AUTO_FIX_SOURCE)
    plan = Plan(
        title="apply",
        count=len(result.changes) + len(result.skipped) + len(result.resolved),
        summary=[f"import/{name}: {len(file_rows)} products" for name, (_, file_rows) in files.items()]
        + [f"changes: {len(result.changes)} ({len(result.changes) - from_picks} auto-fix, {from_picks} from picks)",
           f"registry: {len(result.applied)} -> applied, {len(result.skipped)} -> skipped, "
           f"{len(result.resolved)} -> resolved (already in Shopify)",
           f"ignored: {len(result.ignored)} (see apply.log with -v)"],
        samples=[f"{c.handle} {c.field}: {c.before[:40]!r} -> {c.after[:60]!r} ({c.source})" for c in result.changes],
        warnings=warnings_for(files, result.changes),
        details_path=details,
    )
    import_dir = run_dir / "import"
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        if plan.count == 0 and import_dir.exists():
            write_import_files(import_dir, {})  # nothing left to import: clear stale files
        return 0

    paths = write_import_files(import_dir, files)
    for handle, values in result.applied.items():
        mark_applied(registry, handle, run_dir.name, values)
    for handle in result.skipped:
        mark_skipped(registry, handle)
    mark_resolved(registry, result.resolved)
    save_registry(picker_dir, registry)

    log.summary(f"wrote {len(paths)} file(s) to {import_dir}:")
    for path in paths:
        log.summary(f"  {path.name}")
    log.summary("Import each in Shopify admin → Products → Import, with 'Overwrite products with matching handles' on.")
    log.summary("The next audit confirms each applied pick landed (applied -> resolved).")
    log.summary(f"The registry changed locally ({config.PICKER_REL}/data/_handle-index.json) — "
                "it is published with the next `picker push`, or commit it yourself.")
    return 0
