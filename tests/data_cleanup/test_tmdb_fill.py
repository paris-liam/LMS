import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from tmdb_fill import clean_title_and_year


class TestCleanTitleAndYear(unittest.TestCase):
    def test_extracts_trailing_year(self):
        title, year = clean_title_and_year("Warriors (1994)")
        self.assertEqual(title, "Warriors")
        self.assertEqual(year, 1994)

    def test_no_year_present(self):
        title, year = clean_title_and_year("Bambi")
        self.assertEqual(title, "Bambi")
        self.assertIsNone(year)

    def test_strips_steelbook_noise(self):
        title, year = clean_title_and_year("Trick 'r Treat [Steelbook]")
        self.assertEqual(title, "Trick 'r Treat")
        self.assertIsNone(year)

    def test_strips_free_gift_noise(self):
        title, year = clean_title_and_year("Harriet the Spy (Free Gift)")
        self.assertEqual(title, "Harriet the Spy")
        self.assertIsNone(year)

    def test_strips_widescreen_set_noise(self):
        title, year = clean_title_and_year("Indiana Jones Widescreen Set")
        self.assertEqual(title, "Indiana Jones")
        self.assertIsNone(year)

    def test_strips_parenthesized_noise_and_extracts_year_together(self):
        title, year = clean_title_and_year("Phantasm (Remastered) (1979)")
        self.assertEqual(title, "Phantasm")
        self.assertEqual(year, 1979)

    def test_unrelated_parenthetical_is_not_mistaken_for_year(self):
        # "Free Gift" isn't 4 digits, so it must not be parsed as a year.
        title, year = clean_title_and_year("A Pig's Tale (Free Gift)")
        self.assertEqual(title, "A Pig's Tale")
        self.assertIsNone(year)


if __name__ == "__main__":
    unittest.main()
