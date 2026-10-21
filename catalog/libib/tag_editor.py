"""`libib tags` — the browser loop: set each changed item's tags in Libib,
one login, retries per item, and a CSV report written as it goes.

The report has no barcode column: it may be read off a public CI log.
"""

import csv
from pathlib import Path

from catalog.core import log
from catalog.libib import venv
from catalog.libib.fix import ITEM_ATTEMPTS, RETRY_PAUSE_MS
from catalog.libib.tags import LibibChange

REPORT_COLUMNS = ["item_id", "title", "add", "remove", "status", "message"]


def edit_with_retries(edit, page, change: LibibChange, pause, attempts: int = ITEM_ATTEMPTS) -> tuple[str, str]:
    for attempt in range(attempts):
        try:
            status, message = edit(page, change.barcode, change.add, change.remove)
        except Exception as exc:  # keep going across the whole list
            status, message = "error", f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        if status != "error" or attempt == attempts - 1:
            return status, message
        pause()


def run_tag_editor(changes: list[LibibChange], report_path, email: str, password: str, headless: bool) -> list[dict]:
    sync_playwright = venv.sync_playwright("tags")
    from catalog.libib import browser

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with sync_playwright() as p, report_path.open("w", newline="", encoding="utf-8") as report_f:
        writer = csv.DictWriter(report_f, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        report_f.flush()
        chromium = p.chromium.launch(headless=headless)
        try:
            page = chromium.new_page()
            browser.login(page, email, password)
            for index, change in enumerate(changes, start=1):
                status, message = edit_with_retries(browser.set_item_tags, page, change,
                                                    pause=lambda: page.wait_for_timeout(RETRY_PAUSE_MS))
                outcome = {"item_id": change.item_id, "title": change.title,
                           "add": ", ".join(sorted(change.add)), "remove": ", ".join(sorted(change.remove)),
                           "status": status, "message": message}
                results.append(outcome)
                writer.writerow(outcome)
                report_f.flush()
                log.progress(index, len(changes), change.title, f"{status} — {message}")
        finally:
            chromium.close()
    return results
