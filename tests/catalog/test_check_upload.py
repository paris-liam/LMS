import contextlib
import csv
import io
import os
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

from catalog.cli import main  # noqa: E402
from catalog.client_sheet.check import check, detect_shape  # noqa: E402
from catalog.client_sheet.transform import FILL_COLUMNS  # noqa: E402
from catalog.core.columns import GENRE_METAFIELD, TEMPLATE_COLUMNS  # noqa: E402
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS  # noqa: E402

TEMPLATE_DIR = os.path.join(ROOT, "catalog", "client_sheet", "template")
GOOD_IMPORT = os.path.join(TEMPLATE_DIR, "sheet-export.csv")
GOOD_FILL = os.path.join(TEMPLATE_DIR, "sheet-export-input.csv")
GOOD_LIBIB = os.path.join(TEMPLATE_DIR, "client-upload-template.libib-expected.csv")


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
    return [p.message for p in problems if not p.warning]


def _warnings(path):
    _, _, problems = check(path)
    return [p.message for p in problems if p.warning]


class TestShapeDetection(unittest.TestCase):
    def test_recognises_all_three_shapes(self):
        self.assertEqual(detect_shape(FILL_COLUMNS), "fill")
        self.assertEqual(detect_shape(TEMPLATE_COLUMNS), "import")
        self.assertEqual(detect_shape(LIBIB_MOVIE_COLUMNS), "libib")

    def test_names_what_differs_on_a_near_miss(self):
        with self.assertRaises(ValueError) as caught:
            detect_shape([c for c in TEMPLATE_COLUMNS if c != "Vendor"])
        self.assertIn("missing", str(caught.exception))
        self.assertIn("Vendor", str(caught.exception))

    def test_rejects_an_unrelated_header(self):
        with self.assertRaises(ValueError) as caught:
            detect_shape(["Title", "Nonsense"])
        self.assertIn("none of", str(caught.exception))


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

    def test_libib_fixture_has_no_problems(self):
        shape, rows, problems = check(GOOD_LIBIB)
        self.assertEqual(shape, "libib")
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 1)


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
            any("is not one of the" in m for m in _messages(path)),
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

    def test_flags_a_floor_sale_published_to_the_online_store(self):
        rows = _read(GOOD_IMPORT)
        sale = next(r for r in rows if "Floor Sale" in r["Tags"])
        sale["Published"] = "TRUE"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("Floor Sale published" in m for m in _messages(path)))

    def test_flags_a_floor_sale_with_published_left_blank(self):
        # Shopify publishes a blank to the online store, so blank is not safe.
        rows = _read(GOOD_IMPORT)
        sale = next(r for r in rows if "Floor Sale" in r["Tags"])
        sale["Published"] = ""
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("Floor Sale published" in m for m in _messages(path)))

    def test_flags_a_rental_kept_off_the_online_store(self):
        rows = _read(GOOD_IMPORT)
        rental = next(r for r in rows if "Rental" in r["Tags"])
        rental["Published"] = "FALSE"
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("Rental not published" in m for m in _messages(path)))

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


class TestDescriptionAndImageAreOptional(unittest.TestCase):
    """Decided 2026-10-01: a client upload may leave both blank; the catalogue
    fill adds them later."""

    def test_fill_row_without_description_or_image_is_clean(self):
        rows = _read(GOOD_FILL)
        rows[0]["Description"] = ""
        rows[0]["Image URL"] = ""
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertEqual(_messages(path), [])

    def test_import_row_without_image_is_clean(self):
        rows = _read(GOOD_IMPORT)
        rows[0]["Image Src"] = ""
        rows[0]["Image Alt Text"] = ""
        path = _write(rows, TEMPLATE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertEqual(_messages(path), [])


class TestFillBarcodes(unittest.TestCase):
    def test_rental_without_barcode_is_only_a_warning(self):
        rows = _read(GOOD_FILL)
        rental = next(r for r in rows if r["Type"] == "Rental")
        rental["Barcode"] = ""
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertEqual(_messages(path), [])
        self.assertTrue(any("not on the Libib import tab" in m for m in _warnings(path)))

    def test_flags_a_barcode_that_lost_its_leading_zero(self):
        rows = _read(GOOD_FILL)
        rows[0]["Barcode"] = "7530234"
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("is not 8 digits" in m for m in _messages(path)))

    def test_flags_a_barcode_used_twice(self):
        rows = _read(GOOD_FILL)
        rentals = [r for r in rows if r["Type"] == "Rental"]
        rentals[1]["Barcode"] = rentals[0]["Barcode"]
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("barcode" in m and "already used" in m for m in _messages(path)))


class TestLibibTab(unittest.TestCase):
    def _check(self, **changes):
        rows = _read(GOOD_LIBIB)
        rows[0].update(changes)
        path = _write(rows, LIBIB_MOVIE_COLUMNS)
        self.addCleanup(os.unlink, path)
        return path

    def test_flags_a_missing_call_number(self):
        self.assertTrue(any("no call number" in m for m in _messages(self._check(call_number=""))))

    def test_flags_a_short_call_number(self):
        path = self._check(call_number="7530234")
        self.assertTrue(any("is not 8 digits" in m for m in _messages(path)))

    def test_flags_a_repeated_call_number(self):
        rows = _read(GOOD_LIBIB)
        rows.append(dict(rows[0]))
        path = _write(rows, LIBIB_MOVIE_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertTrue(any("call number" in m and "already used" in m for m in _messages(path)))

    def test_flags_tags_without_a_format(self):
        path = self._check(tags="comedy")
        self.assertTrue(any("do not start with a media format" in m for m in _messages(path)))

    def test_flags_an_unknown_genre_handle(self):
        path = self._check(tags="VHS, not-a-genre")
        self.assertTrue(any("is not a real genre" in m for m in _messages(path)))

    def test_no_genre_is_a_warning(self):
        path = self._check(tags="VHS")
        self.assertEqual(_messages(path), [])
        self.assertTrue(any("no genre" in m for m in _warnings(path)))

    def test_flags_a_price_or_extra_copies(self):
        self.assertTrue(any("is not 0" in m for m in _messages(self._check(price="4.99"))))
        self.assertTrue(any("is not 1" in m for m in _messages(self._check(copies="2"))))

    def test_a_blank_description_is_fine(self):
        self.assertEqual(_messages(self._check(description="")), [])


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


class TestCli(unittest.TestCase):
    def run_cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["check-upload", *argv])

    def test_cli_exit_codes(self):
        self.assertEqual(self.run_cli(GOOD_IMPORT), 0)
        bad = _read(GOOD_IMPORT)
        bad[0]["Variant Price"] = "abc"
        self.assertEqual(self.run_cli(_write(bad, TEMPLATE_COLUMNS)), 1)
        self.assertEqual(self.run_cli(os.path.join(TEMPLATE_DIR, "no-such-file.csv")), 2)

    def test_warnings_alone_exit_zero(self):
        rows = _read(GOOD_FILL)
        for row in rows:
            row["Barcode"] = ""
        path = _write(rows, FILL_COLUMNS)
        self.addCleanup(os.unlink, path)
        self.assertEqual(self.run_cli(path), 0)

    def test_a_google_sheets_bom_download_is_accepted(self):
        with open(GOOD_IMPORT, encoding="utf-8") as handle:
            body = handle.read()
        path = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        path.write("\ufeff" + body)
        path.close()
        self.addCleanup(os.unlink, path.name)
        self.assertEqual(self.run_cli(path.name), 0)


if __name__ == "__main__":
    unittest.main()
