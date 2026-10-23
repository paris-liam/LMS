"""`python3 -m catalog check-barcodes` — every barcode on the store that more
than one variant carries, and every non-Rental variant with no barcode. Read-only.

Retail Barcode Labels builds a barcode from the last 8 digits of the variant
ID, and on this store every variant ID leaves the same remainder mod 32768, so
only ~390,000 of the 100 million 8-digit codes can come up: about 1 new
product in 50 gets a barcode another product already has (29 pairs on
production, 2026-10-19). Every new product not tagged Rental (Floor Sale,
merch, ...) therefore gets its barcodes from a Shopify Flow workflow, set to
each variant's full ID (claudedocs/2026-10-20-floor-sale-barcodes-shopify-flow.md);
a non-Rental variant still without one means the workflow didn't run for it.
Rentals carry their Libib barcode instead. Run this after an
import and before printing, with --since set to the batch's date so only the
new copies are listed.

Exit 0 when nothing is listed, 1 when anything is.
"""

from datetime import date
from pathlib import Path

from catalog import config
RENTAL_TAG = "Rental"
from catalog.errors import ShopifyError
from catalog.shopify.reader import default_executor

QUERY_PATH = Path(__file__).parent / "queries" / "variant_barcodes.graphql"


def read_variants(store: str, execute=None) -> list[dict]:
    """Every variant as {barcode, created, handle, title, tags}."""
    if execute is None:
        execute, _ = default_executor(store)
    variants, cursor = [], None
    while True:
        payload = execute(store, QUERY_PATH, {"cursor": cursor})
        if payload.get("errors"):
            raise ShopifyError(f"GraphQL errors from {store}: {payload['errors']}")
        page = payload.get("data", payload)["productVariants"]
        for node in page["nodes"]:
            product = node.get("product") or {}
            variants.append({
                "barcode": (node.get("barcode") or "").strip(),
                "created": (node.get("createdAt") or "")[:10],
                "handle": product.get("handle", ""),
                "title": product.get("title", ""),
                "tags": product.get("tags") or [],
            })
        if not page["pageInfo"]["hasNextPage"]:
            return variants
        cursor = page["pageInfo"]["endCursor"]


def shared_barcodes(variants: list[dict], since: date | None = None) -> dict[str, list[dict]]:
    """Barcode -> its variants, oldest first, for every barcode on 2+ variants.
    With `since`, only barcodes at least one of whose variants was created then or later."""
    by_barcode: dict[str, list[dict]] = {}
    for variant in variants:
        if variant["barcode"]:
            by_barcode.setdefault(variant["barcode"], []).append(variant)
    cutoff = since.isoformat() if since else ""
    return {
        barcode: sorted(group, key=lambda v: v["created"])
        for barcode, group in sorted(by_barcode.items())
        if len(group) > 1 and any(v["created"] >= cutoff for v in group)
    }


def non_rental_without_barcode(variants: list[dict], since: date | None = None) -> list[dict]:
    """Variants of products not tagged Rental with no barcode (created on or after `since`), oldest first."""
    cutoff = since.isoformat() if since else ""
    return sorted((v for v in variants
                   if not v["barcode"] and RENTAL_TAG not in v["tags"] and v["created"] >= cutoff),
                  key=lambda v: v["created"])


def _line(v: dict) -> str:
    return f"{v['created']}  {v['title']}  ({v['handle']})  [{', '.join(v['tags'])}]"


def run_command(args, read=read_variants) -> int:
    since = date.fromisoformat(args.since) if args.since else None
    variants = read(args.store)
    shared = shared_barcodes(variants, since)
    missing = non_rental_without_barcode(variants, since)
    scope = f" (variants created since {since})" if since else ""
    if not shared and not missing:
        print(f"✓ no shared barcodes and no non-Rental variant without one on {args.store}{scope}.")
        return 0
    if shared:
        print(f"✗ {len(shared)} barcode(s) on more than one product on {args.store}{scope}:\n")
        for barcode, group in shared.items():
            print(f"  {barcode}")
            for v in group:
                print(f"    {_line(v)}")
        print("\nGive the newer copy a new barcode by hand (regenerating in the app gives it the same "
              "number again), then print its label.\n")
    if missing:
        print(f"✗ {len(missing)} non-Rental variant(s) with no barcode on {args.store}{scope}:\n")
        for v in missing:
            print(f"    {_line(v)}")
        print("\nThe Flow workflow didn't set these — check its run history, then type each "
              "variant's ID in as its barcode. Don't generate them in the app.")
    return 1


def register(subparsers) -> None:
    p = subparsers.add_parser("check-barcodes", help="list shared barcodes and non-Rental variants with none (read-only)")
    p.add_argument("--store", default=config.DEFAULT_STORE, help=f"store domain (default {config.DEFAULT_STORE})")
    p.add_argument("--since", metavar="YYYY-MM-DD",
                   help="only variants created on or after this date (e.g. the batch date)")
    p.set_defaults(func=lambda args: run_command(args))
