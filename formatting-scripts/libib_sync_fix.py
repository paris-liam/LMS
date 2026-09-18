"""Fix one Libib item to match its Shopify counterpart on every 1:1 field:
physical barcode, title, description, tags, and poster image -- in a
single item-open, replacing the separate libib_barcode_update.py /
libib_image_update.py passes with one pass per item.

For each row in the input CSV, it:
  1. Searches Libib for `call:<call_number>` (must return exactly one item)
  2. Opens the item detail page (one page load covers both sub-flows below)
  3. Copies tab: unlocks and sets the physical barcode to call_number,
     unless it already matches (same logic as libib_barcode_update.py)
  4. Edit form: sets title/description/tags if they don't already match,
     uploads image_path as the cover (skipped if image_path is blank)
  5. Reloads the item fresh and verifies barcode/title/description/tags
     actually persisted (poster upload isn't independently re-verifiable
     -- see libib_image_update.py's docstring for why)

Distinguishes a genuine data problem (e.g. Libib's "Barcode already
exists" -- a real collision with another item) from a transient save
failure, so `needs-review` in the report means "a human should look at
this," not "just retry."

Input CSV columns: call_number, title, description, tags, image_path
(image_path may be blank to skip the poster step).

Usage:
    python3 formatting-scripts/libib_sync_fix.py libib-sync/batch-0001/ready.csv

Writes a report CSV next to the input (call_number, barcode_status,
content_status, message).

Credentials are hardcoded below, same as the two scripts this replaces.
"""

import argparse
import csv
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

LIBIB_LOGIN_URL = "https://www.libib.com/login"
LIBIB_EMAIL = "hello@littlemoviestore.com"
LIBIB_PASSWORD = "YoFuckBezos69!"


def read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("call_number", "").strip()]


def login(page: Page, email: str, password: str) -> None:
    page.goto(LIBIB_LOGIN_URL)
    page.get_by_role("textbox", name="Email").fill(email)
    page.get_by_role("button", name="Next").click()
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url("**/library", timeout=15000)


def open_item(page: Page, call_number: str):
    """Searches and opens the item detail page. Returns None on success,
    or a (status, message) error tuple."""
    page.goto("https://www.libib.com/library")
    search = page.locator("#search")
    search.fill(f"call:{call_number}")
    search.press("Enter")

    items = page.locator(".item-title")
    try:
        items.first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "error", "no item found for this call number"
    page.wait_for_timeout(400)
    count = items.count()
    if count > 1:
        return "error", f"{count} items matched this call number -- ambiguous"

    items.first.click()
    try:
        page.locator(".item-edit-button").first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "error", "item page did not load"
    return None


def fix_barcode(page: Page, call_number: str):
    """Returns (status, message). status is one of updated/skipped/error."""
    try:
        page.locator(".li-copies a").first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "error", "no Copies link on item page"
    page.locator(".li-copies a").first.click()

    rows = page.locator("table tbody tr")
    try:
        rows.first.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        return "error", "no copy rows found after expanding Copies"
    if rows.count() > 1:
        return "error", f"{rows.count()} copies on this item -- needs manual review"

    row = rows.first
    barcode_input = row.locator(".copy-barcode-value input")
    if barcode_input.input_value() == call_number:
        return "skipped", "barcode already matches call_number"

    row.locator(".copy-lock-icon .lock-icon").click()
    try:
        page.locator(".modal-delete").wait_for(state="visible", timeout=3000)
        page.locator(".modal-delete").click()
    except PlaywrightTimeoutError:
        pass  # field may already be unlocked from a prior run

    barcode_input.fill(call_number)
    row.locator(".save-copy-button").click()
    page.wait_for_timeout(600)

    # Libib surfaces a genuine collision as a toast, not a silent failure --
    # distinguish "another item already owns this barcode" from "the save
    # just didn't persist" so the report tells a human what to actually do.
    collision = page.locator(".notification-error", has_text="Barcode already exists")
    if collision.count():
        return "error", "Barcode already exists -- another item already owns this call number as its barcode"

    # The input's in-memory value proves nothing -- it still shows what we
    # just typed regardless of whether the save actually persisted (a known
    # ~8% flake). Reload the item from scratch and re-read.
    verified_value = _read_barcode_fresh(page, call_number)
    if verified_value != call_number:
        return "error", f"save did not persist -- reloaded value is '{verified_value}'"
    return "updated", "ok"


def _read_barcode_fresh(page: Page, call_number: str) -> str:
    """Re-fetches the item from a clean page load and returns its current
    barcode value, bypassing any client-side state we may have just set."""
    err = open_item(page, call_number)
    if err:
        return f"<reload failed: {err[1]}>"
    page.locator(".li-copies a").first.wait_for(state="visible", timeout=8000)
    page.locator(".li-copies a").first.click()
    page.locator("table tbody tr").first.wait_for(state="visible", timeout=8000)
    return page.locator("table tbody tr").first.locator(".copy-barcode-value input").input_value()


def fix_content(page: Page, title: str, description: str, tags: str, image_path: str):
    """Returns (status, message). status is one of updated/skipped/error."""
    page.locator(".item-edit-button").first.click()
    page.wait_for_timeout(400)
    try:
        page.get_by_text("Edit", exact=True).first.click()
    except Exception:
        return "error", "could not open Edit form from the item menu"
    try:
        page.locator("input[name='title']").first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "error", "Edit form did not load"

    title_input = page.locator("input[name='title']").first
    desc_input = page.locator("textarea[name='description']").first
    tags_input = page.locator("input.tags-autocomplete[name='tags']").first

    changed = []
    if title_input.input_value().strip() != title.strip():
        title_input.fill(title.strip())
        changed.append("title")
    if desc_input.input_value().strip() != description.strip():
        desc_input.fill(description.strip())
        changed.append("description")

    from libib_fields import normalized_tag_set

    if normalized_tag_set(tags_input.input_value()) != normalized_tag_set(tags):
        tags_input.fill(tags.strip())
        changed.append("tags")

    if image_path.strip():
        image_file = Path(image_path.strip())
        if not image_file.exists():
            return "error", f"image file not found: {image_path}"
        page.locator("input#cover-image").set_input_files(str(image_file))
        changed.append("poster")

    if not changed:
        return "skipped", "title/description/tags/poster already correct"

    page.locator("input#edit-item-submit").click()
    page.wait_for_timeout(1000)
    return "updated", f"changed: {', '.join(changed)}"


def verify_content(page: Page, call_number: str, title: str, description: str, tags: str):
    """Re-opens the item fresh and confirms title/description/tags
    persisted. Returns None if all good, or an error message string."""
    err = open_item(page, call_number)
    if err:
        return f"could not reload item after save: {err[1]}"
    page.locator(".item-edit-button").first.click()
    page.wait_for_timeout(400)
    page.get_by_text("Edit", exact=True).first.click()
    try:
        page.locator("input[name='title']").first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return "Edit form did not reload"

    from libib_fields import normalized_tag_set

    verified_title = page.locator("input[name='title']").first.input_value().strip()
    verified_desc = page.locator("textarea[name='description']").first.input_value().strip()
    verified_tags = page.locator("input.tags-autocomplete[name='tags']").first.input_value()

    if verified_title != title.strip():
        return f"title did not persist -- reloaded value is {verified_title!r}"
    if verified_desc != description.strip():
        return f"description did not persist -- reloaded value is {verified_desc!r}"
    if normalized_tag_set(verified_tags) != normalized_tag_set(tags):
        return f"tags did not persist -- reloaded value is {verified_tags!r}"
    return None


def sync_item(page: Page, row: dict):
    """Returns (barcode_status, content_status, message)."""
    call_number = row["call_number"].strip()

    err = open_item(page, call_number)
    if err:
        return "error", "error", err[1]

    barcode_status, barcode_message = fix_barcode(page, call_number)

    # Re-open cleanly before the content fix -- the Copies-tab interaction
    # can leave the page in a state the Edit button doesn't reliably act on.
    err = open_item(page, call_number)
    if err:
        return barcode_status, "error", f"barcode: {barcode_message} | content: could not reopen item: {err[1]}"

    content_status, content_message = fix_content(
        page, row["title"], row["description"], row.get("tags", ""), row.get("image_path", "")
    )

    if content_status == "updated":
        verify_err = verify_content(page, call_number, row["title"], row["description"], row.get("tags", ""))
        if verify_err:
            content_status, content_message = "error", verify_err

    message = f"barcode: {barcode_message} | content: {content_message}"
    return barcode_status, content_status, message


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_csv", help="CSV with call_number, title, description, tags, image_path columns")
    parser.add_argument("--report", default=None, help="Report CSV path (default: <input>.sync-report.csv)")
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser window")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_rows(input_path)
    if args.limit:
        rows = rows[: args.limit]
    report_path = Path(args.report) if args.report else input_path.with_suffix(".sync-report.csv")

    print(f"== {input_path.name}: {len(rows)} rows ==", flush=True)

    results = []
    fieldnames = ["call_number", "barcode_status", "content_status", "message"]
    with sync_playwright() as p, report_path.open("w", newline="", encoding="utf-8") as report_f:
        report_writer = csv.DictWriter(report_f, fieldnames=fieldnames)
        report_writer.writeheader()
        report_f.flush()

        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        login(page, LIBIB_EMAIL, LIBIB_PASSWORD)

        for i, row in enumerate(rows, 1):
            call_number = row["call_number"].strip()
            try:
                barcode_status, content_status, message = sync_item(page, row)
            except Exception as exc:  # keep going across a whole batch
                barcode_status, content_status, message = "error", "error", f"{type(exc).__name__}: {exc}"
            result = {
                "call_number": call_number,
                "barcode_status": barcode_status,
                "content_status": content_status,
                "message": message,
            }
            results.append(result)
            report_writer.writerow(result)
            report_f.flush()
            print(f"[{i}/{len(rows)}] {call_number}: {barcode_status}/{content_status} -- {message}", flush=True)

        browser.close()

    both_ok = sum(1 for r in results if r["barcode_status"] != "error" and r["content_status"] != "error")
    errored = sum(1 for r in results if r["barcode_status"] == "error" or r["content_status"] == "error")
    print(f"\n{both_ok} fully ok, {errored} need manual review.", flush=True)
    print(f"Report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
