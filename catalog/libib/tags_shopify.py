"""`libib tags` — the Shopify side: read every rental (with createdAt and
format), the products tagged new-arrival / community-pick, and the Community
Pick entries; add/remove those two product tags.

Uses the pipeline's Dev Dashboard custom app (client credentials grant).
Scopes needed: read_products, write_products, read_metaobjects. Any GraphQL
error while reading raises, and so does a read with no rentals at all, so a
bad read never turns into tag removals.
"""

from typing import Callable

from catalog import config
from catalog.errors import InputShapeError
from catalog.libib.tags import SHOPIFY_COMMUNITY_PICK, SHOPIFY_NEW_ARRIVAL, Product, ShopifyChange, ShopifyState
from catalog.shopify import api
from catalog.shopify.writer import ApiStore

Gql = Callable[..., dict]

PRODUCTS = """
query($q: String!, $after: String) {
  products(first: 250, after: $after, query: $q) {
    nodes { id title tags vendor createdAt variants(first: 5) { nodes { barcode } } }
    pageInfo { hasNextPage endCursor }
  }
}"""
COMMUNITY_PICKS = """
query($after: String) {
  metaobjects(type: "community_pick", first: 250, after: $after) {
    nodes {
      capabilities { publishable { status } }
      field(key: "product") {
        reference { ... on Product { id title tags vendor createdAt variants(first: 5) { nodes { barcode } } } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""
TAGS_ADD = """
mutation($id: ID!, $tags: [String!]!) { tagsAdd(id: $id, tags: $tags) { userErrors { message } } }"""
TAGS_REMOVE = """
mutation($id: ID!, $tags: [String!]!) { tagsRemove(id: $id, tags: $tags) { userErrors { message } } }"""


def _pages(gql: Gql, query: str, root: str, **variables):
    after = None
    while True:
        data = gql(query, after=after, **variables)[root]
        yield from data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            return
        after = data["pageInfo"]["endCursor"]


def _product(node: dict) -> Product:
    barcodes = tuple(b.strip() for b in (v.get("barcode") for v in node["variants"]["nodes"]) if b and b.strip())
    return Product(node["id"], node["title"], tuple(node["tags"]), barcodes, node.get("vendor") or "",
                   node.get("createdAt") or "")


def _tagged(gql: Gql, tag: str) -> tuple[Product, ...]:
    # Shopify's tag: search isn't exact, so re-check each product's tags.
    return tuple(_product(n) for n in _pages(gql, PRODUCTS, "products", q=f"tag:{tag}") if tag in n["tags"])


def _active_picks(gql: Gql) -> tuple[Product, ...]:
    picked = []
    for entry in _pages(gql, COMMUNITY_PICKS, "metaobjects"):
        publishable = (entry.get("capabilities") or {}).get("publishable")
        if publishable and publishable.get("status") != "ACTIVE":
            continue
        reference = (entry.get("field") or {}).get("reference")
        if reference:
            picked.append(_product(reference))
    return tuple(picked)


def _rentals(gql: Gql) -> tuple[Product, ...]:
    rentals = tuple(p for p in map(_product, _pages(gql, PRODUCTS, "products", q="tag:Rental")) if p.is_rental)
    if not rentals:
        raise InputShapeError("Shopify returned no Rental products — not changing anything")
    return rentals


def read_state(gql: Gql) -> ShopifyState:
    return ShopifyState(_rentals(gql), _active_picks(gql), _tagged(gql, SHOPIFY_COMMUNITY_PICK),
                        _tagged(gql, SHOPIFY_NEW_ARRIVAL))


def write_changes(gql: Gql, changes: list[ShopifyChange]) -> list[dict]:
    results = []
    for change in changes:
        query, root = (TAGS_ADD, "tagsAdd") if change.action == "add" else (TAGS_REMOVE, "tagsRemove")
        try:
            errors = gql(query, id=change.product_id, tags=[change.tag])[root]["userErrors"]
            status, message = ("error", "; ".join(e["message"] for e in errors)) if errors else ("updated", "ok")
        except Exception as exc:  # keep going; the run reports the failure
            status, message = "error", f"{type(exc).__name__}: {exc}"
        results.append({"title": change.title, "tag": change.tag, "action": change.action, "status": status,
                        "message": message})
    return results


def store_from_env(store: str) -> ApiStore:
    token = api.request_token(store, config.require_env(config.ENV_SHOPIFY_CLIENT_ID),
                              config.require_env(config.ENV_SHOPIFY_CLIENT_SECRET))
    return ApiStore(api.make_executor(store, token), store)
