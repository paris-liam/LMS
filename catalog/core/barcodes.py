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


# Floor Sale (2026-10-20): the Floor Sale sheet writes the barcode itself, as
# the batch date (yymmdd) then the row's number in the batch (001…999). Nine
# digits, so it can never equal an 8-digit Retail Barcode Labels code (the
# app's are the variant ID's last 8 digits and collide) or a 13-digit Libib one.
FLOOR_SALE_BARCODE = re.compile(r"^[0-9]{9}$")
FLOOR_SALE_BATCH_LIMIT = 999


def floor_sale_barcode(batch_date, number: int) -> str:
    """The barcode of a batch's `number`th row (1-based)."""
    return f"{batch_date.strftime('%y%m%d')}{number:03d}"


def is_floor_sale_barcode(value) -> bool:
    return bool(FLOOR_SALE_BARCODE.match((value or "").strip()))


def is_new_flow_item(barcode, call_number) -> bool:
    """A Libib copy the rental sync app owns: a 201… barcode and no legacy
    call number (a call number equal to that barcode also counts). A legacy
    item can carry a Libib-generated 201… barcode alongside its old call
    number — that one stays with the legacy Libib tooling."""
    call = (call_number or "").strip()
    return is_new_flow_barcode(barcode) and (not call or call == (barcode or "").strip())
