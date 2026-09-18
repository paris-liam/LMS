"""Single source of truth for what "1:1 with Shopify" means for a Libib
item, shared by libib_sync.py's audit/prepare/verify steps so the
eligibility rule and the comparison rule can never drift apart.

Shopify is authoritative. A rental product is eligible for Libib once all
of REQUIRED_FIELDS are filled in; the same field map defines what "matches"
means when auditing an item already in Libib.
"""

import html
import re

from columns import GENRE_METAFIELD

# Libib concept -> Shopify export column
REQUIRED_FIELDS = {
    "title": "Title",
    "poster": "Image Src",
    "barcode": "Variant Barcode",
    "description": "Body (HTML)",
    "genre": GENRE_METAFIELD,
    "tags": "Tags",
    "format": "Vendor",
}


def norm_ws(s: str) -> str:
    """Collapse all whitespace runs (including non-breaking spaces) to a
    single regular space. Shopify's rich-text editor leaves inconsistent
    double-spaces/nbsp in Body (HTML) that don't represent a real content
    difference -- comparing raw strings produces false-positive mismatches."""
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def strip_html(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def is_complete(shopify_row: dict) -> bool:
    return all(shopify_row.get(col, "").strip() for col in REQUIRED_FIELDS.values())


def missing_fields(shopify_row: dict) -> list[str]:
    return [name for name, col in REQUIRED_FIELDS.items() if not shopify_row.get(col, "").strip()]


def expected_title(shopify_row: dict) -> str:
    return norm_ws(shopify_row.get("Title", ""))


def expected_description(shopify_row: dict) -> str:
    return norm_ws(strip_html(shopify_row.get("Body (HTML)", "")))


def expected_tags_string(shopify_row: dict) -> str:
    """What we write into the Libib import CSV's `tags` column."""
    vendor = shopify_row.get("Vendor", "").strip()
    genre = shopify_row.get(GENRE_METAFIELD, "").strip()
    return ", ".join(p for p in (vendor, genre) if p)


def normalized_tag_set(tags_str: str) -> set:
    """Libib lowercases/reformats tags on save, so comparison must be a
    normalized set, not an exact string -- our own "VHS, Comedy" becomes
    Libib's "comedy,vhs"; same content, different formatting."""
    return {t.strip().lower() for t in re.split(r"[,\n]", tags_str or "") if t.strip()}
