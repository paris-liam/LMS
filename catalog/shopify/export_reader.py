"""A Shopify product-export CSV -> snapshot rows (the audit's --from-export path)."""

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import group_rows_by_handle, load_export
from catalog.errors import InputShapeError
from catalog.shopify.snapshot import blank_row

REQUIRED_COLUMNS = ("Handle", "Title")
COPIED_COLUMNS = (
    "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Template Suffix", "Image Src",
    "Image Alt Text", "Option1 Name", "Option1 Value", "Variant Price", "Variant Barcode",
    "Variant Inventory Tracker", "Product Category", GENRE_METAFIELD,
)


def _is_variant_row(row: dict) -> bool:
    """A real variant row carries option, price or barcode data; image rows don't."""
    return any((row.get(c) or "").strip() for c in ("Option1 Value", "Variant Price", "Variant Barcode"))


def read_export(path) -> list[dict]:
    fieldnames, rows = load_export(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise InputShapeError(f"{path} is not a Shopify product export (missing {', '.join(missing)})")

    products = []
    for handle, group in group_rows_by_handle(rows):
        if not (handle or "").strip():
            continue
        primary = group[0]
        out = blank_row()
        out["Handle"] = handle.strip()
        for column in COPIED_COLUMNS:
            value = primary.get(column) or ""
            out[column] = value if column == "Body (HTML)" else value.strip()
        out["Status"] = out["Status"].lower()
        out["Variant Count"] = str(max(sum(1 for r in group if _is_variant_row(r)), 1))
        products.append(out)
    return products
