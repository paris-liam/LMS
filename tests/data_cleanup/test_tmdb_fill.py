import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from tmdb_fill import POSTER_BASE_URL as POSTER_BASE_URL_FOR_TEST

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


from tmdb_fill import build_output


NO_SLEEP = lambda seconds: None


class TestBuildOutput(unittest.TestCase):
    def test_untouched_when_both_fields_already_present(self):
        rows = [make_row(**{
            "Handle": "good-movie",
            "Image Src": "https://img/1.jpg",
            "Body (HTML)": "<p>" + ("A" * 50) + "</p>",
        })]

        def fetch_fn(query, year):
            raise AssertionError("should not be called")

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(review_rows, [])

    def test_fills_image_only_leaves_existing_description_untouched(self):
        original_body = "<p>" + ("A" * 50) + "</p>"
        rows = [make_row(**{
            "Handle": "needs-image",
            "Title": "Warriors (1994)",
            "Image Src": "",
            "Body (HTML)": original_body,
        })]

        def fetch_fn(query, year):
            self.assertEqual(query, "Warriors")
            self.assertEqual(year, 1994)
            return {"results": [make_result("Warriors", 1994, overview="Ignored overview.")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/poster.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], original_body)
        self.assertEqual(review_rows, [])

    def test_fills_description_only_leaves_existing_image_untouched(self):
        rows = [make_row(**{
            "Handle": "needs-description",
            "Title": "Bambi",
            "Image Src": "https://img/existing.jpg",
            "Body (HTML)": "",
        })]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], "https://img/existing.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(review_rows, [])

    def test_fills_both_fields_on_confident_match(self):
        rows = [make_row(**{"Handle": "needs-both", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(review_rows, [])

    def test_no_results_routes_to_review_and_leaves_row_unchanged(self):
        rows = [make_row(**{"Handle": "no-match", "Title": "Totally Fictional Movie XYZ"})]

        def fetch_fn(query, year):
            return {"results": []}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Handle"], "no-match")
        self.assertEqual(review_rows[0]["Reason"], "no TMDB match")

    def test_ambiguous_match_routes_to_review_and_leaves_row_unchanged(self):
        rows = [make_row(**{"Handle": "ambiguous", "Title": "Warriors"})]

        def fetch_fn(query, year):
            return {"results": [make_result("The Parent Trap", 1998)]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(len(review_rows), 1)
        self.assertIn("ambiguous match", review_rows[0]["Reason"])
        self.assertIn("The Parent Trap", review_rows[0]["Reason"])

    def test_confident_match_missing_poster_fills_description_and_flags_review(self):
        rows = [make_row(**{"Handle": "no-poster", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path=None)]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], "")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Reason"], "matched but no TMDB poster")

    def test_confident_match_missing_overview_fills_image_and_flags_review(self):
        rows = [make_row(**{"Handle": "no-overview", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "")
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Reason"], "matched but no TMDB overview")

    def test_failed_fetch_routes_to_review_without_aborting_batch(self):
        rows = [
            make_row(**{"Handle": "broken", "Title": "Bambi"}),
            make_row(**{"Handle": "fine", "Title": "Bambi"}),
        ]
        calls = []

        def fetch_fn(query, year):
            calls.append(query)
            if len(calls) == 1:
                raise RuntimeError("connection reset")
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Handle"], "broken")
        self.assertIn("TMDB request failed", review_rows[0]["Reason"])
        self.assertIn("connection reset", review_rows[0]["Reason"])
        # the second row still got filled despite the first one erroring
        self.assertEqual(output_rows[1]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")

    def test_multi_row_handle_only_fills_primary_row(self):
        rows = [
            make_row(**{"Handle": "multi", "Title": "Bambi", "Image Position": "1"}),
            make_row(**{"Handle": "multi", "Title": "", "Image Src": "", "Image Position": "2"}),
        ]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        # bonus row is untouched
        self.assertEqual(output_rows[1]["Image Src"], "")
        self.assertEqual(output_rows[1]["Body (HTML)"], "")


import json
import tempfile
from unittest.mock import patch

from tmdb_fill import load_export, write_csv, run, make_tmdb_fetcher

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "tmdb_sample_export.csv"


class TestLoadExportAndWriteCsv(unittest.TestCase):
    def test_round_trips_fixture(self):
        fieldnames, rows = load_export(FIXTURE_PATH)
        self.assertIn("Handle", fieldnames)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Handle"], "good-movie")

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.csv"
            write_csv(out_path, fieldnames, rows)
            reloaded_fieldnames, reloaded_rows = load_export(out_path)
            self.assertEqual(reloaded_fieldnames, fieldnames)
            self.assertEqual(reloaded_rows, rows)


class TestMakeTmdbFetcher(unittest.TestCase):
    def test_builds_expected_url_and_parses_json_response(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"results": [{"title": "Bambi"}]}).encode("utf-8")

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("tmdb_fill.urllib.request.urlopen", fake_urlopen):
            fetch = make_tmdb_fetcher("test-api-key")
            data = fetch("Bambi", 1942)

        self.assertEqual(data, {"results": [{"title": "Bambi"}]})
        self.assertIn("api_key=test-api-key", captured["url"])
        self.assertIn("query=Bambi", captured["url"])
        self.assertIn("primary_release_year=1942", captured["url"])

    def test_omits_year_param_when_year_is_none(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"results": []}).encode("utf-8")

        captured = {}

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            return FakeResponse()

        with patch("tmdb_fill.urllib.request.urlopen", fake_urlopen):
            fetch = make_tmdb_fetcher("test-api-key")
            fetch("Bambi", None)

        self.assertNotIn("primary_release_year", captured["url"])


class TestRun(unittest.TestCase):
    def test_writes_filled_and_review_files(self):
        def fetch_fn(query, year):
            if query == "Needs Both":
                return {"results": [make_result("Needs Both", overview="Filled overview.", poster_path="/needs-both.jpg")]}
            return {"results": []}

        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            counts = run(FIXTURE_PATH, outdir, api_key="unused", fetch_fn=fetch_fn, sleep_fn=NO_SLEEP)

            self.assertEqual(counts, {"filled": 3, "review": 1})

            filled_fieldnames, filled_rows = load_export(outdir / "tmdb-filled.csv")
            by_handle = {r["Handle"]: r for r in filled_rows}
            self.assertEqual(by_handle["good-movie"]["Image Src"], "https://img/good.jpg")
            self.assertEqual(
                by_handle["needs-both-movie"]["Image Src"],
                f"{POSTER_BASE_URL_FOR_TEST}/needs-both.jpg",
            )
            self.assertEqual(by_handle["needs-both-movie"]["Body (HTML)"], "<p>Filled overview.</p>")
            self.assertEqual(by_handle["no-match-movie"]["Image Src"], "")

            review_fieldnames, review_rows = load_export(outdir / "tmdb-needs-review.csv")
            self.assertEqual(review_fieldnames, ["Handle", "Title", "Reason"])
            self.assertEqual(len(review_rows), 1)
            self.assertEqual(review_rows[0]["Handle"], "no-match-movie")


if __name__ == "__main__":
    unittest.main()
