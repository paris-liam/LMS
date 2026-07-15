"""Reformat the plain resale movie batch of a store export
into clean Shopify fields, ready for bulk re-upload.

Scope: products with Option1 Name == "Genre" only. Serialized rental items
(Option1 Name == "Condition") and the stray Supercycle Plan product are
out of scope for this pass and are left untouched.
"""

from catalog_common import group_rows_by_handle, load_export, write_csv
from genre_format_mapping import GENRE_VALUE_MAP, resolve_format, resolve_genre

FIXED_VENDOR = "Little Movie Store"
FIXED_CATEGORY = "Media > Videos"
GENRE_COLUMN = "Genre (product.metafields.shopify.genre)"
FORMAT_COLUMN = "Media format (product.metafields.shopify.media-format)"


def classify_row(row: dict) -> tuple[str, str | None]:
    """Classify a product's primary CSV row.

    Returns (status, reason) where status is one of:
    - "in_scope": a plain resale product to reformat
    - "review": can't be cleanly reformatted, needs manual attention
    - "skip": out of scope for this pass (rental, membership plan, or an
      extra image row that isn't a product's primary row)
    """
    option1_name = row["Option1 Name"].strip()

    if option1_name == "Condition":
        return "skip", None
    if row["Type"].strip() == "Supercycle Plan":
        return "skip", None
    if option1_name == "Title":
        return "review", "no genre set (default Title variant)"
    if option1_name != "Genre":
        return "skip", None

    option1_value = row["Option1 Value"].strip()
    if option1_value == "#VALUE!":
        return "review", "corrupted genre value (#VALUE!)"
    if option1_value not in GENRE_VALUE_MAP:
        return "review", f"unrecognized genre value: {option1_value!r}"
    return "in_scope", None


def transform_group(rows: list[dict]) -> tuple[str, list[dict] | None, str | None]:
    """Classify and, if in scope, transform all CSV rows for one product handle.

    `rows` is every CSV row sharing a Handle, in original order (the first
    row is the product's primary row; any remaining rows are extra images).
    Returns (status, transformed_rows_or_None, reason_or_None).
    """
    first = rows[0]
    status, reason = classify_row(first)
    if status != "in_scope":
        return status, None, reason

    vendor = first["Vendor"].strip()
    option1_value = first["Option1 Value"].strip()

    new_first = dict(first)
    new_first["Vendor"] = FIXED_VENDOR
    new_first["Product Category"] = FIXED_CATEGORY
    new_first["Option1 Name"] = "Title"
    new_first["Option1 Value"] = "Default Title"
    new_first[GENRE_COLUMN] = resolve_genre(option1_value) or ""
    new_first[FORMAT_COLUMN] = resolve_format(vendor, option1_value) or ""

    transformed = [new_first] + [dict(r) for r in rows[1:]]
    return "in_scope", transformed, None



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
        status, transformed, reason = transform_group(group)
        if status == "in_scope":
            output_rows.extend(transformed)
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

