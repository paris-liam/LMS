"""Python mirror of the Floor Sale sheet's import formula.

Tab 2 (`Shopify import`) is an array formula in the sheet
(template/floor-sale/import-tab-formula.txt). The sheet is the deliverable;
this module exists so the transform it encodes can be tested and the
expected-output fixture regenerated. Spec:
claudedocs/2026-10-08-floor-sale-upload-sheet.md.

Like transform.py it is deliberately literal: the sheet trusts its own
dropdowns, so a value they cannot produce passes through unchanged and
check-upload is what catches it.
"""

from datetime import date, datetime

from catalog.core.columns import FIXED_VALUES, FLOOR_SALE_TEMPLATE_COLUMNS, GENRE_METAFIELD
from catalog.core.handles import HandleAllocator, derive_floor_sale_handle
from catalog.core.taxonomy import genre_handle

FLOOR_SALE_TAG = "Floor Sale"
FLOOR_SALE_FILL_COLUMNS = ["Title", "Format", "Genre", "Price", "Extra tags", "Copies"]
# Tab 1 as downloaded: the six data columns, then the batch date's label in
# G1 (its value, typed once per batch, is G2 — the first data row).
FLOOR_SALE_FILL_HEADER = FLOOR_SALE_FILL_COLUMNS + ["Batch date"]
BATCH_DATE_COLUMN = "Batch date"
# The sheet formats G2 as yyyy-mm-dd; a US-locale sheet may still show m/d/yyyy.
_BATCH_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")


def _cell(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _extra_tags(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def parse_batch_date(text) -> date | None:
    """The batch date cell as a date, or None when blank or unreadable."""
    value = (text or "").strip()
    for fmt in _BATCH_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def split_fill_tab(rows: list[dict]) -> tuple[list[dict], date | None]:
    """A downloaded tab 1 -> (its filled data rows, the batch date in G2)."""
    batch_date = parse_batch_date(rows[0].get(BATCH_DATE_COLUMN)) if rows else None
    filled = [
        {column: row.get(column) or "" for column in FLOOR_SALE_FILL_COLUMNS}
        for row in rows
        if any(_cell(row, column) for column in FLOOR_SALE_FILL_COLUMNS)
    ]
    return filled, batch_date


def fill_row_to_import_row(row: dict, batch_date: date, allocator: HandleAllocator) -> dict:
    """One tab-1 row -> one tab-2 row, in FLOOR_SALE_TEMPLATE_COLUMNS order."""
    title = _cell(row, "Title")
    media_format = _cell(row, "Format")
    genre = _cell(row, "Genre")

    out = {column: "" for column in FLOOR_SALE_TEMPLATE_COLUMNS}
    out.update({k: v for k, v in FIXED_VALUES.items() if k in out})
    out["Handle"] = allocator.allocate(derive_floor_sale_handle(title, media_format, batch_date))
    out["Title"] = title
    out["Vendor"] = media_format
    out["Tags"] = ", ".join([FLOOR_SALE_TAG] + _extra_tags(row.get("Extra tags")))
    # Sold at the counter only: off the Online Store, still Active so POS can sell it.
    out["Status"] = "Active"
    out["Published"] = "FALSE"
    out["Option1 Value"] = genre
    out["Variant Price"] = _cell(row, "Price")
    # One product per title + format; Copies is how many go on the floor.
    out["Variant Inventory Qty"] = _cell(row, "Copies") or "1"
    out["Variant Taxable"] = "TRUE"
    out[GENRE_METAFIELD] = genre_handle(genre) or ""
    return out


def floor_sale_rows_to_import_rows(rows: list[dict], batch_date: date) -> list[dict]:
    """Every tab-1 row, sharing one allocator so a title + format repeated in a batch gets -2 / -3."""
    allocator = HandleAllocator()
    return [fill_row_to_import_row(row, batch_date, allocator) for row in rows]
