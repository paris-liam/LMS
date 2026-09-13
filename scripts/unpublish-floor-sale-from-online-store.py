#!/usr/bin/env python3
"""
Unpublishes every "Floor Sale"-tagged product from the Online Store sales
channel (keeps product status ACTIVE so POS can still sell them in-store).

Floor Sale items are sold at the counter only, per CLAUDE.md's Rental/Floor
Sale split — they should never be reachable on the website. Re-running is
safe: querying published_status:published means already-unpublished
products just won't show up again.

Auth: uses the Shopify CLI's own authenticated session (run
`shopify store auth --store <store> --scopes write_products` once first if
you haven't already) — no admin token needs to be exported.

Usage:
  python3 scripts/unpublish-floor-sale-from-online-store.py [--store STORE] [--dry-run]
"""
import argparse
import json
import subprocess
import sys

ONLINE_STORE_PUBLICATION_QUERY = 'query { publications(first: 10) { edges { node { id name } } } }'

FETCH_QUERY = '''
query($cursor: String) {
  products(first: 250, after: $cursor, query: "tag:\\"Floor Sale\\" AND published_status:published") {
    edges { node { id title } }
    pageInfo { hasNextPage endCursor }
  }
}
'''

CHUNK_SIZE = 20


def run_graphql(store, query, variables=None, mutate=False):
    cmd = ["shopify", "store", "execute", "--store", store, "-j", "-q", query]
    if variables is not None:
        cmd += ["-v", json.dumps(variables)]
    if mutate:
        cmd.append("--allow-mutations")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"shopify store execute failed (exit {result.returncode})")
    # CLI prints progress lines before the JSON; find the JSON object.
    out = result.stdout
    start = out.find("{")
    return json.loads(out[start:])


def get_online_store_publication_id(store):
    data = run_graphql(store, ONLINE_STORE_PUBLICATION_QUERY)
    for edge in data["publications"]["edges"]:
        if edge["node"]["name"] == "Online Store":
            return edge["node"]["id"]
    raise SystemExit("Could not find an 'Online Store' publication")


def fetch_all_floor_sale_ids(store):
    ids = []
    cursor = None
    while True:
        data = run_graphql(store, FETCH_QUERY, {"cursor": cursor})
        page = data["products"]
        for edge in page["edges"]:
            ids.append((edge["node"]["id"], edge["node"]["title"]))
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return ids


def unpublish_chunk(store, publication_id, chunk):
    parts = []
    variables = {"publicationId": publication_id}
    for i, (product_id, _title) in enumerate(chunk):
        var_name = f"id{i}"
        variables[var_name] = product_id
        parts.append(
            f'm{i}: publishableUnpublish(id: ${var_name}, '
            f'input: [{{publicationId: $publicationId}}]) {{ userErrors {{ field message }} }}'
        )
    var_defs = ", ".join(f"${k}: ID!" for k in variables)
    mutation = f"mutation({var_defs}) {{ {' '.join(parts)} }}"
    return run_graphql(store, mutation, variables, mutate=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default="p0wkgv-wy.myshopify.com")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Looking up Online Store publication id on {args.store} ...")
    publication_id = get_online_store_publication_id(args.store)
    print(f"  found: {publication_id}")

    print("Fetching all published 'Floor Sale' products ...")
    products = fetch_all_floor_sale_ids(args.store)
    print(f"  found {len(products)} products currently published to Online Store")

    if args.dry_run:
        for pid, title in products:
            print(f"  would unpublish: {title} ({pid})")
        return

    total_errors = []
    for start in range(0, len(products), CHUNK_SIZE):
        chunk = products[start:start + CHUNK_SIZE]
        resp = unpublish_chunk(args.store, publication_id, chunk)
        for key, value in resp.items():
            errs = value.get("userErrors") or []
            if errs:
                total_errors.append((key, errs))
        print(f"  unpublished {min(start + CHUNK_SIZE, len(products))}/{len(products)}")

    if total_errors:
        print("Errors encountered:", file=sys.stderr)
        for key, errs in total_errors:
            print(f"  {key}: {errs}", file=sys.stderr)
        raise SystemExit(1)

    print("Done.")


if __name__ == "__main__":
    main()
