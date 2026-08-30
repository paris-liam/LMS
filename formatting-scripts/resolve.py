"""Resolve one product's format, type, genres and price from raw fields.

Every resolver returns (value, reason): a value with reason None, or None
with a human-readable reason that lands in issues.csv. Nothing is guessed —
a genre is never inferred from a title and a type is never inferred from a
price, because both would silently mislabel physical shelf stock.
"""

from columns import FORMATTED_TAG
from taxonomy import canonical_format, canonical_genre, canonical_type

def split_list(value: str) -> list[str]:
    """Split a comma-separated cell into trimmed, non-empty parts."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def resolve_type(tags: list[str]) -> tuple[str | None, str | None]:
    """Find the Rental / Floor Sale tag."""
    found = _dedupe([t for t in (canonical_type(tag) for tag in tags) if t])
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, "no Rental or Floor Sale tag — cannot tell which this is"
    return None, f"tagged as both {' and '.join(found)}"


def resolve_genres(
    option1_value: str, tags: list[str], helper_genres: list[str]
) -> tuple[list[str], str | None]:
    """Resolve the genre list, primary first.

    Helper columns win outright when the sheet supplied them — no union,
    they're the freshest signal available.

    Otherwise the result is a union of Option1 Value and Tags, in that
    order: Option1 Value (the barcode-label slot) supplies genres[0] and
    anything else it names, then any additional genre found in Tags that
    isn't already present is appended. Option1 Value only ever holds one
    value on output, so a second pass that consulted Option1 Value alone
    would silently drop every genre after the first — the union is what
    keeps a product's own output a valid, lossless input to a re-run.
    """
    from_helpers = _dedupe([g for g in (canonical_genre(v) for v in helper_genres) if g])
    if from_helpers:
        return from_helpers, None

    from_option1 = [g for g in (canonical_genre(v) for v in split_list(option1_value)) if g]
    from_tags = [g for g in (canonical_genre(tag) for tag in tags) if g]
    merged = _dedupe(from_option1 + from_tags)
    if merged:
        return merged, None

    return [], (
        f"no usable genre (Option1 Value {option1_value!r}, "
        f"tags {', '.join(tags) or '(none)'})"
    )


def resolve_format(
    vendor: str, option1_value: str, tags: list[str], helper_format: str
) -> tuple[str | None, str | None]:
    """Resolve the media format for product.vendor.

    Precedence: helper column, then a format named inside a compound
    Option1 Value ("4K, Action" is a 4K disc whatever Vendor says), then
    Vendor itself, then a format tag.
    """
    from_helper = canonical_format(helper_format)
    if from_helper:
        return from_helper, None

    for part in split_list(option1_value):
        from_option1 = canonical_format(part)
        if from_option1:
            return from_option1, None

    from_vendor = canonical_format(vendor)
    if from_vendor:
        return from_vendor, None

    for tag in tags:
        from_tag = canonical_format(tag)
        if from_tag:
            return from_tag, None

    return None, f"no media format (Vendor {vendor!r} is not VHS/DVD/Blu-Ray/4K)"


def resolve_price(product_type: str, raw_price: str) -> tuple[str | None, str | None]:
    """Rentals are always 0; floor-sale items must carry a real price."""
    value = (raw_price or "").strip()

    if product_type == "Rental":
        # Blank is treated as zero for rentals
        if not value:
            return "0", None
        # Try to parse numerically
        try:
            numeric_value = float(value)
        except ValueError:
            return None, f"unreadable price ({value})"
        # Numeric zero is valid for rentals
        if numeric_value == 0:
            return "0", None
        # Non-zero rental price is an error
        return None, f"Rental with a nonzero price ({value})"

    # Floor Sale type
    # Blank is treated as no price
    if not value:
        return None, "Floor Sale with no price"
    # Try to parse numerically
    try:
        numeric_value = float(value)
    except ValueError:
        return None, f"unreadable price ({value})"
    # Numeric zero or negative is not valid for floor sale
    if numeric_value == 0:
        return None, "Floor Sale with no price"
    if numeric_value < 0:
        return None, f"Floor Sale with a negative price ({value})"
    # Positive price is valid
    return value, None


def extra_tags(tags: list[str]) -> list[str]:
    """Tags that are not a type, a format, a genre or the Formatted marker —
    curation labels."""
    kept = [
        tag for tag in tags
        if tag != FORMATTED_TAG
        and not (canonical_type(tag) or canonical_format(tag) or canonical_genre(tag))
    ]
    return _dedupe(kept)
