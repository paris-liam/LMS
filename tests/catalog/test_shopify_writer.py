import unittest

from catalog.apply.merge import Change
from catalog.core.columns import GENRE_METAFIELD
from catalog.shopify import writer
from tests_fake_store import FakeStore, product


class TestWriteChanges(unittest.TestCase):
    def test_writes_and_verifies_each_field(self):
        store = FakeStore({"jaws": product("p1")})
        results = writer.write_changes([
            Change("jaws", "Product Category", "", "Media > Videos", "auto-fix"),
            Change("jaws", GENRE_METAFIELD, "", "horror", "auto-fix"),
            Change("jaws", "Image Src", "", "https://x/jaws.jpg", "pick:q"),
            Change("jaws", "Image Alt Text", "", "Jaws poster", "pick:q"),
        ], store)
        self.assertEqual({(r.field, r.status) for r in results},
                         {("Product Category", "written"), (GENRE_METAFIELD, "written"),
                          ("Image Src", "written"), ("Image Alt Text", "written")})
        self.assertEqual(len(store.writes), 1)  # one write per product

    def test_a_field_changed_since_the_audit_is_not_overwritten(self):
        store = FakeStore({"jaws": product("p1", Vendor="DVD")})  # someone set DVD after the audit
        results = writer.write_changes([Change("jaws", "Vendor", "4K UHD", "4K", "auto-fix")], store)
        self.assertEqual(results[0].status, "skipped")
        self.assertIn("changed in Shopify", results[0].message)
        self.assertEqual(store.writes, [])

    def test_a_value_already_in_place_is_skipped(self):
        store = FakeStore({"jaws": product("p1", Vendor="4K")})
        self.assertEqual(writer.write_changes([Change("jaws", "Vendor", "4K UHD", "4K", "x")], store)[0].status,
                         "skipped")

    def test_a_write_that_does_not_persist_is_failed(self):
        store = FakeStore({"jaws": product("p1")}, lose={"Vendor"})
        result = writer.write_changes([Change("jaws", "Vendor", "VHS", "DVD", "x")], store)[0]
        self.assertEqual(result.status, "failed")
        self.assertIn("read back", result.message)

    def test_one_products_error_does_not_stop_the_rest(self):
        store = FakeStore({"jaws": product("p1"), "heat": product("p2")}, fail={"jaws"})
        results = writer.write_changes([Change("jaws", "Vendor", "VHS", "DVD", "x"),
                                        Change("heat", "Vendor", "VHS", "DVD", "x")], store)
        self.assertEqual({(r.handle, r.status) for r in results}, {("jaws", "failed"), ("heat", "written")})

    def test_a_missing_product_fails_its_changes(self):
        result = writer.write_changes([Change("gone", "Vendor", "VHS", "DVD", "x")], FakeStore({}))[0]
        self.assertEqual(result.status, "failed")

    def test_unsupported_fields_are_refused_up_front(self):
        with self.assertRaises(ValueError):
            writer.write_changes([Change("jaws", "Title", "a", "b", "x")], FakeStore({"jaws": product("p1")}))

    def test_tag_and_genre_comparison_ignores_order_and_case(self):
        self.assertTrue(writer._same("Tags", "VHS, Rental", "rental, vhs"))
        self.assertTrue(writer._same(GENRE_METAFIELD, "comedy; drama", "comedy;drama"))
        self.assertTrue(writer._same("Body (HTML)", "<p>A  shark.</p>", "A shark."))
        self.assertTrue(writer._same("Variant Price", "5", "5.00"))


class FakeExecute:
    """Records the GraphQL an ApiStore sends; answers from a canned product."""

    def __init__(self):
        self.sent = []

    def __call__(self, store, query, variables):
        text = query.read_text()
        self.sent.append((text, variables))
        if "products(first: 1" in text:
            return {"data": {"products": {"nodes": [{
                "id": "gid://p/1", "handle": "jaws", "vendor": "VHS", "descriptionHtml": "", "tags": ["Rental"],
                "category": None, "options": [{"id": "o1", "name": "Genre", "optionValues": [{"id": "ov1", "name": "Drama"}]}],
                "variants": {"nodes": [{"id": "v1", "price": "0.00"}]}, "metafield": None,
                "media": {"nodes": []}}]}}}
        if "metaobjectByHandle" in text:
            return {"data": {"metaobjectByHandle": {"id": "gid://mo/horror"}}}
        root = text.split("{", 2)[1].split("(")[0].strip()
        return {"data": {root: {"userErrors": [], "product": {"media": {"nodes": [{"id": "m1"}]}}}}}


class TestApiStore(unittest.TestCase):
    def test_write_sends_the_expected_mutations(self):
        execute = FakeExecute()
        store = writer.ApiStore(execute, "shop", sleep=lambda s: None)
        p = store.get("jaws")
        self.assertEqual(p["fields"]["Option1 Value"], "Drama")
        store.write(p, {"Vendor": "DVD", "Product Category": "Media > Videos", GENRE_METAFIELD: "horror",
                        "Option1 Value": "Horror", "Variant Price": "4.00", "Image Src": "https://x.jpg"})
        sent = " ".join(text for text, _ in execute.sent)
        for mutation in ("productUpdate", "productOptionUpdate", "metafieldsSet", "productVariantsBulkUpdate"):
            self.assertIn(mutation, sent)
        update = next(v for t, v in execute.sent if "productUpdate(product: $p) {" in t)
        self.assertEqual(update["p"]["category"], "gid://shopify/TaxonomyCategory/me-7")
        genre = next(v for t, v in execute.sent if "metafieldsSet" in t)
        self.assertEqual(genre["m"][0]["value"], '["gid://mo/horror"]')

    def test_an_unknown_category_is_refused(self):
        store = writer.ApiStore(FakeExecute(), "shop")
        with self.assertRaises(RuntimeError):
            store.write(store.get("jaws"), {"Product Category": "Toys"})


if __name__ == "__main__":
    unittest.main()
