import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeExecute  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync import shopify as rs  # noqa: E402
from catalog.rental_sync.shopify import RentalShop, cached_token  # noqa: E402

STORE = "lms-sandbox-lutsfahz.myshopify.com"


def shop(responses):
    execute = FakeExecute(responses)
    return RentalShop(execute, STORE), execute


def data(payload):
    return {"data": payload}


class TestReads(unittest.TestCase):
    def test_new_flow_barcodes_paginates_and_filters(self):
        pages = {
            None: {"nodes": [{"barcode": "2010000000014"}, {"barcode": "20144890"}],
                   "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
            "c1": {"nodes": [{"barcode": " 2010000000021 "}, {"barcode": None}],
                   "pageInfo": {"hasNextPage": False, "endCursor": None}},
        }
        s, execute = shop([("productVariants(first: 250", lambda v: data({"productVariants": pages[v["after"]]}))])
        self.assertEqual(s.new_flow_barcodes(), {"2010000000014", "2010000000021"})
        self.assertIn('barcode:201*', execute.calls[0][0])

    def test_barcode_owner_needs_an_exact_match(self):
        s, _ = shop([("productVariants(first: 10", data({"productVariants": {"nodes": [
            {"barcode": "20100000000140", "product": {"id": "gid://shopify/Product/9", "handle": "other"}},
            {"barcode": "2010000000014",
             "product": {"id": "gid://shopify/Product/1", "handle": "jaws-vhs-rental-2010000000014"}}]}}))])
        self.assertEqual(s.barcode_owner("2010000000014"),
                         {"id": "gid://shopify/Product/1", "handle": "jaws-vhs-rental-2010000000014"})
        s2, _ = shop([("productVariants(first: 10", data({"productVariants": {"nodes": []}}))])
        self.assertIsNone(s2.barcode_owner("2010000000014"))

    def test_product_summary_counts_variants(self):
        s, _ = shop([("variantsCount", data({"product": {
            "id": "gid://shopify/Product/1", "handle": "jaws", "title": "Jaws", "vendor": "VHS",
            "tags": ["Rental"], "featuredMedia": {"preview": {"image": {"url": "https://x/p.jpg"}}},
            "variantsCount": {"count": 2}}}))])
        self.assertEqual(s.product_summary("gid://shopify/Product/1"), {
            "id": "gid://shopify/Product/1", "handle": "jaws", "title": "Jaws", "vendor": "VHS",
            "tags": ["Rental"], "image": "https://x/p.jpg", "copies": 2})

    def test_product_summary_missing_product(self):
        s, _ = shop([("variantsCount", data({"product": None}))])
        self.assertIsNone(s.product_summary("gid://shopify/Product/1"))

    def test_handle_taken_uses_a_direct_lookup(self):
        found, execute = shop([("productByIdentifier", data({"productByIdentifier": {"id": "gid://shopify/Product/1"}}))])
        self.assertTrue(found.handle_taken("jaws-vhs-rental-2010000000014"))
        text, variables = execute.calls[0]
        self.assertIn("productByIdentifier", text)
        self.assertEqual(variables, {"h": "jaws-vhs-rental-2010000000014"})
        missing, _ = shop([("productByIdentifier", data({"productByIdentifier": None}))])
        self.assertFalse(missing.handle_taken("jaws-vhs-rental-2010000000014"))

    def test_exactly_one_location(self):
        one, _ = shop([("locations(", data({"locations": {"nodes": [{"id": "gid://shopify/Location/1", "name": "Shop"}]}}))])
        self.assertEqual(one.location_id(), "gid://shopify/Location/1")
        two, _ = shop([("locations(", data({"locations": {"nodes": [{"id": "a", "name": "Shop"}, {"id": "b", "name": "Warehouse"}]}}))])
        with self.assertRaisesRegex(SetupError, "exactly one active Shopify location, found 2: Shop, Warehouse"):
            two.location_id()

    def test_online_store_publication(self):
        s, _ = shop([("publications(", data({"publications": {"nodes": [
            {"id": "p2", "name": "Point of Sale"}, {"id": "p1", "name": "Online Store"}]}}))])
        self.assertEqual(s.online_store_publication_id(), "p1")
        none, _ = shop([("publications(", data({"publications": {"nodes": [{"id": "p2", "name": "Point of Sale"}]}}))])
        with self.assertRaisesRegex(SetupError, "Online Store"):
            none.online_store_publication_id()

    def test_genre_ids_cached_and_unknown_is_setup(self):
        s, execute = shop([("metaobjectByHandle", lambda v: data({"metaobjectByHandle":
                                                                   {"id": f"gid://m/{v['h']}"} if v["h"] != "nope" else None}))])
        self.assertEqual(s.genre_ids(["horror", "drama"]), ["gid://m/horror", "gid://m/drama"])
        s.genre_ids(["horror"])
        self.assertEqual(len(execute.calls), 2)
        with self.assertRaisesRegex(SetupError, "no genre value 'nope'"):
            s.genre_ids(["nope"])

    def test_last_run(self):
        s, _ = shop([("metafield(", data({"shop": {"metafield": {"value": json.dumps({"created": 3})}}}))])
        self.assertEqual(s.last_run(), {"created": 3})
        blank, _ = shop([("metafield(", data({"shop": {"metafield": None}}))])
        self.assertIsNone(blank.last_run())
        garbled, _ = shop([("metafield(", data({"shop": {"metafield": {"value": "{oops"}}}))])
        self.assertIsNone(garbled.last_run())


class TestWrites(unittest.TestCase):
    def test_save_last_run(self):
        s, execute = shop([("shop { id }", data({"shop": {"id": "gid://shopify/Shop/1"}})),
                           ("metafieldsSet", data({"metafieldsSet": {"userErrors": []}}))])
        s.save_last_run({"created": 2})
        sent = execute.calls[1][1]["m"][0]
        self.assertEqual((sent["ownerId"], sent["namespace"], sent["key"], sent["type"]),
                         ("gid://shopify/Shop/1", "lms", "rental_sync_last_run", "json"))
        self.assertEqual(json.loads(sent["value"]), {"created": 2})

    def test_product_set_returns_the_product(self):
        s, execute = shop([("productSet", data({"productSet": {"product": {"id": "gid://p/1", "handle": "h"},
                                                               "userErrors": []}}))])
        self.assertEqual(s.product_set({"title": "Jaws"}), {"id": "gid://p/1", "handle": "h"})
        self.assertIn("synchronous: true", execute.calls[0][0])

    def test_user_errors_raise_shopify_error(self):
        s, _ = shop([("productSet", data({"productSet": {"product": None,
                                                         "userErrors": [{"field": ["handle"], "message": "Handle taken"}]}}))])
        with self.assertRaisesRegex(ShopifyError, "Handle taken"):
            s.product_set({"title": "Jaws"})

    def test_publish_sends_the_publication(self):
        s, execute = shop([("publishablePublish", data({"publishablePublish": {"userErrors": []}}))])
        s.publish("gid://p/1", "gid://pub/1")
        self.assertEqual(execute.calls[0][1], {"id": "gid://p/1", "input": [{"publicationId": "gid://pub/1"}]})


class TestErrors(unittest.TestCase):
    def test_access_denied_is_setup(self):
        s, _ = shop([("locations(", {"errors": [{"message": "Access denied", "extensions": {"code": "ACCESS_DENIED"}}]})])
        with self.assertRaisesRegex(SetupError, "missing a permission"):
            s.location_id()

    def test_access_denied_is_setup_even_when_the_code_is_truncated(self):
        long_error = {"errors": [{
            "message": "Access denied for locations field. Required access: `read_locations` access scope. "
                       "Also: " + "x" * 300,
            "locations": [{"line": 1, "column": 9}],
            "path": ["locations"],
            "extensions": {"code": "ACCESS_DENIED",
                           "documentation": "https://shopify.dev/api/usage/access-scopes"}}]}
        s, _ = shop([("locations(", long_error)])
        with self.assertRaisesRegex(SetupError, "missing a permission"):
            s.location_id()

    def test_raw_network_errors_are_shopify_errors(self):
        import http.client
        for exc in (TimeoutError("timed out"), ConnectionResetError(), http.client.RemoteDisconnected("gone"),
                    http.client.IncompleteRead(b"x")):
            def execute(store, query, variables, exc=exc):
                raise exc
            with self.assertRaisesRegex(ShopifyError, "could not reach Shopify: " + type(exc).__name__):
                RentalShop(execute, STORE).location_id()

    def test_other_graphql_errors_are_shopify(self):
        s, _ = shop([("locations(", {"errors": [{"message": "Internal error"}]})])
        with self.assertRaisesRegex(ShopifyError, "Internal error"):
            s.location_id()


class TestToken(unittest.TestCase):
    def setUp(self):
        rs._tokens.clear()

    def test_reused_until_expiry(self):
        clock, issued = [1000.0], []

        def request(store, cid, secret):
            issued.append(store)
            return f"t{len(issued)}"

        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t1")
        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t1")
        clock[0] += rs.TOKEN_LIFETIME_SECONDS + 1
        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t2")


if __name__ == "__main__":
    unittest.main()
