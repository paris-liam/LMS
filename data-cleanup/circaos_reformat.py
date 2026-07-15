"""Reformat the serialized-rental ("CircaOS") movie batch of a store
export into the same clean Shopify fields as the resale batch
(reformat_movies.py).

Scope: products with Option1 Name == "Condition" only, excluding the stray
Supercycle Plan product. See
docs/superpowers/specs/2026-07-14-circaos-product-reformat-design.md.
"""

from catalog_common import add_tags, group_rows_by_handle, load_export, split_tags, write_csv
from genre_format_mapping import VENDOR_TO_FORMAT, GENRE_VALUE_MAP
from reformat_movies import FIXED_VENDOR, FIXED_CATEGORY, GENRE_COLUMN, FORMAT_COLUMN

TAG_TO_ADD = "CircaOS Import"

# Includes "Special Interest" (maps to (None, None)) intentionally: a product
# tagged only "Special Interest" is still in scope, just ships with a blank
# genre, matching reformat_movies.py's handling of the same value.
SIMPLE_GENRE_TAGS = {k: v for k, v in GENRE_VALUE_MAP.items() if "," not in k}

BARCODE_FORMAT_PREFIXES = [
    ("VHS", "vhs"),
    ("DVD", "dvd"),
    ("BLR", "blu-ray"),
    ("4K", "4-k"),
]


def has_genre_tag(tags_str: str) -> bool:
    return any(t in SIMPLE_GENRE_TAGS for t in split_tags(tags_str))


def extract_genre_from_tags(tags_str: str) -> str | None:
    for t in split_tags(tags_str):
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
    tags = split_tags(tags_str)
    if "4K" in tags or "4k" in tags:
        return "4-k"
    return VENDOR_TO_FORMAT.get(vendor)


def build_tags(tags_str: str) -> str:
    return add_tags(tags_str, [TAG_TO_ADD])


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


FORMAT_HANDLE_SUFFIX = {
    "vhs": "vhs",
    "dvd": "dvd",
    "blu-ray": "bluray",
    "4-k": "4k",
}


def build_product_handles(
    base_handle: str, real_rows: list[dict], vendor: str, tags_str: str
) -> list[str]:
    if len(real_rows) == 1:
        return [base_handle]
    formats = [
        resolve_circaos_format(vendor, tags_str, r["Variant Barcode"].strip())
        for r in real_rows
    ]
    if len(set(formats)) > 1:
        return [
            f"{base_handle}-{FORMAT_HANDLE_SUFFIX.get(fmt, 'copy')}" for fmt in formats
        ]
    return [base_handle] + [
        f"{base_handle}-copy-{i + 1}" for i in range(1, len(real_rows))
    ]


def transform_circaos_group(
    rows: list[dict],
) -> tuple[str, list[list[dict]] | None, str | None]:
    """Classify and, if in scope, transform all CSV rows for one product handle.

    `rows` is every CSV row sharing a Handle, in original order. Returns
    (status, products, reason). `products` is a list where each element is
    the list of output CSV rows for one product — usually one product per
    group, but multi-copy titles produce one product per real variant row.
    """
    first = rows[0]
    status, reason = classify_circaos_row(first)
    if status != "in_scope":
        return status, None, reason

    vendor = first["Vendor"].strip()
    tags_str = first["Tags"]
    genre = extract_genre_from_tags(tags_str)
    new_tags = build_tags(tags_str)

    real_rows = [r for r in rows if r["Option1 Value"].strip()]
    extra_image_rows = [r for r in rows if not r["Option1 Value"].strip()]
    base_handle = first["Handle"]
    new_handles = build_product_handles(base_handle, real_rows, vendor, tags_str)

    products = []
    for i, (real_row, new_handle) in enumerate(zip(real_rows, new_handles)):
        fmt = resolve_circaos_format(vendor, tags_str, real_row["Variant Barcode"].strip())
        new_row = dict(real_row)
        new_row["Handle"] = new_handle
        new_row["Vendor"] = FIXED_VENDOR
        new_row["Product Category"] = FIXED_CATEGORY
        new_row["Option1 Name"] = "Title"
        new_row["Option1 Value"] = "Default Title"
        new_row["Option2 Name"] = ""
        new_row["Option2 Value"] = ""
        new_row["Variant SKU"] = ""
        new_row[GENRE_COLUMN] = genre or ""
        new_row[FORMAT_COLUMN] = fmt or ""
        new_row["Tags"] = new_tags

        product_rows = [new_row]
        if i == 0:
            product_rows += [dict(r) for r in extra_image_rows]
        products.append(product_rows)

    return "in_scope", products, None


def build_output(
    rows: list[dict], fieldnames: list[str]
) -> tuple[list[str], list[dict], list[dict]]:
    """Run the full reformat over every row, split into output vs. review rows.

    Returns (new_fieldnames, output_rows, review_rows). new_fieldnames is
    fieldnames with FORMAT_COLUMN inserted if it wasn't already present.
    """
    new_fieldnames = list(fieldnames)
    if FORMAT_COLUMN not in new_fieldnames:
        genre_index = new_fieldnames.index(GENRE_COLUMN)
        new_fieldnames.insert(genre_index + 1, FORMAT_COLUMN)

    output_rows: list[dict] = []
    review_rows: list[dict] = []
    for handle, group in group_rows_by_handle(rows):
        status, products, reason = transform_circaos_group(group)
        if status == "in_scope":
            for product_rows in products:
                output_rows.extend(product_rows)
        elif status == "review":
            review_rows.append(
                {"Handle": handle, "Title": group[0]["Title"], "Reason": reason}
            )
        # status == "skip": out of scope for this pass, omitted entirely

    return new_fieldnames, output_rows, review_rows


def main(input_path, output_path, review_path) -> tuple[int, int]:
    fieldnames, rows = load_export(input_path)
    new_fieldnames, output_rows, review_rows = build_output(rows, fieldnames)
    write_csv(output_path, new_fieldnames, output_rows)
    write_csv(review_path, ["Handle", "Title", "Reason"], review_rows)
    return len(output_rows), len(review_rows)

