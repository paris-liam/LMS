import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from resolve import (
    extra_tags,
    resolve_format,
    resolve_genres,
    resolve_price,
    resolve_type,
    split_list,
)


class TestSplitList(unittest.TestCase):
    def test_splits_on_commas_and_trims(self):
        self.assertEqual(split_list("Rental, VHS,  Comedy "), ["Rental", "VHS", "Comedy"])

    def test_drops_empties(self):
        self.assertEqual(split_list("Rental,,VHS"), ["Rental", "VHS"])
        self.assertEqual(split_list(""), [])


class TestResolveType(unittest.TestCase):
    def test_finds_the_type_tag(self):
        self.assertEqual(resolve_type(["Rental", "VHS", "Comedy"]), ("Rental", None))
        self.assertEqual(resolve_type(["Floorsale", "DVD"]), ("Floor Sale", None))

    def test_no_type_tag_is_flagged_never_guessed_from_price(self):
        value, reason = resolve_type(["VHS", "Comedy"])
        self.assertIsNone(value)
        self.assertIn("no Rental or Floor Sale tag", reason)

    def test_both_types_is_flagged(self):
        value, reason = resolve_type(["Rental", "Floor Sale", "VHS"])
        self.assertIsNone(value)
        self.assertIn("both", reason)


class TestResolveGenres(unittest.TestCase):
    def test_prefers_option1_value(self):
        self.assertEqual(resolve_genres("Comedy", ["Rental", "Drama"], []), (["Comedy"], None))

    def test_compound_option1_keeps_only_the_genre_part(self):
        self.assertEqual(resolve_genres("4K, Action", [], []), (["Action"], None))
        self.assertEqual(resolve_genres("Comedy, Criterion Collection", [], []), (["Comedy"], None))

    def test_falls_back_to_tags_when_option1_is_unusable(self):
        self.assertEqual(resolve_genres("Standard", ["Rental", "Horror"], []), (["Horror"], None))
        self.assertEqual(resolve_genres("#VALUE!", ["Comedy"], []), (["Comedy"], None))

    def test_helper_columns_win_when_present(self):
        genres, reason = resolve_genres("", ["Rental"], ["Sci-Fi", "Thriller", ""])
        self.assertEqual(genres, ["Sci-Fi", "Thriller"])
        self.assertIsNone(reason)

    def test_multiple_tag_genres_keep_tag_order(self):
        self.assertEqual(resolve_genres("", ["Comedy", "Rental", "Musical"], [])[0],
                         ["Comedy", "Musical"])

    def test_deduplicates(self):
        self.assertEqual(resolve_genres("Comedy", ["Comedy", "comedy"], [])[0], ["Comedy"])

    def test_no_usable_genre_is_flagged(self):
        for option1, tags in (("Special Interest", ["Rental"]), ("#REF!", []),
                              ("Chicago", []), ("", ["Rental", "VHS"])):
            genres, reason = resolve_genres(option1, tags, [])
            self.assertEqual(genres, [])
            self.assertIn("no usable genre", reason)


class TestResolveFormat(unittest.TestCase):
    def test_reads_vendor_and_fixes_case(self):
        self.assertEqual(resolve_format("BLU-RAY", "", [], ""), ("Blu-Ray", None))
        self.assertEqual(resolve_format("Dvd", "", [], ""), ("DVD", None))

    def test_helper_column_wins(self):
        self.assertEqual(resolve_format("VHS", "", [], "4K"), ("4K", None))

    def test_compound_option1_overrides_vendor(self):
        """A DVD-vendored row whose genre cell says "4K, Action" is a 4K disc."""
        self.assertEqual(resolve_format("DVD", "4K, Action", [], ""), ("4K", None))

    def test_falls_back_to_a_format_tag(self):
        self.assertEqual(resolve_format("Unknown", "", ["Rental", "4K"], ""), ("4K", None))

    def test_unusable_vendor_with_no_other_signal_is_flagged(self):
        for vendor in ("Unknown", "Little Movie Store", "Walt Disney", ""):
            value, reason = resolve_format(vendor, "Comedy", ["Rental"], "")
            self.assertIsNone(value, vendor)
            self.assertIn("no media format", reason)


class TestResolvePrice(unittest.TestCase):
    def test_rental_is_forced_to_zero(self):
        self.assertEqual(resolve_price("Rental", ""), ("0", None))
        self.assertEqual(resolve_price("Rental", "0.00"), ("0", None))

    def test_rental_with_a_real_price_is_flagged(self):
        value, reason = resolve_price("Rental", "12.99")
        self.assertIsNone(value)
        self.assertIn("Rental with a nonzero price", reason)

    def test_floor_sale_keeps_its_price(self):
        self.assertEqual(resolve_price("Floor Sale", "24.99"), ("24.99", None))

    def test_floor_sale_at_zero_or_blank_is_flagged(self):
        for raw in ("0", "0.00", ""):
            value, reason = resolve_price("Floor Sale", raw)
            self.assertIsNone(value, raw)
            self.assertIn("Floor Sale with no price", reason)

    def test_unparseable_price_is_flagged(self):
        value, reason = resolve_price("Floor Sale", "#REF!")
        self.assertIsNone(value)
        self.assertIn("unreadable price", reason)


class TestExtraTags(unittest.TestCase):
    def test_keeps_only_tags_that_are_not_type_format_or_genre(self):
        tags = ["Rental", "VHS", "Comedy", "Criterion Collection", "A24"]
        self.assertEqual(extra_tags(tags), ["Criterion Collection", "A24"])

    def test_preserves_order_and_deduplicates(self):
        self.assertEqual(extra_tags(["A24", "Rental", "A24"]), ["A24"])


if __name__ == "__main__":
    unittest.main()
