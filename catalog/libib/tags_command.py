"""`python3 -m catalog libib tags` — tag the newest titles as new arrivals and
mirror Community Picks: Libib's `new arrival` / `community pick` and
Shopify's `new-arrival` / `community-pick` product tags. The numbers
(how many titles, an optional age limit, the unattended change limit) live
in catalog/libib/tag_settings.json.

Shopify is read first (a failed read stops the run before Libib is opened),
then Libib is exported, then every change is listed in one Plan. Like every
writing command it needs approval — except `--unattended`, the daily
GitHub Actions run, which may make at most --max-changes changes; a bigger
list changes nothing and exits 2 until someone reviews it with --dry-run and
re-runs with --approve <code>.

Nothing printed here carries a barcode or call number: the Actions logs
are public. Items are named by title and Libib item id.
"""

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from catalog import config
from catalog.core import log
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.errors import InputShapeError
from catalog.libib.exports import load_libib
from catalog.libib.tag_settings import SETTINGS_PATH, load_settings
from catalog.libib.tags import LibibChange, ShopifyChange, ShopifyState, plan_tags

DEFAULT_REPORT_DIR = "libib-tags"


@dataclass
class TagDeps:
    read_shopify: Callable[[], ShopifyState]
    export_libib: Callable[[Path], tuple[Path, Path]]
    write_shopify: Callable[[list[ShopifyChange]], list[dict]]
    edit_libib: Callable[[list[LibibChange], Path], list[dict]]
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))


def register(sub) -> None:
    p = sub.add_parser("tags", help="mirror Shopify's new-arrival / Community Pick tags into Libib (browser)")
    approval = p.add_mutually_exclusive_group()
    approval.add_argument("--dry-run", action="store_true",
                          help="list every change and print an approval code; change nothing")
    approval.add_argument("--approve", metavar="CODE",
                          help="make the changes a --dry-run listed (the code it printed); refuses if they differ")
    approval.add_argument("--unattended", action="store_true",
                          help="scheduled run: no prompt, but at most --max-changes changes")
    p.add_argument("--max-changes", type=int, default=None,
                   help="with --unattended: refuse a bigger change list (default: max_changes in the settings file)")
    p.add_argument("--settings", default=str(SETTINGS_PATH), help="settings file (default catalog/libib/tag_settings.json)")
    p.add_argument("--store", default=config.DEFAULT_STORE, help=f"Shopify store (default {config.DEFAULT_STORE})")
    p.add_argument("--headless", action="store_true", help="no visible browser window")
    p.add_argument("--report-dir", default=DEFAULT_REPORT_DIR,
                   help=f"where each run's CSV report goes (default {DEFAULT_REPORT_DIR}/)")
    log.add_verbosity_args(p)
    p.set_defaults(func=run_tags_command)


def default_deps(args) -> TagDeps:
    from catalog.libib import tag_editor, transfer, tags_shopify

    store = tags_shopify.store_from_env(args.store)
    email, password = config.require_env(config.ENV_LIBIB_EMAIL), config.require_env(config.ENV_LIBIB_PASSWORD)
    return TagDeps(
        read_shopify=lambda: tags_shopify.read_state(store.gql),
        export_libib=lambda dest: transfer.run_browser_export(email, password, dest, args.headless),
        write_shopify=lambda changes: tags_shopify.write_changes(store.gql, changes),
        edit_libib=lambda changes, report: tag_editor.run_tag_editor(changes, report, email, password, args.headless),
    )


def _libib_line(c: LibibChange) -> str:
    edits = " ".join([*(f"+ {t}" for t in sorted(c.add)), *(f"- {t}" for t in sorted(c.remove))])
    return f"libib    {edits:<34} {c.title}  [item {c.item_id}]"


def _shopify_line(c: ShopifyChange) -> str:
    return f"shopify  {'+' if c.action == 'add' else '-'} {c.tag:<32} {c.title}"


def run_tags_command(args, deps: TagDeps | None = None, stdin=None) -> int:
    log.setup_logging(None, log.verbosity(args))
    log.header(f"libib tags — {args.store}")
    settings = load_settings(args.settings)
    max_changes = args.max_changes if args.max_changes is not None else settings.max_changes
    deps = deps or default_deps(args)

    state = deps.read_shopify()
    with tempfile.TemporaryDirectory() as tmp:
        barcodes, library = deps.export_libib(Path(tmp))
        items = load_libib(barcodes, library)
    if not items:
        raise InputShapeError("Libib export has no Rental Library items — not changing anything")

    tags = plan_tags(items, state, settings, deps.now())
    to_libib, to_shopify = tags.libib, tags.shopify
    count = len(to_libib) + len(to_shopify)
    age = settings.new_arrivals_max_age_days
    rule = f"newest {settings.new_arrivals_count} titles" + (f", at most {age} days old" if age else "")
    plan = Plan(
        title="libib tags",
        count=count,
        summary=[f"New arrivals: the {rule} — {tags.new_arrival_titles} titles qualify",
                 f"Shopify: {len(state.rentals)} rentals, {len(state.picked)} Community Picks",
                 f"Libib: {len(items)} items, {len(to_libib)} to retag",
                 f"Shopify tags: {len(to_shopify)} to change"],
        samples=[*map(_libib_line, to_libib), *map(_shopify_line, to_shopify)],
        warnings=[f"unmatched: {u.title} — {u.reason}" for u in tags.unmatched],
    )

    if args.unattended and count > max_changes:
        for line in plan.render().splitlines():
            log.summary(line)
        log.summary(f"{count} changes is over the unattended limit of {max_changes} — nothing changed. "
                    "Review with --dry-run and re-run with --approve <code>.")
        return 2
    if not confirm(plan, dry_run=args.dry_run, approve=args.approve, stdin=stdin, preapproved=args.unattended):
        return 0

    results = deps.write_shopify(to_shopify) if to_shopify else []
    if to_libib:
        report = Path(args.report_dir) / f"{datetime.now():%Y-%m-%d-%H%M%S}.csv"
        results += deps.edit_libib(to_libib, report)
        log.summary(f"Libib report: {report}")
    errors = [r for r in results if r["status"] == "error"]
    for r in errors:
        log.summary(f"  ERROR  {r['title']}: {r['message']}")
    counts = {s: sum(r["status"] == s for r in results) for s in ("updated", "skipped", "error")}
    log.summary(f"Done: {counts['updated']} updated, {counts['skipped']} skipped, {counts['error']} errors.")
    return 1 if errors else 0
