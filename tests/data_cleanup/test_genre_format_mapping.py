import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from genre_format_mapping import (
    VENDOR_TO_FORMAT,
    GENRE_VALUE_MAP,
    resolve_format,
    resolve_genre,
)


class TestVendorToFormat(unittest.TestCase):
    def test_known_formats_map_correctly(self):
        self.assertEqual(VENDOR_TO_FORMAT["VHS"], "vhs")
        self.assertEqual(VENDOR_TO_FORMAT["DVD"], "dvd")
        self.assertEqual(VENDOR_TO_FORMAT["Blu-Ray"], "blu-ray")
        self.assertEqual(VENDOR_TO_FORMAT["BLU-RAY"], "blu-ray")
        self.assertEqual(VENDOR_TO_FORMAT["4K"], "4-k")
        self.assertEqual(VENDOR_TO_FORMAT["4k"], "4-k")
        self.assertEqual(VENDOR_TO_FORMAT["Dvd"], "dvd")

    def test_junk_vendors_map_to_none(self):
        for junk in [
            "Unknown",
            "Unknown Brand",
            "Little Movie Store",
            "Walt Disney",
            "The Franchise Collection",
            "Walt Disney Pictures",
            "Blockbuster",
            "Basquiat",
            "Disney",
            "Arrow Video",
            "Alfred Hitchcock",
            "Universal Pictures",
            "Supercycle",
        ]:
            self.assertIsNone(VENDOR_TO_FORMAT[junk])

    def test_covers_all_20_known_vendor_values(self):
        self.assertEqual(len(VENDOR_TO_FORMAT), 20)


class TestGenreValueMap(unittest.TestCase):
    def test_simple_genres_map_correctly(self):
        self.assertEqual(GENRE_VALUE_MAP["Comedy"], ("comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["Action"], ("action", None))
        self.assertEqual(GENRE_VALUE_MAP["Sci-Fi"], ("sci-fi", None))
        self.assertEqual(GENRE_VALUE_MAP["Foreign"], ("foreign", None))

    def test_typos_normalize_to_canonical_handles(self):
        self.assertEqual(GENRE_VALUE_MAP["Romatic Comedy"], ("romantic-comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["Muscal"], ("musical", None))
        self.assertEqual(GENRE_VALUE_MAP["SciFi"], ("sci-fi", None))
        self.assertEqual(GENRE_VALUE_MAP["Kids"], ("kids-family", None))

    def test_compound_4k_values_override_format(self):
        self.assertEqual(GENRE_VALUE_MAP["4K, Action"], ("action", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Action, 4K"], ("action", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["4k, Fantasy"], ("fantasy", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Kids & Family, 4K"], ("kids-family", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Horror, 4K"], ("horror", "4-k"))

    def test_curation_labels_strip_to_underlying_genre(self):
        self.assertEqual(GENRE_VALUE_MAP["Comedy, Criterion Collection"], ("comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["A24, Sci-Fi"], ("sci-fi", None))

    def test_special_interest_has_no_genre(self):
        self.assertEqual(GENRE_VALUE_MAP["Special Interest"], (None, None))

    def test_value_error_is_not_in_the_map(self):
        self.assertNotIn("#VALUE!", GENRE_VALUE_MAP)

    def test_covers_all_known_genre_values(self):
        # 28 values from the original export audit + the leaked-handle
        # "kids-family" corruption seen in later exports.
        self.assertEqual(len(GENRE_VALUE_MAP), 29)

    def test_leaked_handle_value_maps_to_itself(self):
        self.assertEqual(GENRE_VALUE_MAP["kids-family"], ("kids-family", None))


class TestResolveFormatAndGenre(unittest.TestCase):
    def test_plain_vendor_gives_format(self):
        self.assertEqual(resolve_format("VHS", "Comedy"), "vhs")
        self.assertEqual(resolve_format("Blu-Ray", "Action"), "blu-ray")

    def test_compound_genre_value_overrides_vendor_format(self):
        self.assertEqual(resolve_format("Blu-Ray", "4K, Action"), "4-k")

    def test_junk_vendor_gives_no_format(self):
        self.assertIsNone(resolve_format("Walt Disney", "Drama"))

    def test_resolve_genre_plain(self):
        self.assertEqual(resolve_genre("Comedy"), "comedy")

    def test_resolve_genre_compound(self):
        self.assertEqual(resolve_genre("4K, Action"), "action")

    def test_resolve_genre_special_interest_is_none(self):
        self.assertIsNone(resolve_genre("Special Interest"))

    def test_resolve_genre_unknown_value_is_none(self):
        self.assertIsNone(resolve_genre("#VALUE!"))


if __name__ == "__main__":
    unittest.main()
