import unittest

from datetime import date

from catalog.core.barcodes import barcode_owners, floor_sale_barcode, is_floor_sale_barcode, is_rental_barcode


class TestBarcodes(unittest.TestCase):
    def test_rental_barcode(self):
        self.assertTrue(is_rental_barcode("01577790"))
        self.assertTrue(is_rental_barcode(" 01577790 "))
        for bad in ("", "1577790", "0157779A", "015777901", None):
            self.assertFalse(is_rental_barcode(bad))

    def test_floor_sale_barcode(self):
        self.assertEqual(floor_sale_barcode(date(2026, 10, 20), 7), "261020007")
        self.assertTrue(is_floor_sale_barcode("261020007"))
        # Never mistaken for an app (8-digit) or Libib (13-digit) barcode.
        for other in ("71735546", "2010000123456", "2610201000", ""):
            self.assertFalse(is_floor_sale_barcode(other))
        self.assertFalse(is_rental_barcode("261020007"))

    def test_owners(self):
        rows = [{"Handle": "a", "Variant Barcode": "1"}, {"Handle": "b", "Variant Barcode": " 1 "},
                {"Handle": "c", "Variant Barcode": ""}]
        self.assertEqual(barcode_owners(rows), {"1": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
