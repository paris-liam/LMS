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
SHEET_EXPORT_CSV = os.path.join(TEMPLATE_DIR, "sheet-export.csv")
SHEET_INPUT_CSV = os.path.join(TEMPLATE_DIR, "sheet-export-input.csv")


def _read(path):
    # utf-8-sig: Google Sheets writes a BOM on CSV download.
    with open(path, newline="", encoding="utf-8-sig") as handle:
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

class TestSheetExportSeam(unittest.TestCase):
    """The live spreadsheet's own output against the tested Python transform.

    This is the one fixture in the build that Google Sheets produced rather
    than this repo's own code, so it is the only one that can genuinely
    disagree with the column contract. Every other fixture is generated from
    the same constant it is checked against, which makes it circular.

    sheet-export-input.csv holds the fill-tab rows; sheet-export.csv is what
    the tab-2 array formula emitted for them. Regenerate the pair by pasting
    the input into a real sheet and downloading the import tab. A failure
    here means the formula in import-tab-formula.txt has drifted from
    sheet_transform.py — fix the formula, since the Python side is the
    tested one.
    """

    def test_export_header_matches_the_column_contract(self):
        with open(SHEET_EXPORT_CSV, newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, TEMPLATE_COLUMNS)

    def test_input_header_matches_the_fill_columns(self):
        with open(SHEET_INPUT_CSV, newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, FILL_COLUMNS)

    def test_export_covers_both_types_and_every_format(self):
        """A seam fixture only guards what it exercises."""
        rows = _read(SHEET_INPUT_CSV)
        self.assertEqual({r["Type"] for r in rows}, {"Rental", "Floor Sale"})
        self.assertEqual(
            {r["Format"] for r in rows},
            {"VHS", "DVD", "Blu-Ray", "4K", "Laserdisc", "Betamax"},
        )
        self.assertTrue(
            any(r["Genre 2"] for r in rows), "no multi-genre row to exercise the delimiter"
        )
        self.assertTrue(any(r["Extra tags"] for r in rows), "no extra-tag row")

    def test_sheet_formula_agrees_with_the_python_transform(self):
        produced = {r["Handle"]: r for r in fill_rows_to_import_rows(_read(SHEET_INPUT_CSV))}
        exported = {r["Handle"]: r for r in _read(SHEET_EXPORT_CSV)}

        self.assertEqual(set(exported), set(produced), "handle sets differ")

        for handle, want in produced.items():
            got = exported[handle]
            for column in TEMPLATE_COLUMNS:
                if column == "Variant Price":
                    # Sheets drops trailing zeros ("8"), Python keeps them
                    # ("8.00"). Shopify normalizes both, so compare by value.
                    self.assertAlmostEqual(
                        float(got[column] or 0), float(want[column] or 0), places=2,
                        msg=f"{handle}: {column}",
                    )
                else:
                    self.assertEqual(
                        (got[column] or "").strip(), (want[column] or "").strip(),
                        f"{handle}: {column}",
                    )

if __name__ == "__main__":
    unittest.main()
