import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeShop  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync.add_copy import add_copy, next_copy_number  # noqa: E402

PID = "gid://shopify/Product/7"
OLD, OLD2, NEW = "2010000000021", "2010000000038", "2010000000014"


def item(**overrides):
    base = {"id": "9", "barcode": NEW, "title": "Jaws", "tags": "vhs, horror", "description": "A shark.",
            "created": "2026-10-20"}
    base.update(overrides)
    return base


def shop_with(barcodes=(OLD,), **product):
    shop = FakeShop()
    shop.add_rental(PID, list(barcodes), **product)
    return shop


def new_variant(shop):
    return next(v for v in shop.copy_products[PID]["variants"] if v["barcode"] == NEW)


class TestNextCopyNumber(unittest.TestCase):
    def test_next_copy_number_skips_gaps(self):
        self.assertEqual(next_copy_number(["Copy 1", "Copy 3"]), 4)
        self.assertEqual(next_copy_number([]), 2)

    def test_ignores_values_that_are_not_copy_numbers(self):
        self.assertEqual(next_copy_number(["Copy 2", "Spare"]), 3)


class TestAddCopy(unittest.TestCase):
    def test_adds_variant_and_tag(self):
        shop = shop_with(barcodes=(OLD, OLD2), copies=["Copy 1", "Copy 2"], tags=("Rental",))
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "added", result)
        self.assertEqual((result["barcode"], result["title"], result["handle"]), (NEW, "Jaws", "rental-7"))
        self.assertEqual(result["admin_url"], "https://admin.shopify.com/store/lms-sandbox-lutsfahz/products/7")
        self.assertEqual(result["problems"], [])
        sent = next(w[2] for w in shop.writes if w[0] == "add_variant")
        self.assertEqual(sent["optionValues"], [{"optionName": "Genre", "name": "Horror"},
                                                {"optionName": "Copy", "name": "Copy 3"}])
        self.assertEqual((sent["barcode"], sent["price"], sent["taxable"], sent["inventoryPolicy"]),
                         (NEW, "0.00", False, "DENY"))
        self.assertEqual(sent["inventoryItem"], {"tracked": True})
        self.assertEqual(sent["inventoryQuantities"],
                         [{"locationId": "gid://shopify/Location/1", "availableQuantity": 1}])
        self.assertIn(("add_tags", PID, ["Barcode Not Printed"]), shop.writes)
        self.assertNotIn("add_copy_option", [w[0] for w in shop.writes])
        self.assertEqual(new_variant(shop)["inventoryQuantity"], 1)

    def test_first_copy_adds_option(self):
        shop = shop_with()
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "added", result)
        self.assertEqual([w for w in shop.writes if w[0] == "add_copy_option"], [("add_copy_option", PID)])
        self.assertIn({"name": "Copy", "value": "Copy 2"}, new_variant(shop)["selectedOptions"])
        old = shop.copy_products[PID]["variants"][0]
        self.assertIn({"name": "Copy", "value": "Copy 1"}, old["selectedOptions"])

    def test_add_copy_twice_is_skipped(self):
        shop = shop_with()
        self.assertEqual(add_copy(shop, item(), PID)["status"], "added")
        writes = len(shop.writes)
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "skipped_exists", result)
        self.assertEqual(len(shop.writes), writes)
        self.assertEqual([v["barcode"] for v in shop.copy_products[PID]["variants"]].count(NEW), 1)

    def test_variant_on_product_but_not_yet_searchable_is_skipped(self):
        shop = shop_with()
        add_copy(shop, item(), PID)
        del shop.barcodes[NEW]
        writes = len(shop.writes)
        self.assertEqual(add_copy(shop, item(), PID)["status"], "skipped_exists")
        self.assertEqual(len(shop.writes), writes)

    def test_existing_copy_with_problems_needs_attention(self):
        shop = shop_with(barcodes=(OLD, NEW), copies=["Copy 1", "Copy 2"])
        shop.lose.add(("taxable", NEW))
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("charges tax", result["problems"])
        self.assertEqual(shop.writes, [])

    def test_refuses_missing_product(self):
        shop = shop_with()
        result = add_copy(shop, item(), "gid://shopify/Product/404")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["message"], "That Shopify product no longer exists")
        self.assertEqual(shop.writes, [])

    def test_refuses_wrong_format(self):
        shop = shop_with(vendor="VHS")
        result = add_copy(shop, item(tags="dvd, horror"), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("VHS", result["message"])
        self.assertIn("DVD", result["message"])
        self.assertEqual(shop.writes, [])

    def test_refuses_non_rental(self):
        shop = shop_with(tags=("Floor Sale",))
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Rental", result["message"])
        self.assertEqual(shop.writes, [])

    def test_refuses_product_without_genre_option(self):
        shop = shop_with(options=[{"name": "Title", "values": ["Default Title"]}])
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["message"], "unexpected product shape — contact Liam")
        self.assertEqual(shop.writes, [])

    def test_barcode_on_other_product_fails(self):
        shop = shop_with()
        shop.add_rental("gid://shopify/Product/8", [NEW])
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("rental-8", result["message"])
        self.assertEqual(shop.writes, [])

    def test_set_aside_copy_is_refused(self):
        shop = shop_with()
        result = add_copy(shop, item(tags="horror"), PID)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["message"].startswith("not ready: "), result)
        self.assertEqual(shop.owner_calls, [])

    def test_existing_variants_untouched(self):
        shop = shop_with(barcodes=(OLD, OLD2), copies=["Copy 1", "Copy 2"])
        shop.lose.add(("barcode", OLD2))
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["problems"])
        self.assertTrue(any(OLD2 in p for p in result["problems"]), result["problems"])

    def test_new_variant_checked_on_read_back(self):
        shop = shop_with()
        shop.lose.add(("taxable", NEW))
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("charges tax", result["problems"])

    def test_rerun_adds_tag_a_failed_run_left_off(self):
        class FlakyTagShop(FakeShop):
            failures = 1

            def add_tags(self, product_id, tags):
                if self.failures:
                    self.failures -= 1
                    raise ShopifyError("Shopify returned an error: tags timed out")
                super().add_tags(product_id, tags)
        shop = FlakyTagShop()
        shop.add_rental(PID, [OLD], tags=("Rental",))
        first = add_copy(shop, item(), PID)
        self.assertEqual(first["status"], "failed")
        self.assertIn("run the sync again", first["message"])
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "skipped_exists", result)
        self.assertIn("Barcode Not Printed", result["message"])
        self.assertIn("Barcode Not Printed", shop.copy_products[PID]["tags"])
        self.assertEqual([v["barcode"] for v in shop.copy_products[PID]["variants"]].count(NEW), 1)

    def test_write_error_fails_with_message(self):
        class BrokenShop(FakeShop):
            def add_variant(self, product_id, variant_input):
                raise ShopifyError("Shopify returned an error: boom")
        shop = BrokenShop()
        shop.add_rental(PID, [OLD])
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["message"])

    def test_setup_error_after_the_variant_says_it_may_be_partly_added(self):
        class NoTagScopeShop(FakeShop):
            def add_tags(self, product_id, tags):
                raise SetupError("missing permission write_products")
        shop = NoTagScopeShop()
        shop.add_rental(PID, [OLD])
        result = add_copy(shop, item(), PID)
        self.assertEqual(result["status"], "failed")
        self.assertIn("missing permission", result["message"])
        self.assertIn("may have been partly added", result["message"])
        self.assertEqual(result["print"], [NEW])

    def test_setup_error_before_any_write_propagates(self):
        shop = FakeShop(location_error=SetupError("found 2 locations"))
        shop.add_rental(PID, [OLD])
        with self.assertRaises(SetupError):
            add_copy(shop, item(), PID)
        self.assertEqual(shop.writes, [])


class TestPrint(unittest.TestCase):
    """`print` lists the barcode once it is written to Shopify, so its label gets printed."""

    def test_added_prints_the_barcode(self):
        self.assertEqual(add_copy(shop_with(), item(), PID)["print"], [NEW])

    def test_written_but_needs_checking_still_prints(self):
        shop = shop_with()
        shop.lose.add(("taxable", NEW))
        result = add_copy(shop, item(), PID)
        self.assertEqual((result["status"], result["print"]), ("failed", [NEW]))

    def test_tag_failure_after_the_variant_still_prints_and_the_repair_prints(self):
        class FlakyTagShop(FakeShop):
            failures = 1

            def add_tags(self, product_id, tags):
                if self.failures:
                    self.failures -= 1
                    raise ShopifyError("Shopify returned an error: tags timed out")
                super().add_tags(product_id, tags)
        shop = FlakyTagShop()
        shop.add_rental(PID, [OLD], tags=("Rental",))
        first = add_copy(shop, item(), PID)
        self.assertEqual((first["status"], first["print"]), ("failed", [NEW]))
        again = add_copy(shop, item(), PID)
        self.assertEqual((again["status"], again["print"]), ("skipped_exists", [NEW]))

    def test_nothing_written_prints_nothing(self):
        class BrokenShop(FakeShop):
            def add_variant(self, product_id, variant_input):
                raise ShopifyError("Shopify returned an error: boom")
        broken = BrokenShop()
        broken.add_rental(PID, [OLD])
        self.assertEqual(add_copy(broken, item(), PID)["print"], [])
        shop = shop_with()
        add_copy(shop, item(), PID)
        self.assertEqual(add_copy(shop, item(), PID)["print"], [])
        self.assertEqual(add_copy(shop_with(), item(), "gid://shopify/Product/404")["print"], [])


if __name__ == "__main__":
    unittest.main()
