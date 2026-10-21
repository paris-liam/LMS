"""Add one Libib copy to an existing Shopify rental product as a new variant,
then read the product back and check it landed as intended.

The product is checked before anything is written: it must still exist, carry
the Rental tag, match the copy's format and have the Genre option. The copy
becomes the next `Copy N` value (Option 2); the first added copy also gives the
product its Copy option, with the existing variant as `Copy 1`. Title,
description, Vendor, genre metafield, image and the existing variants are never
changed. Rerun-safe: a barcode already on the product is verified, not re-added.
"""

import re

from catalog.core.barcodes import is_new_flow_barcode
from catalog.errors import CatalogError, ShopifyError
from catalog.rental_sync.create import FIXED_TAGS, _variant_problems, admin_url
from catalog.rental_sync.transform import transform

COPY_OPTION, GENRE_OPTION = "Copy", "Genre"
NOT_PRINTED = FIXED_TAGS[1]
COPY_VALUE = re.compile(r"^Copy (\d+)$")
SHAPE_MESSAGE = "unexpected product shape — contact Liam"


def next_copy_number(values: list[str]) -> int:
    numbers = [int(m.group(1)) for m in map(COPY_VALUE.match, values) if m]
    return max(numbers, default=1) + 1


def _option(product: dict, name: str) -> dict | None:
    return next((o for o in product["options"] if o["name"] == name), None)


def _by_barcode(product: dict) -> dict:
    return {(v.get("barcode") or "").strip(): v for v in product["variants"]}


def _mismatch(product: dict, copy: dict) -> str:
    if "Rental" not in product["tags"]:
        return "That Shopify product isn't tagged Rental any more"
    if product["vendor"] != copy["format"]:
        return f"That Shopify product is {product['vendor'] or 'missing a format'}, but this copy is {copy['format']}"
    genre = _option(product, GENRE_OPTION)
    others = [o["name"] for o in product["options"] if o["name"] not in (GENRE_OPTION, COPY_OPTION)]
    if not genre or len(genre["values"]) != 1 or others:
        return SHAPE_MESSAGE
    return ""


def variant_input(copy: dict, genre: str, copy_value: str, location_id: str) -> dict:
    return {
        "optionValues": [{"optionName": GENRE_OPTION, "name": genre},
                         {"optionName": COPY_OPTION, "name": copy_value}],
        "barcode": copy["barcode"],
        "price": "0.00",
        "taxable": False,
        "inventoryPolicy": "DENY",
        "inventoryItem": {"tracked": True},
        "inventoryQuantities": [{"locationId": location_id, "availableQuantity": 1}],
    }


def verify(product: dict, barcode: str, copy_value: str, old_barcodes: list[str]) -> list[str]:
    variants = _by_barcode(product)
    variant = variants.get(barcode)
    if variant is None:
        return [f"no variant has barcode {barcode}"]
    problems = _variant_problems(variant, "")
    selected = {o["name"]: o["value"] for o in variant.get("selectedOptions") or []}
    if copy_value and selected.get(COPY_OPTION) != copy_value:
        problems.append(f"copy is {selected.get(COPY_OPTION)!r}, not {copy_value}")
    problems += [f"existing copy {b} is missing" for b in old_barcodes if b not in variants]
    if NOT_PRINTED not in product["tags"]:
        problems.append(f"missing tag: {NOT_PRINTED}")
    return problems


def _existing(shop, product: dict, barcode: str, result: dict) -> dict:
    problems = verify(product, barcode, "", [])
    missing_tag = f"missing tag: {NOT_PRINTED}"
    if problems == [missing_tag]:
        try:
            shop.add_tags(product["id"], [NOT_PRINTED])
            node = shop.product_for_copy(product["id"])
        except CatalogError as exc:
            return {**result, "problems": problems,
                    "message": f"already on this product, but the {NOT_PRINTED} tag could not be added ({exc}) "
                               f"— run the sync again or add it in Shopify admin"}
        problems = verify(node, barcode, "", []) if node else ["could not be read back"]
        if not problems:
            return {**result, "status": "skipped_exists",
                    "message": f"already a copy on {product['handle']}; added the missing {NOT_PRINTED} tag"}
    if problems:
        return {**result, "problems": problems,
                "message": "already on this product but needs attention: " + "; ".join(problems)
                           + " — fix it in Shopify admin"}
    return {**result, "status": "skipped_exists", "message": f"already a copy on {product['handle']}"}


def add_copy(shop, item: dict, product_id: str) -> dict:
    copy = transform(item)
    result = {"status": "failed", "barcode": copy["barcode"], "title": copy["title"], "handle": "",
              "admin_url": admin_url(shop.store, product_id), "message": "", "problems": []}
    if not is_new_flow_barcode(copy["barcode"]):
        return {**result, "message": "not ready: barcode is not a 13-digit 201… Libib barcode"}
    if copy["set_aside"]:
        return {**result, "message": "not ready: " + "; ".join(copy["set_aside"])}

    try:
        owner = shop.barcode_owner(copy["barcode"])
        if owner and owner["id"] != product_id:
            return {**result, "message": f"This barcode is already on another Shopify product ({owner['handle']}) "
                                         f"— check it in Shopify admin"}
        product = shop.product_for_copy(product_id)
    except ShopifyError as exc:
        return {**result, "message": str(exc)}
    if product is None:
        return {**result, "message": "That Shopify product no longer exists"}
    result["handle"] = product["handle"]
    if copy["barcode"] in _by_barcode(product):
        return _existing(shop, product, copy["barcode"], result)
    mismatch = _mismatch(product, copy)
    if mismatch:
        return {**result, "message": mismatch}

    copies = _option(product, COPY_OPTION)
    copy_value = f"Copy {next_copy_number(copies['values'] if copies else [])}"
    old_barcodes = list(_by_barcode(product))
    try:
        location = shop.location_id()
        if not copies:
            shop.add_copy_option(product_id)
        shop.add_variant(product_id, variant_input(copy, _option(product, GENRE_OPTION)["values"][0],
                                                   copy_value, location))
        shop.add_tags(product_id, [NOT_PRINTED])
    except ShopifyError as exc:
        return {**result, "message": f"{exc} — it may have been partly added; run the sync again (an existing "
                                     f"copy is checked, not duplicated) or look in Shopify admin"}
    try:
        node = shop.product_for_copy(product_id)
    except CatalogError as exc:
        return {**result, "message": f"added in Shopify but could not be checked ({exc}) — look in Shopify admin"}
    problems = verify(node, copy["barcode"], copy_value, old_barcodes) if node else ["could not be read back"]
    if problems:
        return {**result, "problems": problems,
                "message": "added in Shopify but needs checking: " + "; ".join(problems)}
    return {**result, "status": "added", "message": f"added as {copy_value}"}
