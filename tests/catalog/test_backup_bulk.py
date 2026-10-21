import io
import json
import unittest

from catalog.backup.bulk import assemble_products, run_bulk_query
from catalog.errors import ShopifyError


def _run_payload(status="CREATED", user_errors=()):
    return {"data": {"bulkOperationRunQuery": {
        "bulkOperation": {"id": "gid://shopify/BulkOperation/1", "status": status},
        "userErrors": list(user_errors)}}}


def _status_payload(status, url=None, error_code=None):
    return {"data": {"bulkOperation": {"id": "gid://shopify/BulkOperation/1", "status": status,
                                       "errorCode": error_code, "objectCount": "2", "url": url,
                                       "partialDataUrl": None}}}


class Script:
    """execute() that replays payloads in order."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, store, query_path, variables):
        self.calls.append((store, query_path, variables))
        return self.payloads.pop(0)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self):
        return self.now


def _urlopen(body):
    def opener(url, timeout=None):
        opener.url, opener.timeout = url, timeout
        return io.BytesIO(body.encode())
    return opener


class TestRunBulkQuery(unittest.TestCase):
    def test_runs_polls_and_downloads(self):
        execute = Script(_run_payload(), _status_payload("RUNNING"),
                         _status_payload("COMPLETED", url="https://x/f.jsonl"))
        clock = Clock()
        opener = _urlopen('{"id": "a"}\n\n{"id": "b"}\n')
        lines = run_bulk_query(execute, "shop.myshopify.com", "{ products { edges { node { id } } } }",
                               sleep=clock.sleep, urlopen=opener, clock=clock)
        self.assertEqual(lines, [{"id": "a"}, {"id": "b"}])
        self.assertEqual(clock.sleeps, [5, 5])
        self.assertEqual(opener.url, "https://x/f.jsonl")
        self.assertEqual(opener.timeout, 120)
        self.assertEqual(execute.calls[0][2], {"query": "{ products { edges { node { id } } } }"})
        self.assertEqual(execute.calls[1][2], {"id": "gid://shopify/BulkOperation/1"})

    def test_user_errors_raise(self):
        execute = Script(_run_payload(user_errors=[{"message": "bad query"}]))
        with self.assertRaisesRegex(ShopifyError, "bad query"):
            run_bulk_query(execute, "s", "q", sleep=lambda s: None)

    def test_graphql_errors_raise(self):
        execute = Script({"errors": [{"message": "Access denied"}]})
        with self.assertRaisesRegex(ShopifyError, "Access denied"):
            run_bulk_query(execute, "s", "q", sleep=lambda s: None)

    def test_failed_states_raise(self):
        for status in ("FAILED", "CANCELED", "EXPIRED"):
            with self.subTest(status=status):
                execute = Script(_run_payload(), _status_payload(status, error_code="ACCESS_DENIED"))
                with self.assertRaisesRegex(ShopifyError, "ACCESS_DENIED"):
                    run_bulk_query(execute, "s", "q", sleep=lambda s: None)

    def test_completed_without_url_reads_zero_products(self):
        execute = Script(_run_payload(), _status_payload("COMPLETED", url=None))
        self.assertEqual(run_bulk_query(execute, "s", "q", sleep=lambda s: None), [])

    def test_times_out(self):
        running = [_status_payload("RUNNING") for _ in range(10)]
        execute = Script(_run_payload(), *running)
        clock = Clock()
        with self.assertRaisesRegex(ShopifyError, "timed out"):
            run_bulk_query(execute, "s", "q", sleep=clock.sleep, clock=clock,
                           poll_seconds=5, timeout_seconds=10)
        self.assertLessEqual(len(execute.calls) - 1, 3)


class TestAssembleProducts(unittest.TestCase):
    def test_assembles_children_out_of_order(self):
        lines = [
            {"id": "v1", "__typename": "ProductVariant", "__parentId": "p1"},
            {"id": "m9", "__typename": "Metaobject", "__parentId": "mf1"},
            {"id": "p1", "__typename": "Product", "title": "Alien"},
            {"id": "mf1", "__typename": "Metafield", "__parentId": "p1", "key": "k"},
            {"id": "i1", "__typename": "MediaImage", "__parentId": "p1"},
        ]
        products = assemble_products(lines)
        self.assertEqual(len(products), 1)
        product = products[0]
        self.assertEqual([v["id"] for v in product["variants"]], ["v1"])
        self.assertEqual([m["id"] for m in product["media"]], ["i1"])
        self.assertEqual([m["id"] for m in product["metafields"]], ["mf1"])
        self.assertEqual([r["id"] for r in product["metafields"][0]["references"]], ["m9"])

    def test_product_reference_and_empty_lists(self):
        lines = [{"id": "p1", "__typename": "Product"},
                 {"id": "mf1", "__typename": "Metafield", "__parentId": "p1"},
                 {"id": "p9", "__typename": "Product", "__parentId": "mf1"}]
        products = assemble_products(lines)
        self.assertEqual([p["id"] for p in products], ["p1"])
        self.assertEqual(products[0]["metafields"][0]["references"][0]["id"], "p9")
        self.assertEqual(products[0]["variants"], [])
        self.assertEqual(products[0]["media"], [])
