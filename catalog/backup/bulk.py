"""Run one Shopify bulk query and assemble its JSONL into products.

bulkOperationRunQuery is the one mutation the backup sends; it starts a
read-only export job and changes no store data. The finished job is a JSONL
file in which children (variants, metafields, media) are separate lines that
point at their parent through __parentId."""
import json
import time
import urllib.request
from pathlib import Path

from catalog.errors import ShopifyError

QUERIES = Path(__file__).parent / "queries"
RUN_QUERY = QUERIES / "bulk_run.graphql"
STATUS_QUERY = QUERIES / "bulk_status.graphql"
FAILED_STATES = ("FAILED", "CANCELED", "EXPIRED")
DOWNLOAD_TIMEOUT_SECONDS = 120


def _data(payload: dict) -> dict:
    errors = payload.get("errors")
    if errors:
        messages = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
        raise ShopifyError(f"Shopify rejected the bulk operation request: {messages}")
    return payload.get("data") or {}


def _start(execute, store: str, query: str) -> str:
    result = _data(execute(store, RUN_QUERY, {"query": query})).get("bulkOperationRunQuery") or {}
    user_errors = result.get("userErrors") or []
    if user_errors:
        raise ShopifyError("Shopify refused the bulk query: "
                           + "; ".join(str(e.get("message", e)) for e in user_errors))
    operation = result.get("bulkOperation") or {}
    if not operation.get("id"):
        raise ShopifyError("Shopify did not start a bulk operation")
    return operation["id"]


def _download(url: str, urlopen) -> list[dict]:
    with urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        text = response.read().decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line.strip()]


def run_bulk_query(execute, store: str, query: str, *, sleep=time.sleep,
                   urlopen=urllib.request.urlopen, poll_seconds: float = 5,
                   timeout_seconds: float = 1800, clock=time.monotonic) -> list[dict]:
    """Start the job, poll until it ends, and return one dict per JSONL line."""
    operation_id = _start(execute, store, query)
    started = clock()
    while True:
        sleep(poll_seconds)
        operation = _data(execute(store, STATUS_QUERY, {"id": operation_id})).get("bulkOperation") or {}
        status = operation.get("status")
        if status == "COMPLETED":
            url = operation.get("url")
            return _download(url, urlopen) if url else []
        if status in FAILED_STATES:
            raise ShopifyError(f"Shopify bulk operation {status}: {operation.get('errorCode') or 'no error code'}")
        if clock() - started >= timeout_seconds:
            raise ShopifyError(f"Shopify bulk operation timed out after {timeout_seconds:g} seconds "
                               f"(last status {status})")


def assemble_products(lines: list[dict]) -> list[dict]:
    """Nest the flat JSONL into products, in file order. Children may precede
    their parents, so everything is indexed before anything is attached."""
    products = [{**line, "variants": [], "media": [], "metafields": []}
                for line in lines if "__parentId" not in line]
    product_by_id = {p["id"]: p for p in products}
    metafields = {}
    for line in lines:
        parent = product_by_id.get(line.get("__parentId"))
        if parent is None:
            continue
        kind = line.get("__typename")
        if kind == "ProductVariant":
            parent["variants"].append(line)
        elif kind == "Metafield":
            entry = {**line, "references": []}
            metafields[entry["id"]] = entry
            parent["metafields"].append(entry)
        else:
            parent["media"].append(line)
    for line in lines:
        owner = metafields.get(line.get("__parentId"))
        if owner is not None:
            owner["references"].append(line)
    return products
