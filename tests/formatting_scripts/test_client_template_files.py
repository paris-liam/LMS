import csv
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "formatting-scripts"))

from columns import TEMPLATE_COLUMNS
from sheet_transform import FILL_COLUMNS, fill_rows_to_import_rows

TEMPLATE_DIR = os.path.join(ROOT, "formatting-scripts", "client-template")
FILL_CSV = os.path.join(TEMPLATE_DIR, "client-upload-template.csv")
EXPECTED_CSV = os.path.join(TEMPLATE_DIR, "client-upload-template.expected.csv")


def _read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class TestScaffold(unittest.TestCase):
    def test_fill_csv_header_matches_fill_columns(self):
        with open(FILL_CSV, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, FILL_COLUMNS)

    def test_fill_csv_has_one_rental_and_one_floor_sale_example(self):
        rows = _read(FILL_CSV)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(r["Type"] for r in rows), ["Floor Sale", "Rental"]
        )

    def test_expected_csv_header_matches_template_columns(self):
        with open(EXPECTED_CSV, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, TEMPLATE_COLUMNS)

    def test_expected_csv_is_what_the_transform_produces(self):
        produced = fill_rows_to_import_rows(_read(FILL_CSV))
        self.assertEqual(_read(EXPECTED_CSV), produced)


class TestGenerator(unittest.TestCase):
    def test_generator_is_idempotent(self):
        before = open(EXPECTED_CSV, encoding="utf-8").read()
        subprocess.run(
            [sys.executable, os.path.join(TEMPLATE_DIR, "generate_expected.py")],
            check=True,
            cwd=ROOT,
        )
        self.assertEqual(open(EXPECTED_CSV, encoding="utf-8").read(), before)


if __name__ == "__main__":
    unittest.main()
