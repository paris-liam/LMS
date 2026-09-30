#!/usr/bin/env python3
"""One-time regroup of the hosted review picker (CHECKLIST item 13).

Replaces the two by-reason queues (ambiguous-queue, unmatched-queue) with
groups by product type: `rentals`, then `floor-sale-01`, `floor-sale-02`, ...
of up to 100, and `untyped` for anything tagged neither.

 * Cards come from the latest audit's picker-bucket findings. A card already in
   an old queue keeps its stored TMDB candidates; a flagged product that was
   never queued gets fresh candidates.
 * Cards for products the audit no longer flags are dropped.
 * The handle index is updated in the same step, so `apply` accepts picks from
   the new group ids.
 * The old queues and the six 8/31 + 9/2 groups are marked "hidden" in
   batches.json: off the client's launcher, but their data/*.json picks are
   still read by `apply`.

Like every command that writes: --dry-run lists every change and prints an
approval code; --approve CODE makes exactly those changes.

  python3 scripts/regroup-picker.py --dry-run
  python3 scripts/regroup-picker.py --approve CODE [--no-git-sync]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from catalog import config  # noqa: E402
from catalog.core import log  # noqa: E402
from catalog.core.git_sync import sync_review_picker  # noqa: E402
from catalog.core.plan import Plan, add_approval_args, confirm  # noqa: E402
from catalog.core.registry import load_registry, save_registry  # noqa: E402
from catalog.core.runs import resolve_run  # noqa: E402
from catalog.picker.push import (FLOOR_SALE_GROUP_SIZE, RENTALS_GROUP, UNTYPED_GROUP,  # noqa: E402
                                 floor_sale_group)
from catalog.picker.queues import load_products, save_products, update_manifest, write_launcher  # noqa: E402
from catalog.picker.page import build_hosted_picker_html  # noqa: E402
from catalog.tmdb.cache import TmdbCache  # noqa: E402
from catalog.tmdb.candidates import collect_products, rental_or_floor_sale  # noqa: E402
from catalog.tmdb.client import make_fetcher  # noqa: E402

OLD_QUEUES = ("ambiguous-queue", "unmatched-queue")


def plan_regroup(flagged, tags_by_handle, registry, old_cards, review_by_handle):
    """Pure. Returns (groups, dropped, fresh):
    groups  {group id: [handle, ...]} in card order;
    dropped handles queued in an old queue that the audit no longer flags;
    fresh   flagged handles with no stored card (need TMDB candidates)."""
    dropped = sorted(h for h, e in registry.items()
                     if e.get("status") == "queued" and e.get("batch") in OLD_QUEUES and h not in flagged)
    cards = []   # (type, title, handle)
    fresh = []
    for handle in sorted(flagged):
        entry = registry.get(handle)
        if entry is not None and not (entry.get("status") == "queued" and entry.get("batch") in OLD_QUEUES):
            continue  # applied / resolved / skipped / already in a new group: not ours to move
        if handle in old_cards:
            title = old_cards[handle]["title"]
        elif handle in review_by_handle:
            title = review_by_handle[handle]["Title"]
            fresh.append(handle)
        else:
            continue  # flagged but no card and no review entry (shouldn't happen)
        cards.append((rental_or_floor_sale(tags_by_handle.get(handle, "")), title.lower(), handle))
    groups = {}
    rentals = [h for t, _, h in sorted(cards) if t == "Rental"]
    floor = [h for t, _, h in sorted(cards) if t == "Floor Sale"]
    untyped = [h for t, _, h in sorted(cards) if t == ""]
    if rentals:
        groups[RENTALS_GROUP] = rentals
    for i in range(0, len(floor), FLOOR_SALE_GROUP_SIZE):
        groups[floor_sale_group(i // FLOOR_SALE_GROUP_SIZE + 1)] = floor[i:i + FLOOR_SALE_GROUP_SIZE]
    if untyped:
        groups[UNTYPED_GROUP] = untyped
    return groups, dropped, fresh


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="audit run id (default: the latest complete run)")
    parser.add_argument("--no-git-sync", action="store_true")
    parser.add_argument("--runs-dir", default=str(config.RUNS_DIR))
    parser.add_argument("--picker-dir", default=str(config.PICKER_DIR))
    add_approval_args(parser)
    log.add_verbosity_args(parser)
    args = parser.parse_args(argv)

    run_dir = resolve_run(args.runs_dir, args.run)
    log.setup_logging(run_dir / "regroup-picker.log", log.verbosity(args))
    picker_dir = Path(args.picker_dir)
    registry = load_registry(picker_dir)

    with open(run_dir / "findings.csv", encoding="utf-8", newline="") as f:
        flagged = {r["handle"] for r in csv.DictReader(f) if r["bucket"] == "picker"}
    snapshot = json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))
    tags_by_handle = {r["Handle"]: r.get("Tags", "") for r in snapshot}
    review = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))
    review_by_handle = {}
    for entry in review:
        review_by_handle.setdefault(entry["Handle"], entry)
    old_cards = {p["handle"]: p for q in OLD_QUEUES for p in load_products(picker_dir, q)}

    groups, dropped, fresh = plan_regroup(flagged, tags_by_handle, registry, old_cards, review_by_handle)
    moved = sum(len(v) for v in groups.values())
    title_of = lambda h: (old_cards.get(h) or {}).get("title") or review_by_handle.get(h, {}).get("Title", h)  # noqa: E731
    message = f"review-picker: regroup into {', '.join(f'{g} ({len(v)})' for g, v in groups.items())} (audit {run_dir.name})"

    samples = [f"{h} ({title_of(h)}): {registry[h]['batch']} -> {g}"
               for g, hs in groups.items() for h in hs if h in registry]
    samples += [f"{h} ({title_of(h)}): NEW card (TMDB lookup) -> {g}"
                for g, hs in groups.items() for h in hs if h not in registry]
    samples += [f"{h} ({title_of(h)}): card DROPPED (no longer flagged by the audit)" for h in dropped]
    plan = Plan(
        title="regroup picker",
        count=moved + len(dropped),
        summary=[f"{g}: {len(v)} cards" for g, v in groups.items()]
        + [f"{len(fresh)} new cards need TMDB candidates; {len(dropped)} cards dropped",
           f"hidden from the launcher (picks still read by apply): {', '.join(OLD_QUEUES)} + every other existing group",
           "registry: moved handles point at their new group; dropped handles are removed",
           "git: " + ("skipped (--no-git-sync)" if args.no_git_sync
                      else f'commit + push {config.PICKER_REL} on {config.PICKER_BRANCH}: "{message}"')],
        samples=samples,
    )
    if not confirm(plan, dry_run=args.dry_run, approve=args.approve):
        return 0

    fetched = {}
    if fresh:
        cache = TmdbCache(Path(args.runs_dir) / config.TMDB_CACHE_FILENAME)
        try:
            products = collect_products([review_by_handle[h] for h in fresh],
                                        cache.wrap(make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))),
                                        sleep_fn=lambda s: None, progress_fn=log.progress)
        finally:
            cache.save()
        fetched = {p["handle"]: p for p in products}

    for group, handles in groups.items():
        cards = []
        for h in handles:
            card = dict(old_cards.get(h) or fetched[h])
            card["tag"] = rental_or_floor_sale(tags_by_handle.get(h, ""))
            cards.append(card)
        save_products(picker_dir, group, cards)
        (picker_dir / group).mkdir(parents=True, exist_ok=True)
        (picker_dir / group / "index.html").write_text(build_hosted_picker_html(cards, group), encoding="utf-8")
        data_file = picker_dir / "data" / f"{group}.json"
        if not data_file.exists():
            data_file.write_text("[]", encoding="utf-8")
        for h in handles:
            registry[h] = {"batch": group, "status": "queued"}
        update_manifest(picker_dir, group, len(cards))
    for h in dropped:
        del registry[h]
    save_registry(picker_dir, registry)

    manifest_path = picker_dir / "batches.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest:
        if entry["batch_id"] not in groups:
            entry["hidden"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_launcher(picker_dir)
    log.summary(f"regrouped {moved} cards into {len(groups)} groups; dropped {len(dropped)}.")

    if args.no_git_sync:
        log.summary(f"git sync skipped — commit and push {config.PICKER_REL} to publish.")
        return 0
    outcome = sync_review_picker(config.REPO_ROOT, config.PICKER_REL, message, log_fn=log.summary,
                                 deploy_branch=config.PICKER_BRANCH, remote=config.PICKER_REMOTE)
    if not outcome.get("synced") and outcome.get("reason") != "nothing to commit":
        log.summary(f"Note: {config.PICKER_REL} was updated locally but not published ({outcome.get('reason')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
