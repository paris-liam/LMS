import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from taxonomy import (
    GENRES,
    FORMATS,
    TYPES,
    canonical_format,
    canonical_genre,
    canonical_type,
    genre_handle,
    normalize_key,
)


class TestNormalizeKey(unittest.TestCase):
    def test_lowercases_and_collapses_punctuation(self):
        self.assertEqual(normalize_key("Blu-Ray"), "blu ray")
        self.assertEqual(normalize_key("  Kids & Family "), "kids family")
        self.assertEqual(normalize_key("Sci-Fi"), "sci fi")


class TestCanonicalGenre(unittest.TestCase):
    def test_exact_labels_round_trip(self):
        for label in GENRES:
            self.assertEqual(canonical_genre(label), label)

    def test_thirteen_genres(self):
        self.assertEqual(len(GENRES), 13)

    def test_case_and_punctuation_insensitive(self):
        self.assertEqual(canonical_genre("sci-fi"), "Sci-Fi")
        self.assertEqual(canonical_genre("KIDS & FAMILY"), "Kids & Family")

    def test_known_typos_from_the_real_export(self):
        self.assertEqual(canonical_genre("Horor"), "Horror")
        self.assertEqual(canonical_genre("Sc-Fi"), "Sci-Fi")
        self.assertEqual(canonical_genre("SciFi"), "Sci-Fi")
        self.assertEqual(canonical_genre("Kids & Famiy"), "Kids & Family")
        self.assertEqual(canonical_genre("Romatic Comedy"), "Romantic Comedy")
        self.assertEqual(canonical_genre("Muscal"), "Musical")
        self.assertEqual(canonical_genre("Kids"), "Kids & Family")

    def test_unknown_values_return_none(self):
        for value in ("Special Interest", "Chicago", "#REF!", "#VALUE!", "", "   "):
            self.assertIsNone(canonical_genre(value), value)


class TestGenreHandle(unittest.TestCase):
    def test_maps_labels_to_metaobject_handles(self):
        self.assertEqual(genre_handle("Kids & Family"), "kids-family")
        self.assertEqual(genre_handle("Romantic Comedy"), "romantic-comedy")
        self.assertEqual(genre_handle("Foreign"), "foreign")

    def test_unknown_label_returns_none(self):
        self.assertIsNone(genre_handle("Special Interest"))


class TestCanonicalFormat(unittest.TestCase):
    def test_four_formats(self):
        self.assertEqual(FORMATS, ["VHS", "DVD", "Blu-Ray", "4K"])

    def test_fixes_case_from_the_real_export(self):
        self.assertEqual(canonical_format("BLU-RAY"), "Blu-Ray")
        self.assertEqual(canonical_format("Dvd"), "DVD")
        self.assertEqual(canonical_format("4k"), "4K")
        self.assertEqual(canonical_format("vhs"), "VHS")

    def test_non_format_vendors_return_none(self):
        for value in ("Unknown", "Unknown Brand", "Little Movie Store",
                      "Walt Disney", "Arrow Video", "Supercycle", ""):
            self.assertIsNone(canonical_format(value), value)


class TestCanonicalType(unittest.TestCase):
    def test_two_types(self):
        self.assertEqual(TYPES, ["Rental", "Floor Sale"])

    def test_fixes_typos_from_the_real_export(self):
        self.assertEqual(canonical_type("Floorsale"), "Floor Sale")
        self.assertEqual(canonical_type("Foor Sale"), "Floor Sale")
        self.assertEqual(canonical_type("Floor sale"), "Floor Sale")
        self.assertEqual(canonical_type("rental"), "Rental")

    def test_other_tags_return_none(self):
        for value in ("Comedy", "Criterion Collection", "A24", ""):
            self.assertIsNone(canonical_type(value), value)


if __name__ == "__main__":
    unittest.main()
