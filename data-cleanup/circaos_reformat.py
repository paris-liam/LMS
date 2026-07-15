"""Reformat the serialized-rental ("CircaOS") movie batch in
current-movies-export.csv into the same clean Shopify fields as the resale
batch (reformat_movies.py).

Scope: products with Option1 Name == "Condition" only, excluding the stray
Supercycle Plan product. See
docs/superpowers/specs/2026-07-14-circaos-product-reformat-design.md.
"""

from genre_format_mapping import VENDOR_TO_FORMAT, GENRE_VALUE_MAP

TAG_TO_ADD = "CircaOS Import"

SIMPLE_GENRE_TAGS = {k: v for k, v in GENRE_VALUE_MAP.items() if "," not in k}

BARCODE_FORMAT_PREFIXES = [
    ("VHS", "vhs"),
    ("DVD", "dvd"),
    ("BLR", "blu-ray"),
    ("4K", "4-k"),
]


def has_genre_tag(tags_str: str) -> bool:
    tags = [t.strip() for t in tags_str.split(",")]
    return any(t in SIMPLE_GENRE_TAGS for t in tags)


def extract_genre_from_tags(tags_str: str) -> str | None:
    tags = [t.strip() for t in tags_str.split(",")]
    for t in tags:
        if t in SIMPLE_GENRE_TAGS:
            genre_handle, _ = SIMPLE_GENRE_TAGS[t]
            if genre_handle is not None:
                return genre_handle
    return None


def format_from_barcode(barcode: str) -> str | None:
    body = barcode[4:] if barcode.startswith("191-") else barcode
    for prefix, handle in BARCODE_FORMAT_PREFIXES:
        if body.startswith(prefix):
            return handle
    return None


def resolve_circaos_format(vendor: str, tags_str: str, barcode: str) -> str | None:
    from_barcode = format_from_barcode(barcode)
    if from_barcode is not None:
        return from_barcode
    tags = [t.strip() for t in tags_str.split(",")]
    if "4K" in tags or "4k" in tags:
        return "4-k"
    return VENDOR_TO_FORMAT.get(vendor)


def build_tags(tags_str: str) -> str:
    existing = [t.strip() for t in tags_str.split(",") if t.strip()]
    if TAG_TO_ADD not in existing:
        existing.append(TAG_TO_ADD)
    return ", ".join(existing)


def classify_circaos_row(row: dict) -> tuple[str, str | None]:
    """Classify a product's primary CSV row.

    Returns (status, reason) where status is one of:
    - "in_scope": a serialized-rental product to reformat
    - "review": has no genre-like tag, can't be cleanly reformatted
    - "skip": out of scope for this pass (Supercycle Plan, or not part of
      this batch at all)
    """
    if row["Type"].strip() == "Supercycle Plan":
        return "skip", None
    if row["Option1 Name"].strip() != "Condition":
        return "skip", None
    if not has_genre_tag(row["Tags"]):
        return "review", "no genre-like tag found in Tags"
    return "in_scope", None
