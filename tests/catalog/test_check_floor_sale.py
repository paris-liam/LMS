import contextlib
import csv
import io
import os
import tempfile
import unittest
from datetime import date

from catalog.cli import main
from catalog.client_sheet.check import check, detect_shape
from catalog.client_sheet.floor_sale import FLOOR_SALE_FILL_HEADER, floor_sale_rows_to_import_rows
from catalog.core.columns import FLOOR_SALE_TEMPLATE_COLUMNS, GENRE_METAFIELD

FILL = [
    {"Title": "Speed", "Format": "DVD", "Genre": "Action", "Price": "8", "Extra tags": ""},
    {"Title": "Speed", "Format": "DVD", "Genre": "Action", "Price": "8", "Extra tags": ""},
    {"Title": "Heat", "Format": "Blu-Ray", "Genre": "Thriller", "Price": "12.50",
     "Extra tags": "Criterion Collection"},
]
BATCH = date(2026, 10, 8)


def _write(rows, columns):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    handle.close()
    return handle.name


def _import_rows():
    return floor_sale_rows_to_import_rows([dict(r) for r in FILL], BATCH)


def _fill_rows(batch_date="2026-10-08"):
    rows = [dict(r, **{"": "", "Batch date": ""}) for r in FILL]
    rows[0]["Batch date"] = batch_date
    return rows


class _Case(unittest.TestCase):
    def _problems(self, rows, columns):
        path = _write(rows, columns)
        self.addCleanup(os.unlink, path)
        return check(path)

    def errors(self, rows, columns=FLOOR_SALE_TEMPLATE_COLUMNS):
        return [p.message for p in self._problems(rows, columns)[2] if not p.warning]

    def assertFlags(self, text, rows, columns=FLOOR_SALE_TEMPLATE_COLUMNS):
        messages = self.errors(rows, columns)
        self.assertTrue(any(text in m for m in messages), f"{text!r} not in {messages}")


class TestShapes(unittest.TestCase):
    def test_recognises_both_floor_sale_shapes(self):
        self.assertEqual(detect_shape(FLOOR_SALE_FILL_HEADER), "floor-sale-fill")
        self.assertEqual(detect_shape(FLOOR_SALE_TEMPLATE_COLUMNS), "floor-sale-import")

    def test_trailing_blank_header_cells_are_ignored(self):
        self.assertEqual(detect_shape(FLOOR_SALE_FILL_HEADER + ["", ""]), "floor-sale-fill")

    def test_near_miss_names_the_difference(self):
        with self.assertRaises(ValueError) as caught:
            detect_shape([c for c in FLOOR_SALE_TEMPLATE_COLUMNS if c != "Variant Taxable"])
        self.assertIn("floor-sale-import", str(caught.exception))
        self.assertIn("Variant Taxable", str(caught.exception))


class TestCleanFiles(_Case):
    def test_transform_output_is_clean(self):
        shape, rows, problems = self._problems(_import_rows(), FLOOR_SALE_TEMPLATE_COLUMNS)
        self.assertEqual(shape, "floor-sale-import")
        self.assertEqual(len(rows), 3)
        self.assertEqual(problems, [])

    def test_fill_tab_is_clean(self):
        shape, _, problems = self._problems(_fill_rows(), FLOOR_SALE_FILL_HEADER)
        self.assertEqual(shape, "floor-sale-fill")
        self.assertEqual(problems, [])

    def test_a_date_only_row_is_not_a_blank_movie(self):
        rows = [{"Title": "", "Format": "", "Genre": "", "Price": "", "Extra tags": "", "": "",
                 "Batch date": "2026-10-08"}] + _fill_rows("")
        self.assertEqual(self.errors(rows, FLOOR_SALE_FILL_HEADER), [])


class TestFillTab(_Case):
    def _flags(self, text, **changes):
        rows = _fill_rows()
        rows[1].update(changes)
        self.assertFlags(text, rows, FLOOR_SALE_FILL_HEADER)

    def test_missing_or_unreadable_batch_date(self):
        self.assertFlags("no batch date", _fill_rows(""), FLOOR_SALE_FILL_HEADER)
        self.assertFlags("no batch date", _fill_rows("next tuesday"), FLOOR_SALE_FILL_HEADER)

    def test_required_cells(self):
        self._flags("no Title", Title="")
        self._flags("no Format", Format="")
        self._flags("no Genre", Genre="")

    def test_unknown_format_and_genre(self):
        self._flags("format 'Cassette' is not recognised", Format="Cassette")
        self._flags("genre 'Westerns' is not one of the", Genre="Westerns")

    def test_price_must_be_a_positive_number(self):
        self._flags("no price", Price="")
        self._flags("is not a number", Price="eight")
        self._flags("price must be more than 0", Price="0")
        self._flags("price must be more than 0", Price="-3")

    def test_a_type_tag_in_extra_tags(self):
        self._flags("'Rental' in Extra tags", **{"Extra tags": "Rental"})


class TestImportTab(_Case):
    def _flags(self, text, **changes):
        rows = _import_rows()
        rows[1].update(changes)
        self.assertFlags(text, rows)

    def test_required_cells(self):
        self._flags("no Title", Title="")
        self._flags("no format in Vendor", Vendor="")
        self._flags("no genre", **{"Option1 Value": "", GENRE_METAFIELD: ""})

    def test_unknown_format_and_genre(self):
        self._flags("Vendor 'Criterion' is not a media format", Vendor="Criterion")
        self._flags("genre 'Westerns' is not one of the", **{"Option1 Value": "Westerns"})

    def test_genre_that_produced_no_handle(self):
        """The 2026-09-11 bug: a blank metafield beside a real genre imports silently."""
        self._flags("produced no genre handle", **{GENRE_METAFIELD: ""})

    def test_genre_handle_disagreeing_with_the_label(self):
        self._flags("does not match genre", **{GENRE_METAFIELD: "comedy"})

    def test_price(self):
        self._flags("no price", **{"Variant Price": ""})
        self._flags("is not a number", **{"Variant Price": "abc"})
        self._flags("price must be more than 0", **{"Variant Price": "0"})

    def test_must_stay_off_the_website_but_active(self):
        self._flags("published to the online store", Published="TRUE")
        self._flags("published to the online store", Published="")
        self._flags("Status 'Draft' is not Active", Status="Draft")

    def test_taxable_quantity_and_tracking(self):
        self._flags("not taxable", **{"Variant Taxable": "FALSE"})
        self._flags("quantity '2' is not 1", **{"Variant Inventory Qty": "2"})
        self._flags("inventory not tracked", **{"Variant Inventory Tracker": ""})

    def test_tags(self):
        self._flags("missing the Floor Sale tag", Tags="Criterion Collection")
        self._flags("tagged Rental", Tags="Floor Sale, Rental")

    def test_handle_must_carry_a_batch_date(self):
        self._flags("has no batch date", Handle="speed-dvd-floor-sale-3")
        self._flags("has no batch date", Handle="ERROR: type the batch date in 'Add floor sale'!G2")

    def test_duplicate_handle(self):
        rows = _import_rows()
        rows[2]["Handle"] = rows[0]["Handle"]
        self.assertFlags("already used on row 2", rows)


class TestCli(unittest.TestCase):
    def test_exit_codes(self):
        good = _write(_import_rows(), FLOOR_SALE_TEMPLATE_COLUMNS)
        bad_rows = _import_rows()
        bad_rows[0]["Published"] = "TRUE"
        bad = _write(bad_rows, FLOOR_SALE_TEMPLATE_COLUMNS)
        for path in (good, bad):
            self.addCleanup(os.unlink, path)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["check-upload", good]), 0)
            self.assertEqual(main(["check-upload", bad]), 1)


if __name__ == "__main__":
    unittest.main()
