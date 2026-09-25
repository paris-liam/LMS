import csv
import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import InputShapeError
from catalog.shopify.export_reader import read_export

HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Option1 Name",
          "Option1 Value", "Variant Price", "Variant Barcode", "Variant Inventory Tracker",
          "Image Src", "Image Alt Text", GENRE_METAFIELD]


def write(path: Path, rows, header=HEADER):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in header})


def product(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>x</p>",
            "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
            "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0",
            "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
            "Image Src": "https://cdn/x.jpg", "Image Alt Text": "", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


class TestReadExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "export.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_row_per_product_with_extra_image_rows_folded(self):
        write(self.path, [product(), {"Handle": "rushmore-vhs-rental", "Image Src": "https://cdn/2.jpg"}])
        rows = read_export(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Image Src"], "https://cdn/x.jpg")
        self.assertEqual(rows[0]["Variant Count"], "1")

    def test_counts_real_variant_rows(self):
        write(self.path, [product(), {"Handle": "rushmore-vhs-rental", "Option1 Value": "Drama",
                                       "Variant Price": "0", "Variant Barcode": "01577791"}])
        self.assertEqual(read_export(self.path)[0]["Variant Count"], "2")

    def test_plural_barcode_header_is_accepted(self):
        header = [("Variant Barcodes" if c == "Variant Barcode" else c) for c in HEADER]
        r = product()
        r["Variant Barcodes"] = r.pop("Variant Barcode")
        write(self.path, [r], header)
        self.assertEqual(read_export(self.path)[0]["Variant Barcode"], "01577790")

    def test_status_lowercased_and_missing_columns_blank(self):
        write(self.path, [product(Status="Active")])
        r = read_export(self.path)[0]
        self.assertEqual(r["Status"], "active")
        self.assertEqual(r["Template Suffix"], "")

    def test_not_an_export_raises(self):
        write(self.path, [{"Title": "x"}], ["Title", "Format"])
        with self.assertRaises(InputShapeError):
            read_export(self.path)


if __name__ == "__main__":
    unittest.main()
