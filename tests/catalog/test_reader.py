import subprocess
import unittest
from pathlib import Path
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import ShopifyError
from catalog.shopify import reader
from catalog.shopify.reader import _parse_json_output, node_to_row, read_products


def node(**overrides):
    base = {
        "handle": "rushmore-vhs-rental", "title": "Rushmore", "descriptionHtml": "<p>x</p>",
        "vendor": "VHS", "tags": ["Rental", "VHS", "Comedy"], "status": "ACTIVE",
        "templateSuffix": None, "variantsCount": {"count": 1},
        "variants": {"nodes": [{"price": "0.00", "barcode": "01577790",
                                "selectedOptions": [{"name": "Genre", "value": "Comedy"}],
                                "inventoryItem": {"tracked": True}}]},
        "media": {"nodes": [{"image": {"url": "https://cdn.shopify.com/r.jpg", "altText": "Rushmore poster"}}]},
        "genre": {"references": {"nodes": [{"handle": "comedy"}, {"handle": "drama"}]}},
        "category": {"fullName": "Media > Videos"},
    }
    base.update(overrides)
    return base


def page(nodes, has_next, cursor=None):
    return {"products": {"pageInfo": {"hasNextPage": has_next, "endCursor": cursor}, "nodes": nodes}}


class TestNodeToRow(unittest.TestCase):
    def test_query_reads_the_product_category(self):
        query = (Path(reader.__file__).parent / "queries" / "products.graphql").read_text()
        self.assertRegex(query, r"category\s*\{\s*fullName\s*\}")

    def test_full_node(self):
        r = node_to_row(node())
        self.assertEqual(r["Handle"], "rushmore-vhs-rental")
        self.assertEqual(r["Tags"], "Rental, VHS, Comedy")
        self.assertEqual(r["Status"], "active")
        self.assertEqual(r["Template Suffix"], "")
        self.assertEqual(r["Option1 Name"], "Genre")
        self.assertEqual(r["Option1 Value"], "Comedy")
        self.assertEqual(r["Variant Price"], "0.00")
        self.assertEqual(r["Variant Barcode"], "01577790")
        self.assertEqual(r["Variant Inventory Tracker"], "shopify")
        self.assertEqual(r["Variant Count"], "1")
        self.assertEqual(r["Image Src"], "https://cdn.shopify.com/r.jpg")
        self.assertEqual(r["Image Alt Text"], "Rushmore poster")
        self.assertEqual(r[GENRE_METAFIELD], "comedy; drama")
        self.assertEqual(r["Product Category"], "Media > Videos")

    def test_node_with_nothing_optional(self):
        r = node_to_row(node(descriptionHtml=None, vendor=None, tags=[], templateSuffix="retail",
                             variantsCount={"count": 0}, variants={"nodes": []},
                             media={"nodes": [{}]},  # first media is a video: fragment yields {}
                             genre=None, category=None))
        self.assertEqual(r["Body (HTML)"], "")
        self.assertEqual(r["Template Suffix"], "retail")
        self.assertEqual(r["Variant Barcode"], "")
        self.assertEqual(r["Variant Inventory Tracker"], "")
        self.assertEqual(r["Image Src"], "")
        self.assertEqual(r[GENRE_METAFIELD], "")
        self.assertEqual(r["Variant Count"], "0")
        self.assertEqual(r["Product Category"], "")

    def test_untracked_and_null_barcode(self):
        n = node()
        n["variants"]["nodes"][0].update({"barcode": None, "inventoryItem": {"tracked": False}})
        r = node_to_row(n)
        self.assertEqual(r["Variant Barcode"], "")
        self.assertEqual(r["Variant Inventory Tracker"], "")

    def test_first_image_is_used_when_a_video_comes_first(self):
        r = node_to_row(node(media={"nodes": [{}, {"image": {"url": "https://cdn/2.jpg", "altText": "B"}}]}))
        self.assertEqual((r["Image Src"], r["Image Alt Text"]), ("https://cdn/2.jpg", "B"))


class TestReadProducts(unittest.TestCase):
    def test_paginates_until_done(self):
        calls = []

        def execute(store, query_path, variables):
            calls.append(variables["cursor"])
            if variables["cursor"] is None:
                return page([node(handle="a")], True, "c1")
            return {"data": page([node(handle="b")], False)}  # wrapped form also accepted

        rows = read_products("example.myshopify.com", execute=execute)
        self.assertEqual([r["Handle"] for r in rows], ["a", "b"])
        self.assertEqual(calls, [None, "c1"])

    def test_graphql_errors_raise(self):
        with self.assertRaises(ShopifyError):
            read_products("s", execute=lambda *a: {"errors": [{"message": "Throttled"}]})


class TestRunCliQuery(unittest.TestCase):
    def fake_run(self, returncode, stdout="", stderr=""):
        return mock.patch.object(reader.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr))

    def test_auth_failure_names_the_auth_command(self):
        with self.fake_run(1, stderr="Error: You are not logged in to this store"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("p0wkgv-wy.myshopify.com", reader.QUERY_PATH, {"cursor": None})
        self.assertIn("shopify store auth --store p0wkgv-wy.myshopify.com --scopes read_products", str(ctx.exception))

    def test_other_failure_raises_with_stderr(self):
        with self.fake_run(1, stderr="boom"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})
        self.assertIn("boom", str(ctx.exception))

    def test_missing_cli(self):
        with mock.patch.object(reader.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(ShopifyError):
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})

    def test_parses_stdout_with_status_noise(self):
        noisy = 'Loading stored store auth ...\nExecuting GraphQL operation ...\n{"products": {"nodes": []}}\n✨ New version available'
        self.assertEqual(_parse_json_output(noisy), {"products": {"nodes": []}})

    def test_query_file_exists_and_names_every_field(self):
        text = Path(reader.QUERY_PATH).read_text(encoding="utf-8")
        for field in ("handle", "descriptionHtml", "templateSuffix", "variantsCount", "barcode",
                      "tracked", "altText", 'namespace: "shopify", key: "genre"', "endCursor"):
            self.assertIn(field, text)

    def test_a_non_auth_failure_mentioning_author_is_not_called_auth(self):
        with self.fake_run(1, stderr="Field 'author' doesn't exist on type 'Product'"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})
        self.assertNotIn("not authenticated", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
