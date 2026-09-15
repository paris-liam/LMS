"""Map a Shopify product export to Libib's Movie CSV import template.

Mapping decisions and the field-by-field rationale live in
claudedocs/2026-09-14-libib-bulk-upload-plan.md. In short:

- One output row per physical copy (per Shopify variant row's parent
  product), matching the existing "one product per physical copy" model —
  `copies` is always 1, never aggregated.
- `upc_isbn10`/`ean_isbn13` are left blank. Our `Variant Barcodes` values
  are internal serials, not check-digit-valid UPC/EAN, and Libib validates
  the check digit on import — they would be rejected outright. The import
  must run with Libib's Force Import Mode (Pro tier, toggled on the Field
  Alignment step) so title-only rows are accepted.
- The internal serial goes in `call_number` instead, where it's just
  descriptive text.
- Libib has no genre or format field, so both are folded into `tags`.
- Enrichment fields with 0% fill in the source data today (creators,
  length_of, publish_date, etc.) are left blank rather than guessed.

Usage: python3 libib_export.py <shopify_export.csv> <output.csv>
"""

import html
import re
import sys

from catalog_common import load_export, write_csv

LIBIB_MOVIE_COLUMNS = [
    "title",
    "creators",
    "description",
    "upc_isbn10",
    "ean_isbn13",
    "number_of_discs",
    "ensemble",
    "aspect_ratio",
    "tags",
    "notes",
    "group",
    "price",
    "added",
    "publisher",
    "publish_date",
    "length_of",
    "copies",
    "call_number",
    "ddc",
    "lcc",
    "rating",
    "review",
    "review_created",
    "status",
    "began_date",
    "completed_date",
]

GENRE_METAFIELD = "Genre (product.metafields.shopify.genre)"

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(body_html: str) -> str:
    text = _TAG_RE.sub(" ", body_html)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def build_tags(vendor: str, genre: str) -> str:
    parts = [p for p in (vendor.strip(), genre.strip()) if p]
    return ", ".join(parts)


def map_row(row: dict) -> dict:
    return {
        "title": row.get("Title", "").strip(),
        "creators": "",
        "description": strip_html(row.get("Body (HTML)", "")),
        "upc_isbn10": "",
        "ean_isbn13": "",
        "number_of_discs": "",
        "ensemble": "",
        "aspect_ratio": "",
        "tags": build_tags(row.get("Vendor", ""), row.get(GENRE_METAFIELD, "")),
        "notes": "",
        "group": "",
        "price": row.get("Variant Price", "").strip(),
        "added": "",
        "publisher": "",
        "publish_date": "",
        "length_of": "",
        "copies": "1",
        "call_number": row.get("Variant Barcode", "").strip(),
        "ddc": "",
        "lcc": "",
        "rating": "",
        "review": "",
        "review_created": "",
        "status": "",
        "began_date": "",
        "completed_date": "",
    }


def main(in_path: str, out_path: str) -> None:
    _, rows = load_export(in_path)
    parents = [row for row in rows if row.get("Title", "").strip()]
    out_rows = [map_row(row) for row in parents]
    write_csv(out_path, LIBIB_MOVIE_COLUMNS, out_rows)
    print(f"wrote {len(out_rows)} rows to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <shopify_export.csv> <output.csv>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
