"""Work out which of the three input shapes a CSV is, from its header.

A prior output of this script carries a leading Reason column plus the
columns of whatever it came from, so stripping Reason first lets the same
rules classify it.
"""

from columns import REASON_COLUMN


class UnknownShapeError(ValueError):
    """The header matches neither the upload template nor a Shopify export."""


# Checked in order. "Variant Barcode" appears in a raw Shopify export and in
# this script's export output, but never in the 17-column template contract.
# Some raw Shopify exports pluralize it to "Variant Barcodes" instead (seen
# 2026-09-02 on a production export) — accept either spelling.
TEMPLATE_MARKERS = ("Format", "Genre 1")
EXPORT_MARKERS = ("Variant Barcode", "Variant Barcodes")
TEMPLATE_OUTPUT_MARKER = "Status"


def strip_reason(fieldnames: list[str], rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Drop the Reason column added to issues/unmatched files, if present."""
    if REASON_COLUMN not in fieldnames:
        return fieldnames, rows
    kept = [name for name in fieldnames if name != REASON_COLUMN]
    stripped = [{k: v for k, v in row.items() if k != REASON_COLUMN} for row in rows]
    return kept, stripped


def detect_shape(fieldnames: list[str]) -> str:
    """Return "template" or "export"; raise UnknownShapeError if neither."""
    columns = set(fieldnames)
    if all(marker in columns for marker in TEMPLATE_MARKERS):
        return "template"
    if any(marker in columns for marker in EXPORT_MARKERS):
        return "export"
    if TEMPLATE_OUTPUT_MARKER in columns:
        return "template"
    raise UnknownShapeError(
        "Unrecognised CSV header. Expected either the upload template "
        f"(columns {', '.join(TEMPLATE_MARKERS)}), this script's template output "
        f"(column {TEMPLATE_OUTPUT_MARKER}), or a Shopify product export "
        f"(column {' or '.join(EXPORT_MARKERS)}). Got: {', '.join(fieldnames) or '(empty header)'}"
    )
