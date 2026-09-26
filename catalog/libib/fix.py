"""`libib fix` core: build the fixer's input, run the browser fixer, and turn
its report into state changes.

Playwright is imported inside run_fixer only, so every other catalog command
runs on plain Python. Run this command with .venv-libib/bin/python.
"""

import csv
from pathlib import Path

from catalog.core import log
from catalog.errors import CatalogError
from catalog.libib.columns import ready_row
from catalog.libib.diff import FIXABLE_FIELDS

REPORT_COLUMNS = ["call_number", "barcode_status", "content_status", "message"]


def read_ready(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if (row.get("call_number") or "").strip()]


def drift_targets(drift_rows: list[dict]) -> tuple[dict[str, set], list[str]]:
    """Handles whose drift the fixer can repair, and handles that need a
    person (a call_number drift: the fixer finds items by call number)."""
    fields: dict[str, set] = {}
    for d in drift_rows:
        fields.setdefault(d["handle"], set()).add(d["field"])
    manual = sorted(h for h, f in fields.items() if not f <= set(FIXABLE_FIELDS))
    return {h: f for h, f in fields.items() if h not in manual}, manual


def drift_ready_rows(fields_by_handle: dict, rows_by_handle: dict, poster_paths: dict[str, str]) -> list[dict]:
    ready = []
    for handle in sorted(fields_by_handle):
        row = rows_by_handle[handle]
        call = (row.get("Variant Barcode") or "").strip()
        image = poster_paths.get(call, "") if "poster" in fields_by_handle[handle] else ""
        ready.append(ready_row(row, image))
    return ready


def apply_report(state: dict, results: list[dict], handle_by_call: dict, rows_by_handle: dict) -> dict:
    counts = {"ok": 0, "needs_review": 0, "posters": 0, "untracked": 0}
    for r in results:
        handle = handle_by_call.get(r["call_number"])
        if handle is None:
            counts["untracked"] += 1
            continue
        entry = state.setdefault(handle, {"call_number": r["call_number"]})
        if r["barcode_status"] == "error" or r["content_status"] == "error":
            entry.update(status="needs-review", note=r["message"][:300])
            counts["needs_review"] += 1
            continue
        if entry.get("status") != "done":
            entry["status"] = "imported"  # the next diff confirms and promotes it
        entry.pop("note", None)
        counts["ok"] += 1
        if r["content_status"] == "updated" and "poster" in r["message"]:
            src = ((rows_by_handle.get(handle) or {}).get("Image Src") or "").strip()
            if src:
                entry["poster_src"] = src
                counts["posters"] += 1
    return counts


def run_fixer(rows: list[dict], report_path, email: str, password: str, headless: bool) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CatalogError("Playwright is not installed for this Python. Run the fixer with the Libib venv:\n"
                           "  .venv-libib/bin/python -m catalog libib fix …") from None
    from catalog.libib import browser

    report_path = Path(report_path)
    results: list[dict] = []
    with sync_playwright() as p, report_path.open("w", newline="", encoding="utf-8") as report_f:
        writer = csv.DictWriter(report_f, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        report_f.flush()
        chromium = p.chromium.launch(headless=headless)
        page = chromium.new_page()
        browser.login(page, email, password)
        for index, row in enumerate(rows, start=1):
            call = row["call_number"].strip()
            try:
                barcode_status, content_status, message = browser.sync_item(page, row)
            except Exception as exc:  # keep going across a whole batch
                barcode_status, content_status, message = "error", "error", f"{type(exc).__name__}: {exc}"
            outcome = {"call_number": call, "barcode_status": barcode_status,
                       "content_status": content_status, "message": message}
            results.append(outcome)
            writer.writerow(outcome)
            report_f.flush()
            log.progress(index, len(rows), call, f"{barcode_status}/{content_status} — {message}")
        chromium.close()
    return results
