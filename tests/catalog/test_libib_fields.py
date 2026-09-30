import unittest

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS, import_row, ready_row
from catalog.libib.fields import (
    expected_description, expected_tags_string, expected_title, is_complete, is_rental, missing_fields,
    missing_wanted, normalized_tag_set,
)


def rental(**overrides):
    base = {"Handle": "jaws-vhs-rental", "Title": "  Jaws ", "Body (HTML)": "<p>A  shark.</p>\n",
            "Image Src": "https://cdn/j.jpg", "Variant Barcode": "01577790", "Variant Price": "0.00",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", GENRE_METAFIELD: "horror; thriller"}
    base.update(overrides)
    return base


class TestFields(unittest.TestCase):
    def test_is_rental(self):
        self.assertTrue(is_rental(rental()))
        self.assertTrue(is_rental(rental(Tags="rental, VHS")))  # alias spelling still a rental
        self.assertFalse(is_rental(rental(Tags="Floor Sale, VHS")))
        self.assertFalse(is_rental(rental(Tags="Rental, Floor Sale")))  # type conflict: not in scope
        self.assertFalse(is_rental(rental(Tags="VHS")))

    def test_complete_and_missing(self):
        self.assertTrue(is_complete(rental()))
        self.assertEqual(missing_fields(rental(**{GENRE_METAFIELD: "", "Body (HTML)": ""})), ["description", "genre"])

    def test_poster_is_wanted_not_required(self):
        imageless = rental(**{"Image Src": ""})
        self.assertTrue(is_complete(imageless))
        self.assertEqual(missing_fields(imageless), [])
        self.assertEqual(missing_wanted(imageless), ["poster"])
        self.assertEqual(missing_wanted(rental()), [])

    def test_expected_values(self):
        self.assertEqual(expected_title(rental()), "Jaws")
        self.assertEqual(expected_description(rental()), "A shark.")
        self.assertEqual(expected_tags_string(rental()), "VHS, horror; thriller")

    def test_normalized_tag_set_matches_libib_reformatting(self):
        self.assertEqual(normalized_tag_set("VHS, Horror"), normalized_tag_set("horror,vhs"))
        self.assertEqual(normalized_tag_set(""), set())

    def test_multi_genre_semicolons_split_like_libib_does(self):
        # Libib splits the genre metafield's "comedy; sci-fi" into two tags on import.
        self.assertEqual(normalized_tag_set("VHS, comedy; sci-fi"), normalized_tag_set("comedy, sci-fi, vhs"))


class TestColumns(unittest.TestCase):
    def test_import_row(self):
        out = import_row(rental())
        self.assertEqual(list(out), LIBIB_MOVIE_COLUMNS)
        self.assertEqual((out["title"], out["description"], out["tags"], out["price"], out["copies"], out["call_number"]),
                         ("Jaws", "A shark.", "VHS, horror; thriller", "0.00", "1", "01577790"))
        self.assertEqual(out["upc_isbn10"], "")

    def test_ready_row(self):
        out = ready_row(rental(), "libib-sync/batch-0001/01577790.jpg")
        self.assertEqual(list(out), READY_COLUMNS)
        self.assertEqual(out["image_path"], "libib-sync/batch-0001/01577790.jpg")


if __name__ == "__main__":
    unittest.main()
