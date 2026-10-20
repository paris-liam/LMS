import unittest
from datetime import date

from catalog.client_sheet.floor_sale import (
    FLOOR_SALE_FILL_COLUMNS, FLOOR_SALE_FILL_HEADER, floor_sale_rows_to_import_rows, parse_batch_date,
    split_fill_tab,
)
from catalog.core.columns import FLOOR_SALE_TEMPLATE_COLUMNS, GENRE_METAFIELD

BATCH = date(2026, 10, 8)

SPEED = {
    "Title": "Speed",
    "Format": "DVD",
    "Genre": "Action",
    "Price": "8",
    "Extra tags": "",
}


class TestFillColumns(unittest.TestCase):
    def test_five_data_columns_in_order(self):
        self.assertEqual(FLOOR_SALE_FILL_COLUMNS, ["Title", "Format", "Genre", "Price", "Extra tags"])

    def test_batch_date_sits_in_column_g(self):
        self.assertEqual(FLOOR_SALE_FILL_HEADER.index("Batch date"), 6)


class TestTransform(unittest.TestCase):
    def test_emits_exactly_the_floor_sale_columns(self):
        out = floor_sale_rows_to_import_rows([SPEED], BATCH)[0]
        self.assertEqual(list(out), FLOOR_SALE_TEMPLATE_COLUMNS)

    def test_row(self):
        out = floor_sale_rows_to_import_rows([SPEED], BATCH)[0]
        self.assertEqual(out, {
            "Handle": "speed-dvd-floor-sale-20261008",
            "Title": "Speed",
            "Vendor": "DVD",
            "Product Category": "Media > Videos",
            "Tags": "Floor Sale",
            "Status": "Active",
            "Published": "FALSE",
            "Option1 Name": "Genre",
            "Option1 Value": "Action",
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": "1",
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": "8",
            "Variant Taxable": "TRUE",
            GENRE_METAFIELD: "action",
        })

    def test_extra_tags_follow_floor_sale(self):
        row = dict(SPEED, **{"Extra tags": " Criterion Collection ,  Rare Finds,"})
        out = floor_sale_rows_to_import_rows([row], BATCH)[0]
        self.assertEqual(out["Tags"], "Floor Sale, Criterion Collection, Rare Finds")

    def test_title_and_cells_are_trimmed(self):
        row = dict(SPEED, Title="  Speed ", Format=" DVD", Price=" 8 ")
        out = floor_sale_rows_to_import_rows([row], BATCH)[0]
        self.assertEqual(out["Title"], "Speed")
        self.assertEqual(out["Handle"], "speed-dvd-floor-sale-20261008")
        self.assertEqual(out["Variant Price"], "8")

    def test_copies_in_one_batch_get_counted_handles(self):
        rows = floor_sale_rows_to_import_rows([SPEED, dict(SPEED), dict(SPEED, Format="VHS"), dict(SPEED)], BATCH)
        self.assertEqual([r["Handle"] for r in rows], [
            "speed-dvd-floor-sale-20261008",
            "speed-dvd-floor-sale-20261008-2",
            "speed-vhs-floor-sale-20261008",
            "speed-dvd-floor-sale-20261008-3",
        ])

    def test_unknown_genre_leaves_the_metafield_blank_like_the_sheet(self):
        """The sheet's VLOOKUP returns "" through IFERROR; check-upload catches it."""
        out = floor_sale_rows_to_import_rows([dict(SPEED, Genre="Westerns")], BATCH)[0]
        self.assertEqual(out["Option1 Value"], "Westerns")
        self.assertEqual(out[GENRE_METAFIELD], "")


class TestBatchDate(unittest.TestCase):
    def test_reads_iso_and_us_dates(self):
        self.assertEqual(parse_batch_date("2026-10-08"), BATCH)
        self.assertEqual(parse_batch_date(" 10/8/2026 "), BATCH)

    def test_blank_or_junk_is_none(self):
        for text in ("", "  ", "tomorrow", "2026-13-01", None):
            self.assertIsNone(parse_batch_date(text), text)

    def test_split_fill_tab_reads_g2_and_drops_blank_rows(self):
        rows = [
            dict(SPEED, **{"": "", "Batch date": "2026-10-08"}),
            {"Title": "", "Format": "", "Genre": "", "Price": "", "Extra tags": "", "": "", "Batch date": ""},
            dict(SPEED, Title="Heat", **{"": "", "Batch date": ""}),
        ]
        filled, batch_date = split_fill_tab(rows)
        self.assertEqual(batch_date, BATCH)
        self.assertEqual([r["Title"] for r in filled], ["Speed", "Heat"])
        self.assertEqual(list(filled[0]), FLOOR_SALE_FILL_COLUMNS)

    def test_split_fill_tab_with_only_a_date(self):
        rows = [{"Title": "", "Format": "", "Genre": "", "Price": "", "Extra tags": "", "": "",
                 "Batch date": "2026-10-08"}]
        self.assertEqual(split_fill_tab(rows), ([], BATCH))


if __name__ == "__main__":
    unittest.main()
