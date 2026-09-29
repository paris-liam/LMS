"""`python3 -m catalog picker push` — add the latest audit's picker products to
the hosted review picker, then commit + push tools/review-picker (on main)."""

import argparse
import json
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.git_sync import sync_review_picker
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.core.registry import load_registry, save_registry
from catalog.core.runs import resolve_run
from catalog.picker.push import new_entries_by_queue, push
from catalog.tmdb.cache import TmdbCache
from catalog.tmdb.client import make_fetcher


def register(subparsers) -> None:
    picker = subparsers.add_parser("picker", help="the hosted review picker")
    picker_sub = picker.add_subparsers(dest="picker_command", required=True, metavar="<picker command>")
    p = picker_sub.add_parser("push", help="add the latest audit's picker products to the hosted queues")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--no-git-sync", action="store_true", help="write the queue files but don't commit/push")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    add_approval_args(p)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_push_command)


def run_push_command(args, fetch_fn=None, sync_fn=sync_review_picker, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    log.setup_logging(run_dir / "picker-push.log", log.verbosity(args))
    log.header(f"picker push — audit run {run_dir.name}")

    review = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))
    picker_dir = Path(args.picker_dir)
    registry = load_registry(picker_dir)
    entries = new_entries_by_queue(review, registry)
    total = sum(len(v) for v in entries.values())
    message = (f"review-picker: +{len(entries['ambiguous-queue'])} ambiguous, "
               f"+{len(entries['unmatched-queue'])} unmatched (audit {run_dir.name})")

    raw_fetch = None
    if total and not args.dry_run:  # fail fast on a missing key, before asking
        raw_fetch = fetch_fn or make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))

    plan = Plan(
        title="picker push",
        count=total,
        summary=[f"{queue}: +{len(v)} cards" for queue, v in entries.items()]
        + [f"registry: {total} handles -> queued",
           "git: " + ("skipped (--no-git-sync)" if args.no_git_sync
                      else f'commit + push {config.PICKER_REL} on {config.PICKER_BRANCH}: "{message}"')],
        samples=[f"{e['Handle']} [{e['Kind']}] {e['Reason']}" for v in entries.values() for e in v],
    )
    if not confirm(plan, dry_run=args.dry_run, approve=args.approve, stdin=stdin):
        return 0

    cache = TmdbCache(Path(args.runs_dir) / config.TMDB_CACHE_FILENAME)
    try:
        results = push(entries, picker_dir, registry, cache.wrap(raw_fetch))
    finally:
        cache.save()
    save_registry(picker_dir, registry)
    for queue, outcome in results.items():
        log.summary(f"{queue}: +{outcome['added']} (queue now {outcome['batch_total']})")

    if args.no_git_sync:
        log.summary(f"git sync skipped — commit and push {config.PICKER_REL} from {config.PICKER_BRANCH} to publish.")
        return 0
    try:
        rel = str(picker_dir.resolve().relative_to(config.REPO_ROOT))
    except ValueError:
        log.summary(f"{picker_dir} is outside the repo — git sync skipped.")
        return 0
    outcome = sync_fn(config.REPO_ROOT, rel, message, log_fn=log.summary, deploy_branch=config.PICKER_BRANCH,
                      remote=config.PICKER_REMOTE)
    if not outcome.get("synced") and outcome.get("reason") != "nothing to commit":
        log.summary(f"Note: {rel} was updated locally but not published ({outcome.get('reason')}).")
    return 0
