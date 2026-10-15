"""Create one Libib copy as a Shopify rental product, then read it back and
check it landed as intended.

Rerun-safe: a copy whose barcode or handle is already in Shopify is skipped,
so a re-run after a crash, or a repeat click (the page disables the button
while creating), never creates it twice. The handle check is a direct lookup,
so it is never behind a just-created product. Shopify fields are always
derived here from the Libib values, never taken from the browser.
"""

import html
import json
import time

from catalog.core.barcodes import is_new_flow_barcode
from catalog.core.handles import slugify
from catalog.errors import ShopifyError
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
    return list(FIXED_TAGS) + copy["extra_tags"]


def product_set_input(copy: dict, handle: str, location_id: str, genre_ids: list[str], poster: dict | None) -> dict:
    genre = copy["genres"][0]["name"]
    product = {
        "title": copy["title"],
        "handle": handle,
        "descriptionHtml": description_html(copy["description"]),
        "vendor": copy["format"],
        "category": CATEGORY_ID,
        "tags": _tags(copy),
        "status": "ACTIVE",
        "productOptions": [{"name": "Genre", "position": 1, "values": [{"name": genre}]}],
        "variants": [{
            "optionValues": [{"optionName": "Genre", "name": genre}],
            "barcode": copy["barcode"],
            "price": "0.00",
            "taxable": False,
            "inventoryPolicy": "DENY",
            "inventoryItem": {"tracked": True},
            "inventoryQuantities": [{"locationId": location_id, "name": "available", "quantity": 1}],
        }],
        "metafields": [{"namespace": "shopify", "key": "genre", "type": "list.metaobject_reference",
                        "value": json.dumps(genre_ids)}],
    }
    if poster:
        alt = (poster.get("alt") or f"{copy['title']} poster")[:MAX_ALT_LENGTH]
        product["files"] = [{"originalSource": poster["url"], "alt": alt, "contentType": "IMAGE"}]
    return product


def verify(node: dict, copy: dict, handle: str, publication_id: str) -> list[str]:
    problems = []
    if node["handle"] != handle:
        problems.append(f"handle is {node['handle']}, not {handle}")
    variants = node["variants"]["nodes"]
    if len(variants) != 1:
        problems.append(f"has {len(variants)} variants, not 1")
    else:
        variant = variants[0]
        if (variant.get("barcode") or "").strip() != copy["barcode"]:
            problems.append(f"barcode is {variant.get('barcode')!r}")
        if variant.get("taxable") is not False:
            problems.append("charges tax")
        if variant.get("inventoryQuantity") != 1:
            problems.append(f"quantity is {variant.get('inventoryQuantity')}, not 1")
        if not (variant.get("inventoryItem") or {}).get("tracked"):
            problems.append("inventory is not tracked")
    missing = [t for t in _tags(copy) if t not in node["tags"]]
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


def create_copy(shop, item: dict, poster: dict | None, sleep=time.sleep) -> dict:
    copy = transform(item)
    result = {"status": "failed", "barcode": copy["barcode"], "title": copy["title"], "handle": "",
              "admin_url": "", "poster": "none", "message": "", "problems": []}
    if not is_new_flow_barcode(copy["barcode"]):
        return {**result, "message": "not ready: barcode is not a 13-digit 201… Libib barcode"}
    if copy["set_aside"]:
        return {**result, "message": "not ready: " + "; ".join(copy["set_aside"])}
    handle = handle_for(copy)
    result["handle"] = handle

    try:
        owner = shop.barcode_owner(copy["barcode"])
        if owner:
            return {**result, "status": "skipped_exists", "message": f"already in Shopify ({owner})"}
        if shop.handle_taken(handle):
            return {**result, "status": "skipped_exists", "message": f"a product with handle {handle} already exists"}
        location = shop.location_id()
        genre_ids = shop.genre_ids([g["handle"] for g in copy["genres"]])
        publication = shop.online_store_publication_id()
        product = shop.product_set(product_set_input(copy, handle, location, genre_ids, poster))
    except ShopifyError as exc:
        return {**result, "message": str(exc)}

    result["admin_url"] = admin_url(shop.store, product["id"])
    if product["handle"] != handle:
        return {**result, "message": f"Shopify created this as {product['handle']} instead of {handle}, so it is "
                                     f"probably a duplicate of a product created moments ago — check both in "
                                     f"Shopify admin and delete the extra one"}
    try:
        shop.publish(product["id"], publication)
        node = _read_settled(shop, product["id"], bool(poster), sleep)
    except ShopifyError as exc:
        return {**result, "message": f"created in Shopify but not finished ({exc}) — open it in Shopify admin, "
                                     f"publish it to the Online Store and check its details"}

    problems = verify(node, copy, handle, publication)
    if problems:
        return {**result, "problems": problems,
                "message": "created in Shopify but needs checking: " + "; ".join(problems)}
    return {**result, "status": "created", "poster": _poster_status(node) if poster else "none"}
