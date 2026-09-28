"""`python3 -m catalog apply` — turn the latest audit's auto-fixes plus the
client's picks into Shopify import CSVs (runs/<id>/import/*.csv).

Picks are read from the branch the hosted picker commits to (origin/main)
via git fetch + git show, so any local branch works; --local-picks reads the
working tree instead. Nothing is written to Shopify: you import the CSVs.
"""

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from catalog import config
from catalog.apply.csv_groups import build_import_files, warnings_for, write_import_files
from catalog.apply.merge import AUTO_FIX_SOURCE, CHANGE_COLUMNS, merge
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.git_sync import fetch_branch, sync_review_picker
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
    p.add_argument("--no-git-sync", action="store_true",
                   help=f"don't commit/publish the registry and imports/ to {config.PICKER_BRANCH}")
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    p.add_argument("--imports-dir", default=str(config.IMPORTS_DIR), help=argparse.SUPPRESS)
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


def _mirror(files: list[Path], target: Path) -> None:
    """Make `target` hold exactly `files` (a re-apply rewrites the whole set)."""
    target.mkdir(parents=True, exist_ok=True)
    names = {f.name for f in files}
    for old in target.glob("*.csv"):
        if old.name not in names:
            old.unlink()
    for f in files:
        shutil.copy2(f, target / f.name)


def _publish(args, sync_fn, picker_dir: Path, run_id: str) -> bool:
    """Commit + push the registry and this run's imports to the deploy branch.
    True when published."""
    if args.no_git_sync:
        return False
    try:
        rels = [str(Path(p).resolve().relative_to(config.REPO_ROOT.resolve()))
                for p in (picker_dir, Path(args.imports_dir))]
    except ValueError:
        log.summary("picker or imports folder is outside the repo — git sync skipped.")
        return False
    outcome = sync_fn(config.REPO_ROOT, rels, f"apply: import CSVs + registry (audit {run_id})",
                      log_fn=log.summary, deploy_branch=config.PICKER_BRANCH, remote=config.PICKER_REMOTE)
    if outcome.get("synced"):
        log.summary(f"Published to {config.PICKER_BRANCH}: download the CSVs from {rels[1]}/{run_id}/ on GitHub.")
        return True
    if outcome.get("reason") != "nothing to commit":
        log.summary(f"Note: not published ({outcome.get('reason')}).")
    return False


def run_command(args, read_text=None, stdin=None, sync_fn=sync_review_picker) -> int:
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

    # The working-tree registry is the one we update; the deploy branch's
    # registry (when reading picks from it) also knows cards queued on main
    # since this branch forked. Merge sees both; local entries win.
    registry = load_registry(picker_dir)
    view, registry_warning = registry, None
    if not args.local_picks:
        remote_text = read_text("data/_handle-index.json")
        if remote_text is not None:
            remote = json.loads(remote_text)
            view = {**remote, **registry}
            differing = [h for h in set(remote) | set(registry) if remote.get(h) != registry.get(h)]
            if differing:
                registry_warning = (f"the working-tree registry differs from {source} for {len(differing)} handles — "
                                    f"commit {config.PICKER_REL}/data/_handle-index.json and merge it into "
                                    f"{config.PICKER_BRANCH} so both agree")
    result = merge(rows, autofix, picks, view, run_id=run_dir.name)
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
        warnings=warnings_for(files, result.changes) + ([registry_warning] if registry_warning else []),
        details_path=details,
    )
    import_dir = run_dir / "import"
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0  # never touch import/ without approval

    paths = write_import_files(import_dir, files)
    for handle, values in result.applied.items():
        mark_applied(registry, handle, run_dir.name, values)
    for handle in result.skipped:
        mark_skipped(registry, handle)
    mark_resolved(registry, result.resolved)
    save_registry(picker_dir, registry)

    published = Path(args.imports_dir).resolve() / run_dir.name
    _mirror(paths, published)
    log.summary(f"wrote {len(paths)} file(s) to {import_dir} (copy in {published}):")
    for path in paths:
        log.summary(f"  {path.name}")
    log.summary("Import each in Shopify admin → Products → Import, with 'Overwrite products with matching handles' on.")
    log.summary("The next audit confirms each applied pick landed (applied -> resolved).")
    if not _publish(args, sync_fn, picker_dir, run_dir.name):
        log.summary(f"The registry changed in the working tree ({config.PICKER_REL}/data/_handle-index.json) — "
                    f"commit it and merge it into {config.PICKER_BRANCH}; if it is lost, the next apply "
                    "won't know these handles were already applied.")
    return 0
