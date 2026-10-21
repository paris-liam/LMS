"""`python3 -m catalog backup` — copy Libib and Shopify data into a folder of
CSVs (run daily from the private LMS-data repo). Exit 0 only if every selected
source succeeded; a failed source never stops the other from running."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from catalog import config
from catalog.backup.guard import SourceResult
from catalog.backup.libib import backup_libib
from catalog.errors import CatalogError
from catalog.backup.shopify import backup_shopify, read_store

SOURCES = ("libib", "shopify")


@dataclass
class BackupDeps:
    libib: Callable[[Path], SourceResult]
    shopify: Callable[[Path], SourceResult]


def summary_line(results: list[SourceResult], day: date) -> str:
    parts = ", ".join(f"{r.name} {r.summary}" for r in results)
    return f"Backup {day.isoformat()} — {parts}"


def run_backup(args, deps: BackupDeps) -> int:
    out_dir = Path(args.out)
    selected = [s for s in SOURCES if args.only in (None, s)]
    results = []
    for name in selected:
        try:
            result = getattr(deps, name)(out_dir)
        except CatalogError as exc:  # e.g. a missing env var: report it, still run the other source
            result = SourceResult(name, False, "FAILED", " ".join(str(exc).split()))
        results.append(result)
        print(f"{name}: {result.summary}" if result.ok else f"{name}: FAILED — {result.error}")
    if args.message_file:
        Path(args.message_file).write_text(summary_line(results, args.date) + "\n", encoding="utf-8")
    return 0 if all(r.ok for r in results) else 1


def default_deps(args) -> BackupDeps:
    def libib(out_dir: Path) -> SourceResult:
        email = config.require_env(config.ENV_LIBIB_EMAIL)
        password = config.require_env(config.ENV_LIBIB_PASSWORD)

        def export(dest: Path):
            from catalog.libib.transfer import run_browser_export  # Playwright may not be installed
            return run_browser_export(email, password, dest, headless=args.headless)

        return backup_libib(out_dir, export)

    def shopify(out_dir: Path) -> SourceResult:
        from catalog.shopify import api
        client_id = config.require_env(config.ENV_SHOPIFY_CLIENT_ID)
        client_secret = config.require_env(config.ENV_SHOPIFY_CLIENT_SECRET)
        execute = api.make_executor(args.store, api.request_token(args.store, client_id, client_secret))
        return backup_shopify(out_dir, lambda: read_store(execute, args.store))

    return BackupDeps(libib, shopify)


def _date(text: str) -> date:
    return date.fromisoformat(text)


def _run(args) -> int:
    return run_backup(args, default_deps(args))


def register(subparsers) -> None:
    p = subparsers.add_parser("backup", help="back up Libib and Shopify data to CSV files")
    p.add_argument("--out", required=True, help="folder to write libib/ and shopify/ into")
    p.add_argument("--store", default=config.DEFAULT_STORE, help=f"Shopify store (default {config.DEFAULT_STORE})")
    p.add_argument("--only", choices=SOURCES, help="back up just one source (default both)")
    p.add_argument("--headless", action="store_true", help="run the Libib browser without a window")
    p.add_argument("--message-file", help="write the commit message here")
    p.add_argument("--date", type=_date, default=datetime.now(timezone.utc).date(),
                   help="day for the message, YYYY-MM-DD (default today, UTC)")
    p.set_defaults(func=_run)
