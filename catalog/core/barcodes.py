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
