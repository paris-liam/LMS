#!/usr/bin/env python3
"""
Unpublishes every "Rental"-tagged product from the Point of Sale and Shop
sales channels, leaving it on the Online Store channel only.

Only products actually published to POS or Shop are touched, so re-running is
safe. Products that are not on the Online Store are reported but left alone —
this script never publishes anything.

Auth: the catalog pipeline's custom app (SHOPIFY_CLIENT_ID /
SHOPIFY_CLIENT_SECRET), which needs write_publications.

Usage:
  python3 scripts/unpublish-rentals-from-pos-and-shop.py [--store STORE] [--dry-run]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from catalog import config  # noqa: E402
from catalog.shopify import api  # noqa: E402

REMOVE_FROM = ("Point of Sale", "Shop")
KEEP_ON = "Online Store"

PUBLICATIONS_QUERY = "query { publications(first: 20) { nodes { id name } } }"

FETCH_QUERY = """
query($cursor: String, $online: ID!, $pos: ID!, $shop: ID!) {
  products(first: 250, after: $cursor, query: "tag:Rental") {
    nodes {
      id title
      online: publishedOnPublication(publicationId: $online)
      pos: publishedOnPublication(publicationId: $pos)
      shop: publishedOnPublication(publicationId: $shop)
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

CHUNK_SIZE = 20


class _Query:
    """Lets api.make_executor's execute() take a query string instead of a path."""

    def __init__(self, text):
        self.text = text

    def read_text(self, encoding=None):
        return self.text


def make_runner(store):
    token = api.request_token(store, config.get_env(config.ENV_SHOPIFY_CLIENT_ID),
                              config.get_env(config.ENV_SHOPIFY_CLIENT_SECRET))
    execute = api.make_executor(store, token)

    def run(query, variables=None):
        payload = execute(store, _Query(query), variables or {})
        if payload.get("errors"):
            raise SystemExit(f"GraphQL errors: {payload['errors']}")
        return payload["data"]

    return run


def fetch_rentals(run, pubs):
    products, cursor = [], None
    while True:
        page = run(FETCH_QUERY, {"cursor": cursor, "online": pubs[KEEP_ON],
                                 "pos": pubs["Point of Sale"], "shop": pubs["Shop"]})["products"]
        products.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return products
        cursor = page["pageInfo"]["endCursor"]


def unpublish_chunk(run, chunk, pubs):
    variables, var_defs, parts = {}, [], []
    for i, product in enumerate(chunk):
        targets = [pubs["Point of Sale"]] * product["pos"] + [pubs["Shop"]] * product["shop"]
        variables[f"id{i}"] = product["id"]
        var_defs.append(f"$id{i}: ID!")
        inputs = ", ".join(f'{{publicationId: "{t}"}}' for t in targets)
        parts.append(f"m{i}: publishableUnpublish(id: $id{i}, input: [{inputs}]) "
                     f"{{ userErrors {{ field message }} }}")
    mutation = f"mutation({', '.join(var_defs)}) {{ {' '.join(parts)} }}"
    return run(mutation, variables)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=config.DEFAULT_STORE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run = make_runner(args.store)
    pubs = {n["name"]: n["id"] for n in run(PUBLICATIONS_QUERY)["publications"]["nodes"]}
    missing = [name for name in (KEEP_ON, *REMOVE_FROM) if name not in pubs]
    if missing:
        raise SystemExit(f"{args.store} has no publication named {missing}")

    print(f"Fetching 'Rental' products on {args.store} ...")
    products = fetch_rentals(run, pubs)
    to_fix = [p for p in products if p["pos"] or p["shop"]]
    not_online = [p for p in products if not p["online"]]
    print(f"  {len(products)} Rental products")
    print(f"  on Point of Sale: {sum(p['pos'] for p in products)}")
    print(f"  on Shop:          {sum(p['shop'] for p in products)}")
    print(f"  to unpublish:     {len(to_fix)}")
    print(f"  NOT on Online Store (left alone): {len(not_online)}")
    for p in not_online:
        print(f"    {p['title']} ({p['id']})")

    if args.dry_run:
        return

    errors = []
    for start in range(0, len(to_fix), CHUNK_SIZE):
        resp = unpublish_chunk(run, to_fix[start:start + CHUNK_SIZE], pubs)
        errors.extend((k, v["userErrors"]) for k, v in resp.items() if v.get("userErrors"))
        print(f"  unpublished {min(start + CHUNK_SIZE, len(to_fix))}/{len(to_fix)}")

    if errors:
        for key, errs in errors:
            print(f"  {key}: {errs}", file=sys.stderr)
        raise SystemExit(1)
    print("Done.")


if __name__ == "__main__":
    main()
