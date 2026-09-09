"""Python mirror of the client sheet's tab-2 array formula.

The sheet is the deliverable; this module exists so the transform it encodes
can be tested against normalize.py and so the expected-output fixture can be
regenerated when the taxonomy changes. run.py does not import it.

Kept deliberately literal — it mirrors what the spreadsheet formula does,
including the fact that the sheet trusts its own dropdowns and performs no
alias resolution. A value the dropdowns cannot produce is passed through
unchanged rather than corrected, exactly as the formula would.
"""

from columns import FIXED_VALUES, GENRE_METAFIELD, TEMPLATE_COLUMNS
from handles import HandleAllocator, derive_handle
from taxonomy import genre_handle

FILL_COLUMNS = [
    "Title",
    "Format",
    "Type",
    "Genre 1",
    "Genre 2",
    "Genre 3",
    "Price",
    "Description",
    "Image URL",
    "Extra tags",
]


def _cell(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _extra_tags(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def fill_row_to_import_row(row: dict, allocator: HandleAllocator) -> dict:
    """One tab-1 row -> one tab-2 row, in TEMPLATE_COLUMNS order."""
    title = _cell(row, "Title")
    media_format = _cell(row, "Format")
    product_type = _cell(row, "Type")
    genres = [g for g in (_cell(row, f"Genre {n}") for n in (1, 2, 3)) if g]
    image = _cell(row, "Image URL")

    out = {column: "" for column in TEMPLATE_COLUMNS}
    out.update(FIXED_VALUES)
    out["Status"] = "Active"

    out["Handle"] = allocator.allocate(
        derive_handle(title, media_format, product_type)
    )
    out["Title"] = title
    out["Body (HTML)"] = row.get("Description") or ""
    out["Vendor"] = media_format
    out["Tags"] = ", ".join(
        [t for t in [product_type, media_format] if t]
        + genres
        + _extra_tags(row.get("Extra tags"))
    )
    out["Option1 Value"] = genres[0] if genres else ""
    out["Variant Price"] = "0" if product_type == "Rental" else _cell(row, "Price")
    out["Image Src"] = image
    out["Image Alt Text"] = f"{title} poster" if image else ""
    out[GENRE_METAFIELD] = "; ".join(
        handle for handle in (genre_handle(g) for g in genres) if handle
    )
    return out


def fill_rows_to_import_rows(rows: list[dict]) -> list[dict]:
    """Every tab-1 row, sharing one allocator so repeats get -2 / -3."""
    allocator = HandleAllocator()
    return [fill_row_to_import_row(row, allocator) for row in rows]
