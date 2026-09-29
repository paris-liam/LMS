"""`libib selftest` — does every Libib page step the pipeline uses still work?

Libib changes its UI without notice (twice in the week of 2026-09-21, each
time breaking the fixer mid-run). This walks every selector the fixer,
export and import rely on, READ-ONLY: it opens things and looks, and never
clicks Save, Upload-to-import's final Process Import, or anything on the
settings page other than the two Export buttons. Run it on a schedule, and
before any big Libib run; a failure names the step and saves a screenshot.
"""

import csv
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from catalog.libib.columns import LIBIB_MOVIE_COLUMNS
from catalog.libib.exports import BARCODE_REQUIRED, COLLECTION_REQUIRED


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    seconds: float = 0.0


def _visible(page, selector: str, timeout: int = 8000) -> None:
    page.locator(selector).first.wait_for(state="visible", timeout=timeout)


def _present(page, selector: str) -> None:
    if page.locator(selector).count() == 0:
        raise AssertionError(f"{selector} not found on the page")


def _header(path) -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f))


def build_checks(call_number: str, include_import_page: bool):
    """Ordered (name, fn(page, ctx)) pairs; each raises on failure."""
    from catalog.libib import browser, transfer

    def search(page, ctx):
        err = browser.open_item(page, call_number)
        if err:
            raise AssertionError(err[1])

    def item_page(page, ctx):
        _visible(page, ".item-edit-button")
        _visible(page, ".li-copies a")

    def copies_panel(page, ctx):
        page.locator(".li-copies a").first.click()
        _visible(page, "table tbody tr")
        row = page.locator("table tbody tr").first
        value = row.locator(".copy-barcode-value input").input_value()
        if value != call_number:
            raise AssertionError(f"copy barcode reads {value!r}, expected {call_number!r}")
        if row.locator(".copy-barcode-value .lock-icon, .copy-lock-icon .lock-icon").count() == 0:
            raise AssertionError("barcode lock icon not found (the fixer unlocks the barcode with it)")
        if row.locator(".save-copy-button").count() == 0:
            raise AssertionError(".save-copy-button not found")

    def edit_form(page, ctx):
        err = browser.open_item(page, call_number)
        if err:
            raise AssertionError(err[1])
        page.locator(".item-edit-button").first.click()
        page.wait_for_timeout(400)
        page.get_by_text("Edit", exact=True).first.click()
        _visible(page, "input[name='title']")
        if not page.locator("input[name='title']").first.input_value().strip():
            raise AssertionError("Edit form title is empty")
        for selector in ("textarea[name='description']", "input.tags-autocomplete[name='tags']",
                         "input[name='call_number']", "input#cover-image", "input#edit-item-submit",
                         ".anchor[data-section='tng-section']", ".anchor[data-section='catalog-section']"):
            _present(page, selector)

    def edit_sections(page, ctx):
        # The fixer opens these collapsed sections to reach tags and the call number.
        page.locator(".anchor[data-section='tng-section']").first.click()
        _visible(page, "input.tags-autocomplete[name='tags']", 5000)
        page.locator(".anchor[data-section='catalog-section']").first.click()
        _visible(page, "input[name='call_number']", 5000)
        value = page.locator("input[name='call_number']").first.input_value().strip()
        if value != call_number:
            raise AssertionError(f"call number field reads {value!r}, expected {call_number!r}")
        page.goto(browser.LIBIB_SETTINGS_URL)  # leave the form without saving

    def exports(page, ctx):
        barcodes, library = browser.export_csvs(page, ctx["tmp"])
        missing = [c for c in BARCODE_REQUIRED if c not in _header(barcodes)]
        missing += [c for c in COLLECTION_REQUIRED if c not in _header(library)]
        if missing:
            raise AssertionError(f"export columns missing: {', '.join(missing)}")
        with open(barcodes, newline="", encoding="utf-8-sig") as f:
            rows = sum(1 for _ in csv.DictReader(f))
        if rows == 0:
            raise AssertionError("barcode export has no rows")
        ctx["export_rows"] = rows
        return f"{rows} items exported"

    def import_page(page, ctx):
        page.goto(browser.LIBIB_CSV_IMPORT_URL)
        for selector in ("#csv-import-library-select", "label[for='csv-import-select-movie']",
                         "#csv-import-select-movie", "#csv-import-file", "#csv-import-submit"):
            _present(page, selector)

    def import_matching(page, ctx):
        # Upload a one-row file to reach the column-matching page, check it,
        # then leave. Process Import is never clicked: nothing is imported.
        sample = Path(ctx["tmp"]) / "selftest-import.csv"
        with open(sample, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LIBIB_MOVIE_COLUMNS)
            writer.writeheader()
            writer.writerow({c: "" for c in LIBIB_MOVIE_COLUMNS} | {"title": "SELFTEST - never imported",
                                                                   "copies": "1", "call_number": "SELFTEST"})
        page.locator("#csv-import-library-select").select_option(label=browser.RENTAL_LIBRARY)
        page.locator("label[for='csv-import-select-movie']").click()
        page.locator("#csv-import-file").set_input_files(str(sample))
        page.locator("#csv-import-submit").click()
        page.locator("#force-import").wait_for(state="attached", timeout=30000)
        _present(page, "#csv-import-preview-submit")
        selected = page.locator("select.csvgui-select").evaluate_all(
            "els => els.map(s => s.options[s.selectedIndex] ? s.options[s.selectedIndex].text.trim() : '')")
        problems = transfer.mapping_problems(LIBIB_MOVIE_COLUMNS, selected)
        if problems:
            raise AssertionError("; ".join(problems))
        page.goto(browser.LIBIB_SETTINGS_URL)  # abandon the upload

    checks = [("search by call number", search), ("item page", item_page), ("copies panel", copies_panel),
              ("edit form fields", edit_form), ("edit form sections", edit_sections),
              ("exports", exports), ("CSV import page", import_page)]
    if include_import_page:
        checks.append(("CSV import column matching", import_matching))
    return checks


def run_selftest(email: str, password: str, call_number: str, evidence_dir, headless: bool = True,
                 include_import_page: bool = True) -> list[Check]:
    from playwright.sync_api import sync_playwright
    from catalog.libib import browser

    evidence_dir = Path(evidence_dir)
    results: list[Check] = []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        chromium = p.chromium.launch(headless=headless)
        try:
            page = chromium.new_context(accept_downloads=True).new_page()
            started = time.monotonic()
            try:
                browser.login(page, email, password)
                results.append(Check("login", True, "", time.monotonic() - started))
            except Exception as exc:
                results.append(Check("login", False, f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
                                     time.monotonic() - started))
                _screenshot(page, evidence_dir, "login")
                return results
            ctx = {"tmp": tmp}
            for name, fn in build_checks(call_number, include_import_page):
                started = time.monotonic()
                try:
                    detail = fn(page, ctx) or ""
                    results.append(Check(name, True, detail, time.monotonic() - started))
                except Exception as exc:
                    first = str(exc).splitlines()[0] if str(exc) else ""
                    results.append(Check(name, False, f"{type(exc).__name__}: {first}", time.monotonic() - started))
                    _screenshot(page, evidence_dir, name)
        finally:
            chromium.close()
    return results


def _screenshot(page, evidence_dir: Path, name: str) -> None:
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(evidence_dir / f"{name.replace(' ', '-')}.png"), full_page=True)
    except Exception:
        pass
