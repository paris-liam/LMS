"""Turn raw input rows into rows that are safe to import, or into issues.

Pure: dicts in, dicts out, no filesystem and no network, so the whole
classification table is testable without a CSV or an API key.

A product is one Handle group. Its first row is the primary row; any
further rows are extra images, which pass through carrying image fields
only. When a product is flagged, every one of its rows goes to issues.csv
so the operator can fix and re-run the file as a whole.
"""

from catalog_common import group_rows_by_handle
from columns import (
    EXPORT_COLUMNS,
    FIXED_VALUES,
    GENRE_METAFIELD,
    REASON_COLUMN,
    TEMPLATE_COLUMNS,
)
from handles import HandleAllocator, derive_handle
from resolve import extra_tags, resolve_format, resolve_genres, resolve_price, resolve_type, split_list
from taxonomy import genre_handle


def output_columns(shape: str) -> list[str]:
    return TEMPLATE_COLUMNS if shape == "template" else EXPORT_COLUMNS


def _is_variant_row(row: dict) -> bool:
    """A real variant row carries option or price data; image rows don't."""
    return bool(
        (row.get("Option1 Value") or "").strip()
        or (row.get("Variant Price") or "").strip()
        or (row.get("Variant Barcode") or "").strip()
    )


def _blank_row(shape: str) -> dict:
    return {column: "" for column in output_columns(shape)}


def _image_row(row: dict, shape: str) -> dict:
    out = _blank_row(shape)
    out["Handle"] = row.get("Handle", "")
    out["Image Src"] = (row.get("Image Src") or "").strip()
    out["Image Alt Text"] = (row.get("Image Alt Text") or "").strip()
    if "Image Position" in out:
        out["Image Position"] = (row.get("Image Position") or "").strip()
    return out


def _resolve_product(primary: dict, shape: str) -> tuple[dict | None, str | None]:
    """Resolve one primary row into output values, or return a reason."""
    tags = split_list(primary.get("Tags", ""))
    option1_value = (primary.get("Option1 Value") or "").strip()

    helper_format = (primary.get("Format") or "").strip() if shape == "template" else ""
    helper_genres = (
        [(primary.get(f"Genre {n}") or "").strip() for n in (1, 2, 3)]
        if shape == "template" else []
    )

    product_type, reason = resolve_type(tags)
    if reason:
        return None, reason

    media_format, reason = resolve_format(
        primary.get("Vendor", ""), option1_value, tags, helper_format
    )
    if reason:
        return None, reason

    genres, reason = resolve_genres(option1_value, tags, helper_genres)
    if reason:
        return None, reason

    price, reason = resolve_price(product_type, primary.get("Variant Price", ""))
    if reason:
        return None, reason

    extras = extra_tags(tags)
    if shape == "template":
        extra_col = extra_tags(split_list(primary.get("Extra tags", "")))
        extras = extras + [tag for tag in extra_col if tag not in extras]

    return {
        "type": product_type,
        "format": media_format,
        "genres": genres,
        "price": price,
        "extras": extras,
    }, None


def _build_row(primary: dict, resolved: dict, handle: str, shape: str) -> dict:
    out = _blank_row(shape)
    out.update(FIXED_VALUES)

    title = (primary.get("Title") or "").strip()
    image_src = (primary.get("Image Src") or "").strip()
    alt_text = (primary.get("Image Alt Text") or "").strip()

    out["Handle"] = handle
    out["Title"] = title
    out["Body (HTML)"] = primary.get("Body (HTML)", "") or ""
    out["Vendor"] = resolved["format"]
    out["Tags"] = ", ".join(
        [resolved["type"], resolved["format"]] + resolved["genres"] + resolved["extras"]
    )
    out["Option1 Value"] = resolved["genres"][0]
    out["Variant Price"] = resolved["price"]
    out["Image Src"] = image_src
    out["Image Alt Text"] = alt_text or (f"{title} poster" if image_src else "")
    out[GENRE_METAFIELD] = "; ".join(
        h for h in (genre_handle(g) for g in resolved["genres"]) if h
    )

    if shape == "template":
        out["Status"] = "Active"
    else:
        out["Variant Barcode"] = (primary.get("Variant Barcode") or "").strip()
        out["Image Position"] = (primary.get("Image Position") or "").strip()

    return out


def _flag(group: list[dict], reason: str) -> list[dict]:
    """Every row of a flagged product, with Reason prepended."""
    return [{REASON_COLUMN: reason, **row} for row in group]


def _group_products(rows: list[dict], shape: str) -> list[tuple[str, list[dict]]]:
    """Split rows into one group per product.

    An export groups by Handle, because a product's extra images are extra
    rows sharing its handle. A template batch cannot: its Handle cells are
    blank until this script derives them, so grouping by handle would
    collapse the whole batch into one product. One template row is one
    product — one physical copy.
    """
    if shape == "template":
        return [((row.get("Handle") or "").strip(), [row]) for row in rows]
    return group_rows_by_handle(rows)


def normalize_rows(rows: list[dict], shape: str) -> tuple[list[dict], list[dict]]:
    """Normalize every product. Returns (clean_rows, issue_rows)."""
    allocator = HandleAllocator()
    if shape == "template":
        for row in rows:
            allocator.reserve((row.get("Handle") or "").strip())

    clean_rows: list[dict] = []
    issue_rows: list[dict] = []
    produced: dict[str, list[dict]] = {}

    for handle, group in _group_products(rows, shape):
        primary = group[0]

        variant_rows = [row for row in group if _is_variant_row(row)]
        if len(variant_rows) > 1:
            issue_rows.extend(_flag(group, f"product has {len(variant_rows)} variants"))
            continue

        resolved, reason = _resolve_product(primary, shape)
        if reason:
            issue_rows.extend(_flag(group, reason))
            continue

        if shape == "template":
            typed = (primary.get("Handle") or "").strip()
            out_handle = typed or allocator.allocate(
                derive_handle(primary.get("Title", ""), resolved["format"], resolved["type"])
            )
        else:
            out_handle = handle

        product_rows = [_build_row(primary, resolved, out_handle, shape)]
        product_rows += [_image_row(row, shape) for row in group[1:]]

        produced.setdefault(out_handle, []).append({"group": group, "rows": product_rows})

    # Two input products landing on one output handle would merge on import.
    for out_handle, entries in produced.items():
        if len(entries) > 1:
            reason = f"duplicate handle {out_handle} — produced by {len(entries)} input products"
            for entry in entries:
                issue_rows.extend(_flag(entry["group"], reason))
        else:
            clean_rows.extend(entries[0]["rows"])

    return clean_rows, issue_rows
