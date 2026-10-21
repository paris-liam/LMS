"""Read every product from Shopify and write admin-export CSVs.

Reads only: the bulk operation it starts is a read-only export. Files are built
in a temp dir and checked before they replace the existing backup."""
import csv
import io
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from catalog.backup.bulk import QUERIES, assemble_products, run_bulk_query
from catalog.backup.guard import SHOPIFY_REQUIRED, SourceResult, check_csv
from catalog.backup.shopify_csv import build_header, product_rows, split_definitions
from catalog.errors import CatalogError, ShopifyError

MAX_BYTES = 15_000_000
ONLINE_STORE = "Online Store"


def _data(payload: dict) -> dict:
    errors = payload.get("errors")
    if errors:
        raise ShopifyError("Shopify rejected a query: "
                           + "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors))
    return payload.get("data") or {}


def _online_store_id(execute, store: str) -> str:
    nodes = (_data(execute(store, QUERIES / "publications.graphql", {})).get("publications") or {}).get("nodes") or []
    ids = [n["id"] for n in nodes if n.get("name") == ONLINE_STORE]
    if len(ids) != 1:
        raise ShopifyError(f"expected exactly one '{ONLINE_STORE}' publication, found {len(ids)}")
    return ids[0]


def _definitions(execute, store: str) -> list[dict]:
    found, cursor = [], None
    while True:
        page = _data(execute(store, QUERIES / "metafield_definitions.graphql",
                             {"cursor": cursor})).get("metafieldDefinitions") or {}
        found.extend(page.get("nodes") or [])
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return found
        cursor = info.get("endCursor")


def read_store(execute, store: str, **bulk_kwargs):
    """Return (products sorted by handle, kept columns, left-out columns)."""
    publication_id = _online_store_id(execute, store)
    kept, left_out = split_definitions(_definitions(execute, store))
    query = (QUERIES / "products_bulk.graphql").read_text(encoding="utf-8") % {"publication_id": publication_id}
    products = assemble_products(run_bulk_query(execute, store, query, **bulk_kwargs))
    products.sort(key=lambda p: p["handle"])
    empty = [p["handle"] for p in products if not p["variants"]]
    if empty:
        raise ShopifyError(f"{len(empty)} products have no variants (first: {empty[0]}); "
                           "the bulk export shape may have changed")
    return products, kept, left_out


def _line(values: list) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow(values)
    return buffer.getvalue()


def write_products(shopify_dir: Path, header: list[str], products_rows: list[list[dict]],
                   max_bytes: int = MAX_BYTES) -> list[Path]:
    """One inner list per product; a product is never split across parts."""
    shopify_dir.mkdir(parents=True, exist_ok=True)
    header_line = _line(header)
    parts, current, size = [], [], 0
    for rows in products_rows:
        lines = [_line([row.get(name, "") for name in header]) for row in rows]
        need = sum(len(line.encode("utf-8")) for line in lines)
        if current and size + need > max_bytes:
            parts.append(current)
            current, size = [], len(header_line.encode("utf-8"))
        if not current and not parts:
            size = len(header_line.encode("utf-8"))
        current.extend(lines)
        size += need
    if current or not parts:
        parts.append(current)
    names = ["products.csv"] if len(parts) == 1 else [f"products-{i}.csv" for i in range(1, len(parts) + 1)]
    written = []
    for name, lines in zip(names, parts):
        path = shopify_dir / name
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(header_line)
            f.writelines(lines)
        written.append(path)
    for stale in [*shopify_dir.glob("products.csv"), *shopify_dir.glob("products-*.csv")]:
        if stale not in written:
            stale.unlink()
    return written


def backup_shopify(out_dir: Path, read: Callable) -> SourceResult:
    temp = None
    try:
        products, columns, _left_out = read()
        header = build_header(columns)
        out_dir.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".shopify-", dir=out_dir))
        parts = write_products(temp, header, [product_rows(p, columns) for p in products])
        for part in parts:
            check_csv(part, SHOPIFY_REQUIRED)
        target = out_dir / "shopify"
        target.mkdir(parents=True, exist_ok=True)
        for old in [*target.glob("products.csv"), *target.glob("products-*.csv")]:
            old.unlink()
        for part in parts:
            shutil.move(str(part), str(target / part.name))
        return SourceResult("shopify", True, f"{len(products)} products")
    except Exception as exc:
        message = " ".join(str(exc).split())
        if not isinstance(exc, CatalogError):
            message = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
        return SourceResult("shopify", False, "FAILED", message or type(exc).__name__)
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
