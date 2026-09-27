"""Read every product through `shopify store execute` (read-only).

Only query operations are ever sent — never --allow-mutations — so the
pipeline cannot write to Shopify from here.
"""

import json
import subprocess
from pathlib import Path

from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import ShopifyError
from catalog.shopify.snapshot import blank_row

QUERY_PATH = Path(__file__).parent / "queries" / "products.graphql"
_AUTH_HINTS = ("not logged in", "log in", "login", "authenticat", "unauthorized", "401", "403")


def _parse_json_output(text: str) -> dict:
    """The CLI prints status lines around the JSON; keep the outermost object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ShopifyError(f"no JSON in shopify CLI output: {text.strip()[:300]}")
    return json.loads(text[start:end + 1])


def run_cli_query(store: str, query_path: Path, variables: dict) -> dict:
    cmd = ["shopify", "store", "execute", "--store", store, "--json",
           "--query-file", str(query_path), "--variables", json.dumps(variables)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise ShopifyError("the `shopify` CLI is not installed or not on PATH") from None
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        if any(hint in message.lower() for hint in _AUTH_HINTS):
            raise ShopifyError(
                f"Shopify CLI is not authenticated for {store}. Run:\n"
                f"  shopify store auth --store {store} --scopes read_products\n({message})"
            )
        raise ShopifyError(f"shopify store execute failed for {store}: {message}")
    return _parse_json_output(proc.stdout)


def node_to_row(node: dict) -> dict:
    variants = (node.get("variants") or {}).get("nodes") or []
    variant = variants[0] if variants else {}
    options = variant.get("selectedOptions") or []
    option = options[0] if options else {}
    media = (node.get("media") or {}).get("nodes") or []
    image = next((m["image"] for m in media if m and m.get("image")), None) or {}
    references = (((node.get("genre") or {}).get("references")) or {}).get("nodes") or []

    row = blank_row()
    row.update({
        "Handle": node.get("handle") or "",
        "Title": node.get("title") or "",
        "Body (HTML)": node.get("descriptionHtml") or "",
        "Vendor": node.get("vendor") or "",
        "Tags": ", ".join(node.get("tags") or []),
        "Status": (node.get("status") or "").lower(),
        "Template Suffix": node.get("templateSuffix") or "",
        "Image Src": image.get("url") or "",
        "Image Alt Text": image.get("altText") or "",
        "Option1 Name": option.get("name") or "",
        "Option1 Value": option.get("value") or "",
        "Variant Price": variant.get("price") or "",
        "Variant Barcode": variant.get("barcode") or "",
        "Variant Inventory Tracker": "shopify" if (variant.get("inventoryItem") or {}).get("tracked") else "",
        "Variant Count": str(((node.get("variantsCount") or {}).get("count")) or 0),
        "Product Category": (node.get("category") or {}).get("fullName") or "",
        GENRE_METAFIELD: "; ".join(r["handle"] for r in references if r and r.get("handle")),
    })
    return row


def read_products(store: str, execute=run_cli_query) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    page_number = 0
    while True:
        page_number += 1
        payload = execute(store, QUERY_PATH, {"cursor": cursor})
        if payload.get("errors"):
            raise ShopifyError(f"GraphQL errors from {store}: {payload['errors']}")
        products = payload.get("data", payload)["products"]
        rows.extend(node_to_row(n) for n in products["nodes"])
        log.get_logger().info(f"[page {page_number}] {len(rows)} products read from {store}")
        if not products["pageInfo"]["hasNextPage"]:
            return rows
        cursor = products["pageInfo"]["endCursor"]
