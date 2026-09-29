"""Automated Libib CSV transfer: export (Settings -> Export Collection/Barcode
Data) and import (Add Items -> CSV Import, Force Import Mode). The page steps
live in browser.py; this module holds the checks around them, which are pure
so they can be tested without Libib.

An import is never trusted on its own: every run exports Libib first (so a
re-run never imports a copy that is already there) and again afterwards, and a
call number only counts as imported once it appears exactly once in that
second export.
"""

import csv
from collections import Counter
from datetime import date
from pathlib import Path

from catalog.core.csv_io import write_csv
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

# Libib's column-matching page auto-matches our headers; these are the ones
# that carry data, so they must land on exactly these Libib fields.
EXPECTED_MAPPINGS = {
    "title": "Title",
    "description": "Description",
    "tags": "Tags",
    "price": "Price",
    "copies": "Copies",
    "call_number": "Call #",
}


def mapping_problems(columns: list[str], selected: list[str]) -> list[str]:
    """Compare Libib's column matching (one selected field per CSV column, in
    order) with EXPECTED_MAPPINGS. Empty list = safe to import."""
    if len(columns) != len(selected):
        return [f"Libib shows {len(selected)} column matchers for {len(columns)} CSV columns"]
    got = dict(zip(columns, selected))
    return [f"{column} is matched to {got.get(column)!r}, expected {field!r}"
            for column, field in EXPECTED_MAPPINGS.items() if got.get(column) != field]


def export_dir(exports_root, today: date | None = None) -> Path:
    """exports/<YYYY-MM-DD>, or -2, -3 … when that day already has one."""
    root = Path(exports_root)
    base = (today or date.today()).isoformat()
    candidate, n = root / base, 1
    while candidate.exists():
        n += 1
        candidate = root / f"{base}-{n}"
    return candidate


def call_counts(barcode_export, collection: str) -> Counter:
    with open(barcode_export, newline="", encoding="utf-8-sig") as f:
        return Counter((r.get("call_number") or "").strip() for r in csv.DictReader(f)
                       if (r.get("collection") or "").strip() == collection and (r.get("call_number") or "").strip())


def read_import_rows(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split_present(rows: list[dict], counts: Counter) -> tuple[list[dict], list[dict]]:
    """(rows still to import, rows whose call number Libib already has)."""
    todo = [r for r in rows if counts.get(r["call_number"].strip(), 0) == 0]
    present = [r for r in rows if counts.get(r["call_number"].strip(), 0) > 0]
    return todo, present


def write_import_rows(path, rows: list[dict]) -> Path:
    write_csv(path, LIBIB_MOVIE_COLUMNS, rows)
    return Path(path)


def verify_imported(calls: list[str], counts: Counter) -> dict[str, list[str]]:
    """Sort a batch's call numbers by what the post-import export shows."""
    out = {"ok": [], "missing": [], "duplicated": []}
    for call in calls:
        n = counts.get(call, 0)
        out["ok" if n == 1 else "missing" if n == 0 else "duplicated"].append(call)
    return out


def run_browser_export(email: str, password: str, dest_dir, headless: bool = True) -> tuple[Path, Path]:
    """Log in and download both exports into dest_dir. Returns (barcodes, collection)."""
    from playwright.sync_api import sync_playwright
    from catalog.libib import browser

    with sync_playwright() as p:
        chromium = p.chromium.launch(headless=headless)
        try:
            page = chromium.new_context(accept_downloads=True).new_page()
            browser.login(page, email, password)
            return browser.export_csvs(page, dest_dir)
        finally:
            chromium.close()


def run_browser_import(email: str, password: str, csv_path, evidence_dir, headless: bool = True) -> None:
    """Log in, upload csv_path with Force Import Mode, check Libib's column
    matching, then Process Import. Screenshots land in evidence_dir."""
    from playwright.sync_api import sync_playwright
    from catalog.libib import browser

    with sync_playwright() as p:
        chromium = p.chromium.launch(headless=headless)
        try:
            page = chromium.new_page()
            browser.login(page, email, password)
            browser.import_csv(page, csv_path, mapping_problems, evidence_dir)
        finally:
            chromium.close()
