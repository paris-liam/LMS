import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from circaos_reformat import (
    TAG_TO_ADD,
    has_genre_tag,
    extract_genre_from_tags,
    format_from_barcode,
    resolve_circaos_format,
    build_tags,
    classify_circaos_row,
    build_product_handles,
    transform_circaos_group,
)
from reformat_movies import GENRE_COLUMN, FORMAT_COLUMN, FIXED_VENDOR, FIXED_CATEGORY


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Vendor": "VHS",
        "Product Category": "Uncategorized",
        "Type": "",
        "Tags": "Rental, Thriller",
        "Option1 Name": "Condition",
        "Option1 Value": "Standard",
        "Option2 Name": "Serial Number",
        "Option2 Value": "001A",
        "Variant SKU": "191-VHSSOM-001A",
        "Variant Barcode": "191-VHSSOM-001A",
        "Image Src": "https://img/1.jpg",
        "Image Position": "1",
        "Genre (product.metafields.shopify.genre)": "",
    }
    row.update(overrides)
    return row


class TestHasGenreTag(unittest.TestCase):
    def test_true_when_genre_tag_present(self):
        self.assertTrue(has_genre_tag("Rental, Thriller"))

    def test_false_when_only_status_tags(self):
        self.assertFalse(has_genre_tag("Rental, Floor Sale"))

    def test_false_when_no_tags(self):
        self.assertFalse(has_genre_tag(""))


class TestExtractGenreFromTags(unittest.TestCase):
    def test_extracts_plain_genre_tag(self):
        self.assertEqual(extract_genre_from_tags("Rental, Thriller"), "thriller")

    def test_returns_none_when_no_genre_tag(self):
        self.assertIsNone(extract_genre_from_tags("Rental, Floor Sale"))

    def test_skips_null_genre_tag_for_a_later_real_one(self):
        self.assertEqual(extract_genre_from_tags("Special Interest, Comedy"), "comedy")


class TestFormatFromBarcode(unittest.TestCase):
    def test_vhs_prefix(self):
        self.assertEqual(format_from_barcode("191-VHSSCP-001A"), "vhs")

    def test_dvd_prefix(self):
        self.assertEqual(format_from_barcode("191-DVDROY-002A"), "dvd")

    def test_blu_ray_prefix(self):
        self.assertEqual(format_from_barcode("191-BLRSPE-50-001A"), "blu-ray")

    def test_4k_prefix(self):
        self.assertEqual(format_from_barcode("191-4K2MOR-50-001A"), "4-k")

    def test_no_191_prefix_returns_none(self):
        self.assertIsNone(format_from_barcode("88302842"))

    def test_unknown_code_returns_none(self):
        self.assertIsNone(format_from_barcode("191-WLTABC-001A"))


class TestResolveCircaosFormat(unittest.TestCase):
    def test_barcode_takes_priority_over_vendor(self):
        self.assertEqual(
            resolve_circaos_format("DVD", "Rental", "191-BLRSPE-50-001A"), "blu-ray"
        )

    def test_falls_back_to_tags_4k_override(self):
        self.assertEqual(
            resolve_circaos_format("Blu-Ray", "Rental, 4K", "88302842"), "4-k"
        )

    def test_falls_back_to_vendor(self):
        self.assertEqual(resolve_circaos_format("DVD", "Rental", "88302842"), "dvd")

    def test_returns_none_for_unmapped_vendor_and_no_barcode_match(self):
        self.assertIsNone(resolve_circaos_format("Walt Disney", "Rental", "88302842"))


class TestBuildTags(unittest.TestCase):
    def test_appends_tag_to_existing(self):
        self.assertEqual(build_tags("Rental, Thriller"), "Rental, Thriller, CircaOS Import")

    def test_does_not_duplicate_if_already_present(self):
        self.assertEqual(
            build_tags(f"Rental, {TAG_TO_ADD}"), f"Rental, {TAG_TO_ADD}"
        )


class TestClassifyCircaosRow(unittest.TestCase):
    def test_condition_option_with_genre_tag_is_in_scope(self):
        status, reason = classify_circaos_row(make_row())
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)

    def test_supercycle_plan_is_skipped(self):
        status, reason = classify_circaos_row(make_row(Type="Supercycle Plan"))
        self.assertEqual(status, "skip")

    def test_non_condition_option_is_skipped(self):
        status, reason = classify_circaos_row(
            make_row(**{"Option1 Name": "Genre", "Option1 Value": "Comedy"})
        )
        self.assertEqual(status, "skip")

    def test_no_genre_tag_is_flagged_for_review(self):
        status, reason = classify_circaos_row(make_row(Tags="Rental, Floor Sale"))
        self.assertEqual(status, "review")
        self.assertIn("no genre-like tag", reason)


class TestBuildProductHandles(unittest.TestCase):
    def test_single_real_row_keeps_original_handle(self):
        rows = [make_row()]
        handles = build_product_handles("some-movie", rows, "VHS", "Rental")
        self.assertEqual(handles, ["some-movie"])

    def test_same_format_copies_get_copy_suffix(self):
        rows = [
            make_row(**{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(**{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        handles = build_product_handles("split-same-format", rows, "DVD", "Drama, Rental")
        self.assertEqual(handles, ["split-same-format", "split-same-format-copy-2"])

    def test_different_format_copies_get_format_suffix(self):
        rows = [
            make_row(**{"Variant Barcode": "191-BLRDIF-50-001A"}),
            make_row(**{"Variant Barcode": "191-DVDDIF-001A"}),
        ]
        handles = build_product_handles("split-diff-format", rows, "BLU-RAY", "Action, Rental")
        self.assertEqual(handles, ["split-diff-format-bluray", "split-diff-format-dvd"])


class TestTransformCircaosGroup(unittest.TestCase):
    def test_simple_product_gets_full_transform(self):
        status, products, reason = transform_circaos_group([make_row()])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 1)
        row = products[0][0]
        self.assertEqual(row["Vendor"], FIXED_VENDOR)
        self.assertEqual(row["Product Category"], FIXED_CATEGORY)
        self.assertEqual(row["Option1 Name"], "Title")
        self.assertEqual(row["Option1 Value"], "Default Title")
        self.assertEqual(row["Option2 Name"], "")
        self.assertEqual(row["Option2 Value"], "")
        self.assertEqual(row["Variant SKU"], "")
        self.assertEqual(row["Variant Barcode"], "191-VHSSOM-001A")
        self.assertEqual(row[GENRE_COLUMN], "thriller")
        self.assertEqual(row[FORMAT_COLUMN], "vhs")
        self.assertEqual(row["Tags"], "Rental, Thriller, CircaOS Import")

    def test_split_same_format_produces_two_products(self):
        rows = [
            make_row(Handle="split-same", Vendor="DVD", Tags="Drama, Rental",
                     **{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(Handle="split-same", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        status, products, reason = transform_circaos_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0][0]["Handle"], "split-same")
        self.assertEqual(products[1][0]["Handle"], "split-same-copy-2")
        self.assertEqual(products[0][0][FORMAT_COLUMN], "dvd")
        self.assertEqual(products[1][0][FORMAT_COLUMN], "dvd")

    def test_split_different_format_produces_two_products(self):
        rows = [
            make_row(Handle="split-diff", Vendor="BLU-RAY", Tags="Action, Rental",
                     **{"Variant Barcode": "191-BLRDIF-50-001A"}),
            make_row(Handle="split-diff", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDDIF-001A"}),
        ]
        status, products, reason = transform_circaos_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertEqual(products[0][0]["Handle"], "split-diff-bluray")
        self.assertEqual(products[1][0]["Handle"], "split-diff-dvd")
        self.assertEqual(products[0][0][FORMAT_COLUMN], "blu-ray")
        self.assertEqual(products[1][0][FORMAT_COLUMN], "dvd")

    def test_extra_image_rows_pass_through_on_first_product_only(self):
        primary = make_row(Handle="multi-image-title", Tags="Horror, Rental")
        image_2 = {"Handle": "multi-image-title", "Option1 Value": "", "Image Src": "https://img/b.jpg", "Image Position": "2"}
        image_3 = {"Handle": "multi-image-title", "Option1 Value": "", "Image Src": "https://img/c.jpg", "Image Position": "3"}
        status, products, reason = transform_circaos_group([primary, image_2, image_3])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 1)
        self.assertEqual(len(products[0]), 3)
        self.assertEqual(products[0][1], image_2)
        self.assertEqual(products[0][2], image_3)

    def test_review_group_returns_no_products(self):
        status, products, reason = transform_circaos_group([make_row(Tags="Rental, Floor Sale")])
        self.assertEqual(status, "review")
        self.assertIsNone(products)

    def test_skip_group_returns_no_products(self):
        status, products, reason = transform_circaos_group(
            [make_row(**{"Option1 Name": "Genre", "Option1 Value": "Comedy"})]
        )
        self.assertEqual(status, "skip")
        self.assertIsNone(products)


if __name__ == "__main__":
    unittest.main()
