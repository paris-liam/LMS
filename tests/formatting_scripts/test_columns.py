import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

from columns import (
    EXPORT_COLUMNS,
    FIXED_VALUES,
    GENRE_METAFIELD,
    REASON_COLUMN,
    TEMPLATE_COLUMNS,
)


class TestTemplateContract(unittest.TestCase):
    # The sheet-vs-contract seam test lives with the real spreadsheet export, not
    # here: any fixture this repo generates from TEMPLATE_COLUMNS can only compare
    # the constant against itself. A CSV exported from the built Google Sheet can
    # genuinely disagree, so that check is added when that export first exists.

    def test_has_seventeen_columns(self):
        self.assertEqual(len(TEMPLATE_COLUMNS), 17)


class TestExportContract(unittest.TestCase):
    def test_sets_only_intended_columns(self):
        self.assertEqual(EXPORT_COLUMNS, [
            "Handle", "Title", "Body (HTML)", "Vendor", "Product Category",
            "Tags", "Option1 Name", "Option1 Value",
            "Variant Inventory Tracker", "Variant Inventory Qty",
            "Variant Inventory Policy", "Variant Fulfillment Service",
            "Variant Price", "Variant Barcode",
            "Image Src", "Image Position", "Image Alt Text",
            GENRE_METAFIELD,
        ])

    def test_omits_columns_shopify_must_leave_untouched(self):
        for column in ("Status", "Published", "SEO Title", "SEO Description",
                       "Variant SKU", "Variant Grams", "Type"):
            self.assertNotIn(column, EXPORT_COLUMNS)

    def test_carries_barcode_so_printed_labels_survive_a_variant_rebuild(self):
        self.assertIn("Variant Barcode", EXPORT_COLUMNS)


class TestFixedValues(unittest.TestCase):
    def test_inventory_tracker_is_always_shopify(self):
        self.assertEqual(FIXED_VALUES["Variant Inventory Tracker"], "shopify")

    def test_the_rest_of_the_fixed_set(self):
        self.assertEqual(FIXED_VALUES["Product Category"], "Media > Videos")
        self.assertEqual(FIXED_VALUES["Option1 Name"], "Genre")
        self.assertEqual(FIXED_VALUES["Variant Inventory Qty"], "1")
        self.assertEqual(FIXED_VALUES["Variant Inventory Policy"], "deny")
        self.assertEqual(FIXED_VALUES["Variant Fulfillment Service"], "manual")

    def test_reason_column_name(self):
        self.assertEqual(REASON_COLUMN, "Reason")


if __name__ == "__main__":
    unittest.main()
