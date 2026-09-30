"""Libib page operations (Playwright). Moved verbatim from
formatting-scripts/libib_sync_fix.py minus its hardcoded credentials and CLI.
For each item: search `call:<call_number>` (exactly one hit), fix the copy
barcode, then title/description/tags/poster in the Edit form, and reload to
verify what persisted. Imported only by catalog.libib.fix.run_fixer.
"""

from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

LIBIB_LOGIN_URL = "https://www.libib.com/login"
# How long to wait for a Libib page element. Was 8s; raised to 30s after
# Libib ran slow on 2026-09-30 and searches/item pages took longer to appear.
PAGE_WAIT_MS = 30000


def login(page: Page, email: str, password: str) -> None:
    """Libib sometimes answers with a "One moment, please..." holding page
    that reloads itself every 5s (seen 2026-09-30). Typing into the real form
    before its scripts load makes Next submit as a plain form post (the page
    turns into raw JSON), so wait for the form *and* its page load first, and
    start over from a fresh login page if a step still times out."""
    for attempt in range(3):
        try:
            _login_once(page, email, password)
            return
        except PlaywrightTimeoutError:
            if attempt == 2:
                raise
            page.wait_for_timeout(15000)


def _login_once(page: Page, email: str, password: str) -> None:
    page.goto(LIBIB_LOGIN_URL)
    email_box = page.get_by_role("textbox", name="Email")
    email_box.wait_for(state="visible", timeout=90000)
    page.wait_for_load_state("load")
    email_box.fill(email)
    page.get_by_role("button", name="Next").click()
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url("**/library", timeout=15000)


def ensure_rental_library_scope(page: Page) -> None:
    """Libib persists "last viewed collection" server-side, and it silently
    flips between sessions (observed 2026-09-20) -- if the active scope is
    some other collection, every search on this page silently searches
    that (usually near-empty) collection instead and returns nothing,
    which looks exactly like "item not found" errors. Never trust the
    default; force it back to Rental Library on every fresh page load.
    The underlying <select> is a hidden "chosen.js" widget -- a raw JS
    value/change-event hack does NOT reliably register with it (observed
    causing a stuck/wrong scope), so this must be a real UI click."""
    current = page.locator(".chosen-container").first
    try:
        current.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        return  # no collection switcher on this page, nothing to do
    if current.inner_text().strip().startswith("Rental Library"):
        return
    current.click()
    page.wait_for_timeout(400)
    page.locator(".chosen-results li", has_text="Rental Library").click()
    page.wait_for_timeout(800)


def open_item(page: Page, call_number: str):
    """Searches and opens the item detail page. Returns None on success,
    or a (status, message) error tuple."""
    page.goto("https://www.libib.com/library")
    ensure_rental_library_scope(page)
    search = page.locator("#search")
    search.fill(f"call:{call_number}")
    search.press("Enter")

    items = page.locator(".item-title")
    try:
        items.first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
    except PlaywrightTimeoutError:
        return "error", "no item found for this call number"
    # A slow Libib shows the unfiltered library for a while before the search
    # applies (seen 2026-09-30), so give it time to narrow to one hit.
    count = items.count()
    for _ in range(30):
        if count == 1:
            break
        page.wait_for_timeout(500)
        count = items.count()
    if count > 1:
        return "error", f"{count} items matched this call number -- ambiguous"

    items.first.click()
    try:
        page.locator(".item-edit-button").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
    except PlaywrightTimeoutError:
        return "error", "item page did not load"
    return None


def fix_barcode(page: Page, call_number: str):
    """Returns (status, message). status is one of updated/skipped/error."""
    try:
        page.locator(".li-copies a").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
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

    # Libib moved the lock icon into the barcode cell (seen 2026-09-28);
    # accept both layouts.
    row.locator(".copy-barcode-value .lock-icon, .copy-lock-icon .lock-icon").first.click()
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
    page.locator(".li-copies a").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
    page.locator(".li-copies a").first.click()
    page.locator("table tbody tr").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
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
        page.locator("input[name='title']").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
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

    from catalog.libib.fields import normalized_tag_set

    if normalized_tag_set(tags_input.input_value()) != normalized_tag_set(tags):
        # Tags live in the form's collapsed "Tags / Notes / Group" section
        # (seen 2026-09-28); open it first. Title/description are already
        # filled, so switching sections away from them is safe.
        if not tags_input.is_visible():
            page.locator(".anchor[data-section='tng-section']").first.click()
            try:
                tags_input.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeoutError:
                return "error", "could not open the Tags section of the Edit form"
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
        page.locator("input[name='title']").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
    except PlaywrightTimeoutError:
        return "Edit form did not reload"

    from catalog.libib.fields import normalized_tag_set

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


def _open_edit_section(page: Page, field_selector: str, section: str):
    """Open the item's Edit form and reveal `section` so `field_selector` is
    editable. Returns the field locator, or an error message string."""
    page.locator(".item-edit-button").first.click()
    page.wait_for_timeout(400)
    try:
        page.get_by_text("Edit", exact=True).first.click()
    except Exception:
        return "could not open Edit form from the item menu"
    try:
        page.locator("input[name='title']").first.wait_for(state="visible", timeout=PAGE_WAIT_MS)
    except PlaywrightTimeoutError:
        return "Edit form did not load"
    field = page.locator(field_selector).first
    if not field.is_visible():
        page.locator(f".anchor[data-section='{section}']").first.click()
        try:
            field.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError:
            return f"could not open the {section} of the Edit form"
    return field


def set_call_number(page: Page, old: str, new: str):
    """Renumber a Libib item from its old call number to `new` (the Shopify
    barcode). Refuses when `new` already belongs to another item. Returns
    (status, message); status is updated/skipped/error."""
    new_err = open_item(page, new)
    new_in_use = new_err is None or "ambiguous" in new_err[1]
    old_err = open_item(page, old)
    if old_err:
        if new_err is None:
            return "skipped", "already renumbered"
        return "error", f"old call number {old}: {old_err[1]}"
    if new_in_use:
        return "error", f"{new} already belongs to another Libib item -- not renumbering {old}"

    field = _open_edit_section(page, "input[name='call_number']", "catalog-section")
    if isinstance(field, str):
        return "error", field
    if field.input_value().strip() != old:
        return "error", f"call number field shows {field.input_value()!r}, expected {old!r}"
    field.fill(new)
    page.locator("input#edit-item-submit").click()
    page.wait_for_timeout(1000)

    err = open_item(page, new)
    if err:
        return "error", f"renumber to {new} did not persist: {err[1]}"
    return "updated", f"renumbered from {old}"


def sync_item(page: Page, row: dict):
    """Returns (barcode_status, content_status, message)."""
    call_number = row["call_number"].strip()

    prefix = ""
    old_call_number = (row.get("old_call_number") or "").strip()
    if old_call_number:
        status, message = set_call_number(page, old_call_number, call_number)
        if status == "error":
            return "error", "error", f"call number: {message}"
        prefix = f"call number: {message} | "

    err = open_item(page, call_number)
    if err:
        return "error", "error", prefix + err[1]

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

    message = f"{prefix}barcode: {barcode_message} | content: {content_message}"
    return barcode_status, content_status, message


# --- CSV transfer (Settings exports, CSV Import) -------------------------

LIBIB_SETTINGS_URL = "https://www.libib.com/settings"
LIBIB_CSV_IMPORT_URL = "https://www.libib.com/csvimport"
RENTAL_LIBRARY = "Rental Library"


def export_csvs(page: Page, dest_dir) -> tuple[Path, Path]:
    """Settings -> Export Barcode Data / Export Collection Data, both for the
    Rental Library. Clicks only the two export buttons by id (the same page
    holds Delete Collections). Returns (barcodes_path, library_path)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    page.goto(LIBIB_SETTINGS_URL)
    saved = []
    for accordion, select, button in (
            ("Export Barcode Data", "select[name='settings-barcode-library-export-id']", "#settings-barcode-export-submit"),
            ("Export Collection Data", "select[name='settings-library-export-id']", "#settings-export-library-submit")):
        page.locator("a.accordion-title", has_text=accordion).click()
        page.locator(select).select_option(label=RENTAL_LIBRARY)
        with page.expect_download(timeout=120000) as download:
            page.locator(button).click()
        target = dest_dir / download.value.suggested_filename
        download.value.save_as(target)
        saved.append(target)
    return saved[0], saved[1]


def import_csv(page: Page, csv_path, check_mappings, evidence_dir) -> None:
    """Add Items -> CSV Import into the Rental Library as Movies, Force Import
    Mode on. Refuses (raises, nothing imported) unless check_mappings(columns,
    selected_fields) returns no problems. Saves screenshots of the matching
    page and the result page in evidence_dir."""
    import csv as _csv

    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with open(csv_path, newline="", encoding="utf-8") as f:
        columns = next(_csv.reader(f))

    page.goto(LIBIB_CSV_IMPORT_URL)
    page.locator("#csv-import-library-select").select_option(label=RENTAL_LIBRARY)
    page.locator("label[for='csv-import-select-movie']").click()
    if not page.locator("#csv-import-select-movie").is_checked():
        raise RuntimeError("could not select the Movie item type")
    page.locator("#csv-import-file").set_input_files(str(csv_path))
    page.locator("#csv-import-submit").click()

    force = page.locator("#force-import")
    force.wait_for(state="attached", timeout=30000)
    selected = page.locator("select.csvgui-select").evaluate_all(
        "els => els.map(s => s.options[s.selectedIndex] ? s.options[s.selectedIndex].text.trim() : '')")
    page.screenshot(path=str(evidence_dir / "import-matching.png"), full_page=True)
    problems = check_mappings(columns, selected)
    if problems:
        raise RuntimeError("column matching looks wrong, nothing imported: " + "; ".join(problems))
    force.check()
    if not force.is_checked():
        raise RuntimeError("could not turn on Force Import Mode, nothing imported")

    page.locator("#csv-import-preview-submit").click()
    page.wait_for_load_state("networkidle", timeout=120000)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(evidence_dir / "import-result.png"), full_page=True)
    (evidence_dir / "import-result.html").write_text(page.content(), encoding="utf-8")
