"""The rental barcode rule, shared by the audit and the Libib diff. A rental's
barcode is its Libib call number, so it must be exactly 8 digits and appear on
no other movie (Rental or Floor Sale)."""

import re

RENTAL_BARCODE = re.compile(r"^[0-9]{8}$")


def is_rental_barcode(value) -> bool:
    return bool(RENTAL_BARCODE.match((value or "").strip()))


def barcode_owners(rows: list[dict]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if barcode:
            owners.setdefault(barcode, []).append(row.get("Handle", ""))
    return owners


# New-flow rentals (2026-10-15): Libib generates the barcode (13 digits
# starting 201) and the rental sync app creates the Shopify product from it.
# An 8-digit barcode that happens to start 201 is a legacy rental, not this.
NEW_FLOW_BARCODE = re.compile(r"^201[0-9]{10}$")


def is_new_flow_barcode(value) -> bool:
    return bool(NEW_FLOW_BARCODE.match((value or "").strip()))
