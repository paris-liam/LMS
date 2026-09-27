import sys
import tempfile
import unittest
from pathlib import Path


from catalog.core.registry import (
    filter_unknown, is_known, load_registry, mark_queued, mark_resolved, save_registry,
)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_registry_missing_file_is_empty(self):
        self.assertEqual(load_registry(self.tools_dir), {})

    def test_save_then_load_round_trips(self):
        registry = {}
        mark_queued(registry, ["a", "b"], "ambiguous-queue")
        save_registry(self.tools_dir, registry)
        self.assertEqual(load_registry(self.tools_dir), registry)

    def test_is_known_true_for_queued_and_resolved(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        self.assertTrue(is_known(registry, "a"))
        mark_resolved(registry, ["a"])
        self.assertTrue(is_known(registry, "a"))
        self.assertFalse(is_known(registry, "b"))

    def test_mark_resolved_updates_status_in_place(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        mark_resolved(registry, ["a"])
        self.assertEqual(registry["a"]["status"], "resolved")
        self.assertEqual(registry["a"]["batch"], "ambiguous-queue")  # batch preserved

    def test_mark_resolved_on_an_unqueued_handle_still_marks_it(self):
        registry = {}
        mark_resolved(registry, ["a"])
        self.assertEqual(registry["a"]["status"], "resolved")

    def test_filter_unknown_drops_queued_and_resolved_handles(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        mark_resolved(registry, ["b"])
        rows = [{"Handle": "a"}, {"Handle": "b"}, {"Handle": "c"}]
        self.assertEqual(filter_unknown(rows, registry), [{"Handle": "c"}])


from catalog.core.registry import fix_visible, mark_applied, mark_skipped, promote_applied


class TestLifecycle(unittest.TestCase):
    def test_applied_records_run_and_values(self):
        registry = {"a": {"batch": "ambiguous-queue", "status": "queued"}}
        mark_applied(registry, "a", "2026-09-25", {"Image Src": "https://img/x.jpg"})
        self.assertEqual(registry["a"]["status"], "applied")
        self.assertEqual(registry["a"]["run"], "2026-09-25")
        self.assertEqual(registry["a"]["values"], {"Image Src": "https://img/x.jpg"})
        self.assertEqual(registry["a"]["batch"], "ambiguous-queue")

    def test_skipped(self):
        registry = {"a": {"batch": "q", "status": "queued"}}
        mark_skipped(registry, "a")
        self.assertEqual(registry["a"]["status"], "skipped")

    def test_image_src_counts_as_visible_when_rehosted(self):
        self.assertTrue(fix_visible({"Image Src": "https://cdn.shopify.com/files/x.jpg"},
                                    "Image Src", "https://image.tmdb.org/t/p/w1280/x.jpg"))
        self.assertFalse(fix_visible({"Image Src": ""}, "Image Src", "https://image.tmdb.org/x.jpg"))

    def test_description_compared_as_text(self):
        self.assertTrue(fix_visible({"Body (HTML)": "<p>A  film.</p>\n"}, "Body (HTML)", "<p>A film.</p>"))
        self.assertFalse(fix_visible({"Body (HTML)": ""}, "Body (HTML)", "<p>A film.</p>"))

    def test_other_fields_compared_exactly(self):
        self.assertTrue(fix_visible({"Vendor": "VHS"}, "Vendor", "VHS"))
        self.assertFalse(fix_visible({"Vendor": "vhs"}, "Vendor", "VHS"))

    def test_promote_applied(self):
        registry = {
            "done": {"status": "applied", "run": "r", "values": {"Image Src": "u"}},
            "pending": {"status": "applied", "run": "r", "values": {"Body (HTML)": "<p>x</p>"}},
            "gone": {"status": "applied", "run": "r", "values": {"Image Src": "u"}},
            "queued": {"status": "queued", "batch": "q"},
        }
        rows = {"done": {"Image Src": "https://cdn/1.jpg"}, "pending": {"Body (HTML)": ""},
                "queued": {"Image Src": ""}}
        resolved, missing = promote_applied(registry, rows)
        self.assertEqual(resolved, ["done"])
        self.assertEqual(missing, ["pending"])  # "gone" is not in the snapshot: left alone
        self.assertEqual(registry["done"]["status"], "resolved")
        self.assertEqual(registry["gone"]["status"], "applied")
        self.assertEqual(registry["queued"]["status"], "queued")


class TestFixVisibleTolerance(unittest.TestCase):
    def test_tags_compare_as_sets_ignoring_order_and_case(self):
        self.assertTrue(fix_visible({"Tags": "Comedy, Rental, VHS"}, "Tags", "Rental, VHS, comedy"))
        self.assertFalse(fix_visible({"Tags": "Rental, VHS"}, "Tags", "Rental, VHS, Comedy"))

    def test_genre_metafield_compares_as_sets(self):
        field = "Genre (product.metafields.shopify.genre)"
        self.assertTrue(fix_visible({field: "drama; comedy"}, field, "comedy; drama"))
        self.assertFalse(fix_visible({field: "drama"}, field, "comedy; drama"))

    def test_price_compares_numerically(self):
        self.assertTrue(fix_visible({"Variant Price": "0.00"}, "Variant Price", "0"))
        self.assertFalse(fix_visible({"Variant Price": "4.00"}, "Variant Price", "0"))
        self.assertFalse(fix_visible({"Variant Price": "abc"}, "Variant Price", "0"))


class TestMalformedRegistry(unittest.TestCase):
    def test_bad_json_is_an_input_error(self):
        from catalog.errors import InputShapeError
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "_handle-index.json").write_text("{oops", encoding="utf-8")
            with self.assertRaises(InputShapeError):
                load_registry(tmp)


if __name__ == "__main__":
    unittest.main()
