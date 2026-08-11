import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

import tmdb_fill
from tmdb_fill import (
    POSTER_BASE_URL,
    build_output,
    classify_match,
    clean_title_and_year,
)


def result(title, year="1998", poster="/p.jpg", overview="An overview long enough to count."):
    return {"title": title, "release_date": f"{year}-01-01",
            "poster_path": poster, "overview": overview}


def row(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "",
            "Image Src": "", "Image Alt Text": "", "Tags": "Rental, VHS, Comedy"}
    base.update(overrides)
    return base


def fetcher(results, calls=None):
    def fetch(query, year):
        if calls is not None:
            calls.append((query, year))
        return {"results": results}
    return fetch


class TestPosterBase(unittest.TestCase):
    def test_uses_w1280_not_w500(self):
        self.assertEqual(POSTER_BASE_URL, "https://image.tmdb.org/t/p/w1280")


class TestClassifyMatch(unittest.TestCase):
    def test_no_results_is_none(self):
        best, kind = classify_match("Rushmore", None, [])
        self.assertIsNone(best)
        self.assertEqual(kind, "none")

    def test_single_strong_match_is_confident(self):
        best, kind = classify_match("Rushmore", None, [result("Rushmore")])
        self.assertEqual(kind, "confident")
        self.assertEqual(best["title"], "Rushmore")

    def test_weak_single_match_is_ambiguous(self):
        _, kind = classify_match("Rushmore", None, [result("Rush Hour")])
        self.assertEqual(kind, "ambiguous")

    def test_two_equally_good_candidates_are_ambiguous(self):
        _, kind = classify_match("The Thing", None,
                                 [result("The Thing", "1982"), result("The Thing", "2011")])
        self.assertEqual(kind, "ambiguous")

    def test_a_known_year_breaks_the_tie(self):
        best, kind = classify_match("The Thing", 1982,
                                    [result("The Thing", "1982"), result("The Thing", "2011")])
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1982")

    def test_a_known_year_that_matches_nothing_is_ambiguous(self):
        _, kind = classify_match("The Thing", 1975, [result("The Thing", "1982")])
        self.assertEqual(kind, "ambiguous")


class TestBuildOutput(unittest.TestCase):
    def test_fills_image_description_and_alt_text(self):
        out, review = build_output([row()], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>An overview long enough to count.</p>")
        self.assertEqual(out[0]["Image Alt Text"], "Rushmore (1998) poster")

    def test_never_overwrites_an_existing_description_or_image(self):
        existing = row(**{"Body (HTML)": "<p>The client wrote this one himself.</p>",
                          "Image Src": "https://example.com/mine.jpg"})
        out, review = build_output([existing], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(out[0]["Body (HTML)"], "<p>The client wrote this one himself.</p>")
        self.assertEqual(out[0]["Image Src"], "https://example.com/mine.jpg")
        self.assertEqual(review, [])

    def test_a_complete_row_costs_no_request(self):
        calls = []
        complete = row(**{"Body (HTML)": "<p>A description that is plenty long enough.</p>",
                          "Image Src": "https://example.com/mine.jpg"})
        build_output([complete], fetcher([], calls), sleep_fn=lambda s: None)
        self.assertEqual(calls, [])

    def test_zero_results_is_reported_as_unmatched(self):
        out, review = build_output([row()], fetcher([]), sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertEqual(out[0]["Image Src"], "")

    def test_ambiguous_results_are_reported_for_the_picker(self):
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output([row(Title="The Thing")], fetcher(results), sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "ambiguous")
        self.assertEqual(out[0]["Image Src"], "")

    def test_a_match_with_no_poster_is_unmatched_but_still_fills_the_description(self):
        out, review = build_output([row()], fetcher([result("Rushmore", poster=None)]),
                                   sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertIn("poster", review[0]["Reason"])
        self.assertTrue(out[0]["Body (HTML)"])

    def test_a_request_failure_is_unmatched_and_does_not_abort_the_run(self):
        def boom(query, year):
            raise RuntimeError("network down")

        out, review = build_output([row(), row(Handle="b")], boom, sleep_fn=lambda s: None)
        self.assertEqual(len(out), 2)
        self.assertEqual(review[0]["Kind"], "unmatched")

    def test_writes_no_tags(self):
        out, _ = build_output([row()], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(out[0]["Tags"], "Rental, VHS, Comedy")


if __name__ == "__main__":
    unittest.main()
