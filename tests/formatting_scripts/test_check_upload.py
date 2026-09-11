import csv
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "formatting-scripts"))

from check_upload import check, detect_shape
from columns import GENRE_METAFIELD, TEMPLATE_COLUMNS
from sheet_transform import FILL_COLUMNS

TEMPLATE_DIR = os.path.join(ROOT, "formatting-scripts", "client-template")
GOOD_IMPORT = os.path.join(TEMPLATE_DIR, "sheet-export.csv")
GOOD_FILL = os.path.join(TEMPLATE_DIR, "sheet-export-input.csv")


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write(rows, columns):
    """Write rows to a temp CSV and return its path."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    )
    writer = csv.DictWriter(handle, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    handle.close()
    return handle.name


def _messages(path):
    _, _, problems = check(path)
    return [p.message for p in problems]


class TestShapeDetection(unittest.TestCase):
    def test_recognises_both_shapes(self):
        self.assertEqual(detect_shape(FILL_COLUMNS), "fill")
        self.assertEqual(detect_shape(TEMPLATE_COLUMNS), "import")

    def test_names_what_differs_on_a_near_miss(self):
        with self.assertRaises(ValueError) as caught:
            detect_shape([c for c in TEMPLATE_COLUMNS if c != "Vendor"])
        self.assertIn("missing", str(caught.exception))
        self.assertIn("Vendor", str(caught.exception))

    def test_rejects_an_unrelated_header(self):
        with self.assertRaises(ValueError) as caught:
            detect_shape(["Title", "Nonsense"])
        self.assertIn("neither", str(caught.exception))


class TestCleanFilesPass(unittest.TestCase):
    """The shipped fixtures must stay clean, or the checker is crying wolf."""

    def test_import_fixture_has_no_problems(self):
        shape, rows, problems = check(GOOD_IMPORT)
        self.assertEqual(shape, "import")
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 20)

    def test_fill_fixture_has_no_problems(self):
        shape, rows, problems = check(GOOD_FILL)
        self.assertEqual(shape, "fill")
        self.assertEqual(problems, [])


class TestCatchesTheRealGenreBug(unittest.TestCase):
    """2026-09-11: a genre the mappings tab didn't know made the sheet's
    VLOOKUP return "" through IFERROR, so products imported with an empty
    genre metafield. It survived three import rounds before anyone noticed."""

    def test_flags_a_genre_label_outside_the_thirteen(self):
        rows = _read(GOOD_IMPORT)
        rows[0]["Option1 Value"] = "Science Fiction"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(
            any("not one of the 13" in m for m in _messages(path)),
            "an unknown genre label must be flagged",
        )

    def test_flags_a_genre_that_produced_no_handle(self):
        rows = _read(GOOD_IMPORT)
        rows[0][GENRE_METAFIELD] = ""
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(
            any("produced no genre handle" in m for m in _messages(path)),
            "a blank genre metafield beside a real genre must be flagged",
        )

    def test_flags_a_handle_that_is_not_a_real_genre(self):
        rows = _read(GOOD_IMPORT)
        rows[0][GENRE_METAFIELD] = "not-a-genre"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("is not a real genre" in m for m in _messages(path)))


class TestCatchesCostlyMistakes(unittest.TestCase):
    def test_flags_a_duplicate_handle(self):
        rows = _read(GOOD_IMPORT)
        rows[1]["Handle"] = rows[0]["Handle"]
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        messages = _messages(path)
        self.assertTrue(any("already used on row 2" in m for m in messages))

    def test_flags_a_floor_sale_priced_zero(self):
        rows = _read(GOOD_IMPORT)
        sale = next(r for r in rows if "Floor Sale" in r["Tags"])
        sale["Variant Price"] = "0"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("Floor Sale priced 0" in m for m in _messages(path)))

    def test_flags_a_rental_with_a_price(self):
        rows = _read(GOOD_IMPORT)
        rental = next(r for r in rows if "Rental" in r["Tags"])
        rental["Variant Price"] = "9.99"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("Rental priced" in m for m in _messages(path)))

    def test_flags_untracked_inventory(self):
        rows = _read(GOOD_IMPORT)
        rows[0]["Variant Inventory Tracker"] = ""
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("inventory not tracked" in m for m in _messages(path)))

    def test_flags_a_vendor_that_is_not_a_format(self):
        rows = _read(GOOD_IMPORT)
        rows[0]["Vendor"] = "Criterion"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("is not a media format" in m for m in _messages(path)))

    def test_flags_a_fill_row_missing_its_price(self):
        rows = _read(GOOD_FILL)
        sale = next(r for r in rows if r["Type"] == "Floor Sale")
        sale["Price"] = ""
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("no price" in m for m in _messages(path)))


class TestRowNumbersAreSpreadsheetRows(unittest.TestCase):
    """An operator reads these against the sheet, so row 1 is the header."""

    def test_first_data_row_reports_as_row_two(self):
        rows = _read(GOOD_IMPORT)
        rows[0]["Option1 Value"] = "Science Fiction"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        _, _, problems = check(path)
        self.assertTrue(problems)
        self.assertEqual(problems[0].row, 2)


if __name__ == "__main__":
    unittest.main()
