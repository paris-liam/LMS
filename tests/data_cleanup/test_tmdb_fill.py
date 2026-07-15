import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from tmdb_fill import (
    clean_title_and_year,
    normalize_title,
    title_similarity,
    search_tmdb,
    find_best_match,
    strip_html,
    needs_image,
    needs_description,
)


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


def make_result(title, year=None, overview="An overview.", poster_path="/poster.jpg"):
    return {
        "title": title,
        "release_date": f"{year}-01-01" if year else "",
        "overview": overview,
        "poster_path": poster_path,
    }


class TestNormalizeAndSimilarity(unittest.TestCase):
    def test_normalize_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize_title("The Lion King!"), "the lion king")

    def test_identical_titles_score_one(self):
        self.assertEqual(title_similarity("Warriors", "Warriors"), 1.0)

    def test_dissimilar_titles_score_low(self):
        self.assertLess(title_similarity("Warriors", "The Parent Trap"), 0.5)


class TestSearchTmdb(unittest.TestCase):
    def test_uses_year_filtered_results_when_present(self):
        def fetch(query, year):
            self.assertEqual(query, "Warriors")
            self.assertEqual(year, 1994)
            return {"results": [make_result("Warriors", 1994)]}

        results = search_tmdb(fetch, "Warriors", 1994)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Warriors")

    def test_falls_back_to_no_year_search_when_year_filtered_is_empty(self):
        calls = []

        def fetch(query, year):
            calls.append(year)
            if year is not None:
                return {"results": []}
            return {"results": [make_result("Warriors", 1995)]}

        results = search_tmdb(fetch, "Warriors", 1994)
        self.assertEqual(calls, [1994, None])
        self.assertEqual(len(results), 1)

    def test_returns_empty_when_no_year_given_and_no_results(self):
        results = search_tmdb(lambda q, y: {"results": []}, "Nonexistent Movie", None)
        self.assertEqual(results, [])

    def test_does_not_retry_when_no_year_was_given(self):
        calls = []

        def fetch(query, year):
            calls.append(year)
            return {"results": []}

        search_tmdb(fetch, "Nonexistent Movie", None)
        self.assertEqual(calls, [None])


class TestFindBestMatch(unittest.TestCase):
    def test_confident_on_exact_normalized_match(self):
        results = [make_result("Warriors")]
        best, confident = find_best_match("Warriors", results)
        self.assertEqual(best["title"], "Warriors")
        self.assertTrue(confident)

    def test_not_confident_on_dissimilar_top_result(self):
        results = [make_result("The Parent Trap")]
        best, confident = find_best_match("Warriors", results)
        self.assertEqual(best["title"], "The Parent Trap")
        self.assertFalse(confident)

    def test_no_results_returns_none_and_not_confident(self):
        best, confident = find_best_match("Warriors", [])
        self.assertIsNone(best)
        self.assertFalse(confident)


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Body (HTML)": "",
        "Image Src": "",
    }
    row.update(overrides)
    return row


class TestStripHtml(unittest.TestCase):
    def test_removes_tags(self):
        self.assertEqual(strip_html("<p>Hello <b>world</b></p>"), "Hello world")

    def test_handles_empty_string(self):
        self.assertEqual(strip_html(""), "")

    def test_handles_none(self):
        self.assertEqual(strip_html(None), "")


class TestNeedsImage(unittest.TestCase):
    def test_true_when_no_row_has_image(self):
        group = [make_row(), make_row()]
        self.assertTrue(needs_image(group))

    def test_false_when_primary_row_has_image(self):
        group = [make_row(**{"Image Src": "https://img/1.jpg"})]
        self.assertFalse(needs_image(group))

    def test_false_when_a_bonus_image_row_has_image(self):
        group = [make_row(), make_row(**{"Image Src": "https://img/2.jpg", "Title": ""})]
        self.assertFalse(needs_image(group))


class TestNeedsDescription(unittest.TestCase):
    def test_true_when_body_is_empty(self):
        self.assertTrue(needs_description([make_row(**{"Body (HTML)": ""})]))

    def test_true_when_body_is_short(self):
        self.assertTrue(needs_description([make_row(**{"Body (HTML)": "<p>Too short</p>"})]))

    def test_false_when_body_is_long_enough(self):
        long_body = "<p>" + ("A" * 50) + "</p>"
        self.assertFalse(needs_description([make_row(**{"Body (HTML)": long_body})]))


if __name__ == "__main__":
    unittest.main()
