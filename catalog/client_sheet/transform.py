"""Python mirror of the client sheet's two output formulas.

Tab 2 (`Shopify import`) and tab 3 (`Libib import`) are array formulas in the
sheet (template/import-tab-formula.txt, template/libib-tab-formula.txt). The
sheet is the deliverable; this module exists so the transforms it encodes can
be tested and so the expected-output fixtures can be regenerated when the
taxonomy changes. The pipeline does not import it.

Kept deliberately literal — it mirrors what the spreadsheet formula does,
including the fact that the sheet trusts its own dropdowns and performs no
alias resolution. A value the dropdowns cannot produce is passed through
unchanged rather than corrected, exactly as the formula would.
"""

from catalog.core.columns import FIXED_VALUES, GENRE_METAFIELD, TEMPLATE_COLUMNS
from catalog.core.handles import HandleAllocator, derive_handle
from catalog.core.taxonomy import genre_handle
from catalog.libib.columns import import_row

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
    # Typed in after the Shopify import, once the label is printed. Tab 2
    # ignores it; tab 3 writes it as the Libib call number.
    "Barcode",
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
    # Type + curation tags only: format lives in Vendor and genre in the
    # metafield, so neither is written as a tag (checklist item 14).
    out["Tags"] = ", ".join(
        [t for t in [product_type] if t] + _extra_tags(row.get("Extra tags"))
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


def fill_rows_to_libib_rows(rows: list[dict]) -> list[dict]:
    """Tab 3: one Libib import row per Rental row that has a barcode.

    Built through the pipeline's own import_row, so a copy the client imports
    by hand looks exactly like one `libib sync` would have imported — the
    barcode becomes the call number, which is how every Libib command finds
    the item again.
    """
    out = []
    for row, shopify in zip(rows, fill_rows_to_import_rows(rows)):
        barcode = _cell(row, "Barcode")
        if _cell(row, "Type") != "Rental" or not barcode:
            continue
        out.append(import_row(dict(shopify, **{"Variant Barcode": barcode})))
    return out
