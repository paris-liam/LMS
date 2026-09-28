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


def completed_calls(report_path) -> set[str]:
    """Call numbers a previous (possibly stopped) fixer run finished without
    an error — its report is written row by row, so it survives a stop."""
    path = Path(report_path)
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {r["call_number"].strip() for r in csv.DictReader(f)
                if r.get("call_number") and "error" not in (r.get("barcode_status"), r.get("content_status"))}


def archive_report(report_path) -> Path | None:
    """Move an earlier report aside (ready.sync-report.N.csv) so a resumed
    run doesn't overwrite the record of what the stopped run did."""
    path = Path(report_path)
    if not path.exists():
        return None
    n = 1
    while (target := path.with_name(f"{path.stem}.{n}{path.suffix}")).exists():
        n += 1
    path.rename(target)
    return target


def confirmed_remaps(drift_rows: list[dict], map_rows: list[dict]) -> dict[str, str]:
    """handle -> old Libib call number, for call_number drift that a reprint
    map confirms exactly: same handle, Libib still carries the map's old
    number, and Shopify carries the map's new one. Anything less exact stays
    a manual fix — renumbering the wrong Libib item is hard to notice."""
    pairs = {((m.get("handle") or "").strip(), (m.get("old_barcode") or "").strip(),
              (m.get("new_barcode") or "").strip()) for m in map_rows}
    return {d["handle"]: d["libib"].strip() for d in drift_rows
            if d["field"] == "call_number" and (d["handle"], d["libib"].strip(), d["shopify"].strip()) in pairs}


def drift_targets(drift_rows: list[dict], remaps: dict[str, str] | None = None) -> tuple[dict[str, set], list[str]]:
    """Handles whose drift the fixer can repair, and handles that need a
    person. A call_number drift needs a person (the fixer finds items by call
    number) unless `remaps` confirms the old number to renumber from."""
    remaps = remaps or {}
    fields: dict[str, set] = {}
    for d in drift_rows:
        fields.setdefault(d["handle"], set()).add(d["field"])
    fixable = set(FIXABLE_FIELDS)
    manual = sorted(h for h, f in fields.items() if not f <= (fixable | {"call_number"} if h in remaps else fixable))
    return {h: f for h, f in fields.items() if h not in manual}, manual


def drift_ready_rows(fields_by_handle: dict, rows_by_handle: dict, poster_paths: dict[str, str],
                     remaps: dict[str, str] | None = None) -> list[dict]:
    remaps = remaps or {}
    ready = []
    for handle in sorted(fields_by_handle):
        row = rows_by_handle[handle]
        call = (row.get("Variant Barcode") or "").strip()
        image = poster_paths.get(call, "") if "poster" in fields_by_handle[handle] else ""
        out = ready_row(row, image)
        if "call_number" in fields_by_handle[handle]:
            out["old_call_number"] = remaps.get(handle, "")
        ready.append(out)
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


def run_login_check(email: str, password: str, call_number: str, headless: bool, screenshot) -> str | None:
    """Read-only: log in, force the Rental Library scope, open one item by call
    number. Returns None when all of it works, else the failing step and error
    (a screenshot of the page is saved). For checking a new machine — e.g. a
    cloud box whose address Libib might challenge — before running the fixer."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright is not installed for this Python (pip install playwright; python -m playwright install chromium)"
    from catalog.libib import browser

    step = "launch browser"
    with sync_playwright() as p:
        try:
            chromium = p.chromium.launch(headless=headless)
            page = chromium.new_page()
            step = "login"
            browser.login(page, email, password)
            step = f"open item {call_number}"
            err = browser.open_item(page, call_number)
            if err:
                raise RuntimeError(err[1])
            return None
        except Exception as exc:
            try:
                page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                pass
            return f"{step}: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        finally:
            try:
                chromium.close()
            except Exception:
                pass


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
