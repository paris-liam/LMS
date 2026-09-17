"""Set each Libib copy's physical barcode to match its call_number.

Libib auto-assigns a random SKU barcode to every copy on import, separate
from the `call_number` field (our internal LMS serial). There is no CSV or
REST-API path to bulk-set that per-copy barcode -- Libib's Batch Edit
explicitly excludes it, and the field is locked behind a per-item
"Unlock this field" confirmation in the UI (see
claudedocs/2026-09-14-libib-bulk-upload-plan.md for the wider CSV-import
research). This script drives that UI with Playwright instead of clicking
through it by hand.

For each call_number in the input CSV, it:
  1. Searches Libib for `call:<call_number>` (must return exactly one item)
  2. Opens the item, expands its Copies table (must be exactly one copy)
  3. Unlocks the barcode field, sets it to call_number, saves
  4. Skips items whose barcode already matches (safe to re-run)

Items with 0 or >1 search matches, or >1 copy, are left alone and logged
as needing manual review -- this script never guesses which item/copy to
touch.

Usage:
    python3 formatting-scripts/libib_barcode_update.py libib-import-9.16/libib-import-100.csv

Writes a report CSV next to the input (call_number, status, message).

Credentials are hardcoded below (LIBIB_EMAIL/LIBIB_PASSWORD) at the user's
request -- this repo has a GitHub remote (paris-liam/LMS), so this commits
the Libib account password to git history there.
"""

import argparse
import csv
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

LIBIB_LOGIN_URL = "https://www.libib.com/login"
LIBIB_EMAIL = "hello@littlemoviestore.com"
LIBIB_PASSWORD = "YoFuckBezos69!"


def read_call_numbers(csv_path: Path) -> list:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["call_number"].strip() for row in reader if row.get("call_number", "").strip()]


def login(page: Page, email: str, password: str) -> None:
    page.goto(LIBIB_LOGIN_URL)
    page.get_by_role("textbox", name="Email").fill(email)
    page.get_by_role("button", name="Next").click()
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url("**/library", timeout=15000)


def update_barcode(page: Page, call_number: str):
    """Returns (status, message). status is one of updated/skipped/error."""
    # A previously opened item's detail panel (#item-details-view) doesn't
    # unmount when a new search runs, and it renders its own stray
    # .item-title -- inflating the next row's match count and making it
    # look falsely ambiguous. Force a clean page for every row.
    page.goto("https://www.libib.com/library")
    search = page.locator("#search")
    search.fill(f"call:{call_number}")
    search.press("Enter")

    items = page.locator(".item-title")
    try:
        items.first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "error", "no item found for this call number"
    # Let any remaining matches in the same result batch render before counting.
    page.wait_for_timeout(400)
    count = items.count()
    if count > 1:
        return "error", f"{count} items matched this call number -- ambiguous"

    items.first.click()
    try:
        page.wait_for_selector(".li-copies a", timeout=10000)
    except PlaywrightTimeoutError:
        return "error", "item page did not load a Copies link"
    page.locator(".li-copies a").click()

    rows = page.locator("table tbody tr")
    try:
        rows.first.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        return "error", "no copy rows found after expanding Copies"
    row_count = rows.count()
    if row_count > 1:
        return "error", f"{row_count} copies on this item -- needs manual review"

    row = rows.first
    barcode_input = row.locator(".copy-barcode-value input")
    current_value = barcode_input.input_value()
    if current_value == call_number:
        return "skipped", "barcode already matches call_number"

    row.locator(".copy-lock-icon .lock-icon").click()
    try:
        override_btn = page.locator(".modal-delete")
        override_btn.wait_for(state="visible", timeout=3000)
        override_btn.click()
    except PlaywrightTimeoutError:
        pass  # field may already be unlocked from a prior run

    barcode_input.fill(call_number)
    row.locator(".save-copy-button").click()
    page.wait_for_timeout(600)

    # The input's in-memory value proves nothing -- it still shows what we
    # just typed regardless of whether the save actually persisted (seen in
    # practice: ~8% of rows report success this way but the server keeps
    # the old value). Reload the item from scratch and re-read.
    verified_value = _read_barcode_fresh(page, call_number)
    if verified_value != call_number:
        return "error", f"save did not persist -- reloaded value is '{verified_value}'"
    return "updated", "ok"


def _read_barcode_fresh(page: Page, call_number: str) -> str:
    """Re-fetches the item from a clean page load and returns its current
    barcode value, bypassing any client-side state we may have just set."""
    page.goto("https://www.libib.com/library")
    page.locator("#search").fill(f"call:{call_number}")
    page.locator("#search").press("Enter")
    page.locator(".item-title").first.wait_for(state="visible", timeout=8000)
    page.locator(".item-title").first.click()
    page.locator(".li-copies a").first.wait_for(state="visible", timeout=8000)
    page.locator(".li-copies a").first.click()
    page.locator("table tbody tr").first.wait_for(state="visible", timeout=8000)
    return page.locator("table tbody tr").first.locator(".copy-barcode-value input").input_value()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_csv", help="Libib movie-import CSV with a call_number column")
    parser.add_argument("--report", default=None, help="Report CSV path (default: <input>.barcode-report.csv)")
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser window")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N call numbers")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    call_numbers = read_call_numbers(input_path)
    if args.limit:
        call_numbers = call_numbers[: args.limit]
    report_path = Path(args.report) if args.report else input_path.with_suffix(".barcode-report.csv")

    print(f"== {input_path.name}: {len(call_numbers)} call numbers ==")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        login(page, LIBIB_EMAIL, LIBIB_PASSWORD)

        for i, call_number in enumerate(call_numbers, 1):
            try:
                status, message = update_barcode(page, call_number)
            except Exception as exc:  # keep going across a whole batch
                status, message = "error", f"{type(exc).__name__}: {exc}"
            results.append({"call_number": call_number, "status": status, "message": message})
            print(f"[{i}/{len(call_numbers)}] {call_number}: {status} -- {message}")

        browser.close()

    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["call_number", "status", "message"])
        writer.writeheader()
        writer.writerows(results)

    updated = sum(1 for r in results if r["status"] == "updated")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errored = sum(1 for r in results if r["status"] == "error")
    print(f"\n{updated} updated, {skipped} already correct, {errored} need manual review.")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
