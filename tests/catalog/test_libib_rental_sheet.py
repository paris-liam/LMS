import csv
import os
import re
import unittest

from catalog.client_sheet.libib_rental import (
    LIBIB_RENTAL_FILL_COLUMNS, check_value, fill_rows_to_libib_rows, libib_tags, row_problems,
)
from catalog.core.taxonomy import FORMATS, GENRES
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS
from catalog.rental_sync.transform import transform

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHEET_DIR = os.path.join(ROOT, "catalog", "client_sheet", "template", "libib-rental")
FILL_CSV = os.path.join(SHEET_DIR, "libib-rental-template.csv")
EXPECTED_CSV = os.path.join(SHEET_DIR, "libib-rental-template.expected.csv")
FORMULAS = os.path.join(SHEET_DIR, "formulas.txt")
SHEET_INPUT_CSV = os.path.join(SHEET_DIR, "sheet-export-input.csv")
SHEET_EXPORT_CSV = os.path.join(SHEET_DIR, "sheet-export.csv")
MAPPINGS_CSV = os.path.join(ROOT, "catalog", "client_sheet", "template", "genre-mappings.csv")

JAWS = {
    "Title": "Jaws", "Format": "VHS", "Genre 1": "Horror", "Genre 2": "", "Genre 3": "",
    "Copies": "", "Description": "", "Extra tags": "",
}


def row(**overrides):
    return dict(JAWS, **{k.replace("_", " "): v for k, v in overrides.items()})


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _header(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


class TestCheck(unittest.TestCase):
    def test_ready_row(self):
        self.assertEqual(row_problems(JAWS), [])
        self.assertEqual(check_value(JAWS), "OK")

    def test_blank_row_shows_nothing(self):
        self.assertEqual(check_value({c: "  " for c in LIBIB_RENTAL_FILL_COLUMNS}), "")

    def test_every_problem_in_order(self):
        bad = {"Title": "", "Format": "Cassette", "Genre 1": "", "Genre 2": "Western",
               "Genre 3": "", "Copies": "1.5", "Description": "", "Extra tags": ""}
        self.assertEqual(check_value(bad), "; ".join([
            "no title", "pick a format", "unknown genre 'Western'",
            "copies must be a whole number",
        ]))

    def test_no_genre(self):
        self.assertEqual(row_problems(row(Genre_1="")), ["pick a genre"])

    def test_format_and_genre_match_any_case(self):
        self.assertEqual(row_problems(row(Format="blu-ray", Genre_1="kids & family")), [])

    def test_copies(self):
        for good in ("", "1", "12"):
            self.assertEqual(row_problems(row(Copies=good)), [], good)
        for bad in ("0", "-1", "two", "01"):
            self.assertEqual(row_problems(row(Copies=bad)), ["copies must be a whole number"], bad)



class TestLibibRow(unittest.TestCase):
    def test_emits_exactly_the_libib_columns(self):
        out = fill_rows_to_libib_rows([JAWS])[0]
        self.assertEqual(list(out), LIBIB_MOVIE_COLUMNS)

    def test_row(self):
        out = fill_rows_to_libib_rows([row(Title="  Jaws \n 2 ", Description=" A  shark. ",
                                           Copies="3")])[0]
        filled = {k: v for k, v in out.items() if v}
        self.assertEqual(filled, {
            "title": "Jaws 2", "description": "A shark.", "tags": "vhs, horror", "copies": "3",
        })

    def test_lookup_and_join_columns_stay_blank(self):
        """No UPC/EAN (no Libib lookup), no Call # (the sync app joins on Libib's barcode)."""
        out = fill_rows_to_libib_rows([row(Copies="2")])[0]
        for column in ("upc_isbn10", "ean_isbn13", "call_number", "price"):
            self.assertEqual(out[column], "", column)

    def test_held_back_rows_are_left_out(self):
        out = fill_rows_to_libib_rows([row(Genre_1=""), JAWS, {c: "" for c in LIBIB_RENTAL_FILL_COLUMNS}])
        self.assertEqual([r["title"] for r in out], ["Jaws"])

    def test_tags_lowercase_slugged_and_deduped(self):
        r = row(Format="Blu-Ray", Genre_1="Kids & Family", Genre_2="Horror", Genre_3="Kids & Family",
                Extra_tags=" Criterion Collection ,, Horror, Rare Finds,")
        self.assertEqual(libib_tags(r), "blu-ray, kids-family, horror, criterion collection, rare finds")

    def test_every_ready_row_passes_the_sync_app(self):
        """Each format x genre the sheet can produce is accepted by the rental
        sync app (catalog/rental_sync/transform.py) without being set aside."""
        rows = [row(Format=f, Genre_1=g, Extra_tags="Criterion Collection")
                for f in FORMATS for g in GENRES]
        for out in fill_rows_to_libib_rows(rows):
            result = transform({"barcode": "2010000000014", "title": out["title"],
                                "tags": out["tags"], "description": "x", "created": ""})
            self.assertEqual(result["set_aside"], [], out["tags"])
            self.assertEqual(result["extra_tags"], ["criterion collection"])


class TestTemplateFiles(unittest.TestCase):
    def test_fill_csv_is_the_fill_tab_shape(self):
        self.assertEqual(_header(FILL_CSV), LIBIB_RENTAL_FILL_COLUMNS)

    def test_scaffold_shows_a_held_back_row(self):
        self.assertIn("pick a genre", [check_value(r) for r in _read(FILL_CSV)])

    def test_expected_csv_is_what_the_transform_produces(self):
        self.assertEqual(_header(EXPECTED_CSV), LIBIB_MOVIE_COLUMNS)
        self.assertEqual(_read(EXPECTED_CSV), fill_rows_to_libib_rows(_read(FILL_CSV)))

    def test_mappings_cover_every_genre(self):
        with open(MAPPINGS_CSV, newline="", encoding="utf-8") as handle:
            self.assertEqual(dict(csv.reader(handle)), GENRES)


class TestFormulas(unittest.TestCase):
    def setUp(self):
        with open(FORMULAS, encoding="utf-8") as handle:
            self.text = handle.read()

    def test_header_literal_matches_libib_columns(self):
        literal = re.search(r"header,\s*\{(.*?)\}", self.text).group(1)
        self.assertEqual(re.findall(r'"([^"]*)"', literal), LIBIB_MOVIE_COLUMNS)

    def test_body_is_as_wide_as_the_header(self):
        body = re.search(r"body,\s*HSTACK\((.*?)\),\n", self.text).group(1)
        self.assertEqual(len([p for p in body.split(",") if p.strip()]), len(LIBIB_MOVIE_COLUMNS))

    def test_check_formula_lists_every_format(self):
        literal = re.search(r"MATCH\(fmt, \{(.*?)\}", self.text).group(1)
        self.assertEqual(re.findall(r'"([^"]*)"', literal), FORMATS)

    def test_check_messages_match_the_python_mirror(self):
        for message in ("no title", "pick a format", "pick a genre", "unknown genre '",
                        "copies must be a whole number"):
            self.assertIn(f'"{message}', self.text)

    def test_source_range_is_as_wide_as_the_fill_tab(self):
        self.assertIn("'Add rentals'!A2:H", self.text)
        self.assertIn("BYROW(A2:H,", self.text)
        self.assertEqual(len(LIBIB_RENTAL_FILL_COLUMNS), ord("H") - ord("A") + 1)



class TestSheetExportSeam(unittest.TestCase):
    """The live sheet's own output against the tested Python mirror.

    Both files are Google Sheets downloads (captured 2026-10-19):
    sheet-export-input.csv is the `Add rentals` tab including its Check
    column, sheet-export.csv what the `Libib import` formula emitted for it.
    They're the only fixtures here the repo didn't generate, so the only ones
    that can disagree with the code. Re-capture both after any formula change.
    A failure means formulas.txt has drifted from libib_rental.py — fix the
    formula, since the Python side is the tested one.
    """

    def test_input_header_is_the_fill_tab_plus_check(self):
        self.assertEqual(_header(SHEET_INPUT_CSV), LIBIB_RENTAL_FILL_COLUMNS + ["Check"])

    def test_export_header_matches_libib_columns(self):
        self.assertEqual(_header(SHEET_EXPORT_CSV), LIBIB_MOVIE_COLUMNS)

    def test_check_column_agrees_with_the_python_mirror(self):
        for sheet_row in _read(SHEET_INPUT_CSV):
            self.assertEqual(sheet_row["Check"], check_value(sheet_row), sheet_row["Title"])

    def test_import_tab_agrees_with_the_python_mirror(self):
        self.assertEqual(_read(SHEET_EXPORT_CSV), fill_rows_to_libib_rows(_read(SHEET_INPUT_CSV)))


if __name__ == "__main__":
    unittest.main()
