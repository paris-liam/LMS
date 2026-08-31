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
            "Image Src": "", "Image Alt Text": "", "Tags": "Rental, VHS, Comedy",
            "Vendor": "VHS", "Genre (product.metafields.shopify.genre)": "comedy"}
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

    def test_alt_text_uses_the_cleaned_title_not_the_raw_one(self):
        """A raw title of "Alien (1979)" must not produce alt text of
        "Alien (1979) (1979) poster" — clean_title_and_year already
        stripped the year, so alt text must build from that, not Title."""
        out, review = build_output(
            [row(Title="Alien (1979)")], fetcher([result("Alien", "1979")]),
            sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Alt Text"], "Alien (1979) poster")

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
        out, review = build_output([row(Title="The Thing", Vendor="DVD")], fetcher(results), sleep_fn=lambda s: None)
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

    def test_ambiguous_review_rows_carry_vendor_and_genre(self):
        """The picker page needs format/genre without re-looking up the row —
        classify_match only ever sees clean_title/year, so this has to be
        threaded through from the source row explicitly."""
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        _, review = build_output(
            [row(Title="The Thing", Vendor="DVD",
                 **{"Genre (product.metafields.shopify.genre)": "horror"})],
            fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Vendor"], "DVD")
        self.assertEqual(review[0]["Genre"], "horror")

    def test_vhs_format_filters_out_a_post_cutoff_remake(self):
        """A VHS row with no title year and two same-titled candidates (an
        old release and a post-cutoff remake) should resolve confidently to
        the old one — VHS didn't exist to carry the remake."""
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="VHS")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Alt Text"], "The Thing (1982) poster")

    def test_dvd_format_does_not_filter_by_year(self):
        """The same two candidates on a DVD row must stay ambiguous — DVD
        carries both new releases and old catalog re-releases, so no date
        filter applies."""
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="DVD")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "ambiguous")
        self.assertEqual(out[0]["Image Src"], "")

    def test_vhs_cutoff_boundary_is_inclusive_of_2008(self):
        out, review = build_output(
            [row(Title="Rushmore", Vendor="VHS")],
            fetcher([result("Rushmore", "2008")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertTrue(out[0]["Image Src"])

    def test_vhs_cutoff_excludes_2009_when_an_older_candidate_remains(self):
        """A post-cutoff candidate is dropped from consideration even when
        it's not the only one — the older candidate should win confidently
        rather than the pair reading as ambiguous."""
        results = [result("Rushmore", "1998"), result("Rushmore", "2009")]
        out, review = build_output(
            [row(Title="Rushmore", Vendor="VHS")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Alt Text"], "Rushmore (1998) poster")

    def test_vhs_falls_back_to_unfiltered_results_when_the_cutoff_empties_the_set(self):
        """If every candidate is past the cutoff, that's more likely a
        format/data mismatch than a true miss — fall back to the unfiltered
        results rather than reporting no match."""
        out, review = build_output(
            [row(Title="Rushmore", Vendor="VHS")],
            fetcher([result("Rushmore", "2015")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertTrue(out[0]["Image Src"])

    def test_vhs_cutoff_does_not_apply_when_the_title_itself_has_a_year(self):
        """An explicit title year wins over the format cutoff on conflict —
        a VHS row titled "... (2011)" should still be able to match 2011."""
        out, review = build_output(
            [row(Title="The Thing (2011)", Vendor="VHS")],
            fetcher([result("The Thing", "2011")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertTrue(out[0]["Image Src"])

    def test_non_vhs_vendor_values_are_treated_like_dvd(self):
        """Blu-Ray/4K/blank Vendor values all get the same no-filter
        treatment as DVD — only VHS carries the cutoff."""
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="Blu-Ray")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
