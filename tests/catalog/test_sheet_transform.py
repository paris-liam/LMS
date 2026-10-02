import unittest

from catalog.client_sheet.transform import FILL_COLUMNS, fill_rows_to_import_rows, fill_rows_to_libib_rows
from catalog.core.columns import GENRE_METAFIELD, TEMPLATE_COLUMNS
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

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
    "Barcode": "07530234",
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
    "Barcode": "",
}


class TestFillColumns(unittest.TestCase):
    def test_eleven_columns_in_order(self):
        self.assertEqual(FILL_COLUMNS, [
            "Title", "Format", "Type", "Genre 1", "Genre 2", "Genre 3",
            "Price", "Description", "Image URL", "Extra tags", "Barcode",
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
        # Type only: format lives in Vendor, genre in the metafield.
        self.assertEqual(out["Tags"], "Rental")
        self.assertEqual(out["Image Alt Text"], "Rushmore poster")
        self.assertEqual(out[GENRE_METAFIELD], "comedy")

    def test_floor_sale_row_multi_genre_and_extra_tag(self):
        out = fill_rows_to_import_rows([FLOOR_SALE])[0]
        self.assertEqual(out["Handle"], "little-shop-of-horrors-blu-ray-floor-sale")
        self.assertEqual(out["Variant Price"], "19.99")
        self.assertEqual(out["Tags"], "Floor Sale, Criterion Collection")
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

    def test_barcode_never_reaches_the_shopify_import(self):
        out = fill_rows_to_import_rows([RENTAL])[0]
        self.assertNotIn("07530234", out.values())


class TestLibibTransform(unittest.TestCase):
    def test_rental_with_barcode_becomes_one_libib_row(self):
        rows = fill_rows_to_libib_rows([RENTAL])
        self.assertEqual(len(rows), 1)
        out = rows[0]
        self.assertEqual(list(out), LIBIB_MOVIE_COLUMNS)
        self.assertEqual(out["title"], "Rushmore")
        # The barcode is the call number: it is how every Libib command finds
        # the copy again. Leading zero kept.
        self.assertEqual(out["call_number"], "07530234")
        self.assertEqual(out["tags"], "VHS, comedy")
        self.assertEqual(out["price"], "0")
        self.assertEqual(out["copies"], "1")
        self.assertEqual(out["upc_isbn10"], "")

    def test_floor_sales_and_rentals_without_barcode_are_left_out(self):
        no_barcode = dict(RENTAL, Barcode="")
        sale_with_barcode = dict(FLOOR_SALE, Barcode="12345678")
        self.assertEqual(fill_rows_to_libib_rows([no_barcode, sale_with_barcode]), [])

    def test_multi_genre_tags_match_the_sync(self):
        row = dict(RENTAL, **{"Genre 2": "Horror"})
        self.assertEqual(fill_rows_to_libib_rows([row])[0]["tags"], "VHS, comedy; horror")

    def test_description_is_optional_and_whitespace_collapsed(self):
        blank = fill_rows_to_libib_rows([dict(RENTAL, Description="")])[0]
        self.assertEqual(blank["description"], "")
        messy = fill_rows_to_libib_rows([dict(RENTAL, Description="  Two\n\nlines  ")])[0]
        self.assertEqual(messy["description"], "Two lines")

    def test_libib_row_matches_what_libib_sync_would_import(self):
        """A hand-imported copy must look like a synced one, or the next
        `libib sync` reports drift on it."""
        from catalog.libib.columns import import_row
        shopify = fill_rows_to_import_rows([RENTAL])[0]
        shopify["Variant Barcode"] = "07530234"
        self.assertEqual(fill_rows_to_libib_rows([RENTAL])[0], import_row(shopify))




if __name__ == "__main__":
    unittest.main()
