"""What "1:1 with Shopify" means for a Libib item (moved from
formatting-scripts/libib_fields.py). Shopify is authoritative: a rental is
eligible for Libib once every REQUIRED_FIELDS column is filled, and the same
expected_* values define drift."""

import re

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.taxonomy import canonical_type
from catalog.core.text import norm_ws, strip_html

# Libib concept -> snapshot column. The poster is not here: a rental goes to
# Libib without one and the poster is uploaded when it appears (WANTED_FIELDS).
REQUIRED_FIELDS = {
    "title": "Title",
    "barcode": "Variant Barcode",
    "description": "Body (HTML)",
    "genre": GENRE_METAFIELD,
    "tags": "Tags",
    "format": "Vendor",
}

# Worth having, never blocks a rental from Libib.
WANTED_FIELDS = {"poster": "Image Src"}


def is_rental(row: dict) -> bool:
    types = {canonical_type(t) for t in (row.get("Tags") or "").split(",")} - {None}
    return types == {"Rental"}


def is_complete(row: dict) -> bool:
    return all((row.get(col) or "").strip() for col in REQUIRED_FIELDS.values())


def missing_fields(row: dict) -> list[str]:
    return [name for name, col in REQUIRED_FIELDS.items() if not (row.get(col) or "").strip()]


def missing_wanted(row: dict) -> list[str]:
    return [name for name, col in WANTED_FIELDS.items() if not (row.get(col) or "").strip()]


def expected_title(row: dict) -> str:
    return norm_ws(row.get("Title", ""))


def expected_description(row: dict) -> str:
    return norm_ws(strip_html(row.get("Body (HTML)", "")))


def expected_tags_string(row: dict) -> str:
    """What goes in Libib's `tags`: the format (Vendor) and the genre handles."""
    vendor = (row.get("Vendor") or "").strip()
    genre = (row.get(GENRE_METAFIELD) or "").strip()
    return ", ".join(p for p in (vendor, genre) if p)


def normalized_tag_set(tags: str) -> set[str]:
    """Libib lowercases and reorders tags on save ("VHS, Comedy" -> "comedy,vhs"),
    so tags compare as a normalised set."""
    return {t.strip().lower() for t in re.split(r"[,;\n]", tags or "") if t.strip()}
