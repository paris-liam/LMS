import unittest

from catalog.core.barcodes import barcode_owners, is_rental_barcode


class TestBarcodes(unittest.TestCase):
    def test_rental_barcode(self):
        self.assertTrue(is_rental_barcode("01577790"))
        self.assertTrue(is_rental_barcode(" 01577790 "))
        for bad in ("", "1577790", "0157779A", "015777901", None):
            self.assertFalse(is_rental_barcode(bad))

    def test_owners(self):
        rows = [{"Handle": "a", "Variant Barcode": "1"}, {"Handle": "b", "Variant Barcode": " 1 "},
                {"Handle": "c", "Variant Barcode": ""}]
        self.assertEqual(barcode_owners(rows), {"1": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
