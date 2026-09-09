import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "formatting-scripts"))

from columns import FORMATTED_TAG, GENRE_METAFIELD, TEMPLATE_COLUMNS
from normalize import normalize_rows
from sheet_transform import FILL_COLUMNS, fill_rows_to_import_rows

RENTAL = {
    "Title": "Rushmore",
    "Format": "VHS",
    "Type": "Rental",
    "Genre 1": "Comedy",
    "Genre 2": "",
    "Genre 3": "",
    "Price": "",
    "Description": "A precocious student falls for a teacher at Rushmore Academy.",
    "Image URL": "https://example.com/posters/rushmore.jpg",
    "Extra tags": "",
}

FLOOR_SALE = {
    "Title": "Little Shop of Horrors",
    "Format": "Blu-Ray",
    "Type": "Floor Sale",
    "Genre 1": "Musical",
    "Genre 2": "Comedy",
    "Genre 3": "Horror",
    "Price": "19.99",
    "Description": "A flower-shop worker discovers a blood-hungry plant.",
    "Image URL": "",
    "Extra tags": "Criterion Collection",
}


class TestFillColumns(unittest.TestCase):
    def test_ten_columns_in_order(self):
        self.assertEqual(FILL_COLUMNS, [
            "Title", "Format", "Type", "Genre 1", "Genre 2", "Genre 3",
            "Price", "Description", "Image URL", "Extra tags",
        ])


class TestTransform(unittest.TestCase):
    def test_emits_exactly_the_template_columns(self):
        out = fill_rows_to_import_rows([RENTAL])[0]
        self.assertEqual(list(out), TEMPLATE_COLUMNS)

    def test_rental_row(self):
        out = fill_rows_to_import_rows([RENTAL])[0]
        self.assertEqual(out["Handle"], "rushmore-vhs-rental")
        self.assertEqual(out["Vendor"], "VHS")
        self.assertEqual(out["Product Category"], "Media > Videos")
        self.assertEqual(out["Status"], "Active")
        self.assertEqual(out["Option1 Name"], "Genre")
        self.assertEqual(out["Option1 Value"], "Comedy")
        self.assertEqual(out["Variant Inventory Tracker"], "shopify")
        self.assertEqual(out["Variant Inventory Qty"], "1")
        self.assertEqual(out["Variant Inventory Policy"], "deny")
        self.assertEqual(out["Variant Fulfillment Service"], "manual")
        self.assertEqual(out["Variant Price"], "0")
        self.assertEqual(out["Tags"], "Rental, VHS, Comedy")
        self.assertEqual(out["Image Alt Text"], "Rushmore poster")
        self.assertEqual(out[GENRE_METAFIELD], "comedy")

    def test_floor_sale_row_multi_genre_and_extra_tag(self):
        out = fill_rows_to_import_rows([FLOOR_SALE])[0]
        self.assertEqual(out["Handle"], "little-shop-of-horrors-blu-ray-floor-sale")
        self.assertEqual(out["Variant Price"], "19.99")
        self.assertEqual(
            out["Tags"],
            "Floor Sale, Blu-Ray, Musical, Comedy, Horror, Criterion Collection",
        )
        self.assertEqual(out[GENRE_METAFIELD], "musical; comedy; horror")

    def test_blank_image_gives_blank_alt_text(self):
        out = fill_rows_to_import_rows([FLOOR_SALE])[0]
        self.assertEqual(out["Image Src"], "")
        self.assertEqual(out["Image Alt Text"], "")

    def test_repeated_title_and_format_get_suffixed_handles(self):
        rows = fill_rows_to_import_rows([RENTAL, dict(RENTAL), dict(RENTAL)])
        self.assertEqual(
            [r["Handle"] for r in rows],
            ["rushmore-vhs-rental", "rushmore-vhs-rental-2", "rushmore-vhs-rental-3"],
        )

    def test_apostrophes_are_deleted_not_hyphenated(self):
        row = dict(RENTAL, Title="The Monkey's Uncle")
        out = fill_rows_to_import_rows([row])[0]
        self.assertEqual(out["Handle"], "the-monkeys-uncle-vhs-rental")


class TestAgreesWithPipeline(unittest.TestCase):
    """The sheet's output is already canonical, so a pipeline pass over it
    must change nothing except appending the Formatted tag."""

    def test_pipeline_pass_is_a_no_op_apart_from_the_formatted_tag(self):
        sheet_rows = fill_rows_to_import_rows([RENTAL, FLOOR_SALE])
        clean, issues = normalize_rows([dict(r) for r in sheet_rows], "template")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), len(sheet_rows))
        for produced, expected in zip(clean, sheet_rows):
            self.assertEqual(
                produced["Tags"], expected["Tags"] + ", " + FORMATTED_TAG
            )
            for column in TEMPLATE_COLUMNS:
                if column == "Tags":
                    continue
                self.assertEqual(
                    produced[column], expected[column], f"column {column!r} differs"
                )


if __name__ == "__main__":
    unittest.main()
