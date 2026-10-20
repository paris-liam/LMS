"""`python3 -m catalog duplicates` — count products that are copies of the same
movie + format (read-only). Reads the latest audit snapshot and writes
duplicates.csv, duplicate-editions.csv and duplicates-summary.txt into that
run folder."""

import argparse
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.runs import resolve_run
from catalog.duplicates.match import edition_pairs, find_groups, product_format
from catalog.duplicates.report import write_reports
from catalog.shopify.snapshot import load_snapshot


def register(subparsers) -> None:
    p = subparsers.add_parser("duplicates", help="count copies of the same movie + format (read-only)")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def run_command(args) -> int:
    run_dir = resolve_run(Path(args.runs_dir), args.run)
    log.setup_logging(None, log.verbosity(args))
    log.header(f"duplicates — audit run {run_dir.name}")
    rows = load_snapshot(run_dir / "snapshot.json")
    groups, unclassifiable = find_groups(rows)
    pairs = edition_pairs([r for r in rows if product_format(r)])
    paths = write_reports(run_dir, rows, groups, unclassifiable, pairs)
    for line in paths["summary"].read_text(encoding="utf-8").splitlines():
        log.summary(line)
    for path in paths.values():
        log.summary(f"-> {path}")
    return 0
