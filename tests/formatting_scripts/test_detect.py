import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

from columns import EXPORT_COLUMNS, TEMPLATE_COLUMNS
from detect import UnknownShapeError, detect_shape, strip_reason

RAW_TEMPLATE = TEMPLATE_COLUMNS + ["Format", "Genre 1", "Genre 2", "Genre 3", "Year", "Extra tags"]
RAW_EXPORT = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
              "Tags", "Published", "Option1 Name", "Option1 Value", "Variant SKU",
              "Variant Inventory Tracker", "Variant Price", "Variant Barcode",
              "Image Src", "Image Position", "Image Alt Text", "Status"]


class TestDetectShape(unittest.TestCase):
    def test_raw_client_template_with_helper_columns(self):
        self.assertEqual(detect_shape(RAW_TEMPLATE), "template")

    def test_raw_shopify_export(self):
        self.assertEqual(detect_shape(RAW_EXPORT), "export")

    def test_our_own_template_output(self):
        self.assertEqual(detect_shape(TEMPLATE_COLUMNS), "template")

    def test_our_own_export_output(self):
        self.assertEqual(detect_shape(EXPORT_COLUMNS), "export")

    def test_a_real_export_carrying_both_markers_is_an_export(self):
        """Real Shopify exports have Status AND Variant Barcode; the barcode
        check must win, or every catalogue export reads as a template."""
        self.assertIn("Status", RAW_EXPORT)
        self.assertIn("Variant Barcode", RAW_EXPORT)
        self.assertEqual(detect_shape(RAW_EXPORT), "export")

    def test_unknown_header_is_a_hard_error_naming_what_was_missing(self):
        with self.assertRaises(UnknownShapeError) as caught:
            detect_shape(["Name", "Price", "Qty"])
        message = str(caught.exception)
        self.assertIn("Genre 1", message)
        self.assertIn("Variant Barcode", message)
        self.assertIn("Status", message)


class TestStripReason(unittest.TestCase):
    def test_removes_the_reason_column_and_its_values(self):
        fieldnames = ["Reason"] + TEMPLATE_COLUMNS
        rows = [{"Reason": "no usable genre", "Handle": "a", "Title": "A"}]
        new_fieldnames, new_rows = strip_reason(fieldnames, rows)
        self.assertEqual(new_fieldnames, TEMPLATE_COLUMNS)
        self.assertNotIn("Reason", new_rows[0])
        self.assertEqual(new_rows[0]["Handle"], "a")

    def test_leaves_a_reasonless_file_alone(self):
        rows = [{"Handle": "a"}]
        new_fieldnames, new_rows = strip_reason(TEMPLATE_COLUMNS, rows)
        self.assertEqual(new_fieldnames, TEMPLATE_COLUMNS)
        self.assertEqual(new_rows, rows)

    def test_a_prior_issues_file_round_trips_to_its_origin_shape_export(self):
        fieldnames, _ = strip_reason(["Reason"] + RAW_EXPORT, [])
        self.assertEqual(detect_shape(fieldnames), "export")

    def test_a_prior_issues_file_round_trips_to_its_origin_shape_template(self):
        fieldnames, _ = strip_reason(["Reason"] + TEMPLATE_COLUMNS, [])
        self.assertEqual(detect_shape(fieldnames), "template")


if __name__ == "__main__":
    unittest.main()
