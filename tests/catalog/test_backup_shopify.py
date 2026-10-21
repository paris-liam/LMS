import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from catalog.backup.bulk import QUERIES
from catalog.backup.guard import SourceResult
from catalog.backup.shopify import backup_shopify, read_store, write_products
from catalog.errors import ShopifyError

STORE = "shop.myshopify.com"
PUB = "gid://shopify/Publication/9"


def _products_jsonl(handles):
    lines = []
    for i, handle in enumerate(handles):
        pid = f"gid://shopify/Product/{i}"
        lines.append({"__typename": "Product", "id": pid, "handle": handle, "title": handle.title(),
                      "descriptionHtml": "", "vendor": "DVD", "productType": "", "tags": [], "status": "ACTIVE",
                      "isGiftCard": False, "category": None, "seo": {"title": None, "description": None},
                      "published": True, "options": []})
        lines.append({"__typename": "ProductVariant", "id": f"gid://shopify/ProductVariant/{i}",
                      "__parentId": pid, "position": 1, "sku": "", "price": "5.00", "compareAtPrice": None,
                      "taxable": True, "barcode": None, "inventoryQuantity": 1, "inventoryPolicy": "DENY",
                      "selectedOptions": [], "image": None, "unitPriceMeasurement": None, "inventoryItem": None})
    return "\n".join(json.dumps(line) for line in lines) + "\n"


class FakeShopify:
    def __init__(self, publications=None, handles=("b-movie", "a-movie")):
        self.publications = publications if publications is not None else [{"id": PUB, "name": "Online Store"}]
        self.handles = handles
        self.calls = []

    def __call__(self, store, query_path, variables):
        self.calls.append((query_path.name, variables))
        name = query_path.name
        if name == "publications.graphql":
            return {"data": {"publications": {"nodes": self.publications}}}
        if name == "metafield_definitions.graphql":
            if variables.get("cursor") is None:
                return {"data": {"metafieldDefinitions": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                    "nodes": [{"name": "Genre", "namespace": "shopify", "key": "genre"}]}}}
            return {"data": {"metafieldDefinitions": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"name": "Methods", "namespace": "supercycle", "key": "methods"}]}}}
        if name == "bulk_run.graphql":
            return {"data": {"bulkOperationRunQuery": {
                "bulkOperation": {"id": "gid://shopify/BulkOperation/1", "status": "CREATED"}, "userErrors": []}}}
        if name == "bulk_status.graphql":
            return {"data": {"bulkOperation": {"id": "x", "status": "COMPLETED", "errorCode": None,
                                               "objectCount": "4", "url": "https://x/f.jsonl",
                                               "partialDataUrl": None}}}
        raise AssertionError(name)

    def urlopen(self, url, timeout=None):
        return io.BytesIO(_products_jsonl(self.handles).encode())


def _read(fake):
    return read_store(fake, STORE, sleep=lambda s: None, urlopen=fake.urlopen)


class TestReadStore(unittest.TestCase):
    def test_read_store_sorts_by_handle_and_splits_columns(self):
        products, kept, left_out = _read(FakeShopify())
        self.assertEqual([p["handle"] for p in products], ["a-movie", "b-movie"])
        self.assertEqual([c.key for c in kept], ["genre"])
        self.assertEqual([c.key for c in left_out], ["methods"])
        self.assertEqual(len(products[0]["variants"]), 1)

    def test_product_without_variants_is_an_error(self):
        class NoVariants(FakeShopify):
            def urlopen(self, url, timeout=None):
                lines = [l for l in _products_jsonl(self.handles).splitlines() if '"ProductVariant"' not in l]
                return io.BytesIO(("\n".join(lines) + "\n").encode())

        with self.assertRaises(ShopifyError) as cm:
            _read(NoVariants())
        self.assertIn("2 products", str(cm.exception))
        self.assertIn("a-movie", str(cm.exception))

    def test_read_store_needs_one_online_store(self):
        for pubs in ([], [{"id": "a", "name": "Online Store"}, {"id": "b", "name": "Online Store"}]):
            with self.assertRaises(ShopifyError):
                _read(FakeShopify(publications=pubs))

    def test_bulk_query_carries_publication_id(self):
        fake = FakeShopify()
        _read(fake)
        sent = [v for n, v in fake.calls if n == "bulk_run.graphql"][0]["query"]
        self.assertIn(PUB, sent)
        self.assertNotIn("%(publication_id)s", sent)

    def test_bulk_query_requests_typename_on_every_nested_node(self):
        text = (QUERIES / "products_bulk.graphql").read_text()
        for selection in ("variants", "media", "metafields", "references"):
            start = text.index(f"{selection} {{ edges {{ node {{")
            end = text.index("} } }", start)
            self.assertIn("__typename", text[start:end], selection)


def _rows(handle, n=1, body="x"):
    return [{"Handle": handle, "Title": "T", "Body (HTML)": body, "Status": "active"} for _ in range(n)]


HEADER = ["Handle", "Title", "Body (HTML)", "Status"]


class TestWriteProducts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_written_csv_round_trips_awkward_html(self):
        body = '<p>a, "b"\nc</p>'
        (path,) = write_products(self.dir, HEADER, [_rows("h", body=body)])
        with open(path, newline="", encoding="utf-8") as f:
            self.assertEqual(list(csv.DictReader(f))[0]["Body (HTML)"], body)

    def test_splits_on_product_boundaries(self):
        products = [_rows(f"h{i}", n=2) for i in range(5)]
        (whole,) = write_products(self.dir, HEADER, products)
        with open(whole, newline="", encoding="utf-8") as f:
            expected = list(csv.DictReader(f))
        parts = write_products(self.dir, HEADER, products, max_bytes=80)
        self.assertGreater(len(parts), 1)
        seen, combined = [], []
        for part in parts:
            with open(part, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, HEADER)
                rows = list(reader)
            combined += rows
            handles = {r["Handle"] for r in rows}
            self.assertFalse(handles & set(seen))
            seen += handles
        self.assertEqual(combined, expected)

    def test_single_file_removes_stale_parts(self):
        for name in ("products-1.csv", "products-2.csv"):
            (self.dir / name).write_text("old")
        write_products(self.dir, HEADER, [_rows("h")])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["products.csv"])
        write_products(self.dir, HEADER, [_rows(f"h{i}", 2) for i in range(5)], max_bytes=80)
        self.assertNotIn("products.csv", [p.name for p in self.dir.iterdir()])


class TestBackupShopify(unittest.TestCase):
    def test_non_catalog_error_keeps_type_name(self):
        def read():
            raise KeyError("unit")
        with tempfile.TemporaryDirectory() as tmp:
            result = backup_shopify(Path(tmp), read)
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith("KeyError"), result.error)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _product(self, handle):
        return {"handle": handle, "title": handle, "status": "ACTIVE", "variants": [], "media": [],
                "metafields": [], "options": [], "tags": []}

    def test_writes_and_moves_into_shopify_dir(self):
        result = backup_shopify(self.out, lambda: ([self._product("a"), self._product("b")], [], []))
        self.assertEqual(result, SourceResult("shopify", True, "2 products"))
        self.assertTrue((self.out / "shopify" / "products.csv").exists())
        self.assertEqual([p.name for p in self.out.iterdir()], ["shopify"])

    def test_zero_products_keeps_old_file(self):
        (self.out / "shopify").mkdir()
        old = self.out / "shopify" / "products.csv"
        old.write_text("X")
        result = backup_shopify(self.out, lambda: ([], [], []))
        self.assertFalse(result.ok)
        self.assertEqual(result.summary, "FAILED")
        self.assertEqual(old.read_text(), "X")
        self.assertEqual([p.name for p in self.out.iterdir()], ["shopify"])

    def test_read_failure_returns_failed_result(self):
        def read():
            raise ShopifyError("boom")
        self.assertEqual(backup_shopify(self.out, read), SourceResult("shopify", False, "FAILED", "boom"))


if __name__ == "__main__":
    unittest.main()
