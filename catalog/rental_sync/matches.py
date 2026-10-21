"""Resolve a new copy's siblings (other copies of the same Libib item already
in Shopify) to the one Shopify product they live on, so the copy can be added
there instead of making a second product."""

from catalog.rental_sync.create import admin_url

SEVERAL_PRODUCTS = "This Libib item is on several Shopify products — combine them first"

NOT_FOUND = "This Libib item is already in Shopify, but its product couldn't be found — try the sync again in a few minutes."


def attach_matches(result: dict, shop, store: str) -> dict:
    owners: dict[str, dict | None] = {}
    summaries: dict[str, dict | None] = {}

    def owner(barcode):
        if barcode not in owners:
            owners[barcode] = shop.barcode_owner(barcode)
        return owners[barcode]

    def summary(product_id):
        if product_id not in summaries:
            summaries[product_id] = shop.product_summary(product_id)
        return summaries[product_id]

    ready = []
    for copy in result["ready"]:
        ids = list(dict.fromkeys(o["id"] for o in map(owner, copy["siblings_in_shopify"]) if o))
        if len(ids) > 1:
            copy["set_aside"].append(SEVERAL_PRODUCTS)
            copy["products"] = [admin_url(store, i) for i in ids]
            result["set_aside"].append(copy)
            continue
        if ids and summary(ids[0]):
            copy["match"] = {**summary(ids[0]), "admin_url": admin_url(store, ids[0])}
        elif copy["siblings_in_shopify"]:
            copy["set_aside"].append(NOT_FOUND)
            result["set_aside"].append(copy)
            continue
        ready.append(copy)
    result["ready"] = ready
    return result
