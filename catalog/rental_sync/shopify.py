"""The rental sync app's Shopify access: the reads behind the barcode diff and
setup checks, the last-run metafield, and the writes create.py makes.

Uses the same Dev Dashboard custom app as the pipeline (client credentials
grant). A Vercel instance that stays warm reuses its token; a cold one asks
for a new one. Scopes needed: read/write_products, write_inventory,
read_locations, read_metaobjects, read/write_publications.
"""

import http.client
import json
import time

from catalog.core.barcodes import is_new_flow_barcode
from catalog.errors import SetupError, ShopifyError
from catalog.shopify import api
from catalog.shopify.writer import ApiStore

TOKEN_LIFETIME_SECONDS = 23 * 3600   # Shopify issues 24 h tokens
LAST_RUN_NAMESPACE, LAST_RUN_KEY = "lms", "rental_sync_last_run"
ONLINE_STORE = "Online Store"

_tokens: dict[tuple[str, str], tuple[str, float]] = {}


def cached_token(store, client_id, client_secret, now=time.time, request=api.request_token) -> str:
    key = (store, client_id)
    token, expires = _tokens.get(key, ("", 0.0))
    if token and expires > now():
        return token
    token = request(store, client_id, client_secret)
    _tokens[key] = (token, now() + TOKEN_LIFETIME_SECONDS)
    return token


NEW_FLOW_BARCODES = """
query($after: String) {
  productVariants(first: 250, after: $after, query: "barcode:201*") {
    nodes { barcode }
    pageInfo { hasNextPage endCursor }
  }
}"""
VARIANTS_BY_BARCODE = """
query($q: String!) { productVariants(first: 10, query: $q) { nodes { barcode product { id handle } } } }"""
PRODUCT_BY_HANDLE = """
query($h: String!) { productByIdentifier(identifier: {handle: $h}) { id } }"""
LOCATIONS = """
query { locations(first: 10, includeInactive: false) { nodes { id name } } }"""
PUBLICATIONS = """
query { publications(first: 25) { nodes { id name } } }"""
GENRE_BY_HANDLE = """
query($h: String!) { metaobjectByHandle(handle: {type: "shopify--genre", handle: $h}) { id } }"""
LAST_RUN = """
query { shop { metafield(namespace: "lms", key: "rental_sync_last_run") { value } } }"""
SHOP_ID = """
query { shop { id } }"""
SET_METAFIELDS = """
mutation($m: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $m) { userErrors { field message } } }"""
PRODUCT_SET = """
mutation($input: ProductSetInput!) {
  productSet(input: $input, synchronous: true) { product { id handle } userErrors { field message } }
}"""
PUBLISH = """
mutation($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}"""
READ_BACK = """
query($id: ID!) {
  product(id: $id) {
    id handle tags
    variants(first: 5) { nodes { barcode taxable inventoryQuantity inventoryItem { tracked } } }
    resourcePublicationsV2(first: 20, onlyPublished: true) { nodes { publication { id name } } }
    media(first: 5) { nodes { status } }
  }
}"""


class RentalShop:
    def __init__(self, execute, store: str):
        self.store = store
        self._api = ApiStore(execute, store)
        self._genre_ids: dict[str, str] = {}

    def gql(self, query: str, **variables) -> dict:
        try:
            return self._api.gql(query, **variables)
        except RuntimeError as exc:
            # ApiStore truncates the error text to 300 chars, which can cut off the
            # ACCESS_DENIED code but keeps the leading "Access denied" message.
            if "ACCESS_DENIED" in str(exc) or "Access denied" in str(exc):
                raise SetupError(f"the Shopify app is missing a permission: {exc}") from None
            raise ShopifyError(f"Shopify returned an error: {exc}") from None
        except (OSError, http.client.HTTPException) as exc:
            # urllib lets raw socket/http errors through from getresponse()/read()
            raise ShopifyError(f"could not reach Shopify: {type(exc).__name__}") from None

    def mutate(self, query: str, root: str, **variables) -> dict:
        result = self.gql(query, **variables)[root]
        errors = result.get("userErrors") or []
        if errors:
            raise ShopifyError("; ".join(e.get("message", "") for e in errors))
        return result

    # reads

    def new_flow_barcodes(self) -> set[str]:
        found: set[str] = set()
        after = None
        while True:
            page = self.gql(NEW_FLOW_BARCODES, after=after)["productVariants"]
            found |= {(n.get("barcode") or "").strip() for n in page["nodes"]}
            if not page["pageInfo"]["hasNextPage"]:
                return {b for b in found if is_new_flow_barcode(b)}
            after = page["pageInfo"]["endCursor"]

    def barcode_owner(self, barcode: str) -> dict | None:
        nodes = self.gql(VARIANTS_BY_BARCODE, q=f"barcode:{barcode}")["productVariants"]["nodes"]
        return next(({"id": n["product"]["id"], "handle": n["product"]["handle"]}
                     for n in nodes if (n.get("barcode") or "").strip() == barcode), None)

    def handle_taken(self, handle: str) -> bool:
        return self.gql(PRODUCT_BY_HANDLE, h=handle)["productByIdentifier"] is not None

    def location_id(self) -> str:
        nodes = self.gql(LOCATIONS)["locations"]["nodes"]
        if len(nodes) != 1:
            names = ", ".join(n["name"] for n in nodes) or "none"
            raise SetupError(f"expected exactly one active Shopify location, found {len(nodes)}: {names}")
        return nodes[0]["id"]

    def online_store_publication_id(self) -> str:
        nodes = self.gql(PUBLICATIONS)["publications"]["nodes"]
        matches = [n["id"] for n in nodes if n["name"] == ONLINE_STORE]
        if len(matches) != 1:
            raise SetupError(f"found {len(matches)} '{ONLINE_STORE}' sales channels in Shopify — expected one")
        return matches[0]

    def genre_ids(self, handles: list[str]) -> list[str]:
        for handle in handles:
            if handle not in self._genre_ids:
                node = self.gql(GENRE_BY_HANDLE, h=handle)["metaobjectByHandle"]
                if not node:
                    raise SetupError(f"Shopify has no genre value '{handle}' (shopify--genre metaobject)")
                self._genre_ids[handle] = node["id"]
        return [self._genre_ids[h] for h in handles]

    def last_run(self) -> dict | None:
        node = self.gql(LAST_RUN)["shop"]["metafield"]
        if not node:
            return None
        try:
            return json.loads(node["value"])
        except (TypeError, ValueError):
            return None

    def read_back(self, product_id: str) -> dict:
        return self.gql(READ_BACK, id=product_id)["product"]

    # writes

    def save_last_run(self, summary: dict) -> None:
        shop_id = self.gql(SHOP_ID)["shop"]["id"]
        self.mutate(SET_METAFIELDS, "metafieldsSet", m=[{
            "ownerId": shop_id, "namespace": LAST_RUN_NAMESPACE, "key": LAST_RUN_KEY,
            "type": "json", "value": json.dumps(summary)}])

    def product_set(self, product_input: dict) -> dict:
        return self.mutate(PRODUCT_SET, "productSet", input=product_input)["product"]

    def publish(self, product_id: str, publication_id: str) -> None:
        self.mutate(PUBLISH, "publishablePublish", id=product_id, input=[{"publicationId": publication_id}])


def shop_from_env(env: dict) -> RentalShop:
    store = env["SHOPIFY_STORE"].strip()
    token = cached_token(store, env["SHOPIFY_CLIENT_ID"].strip(), env["SHOPIFY_CLIENT_SECRET"].strip())
    return RentalShop(api.make_executor(store, token), store)
