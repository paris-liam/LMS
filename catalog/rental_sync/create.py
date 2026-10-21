"""Create one Libib item as a Shopify rental product (a variant per copy),
then read it back and check it landed as intended.

Rerun-safe: a copy whose barcode or handle is already in Shopify is never
created twice. A barcode hit is read back and verified like a new product, so
only a clean one counts as skipped; one a previous run left unfinished is
reported as needing attention. The handle check is a direct lookup,
so it is never behind a just-created product. Shopify fields are always
derived here from the Libib values, never taken from the browser.
"""

import html
import json
import time

from catalog.core.barcodes import is_new_flow_barcode
from catalog.core.handles import slugify
from catalog.errors import CatalogError, ShopifyError
from catalog.rental_sync.transform import transform
from catalog.shopify.writer import MOVIE_CATEGORY_IDS

FIXED_TAGS = ("Rental", "Barcode Not Printed")
CATEGORY_ID = MOVIE_CATEGORY_IDS["Media > Videos"]
MEDIA_WAIT_SECONDS = 20
MEDIA_POLL_SECONDS = 2
MAX_ALT_LENGTH = 500


def handle_for(copy: dict) -> str:
    return f"{slugify(copy['title'])}-{slugify(copy['format'])}-rental-{copy['barcode']}"


def description_html(text: str) -> str:
    return f"<p>{html.escape(text, quote=False)}</p>" if text else ""


def admin_url(store: str, product_id: str) -> str:
    return f"https://admin.shopify.com/store/{store.split('.')[0]}/products/{product_id.rsplit('/', 1)[-1]}"


def _tags(copy: dict) -> list[str]:
    fixed = {t.lower() for t in FIXED_TAGS}
    return list(FIXED_TAGS) + [t for t in copy["extra_tags"] if t.lower() not in fixed]


def product_set_input(copies: list[dict], handle: str, location_id: str, genre_ids: list[str],
                      poster: dict | None) -> dict:
    first = copies[0]
    genre = first["genres"][0]["name"]
    several = len(copies) > 1
    options = [{"name": "Genre", "position": 1, "values": [{"name": genre}]}]
    if several:
        options.append({"name": "Copy", "position": 2,
                        "values": [{"name": f"Copy {n}"} for n in range(1, len(copies) + 1)]})
    variants = []
    for n, copy in enumerate(copies, 1):
        values = [{"optionName": "Genre", "name": genre}]
        if several:
            values.append({"optionName": "Copy", "name": f"Copy {n}"})
        variants.append({
            "optionValues": values,
            "barcode": copy["barcode"],
            "price": "0.00",
            "taxable": False,
            "inventoryPolicy": "DENY",
            "inventoryItem": {"tracked": True},
            "inventoryQuantities": [{"locationId": location_id, "name": "available", "quantity": 1}],
        })
    product = {
        "title": first["title"],
        "handle": handle,
        "descriptionHtml": description_html(first["description"]),
        "vendor": first["format"],
        "category": CATEGORY_ID,
        "tags": _tags(first),
        "status": "ACTIVE",
        "productOptions": options,
        "variants": variants,
        "metafields": [{"namespace": "shopify", "key": "genre", "type": "list.metaobject_reference",
                        "value": json.dumps(genre_ids)}],
    }
    if poster:
        alt = (poster.get("alt") or f"{first['title']} poster")[:MAX_ALT_LENGTH]
        product["files"] = [{"originalSource": poster["url"], "alt": alt, "contentType": "IMAGE"}]
    return product


def _variant_problems(variant: dict, label: str) -> list[str]:
    problems = []
    if variant.get("taxable") is not False:
        problems.append(label + "charges tax")
    if variant.get("inventoryQuantity") != 1:
        problems.append(f"{label}quantity is {variant.get('inventoryQuantity')}, not 1")
    if not (variant.get("inventoryItem") or {}).get("tracked"):
        problems.append(label + "inventory is not tracked")
    return problems


def verify(node: dict, copies: list[dict], handle: str, publication_id: str) -> list[str]:
    problems = []
    if node["handle"] != handle:
        problems.append(f"handle is {node['handle']}, not {handle}")
    variants = node["variants"]["nodes"]
    if len(variants) != len(copies):
        problems.append(f"has {len(variants)} variants, not {len(copies)}")
    by_barcode = {(v.get("barcode") or "").strip(): v for v in variants}
    for copy in copies:
        variant = by_barcode.get(copy["barcode"])
        label = f"{copy['barcode']}: " if len(copies) > 1 else ""
        if variant is None:
            problems.append(f"barcode is {variants[0].get('barcode')!r}" if len(variants) == len(copies) == 1
                            else f"no variant has barcode {copy['barcode']}")
            continue
        problems += _variant_problems(variant, label)
    missing = [t for t in _tags(copies[0]) if t not in node["tags"]]
    if missing:
        problems.append("missing tags: " + ", ".join(missing))
    published = {n["publication"]["id"]: n["publication"]["name"] for n in node["resourcePublicationsV2"]["nodes"]}
    if publication_id not in published:
        problems.append("not on the Online Store")
    others = sorted(name for pid, name in published.items() if pid != publication_id)
    if others:
        problems.append("also on " + ", ".join(others))
    return problems


def _poster_status(node: dict) -> str:
    statuses = [m["status"] for m in node["media"]["nodes"]]
    if not statuses:
        return "failed"
    return "failed" if "FAILED" in statuses else "ok"


def _read(shop, product_id: str) -> dict:
    node = shop.read_back(product_id)
    if node is None:
        raise ShopifyError("the new product could not be read back")
    return node


def _read_settled(shop, product_id: str, wait_for_media: bool, sleep) -> dict:
    node = _read(shop, product_id)
    waited = 0
    while wait_for_media and waited < MEDIA_WAIT_SECONDS and any(
            m["status"] in ("UPLOADED", "PROCESSING") for m in node["media"]["nodes"]):
        sleep(MEDIA_POLL_SECONDS)
        waited += MEDIA_POLL_SECONDS
        node = _read(shop, product_id)
    return node


def _existing(shop, copies: list[dict], owner: dict, result: dict) -> dict:
    result = {**result, "handle": owner["handle"], "admin_url": admin_url(shop.store, owner["id"])}
    try:
        node = shop.read_back(owner["id"])
        problems = (verify(node, copies, owner["handle"], shop.online_store_publication_id())
                    if node else ["could not be read back"])
    except CatalogError as exc:
        problems = [f"could not be checked ({exc})"]
    if problems:
        return {**result, "problems": problems,
                "message": "already in Shopify but needs attention: " + "; ".join(problems)
                           + " — fix it in Shopify admin"}
    return {**result, "status": "skipped_exists", "message": f"already in Shopify ({owner['handle']})"}


def create_item(shop, items: list[dict], poster: dict | None, sleep=time.sleep) -> dict:
    result = {"status": "failed", "barcode": "", "barcodes": [], "title": "", "handle": "",
              "admin_url": "", "poster": "none", "message": "", "problems": []}
    if not items:
        return {**result, "message": "not ready: no copies were sent"}
    copies = sorted((transform(i) for i in items), key=lambda c: c["barcode"])
    result = {**result, "barcode": copies[0]["barcode"], "barcodes": [c["barcode"] for c in copies],
              "title": copies[0]["title"]}
    if len({i.get("id") for i in items}) > 1:
        return {**result, "message": "not ready: these copies are not all from the same Libib item"}
    for copy in copies:
        if not is_new_flow_barcode(copy["barcode"]):
            return {**result, "message": "not ready: barcode is not a 13-digit 201… Libib barcode"}
        if copy["set_aside"]:
            return {**result, "message": "not ready: " + "; ".join(copy["set_aside"])}
    handle = handle_for(copies[0])
    result["handle"] = handle

    try:
        owners = [shop.barcode_owner(c["barcode"]) for c in copies]
    except ShopifyError as exc:
        return {**result, "message": str(exc)}
    if all(owners) and len({o["id"] for o in owners}) == 1:
        return _existing(shop, copies, owners[0], result)
    if any(owners):
        return {**result, "message": "Some of these copies are already in Shopify — run the sync again so "
                                     "they're added as copies"}
    try:
        if shop.handle_taken(handle):
            return {**result, "status": "skipped_exists", "message": f"a product with handle {handle} already exists"}
        location = shop.location_id()
        genre_ids = shop.genre_ids([g["handle"] for g in copies[0]["genres"]])
        publication = shop.online_store_publication_id()
    except ShopifyError as exc:
        return {**result, "message": str(exc)}
    try:
        product = shop.product_set(product_set_input(copies, handle, location, genre_ids, poster))
    except ShopifyError as exc:
        return {**result, "message": f"{exc} — it may have been created anyway; run the sync again (an existing "
                                     f"copy is checked, not duplicated) or look in Shopify admin"}

    result["admin_url"] = admin_url(shop.store, product["id"])
    if product["handle"] != handle:
        return {**result, "message": f"Shopify created this as {product['handle']} instead of {handle}, so it is "
                                     f"probably a duplicate of a product created moments ago — check both in "
                                     f"Shopify admin and delete the extra one"}
    try:
        shop.publish(product["id"], publication)
        node = _read_settled(shop, product["id"], bool(poster), sleep)
    except CatalogError as exc:
        return {**result, "message": f"created in Shopify but not finished ({exc}) — open it in Shopify admin, "
                                     f"publish it to the Online Store and check its details"}

    problems = verify(node, copies, handle, publication)
    if problems:
        return {**result, "problems": problems,
                "message": "created in Shopify but needs checking: " + "; ".join(problems)}
    return {**result, "status": "created", "poster": _poster_status(node) if poster else "none"}
