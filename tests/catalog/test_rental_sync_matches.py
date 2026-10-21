import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeShop  # noqa: E402

from catalog.rental_sync.matches import SEVERAL_PRODUCTS, attach_matches  # noqa: E402


def copy(barcode, siblings):
    return {"barcode": barcode, "item_id": "a1", "siblings_in_shopify": siblings, "set_aside": [],
            "libib_duplicate": None, "match": None}


def shop_with(*barcodes):
    shop = FakeShop(barcodes=barcodes)
    for owner in shop.barcodes.values():
        shop.products[owner["id"]] = {"id": owner["id"], "handle": owner["handle"], "title": "Jaws",
                                      "vendor": "VHS", "tags": [], "image": "", "copies": 1}
    return shop


class TestAttachMatches(unittest.TestCase):
    def test_one_owner_becomes_match(self):
        shop = shop_with("2010000000014")
        result = attach_matches({"ready": [copy("2010000000045", ["2010000000014"])], "set_aside": []},
                                shop, shop.store)
        match = result["ready"][0]["match"]
        self.assertEqual(match["handle"], "existing-2010000000014")
        self.assertTrue(match["admin_url"].endswith("/products/existing-2010000000014"))

    def test_no_siblings_leaves_match_empty(self):
        shop = shop_with()
        result = attach_matches({"ready": [copy("2010000000045", [])], "set_aside": []}, shop, shop.store)
        self.assertIsNone(result["ready"][0]["match"])

    def test_siblings_on_two_products_set_aside(self):
        shop = shop_with("2010000000014", "2010000000021")
        result = attach_matches(
            {"ready": [copy("2010000000045", ["2010000000014", "2010000000021"])], "set_aside": []},
            shop, shop.store)
        self.assertEqual(result["ready"], [])
        aside = result["set_aside"][0]
        self.assertIn(SEVERAL_PRODUCTS, aside["set_aside"])
        self.assertEqual(len(aside["products"]), 2)

    def test_owner_lookup_cached(self):
        shop = shop_with("2010000000014")
        ready = [copy(f"20100000000{n}", ["2010000000014"]) for n in (45, 52, 69)]
        attach_matches({"ready": ready, "set_aside": []}, shop, shop.store)
        self.assertEqual(shop.owner_calls, ["2010000000014"])


if __name__ == "__main__":
    unittest.main()
