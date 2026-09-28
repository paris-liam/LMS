"""Libib's Movie CSV import template and the ready.csv the fixer reads."""

from catalog.libib.fields import expected_description, expected_tags_string, expected_title

LIBIB_MOVIE_COLUMNS = [
    "title", "creators", "description", "upc_isbn10", "ean_isbn13", "number_of_discs", "ensemble",
    "aspect_ratio", "tags", "notes", "group", "price", "added", "publisher", "publish_date", "length_of",
    "copies", "call_number", "ddc", "lcc", "rating", "review", "review_created", "status", "began_date",
    "completed_date",
]
READY_COLUMNS = ["call_number", "title", "description", "tags", "image_path", "old_call_number"]


def import_row(row: dict) -> dict:
    """One Libib import row per physical copy. The UPC/EAN fields stay blank —
    Force Import Mode needs only a title; the barcode goes in call_number."""
    out = {column: "" for column in LIBIB_MOVIE_COLUMNS}
    out.update({
        "title": expected_title(row),
        "description": expected_description(row),
        "tags": expected_tags_string(row),
        "price": (row.get("Variant Price") or "").strip(),
        "copies": "1",
        "call_number": (row.get("Variant Barcode") or "").strip(),
    })
    return out


def ready_row(row: dict, image_path: str) -> dict:
    return {
        "call_number": (row.get("Variant Barcode") or "").strip(),
        "title": expected_title(row),
        "description": expected_description(row),
        "tags": expected_tags_string(row),
        "image_path": image_path,
        "old_call_number": "",  # set only when the fixer must renumber the item first
    }
