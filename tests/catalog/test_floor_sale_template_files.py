import csv
import os
import re
import unittest

from catalog.client_sheet.check import check
from catalog.client_sheet.floor_sale import (
    FLOOR_SALE_FILL_HEADER, floor_sale_rows_to_import_rows, split_fill_tab,
)
from catalog.core.columns import FLOOR_SALE_TEMPLATE_COLUMNS
from catalog.core.taxonomy import FORMATS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FLOOR_SALE_DIR = os.path.join(ROOT, "catalog", "client_sheet", "template", "floor-sale")
FILL_CSV = os.path.join(FLOOR_SALE_DIR, "floor-sale-template.csv")
EXPECTED_CSV = os.path.join(FLOOR_SALE_DIR, "floor-sale-template.expected.csv")
SHEET_INPUT_CSV = os.path.join(FLOOR_SALE_DIR, "sheet-export-input.csv")
FORMULA = os.path.join(FLOOR_SALE_DIR, "import-tab-formula.txt")


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _header(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


class TestScaffold(unittest.TestCase):
    def test_fill_csv_is_the_fill_tab_shape(self):
        self.assertEqual(_header(FILL_CSV), FLOOR_SALE_FILL_HEADER)

    def test_expected_csv_is_what_the_transform_produces(self):
        self.assertEqual(_header(EXPECTED_CSV), FLOOR_SALE_TEMPLATE_COLUMNS)
        rows, batch_date = split_fill_tab(_read(FILL_CSV))
        self.assertEqual(_read(EXPECTED_CSV), floor_sale_rows_to_import_rows(rows, batch_date))

    def test_shipped_files_pass_check_upload(self):
        for path in (FILL_CSV, EXPECTED_CSV, SHEET_INPUT_CSV):
            _, _, problems = check(path)
            self.assertEqual(problems, [], os.path.basename(path))


class TestFormula(unittest.TestCase):
    def setUp(self):
        with open(FORMULA, encoding="utf-8") as handle:
            self.text = handle.read()

    def test_header_literal_matches_the_column_contract(self):
        literal = re.search(r"header,\s*\{(.*?)\}", self.text).group(1)
        self.assertEqual(re.findall(r'"([^"]*)"', literal), FLOOR_SALE_TEMPLATE_COLUMNS)

    def test_error_row_is_as_wide_as_the_header(self):
        literal = re.search(r"oops,\s*\{(.*?)\},\n", self.text).group(1)
        self.assertEqual(len(re.findall(r'"([^"]*)"', literal)), len(FLOOR_SALE_TEMPLATE_COLUMNS))


class TestSeamInput(unittest.TestCase):
    """The rows the live sheet is fed for the seam test. A seam fixture only
    guards what it exercises."""

    def test_covers_every_format_and_the_awkward_cases(self):
        rows, batch_date = split_fill_tab(_read(SHEET_INPUT_CSV))
        self.assertIsNotNone(batch_date)
        self.assertEqual({r["Format"] for r in rows}, set(FORMATS))
        handles = [r["Handle"] for r in floor_sale_rows_to_import_rows(rows, batch_date)]
        self.assertTrue(any(h.endswith("-2") for h in handles), "no repeat copy")
        self.assertTrue(any("'" in r["Title"] for r in rows), "no apostrophe title")
        self.assertTrue(any(not r["Title"].isascii() for r in rows), "no accented title")
        self.assertTrue(any("," in r["Extra tags"] for r in rows), "no multi-tag row")
        self.assertTrue(any("." in r["Price"] for r in rows), "no decimal price")


if __name__ == "__main__":
    unittest.main()
