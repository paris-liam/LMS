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
)


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


if __name__ == "__main__":
    unittest.main()
