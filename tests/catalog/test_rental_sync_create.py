import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import ONLINE_STORE_ID, FakeShop  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync.create import admin_url, create_copy, description_html, handle_for  # noqa: E402
from catalog.rental_sync.transform import transform  # noqa: E402

POSTER = {"url": "https://image.tmdb.org/t/p/w1280/jaws.jpg", "alt": "Jaws (1975) poster"}


def item(**overrides):
    base = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror, thriller, criterion",
            "description": "A shark.", "created": "2026-10-14"}
    base.update(overrides)
    return base


def run(shop, poster=POSTER, **overrides):
    sleeps = []
    result = create_copy(shop, item(**overrides), poster, sleep=sleeps.append)
    return result, sleeps


class TestHelpers(unittest.TestCase):
    def test_handle(self):
        self.assertEqual(handle_for(transform(item(title="The Monkey's Uncle", tags="blu-ray, comedy"))),
                         "the-monkeys-uncle-blu-ray-rental-2010000000014")

    def test_description_is_escaped(self):
        self.assertEqual(description_html("Tom & Jerry <b>live</b>"), "<p>Tom &amp; Jerry &lt;b&gt;live&lt;/b&gt;</p>")
        self.assertEqual(description_html(""), "")

    def test_admin_url(self):
        self.assertEqual(admin_url("lms-sandbox-lutsfahz.myshopify.com", "gid://shopify/Product/42"),
                         "https://admin.shopify.com/store/lms-sandbox-lutsfahz/products/42")


class TestCreate(unittest.TestCase):
    def test_creates_with_every_field(self):
        shop = FakeShop()
        result, _ = run(shop)
        self.assertEqual(result["status"], "created", result)
        self.assertEqual(result["poster"], "ok")
        self.assertEqual(result["admin_url"], "https://admin.shopify.com/store/lms-sandbox-lutsfahz/products/101")
        sent = shop.created[0]
        self.assertEqual(sent["handle"], "jaws-vhs-rental-2010000000014")
        self.assertEqual((sent["title"], sent["vendor"], sent["status"]), ("Jaws", "VHS", "ACTIVE"))
        self.assertEqual(sent["descriptionHtml"], "<p>A shark.</p>")
        self.assertEqual(sent["category"], "gid://shopify/TaxonomyCategory/me-7")
        self.assertEqual(sent["tags"], ["Rental", "Barcode Not Printed", "criterion"])
        self.assertEqual(sent["productOptions"], [{"name": "Genre", "position": 1, "values": [{"name": "Horror"}]}])
        variant = sent["variants"][0]
        self.assertEqual(variant["optionValues"], [{"optionName": "Genre", "name": "Horror"}])
        self.assertEqual((variant["barcode"], variant["price"], variant["taxable"], variant["inventoryPolicy"]),
                         ("2010000000014", "0.00", False, "DENY"))
        self.assertEqual(variant["inventoryItem"], {"tracked": True})
        self.assertEqual(variant["inventoryQuantities"],
                         [{"locationId": "gid://shopify/Location/1", "name": "available", "quantity": 1}])
        metafield = sent["metafields"][0]
        self.assertEqual((metafield["namespace"], metafield["key"], metafield["type"]),
                         ("shopify", "genre", "list.metaobject_reference"))
        self.assertEqual(json.loads(metafield["value"]),
                         ["gid://shopify/Metaobject/horror", "gid://shopify/Metaobject/thriller"])
        self.assertEqual(sent["files"], [{"originalSource": POSTER["url"], "alt": POSTER["alt"], "contentType": "IMAGE"}])
        self.assertEqual(shop.published, [("gid://shopify/Product/101", ONLINE_STORE_ID)])

    def test_no_poster(self):
        shop = FakeShop()
        result, _ = run(shop, poster=None)
        self.assertEqual((result["status"], result["poster"]), ("created", "none"))
        self.assertNotIn("files", shop.created[0])

    def test_pasted_poster_without_alt_gets_title_alt(self):
        shop = FakeShop()
        run(shop, poster={"url": "https://example.com/p.jpg", "alt": ""})
        self.assertEqual(shop.created[0]["files"][0]["alt"], "Jaws poster")

    def test_barcode_already_in_shopify_is_skipped(self):
        shop = FakeShop(barcodes=["2010000000014"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "skipped_exists")
        self.assertIn("existing-2010000000014", result["message"])
        self.assertEqual(shop.created, [])

    def test_double_submit_creates_once(self):
        shop = FakeShop()
        first, _ = run(shop)
        second, _ = run(shop)
        self.assertEqual((first["status"], second["status"]), ("created", "skipped_exists"))
        self.assertEqual(len(shop.created), 1)

    def test_handle_already_in_shopify_is_skipped(self):
        shop = FakeShop(handles=["jaws-vhs-rental-2010000000014"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "skipped_exists")
        self.assertEqual(shop.created, [])

    def test_set_aside_copy_is_refused(self):
        shop = FakeShop()
        result, _ = run(shop, tags="vhs, horor")
        self.assertEqual(result["status"], "failed")
        self.assertIn("looks like a misspelling", result["message"])
        self.assertEqual(shop.created, [])

    def test_legacy_barcode_is_refused(self):
        shop = FakeShop()
        result, _ = run(shop, barcode="20144890")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(shop.created, [])

    def test_product_set_error_fails_without_publishing(self):
        shop = FakeShop(set_error=ShopifyError("Handle has already been taken"))
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Handle has already been taken", result["message"])
        self.assertEqual(shop.published, [])

    def test_publish_error_says_the_product_exists(self):
        shop = FakeShop(publish_error=ShopifyError("Publication not found"))
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["admin_url"])
        self.assertIn("created in Shopify but", result["message"])
        self.assertIn("Publication not found", result["message"])

    def test_verify_mismatches_fail(self):
        shop = FakeShop(lose=["taxable", "quantity", "tags"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertIn("charges tax", result["problems"])
        self.assertIn("quantity is 0, not 1", result["problems"])
        self.assertIn("missing tags: Rental, Barcode Not Printed, criterion", result["problems"])

    def test_also_on_point_of_sale_fails(self):
        result, _ = run(FakeShop(extra_channels=["Point of Sale"]))
        self.assertEqual(result["status"], "failed")
        self.assertIn("also on Point of Sale", result["problems"])

    def test_poster_that_shopify_could_not_fetch(self):
        result, _ = run(FakeShop(media=["PROCESSING", "FAILED"]))
        self.assertEqual((result["status"], result["poster"]), ("created", "failed"))

    def test_poster_still_processing_counts_as_ok_after_a_bounded_wait(self):
        result, sleeps = run(FakeShop(media=["PROCESSING"]))
        self.assertEqual((result["status"], result["poster"]), ("created", "ok"))
        self.assertLessEqual(sum(sleeps), 20)
        self.assertTrue(sleeps)

    def test_setup_errors_propagate(self):
        with self.assertRaises(SetupError):
            run(FakeShop(location_error=SetupError("two locations")))


if __name__ == "__main__":
    unittest.main()
