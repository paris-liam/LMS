import csv
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

TEMPLATE_CSV = REPO_ROOT / "data-cleanup/client-template/client-upload-template-rental.csv"


class TestTemplateContract(unittest.TestCase):
    def test_matches_the_client_template_header_exactly(self):
        """The seam: if the sheet changes and this doesn't, imports drift."""
        with open(TEMPLATE_CSV, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        # The sheet carries helper columns R-W after the 17 Shopify columns.
        self.assertEqual(TEMPLATE_COLUMNS, header[:17])

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
