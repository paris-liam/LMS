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


def result(title, year="1998", poster="/p.jpg", overview="An overview long enough to count.",
           genre_ids=None, popularity=0):
    return {"title": title, "release_date": f"{year}-01-01" if year else "",
            "poster_path": poster or "", "overview": overview,
            "genre_ids": genre_ids or [], "popularity": popularity}


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

    def test_partial_title_lone_candidate_is_ambiguous_not_auto_accepted(self):
        """"It's the Rage" vs. "All the Rage" shares most tokens but isn't
        the same title — a fuzzy matcher auto-accepting this would quietly
        pick a wrong-but-similar film. Route to the picker instead."""
        _, kind = classify_match("It's the Rage", None, [result("All the Rage")])
        self.assertEqual(kind, "ambiguous")

    def test_incomplete_duplicate_is_dropped_leaving_a_single_confident_match(self):
        """A second same-titled candidate with blank year/poster is TMDB
        duplicate-entry noise, not a real alternate release — once it's
        dropped, the fully-populated candidate is the only one left."""
        results = [result("Jagged Edge", "1985"), result("Jagged Edge", year="", poster=None)]
        best, kind = classify_match("Jagged Edge", None, results)
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1985")

    def test_incomplete_duplicate_dropped_even_when_it_sorts_first(self):
        results = [result("Jagged Edge", year="", poster=None), result("Jagged Edge", "1985")]
        best, kind = classify_match("Jagged Edge", None, results)
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1985")

    def test_genre_mismatch_breaks_a_tie_between_two_exact_titles(self):
        """"Mandela" has a dramatized 1987 biopic and documentaries from
        1989/1996 — catalog genre "drama" should resolve to the 1987 one
        without any popularity guesswork."""
        results = [
            result("Mandela", "1987", genre_ids=[18]),
            result("Mandela", "1989", genre_ids=[99]),
            result("Mandela", "1996", genre_ids=[99]),
        ]
        best, kind = classify_match("Mandela", None, results, genre="drama")
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1987")

    def test_large_popularity_gap_breaks_a_tie_when_genre_does_not(self):
        """When both exact-title candidates share (or lack) genre data, a
        10x+ popularity gap is a reasonable signal for the well-known film
        over the obscure one."""
        results = [
            result("Paradise Alley", "1978", popularity=25.0),
            result("Paradise Alley", "1962", popularity=1.0),
        ]
        best, kind = classify_match("Paradise Alley", None, results, genre="drama")
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1978")

    def test_genre_tiebreak_ignores_a_candidate_beyond_the_catalog_year_range(self):
        """Regression: a 2025 same-titled candidate can be the *only* one
        tagged with the catalog's genre among several exact-title ties,
        which would otherwise win the genre tiebreak outright — but the
        catalogue carries nothing from 2020 on, so that candidate must be
        excluded from tiebreak consideration before genre gets to decide,
        the same way GLOBAL_YEAR_CUTOFF already excludes it elsewhere.
        Modeled on a real catalogue case: "Elephant" (comedy genre) had
        2003/1993/2010/2020/2025 exact-title candidates, and only the 2025
        one carried a comedy genre tag."""
        results = [
            result("Elephant", "2003", genre_ids=[80, 18], popularity=5.19),
            result("Elephant", "1993", genre_ids=[10770, 80, 18], popularity=1.13),
            result("Elephant", "2010", genre_ids=[18], popularity=0.78),
            result("Elephant", "2020", genre_ids=[99, 10751, 12], popularity=2.32),
            result("Elephant", "2025", genre_ids=[35, 18], popularity=1.71),
        ]
        best, kind = classify_match("Elephant", None, results, genre="comedy")
        self.assertEqual(kind, "ambiguous")
        self.assertEqual(best["release_date"][:4], "2003")

    def test_small_popularity_gap_is_not_decisive(self):
        """A small gap isn't a reliable enough signal to auto-accept — this
        should still go to the picker."""
        results = [
            result("Communion", "1989", popularity=12.0),
            result("Communion", "2013", popularity=9.0),
        ]
        _, kind = classify_match("Communion", None, results, genre="drama")
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
        """A lone post-cutoff candidate is still the only candidate — since
        the cutoff only ever runs on an already-ambiguous result, a single
        confident match here never even reaches the filter."""
        out, review = build_output(
            [row(Title="Rushmore", Vendor="VHS")],
            fetcher([result("Rushmore", "2015")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertTrue(out[0]["Image Src"])

    def test_vhs_cutoff_never_overrides_an_already_confident_match(self):
        """Regression: a VHS row can already have a confident (if
        incomplete — e.g. TMDB has no poster for it) match to a post-cutoff
        film that happens to share a title with an older, pre-cutoff film.
        The cutoff filter must never run in that case — doing so would
        silently swap the correct-but-posterless match for a same-titled
        wrong one just because it's older and has a poster. Modeled on a
        real catalogue case: "Long Walk Home" (2012, no poster) vs. "The
        Long Walk Home" (1990, has a poster)."""
        results = [
            result("Long Walk Home", "2012", poster=None),
            result("The Long Walk Home", "1990"),
        ]
        out, review = build_output(
            [row(Title="Long Walk Home", Vendor="VHS")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertIn("poster", review[0]["Reason"])
        self.assertEqual(out[0]["Image Src"], "")

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
        """Blu-Ray/4K/blank Vendor values all get the same treatment as
        DVD — the tight 2008 VHS cutoff doesn't apply, only the looser
        2019 global one, so a same-titled 2011 candidate still causes
        genuine ambiguity here."""
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="Blu-Ray")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "ambiguous")

    def test_global_cutoff_resolves_a_post_2020_candidate_on_a_non_vhs_row(self):
        """The catalogue carries nothing from 2020 on regardless of format —
        a DVD row with a same-titled 2020+ candidate should resolve
        confidently to the older one, same disambiguation logic as VHS but
        with the looser cutoff."""
        results = [result("The Thing", "1982"), result("The Thing", "2021")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="DVD")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Alt Text"], "The Thing (1982) poster")

    def test_global_cutoff_boundary_is_inclusive_of_2019(self):
        results = [result("The Thing", "1982"), result("The Thing", "2019")]
        out, review = build_output(
            [row(Title="The Thing", Vendor="DVD")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "ambiguous")

    def test_global_cutoff_never_overrides_an_already_confident_match(self):
        """Same regression class as the VHS cutoff bug, generalized: a DVD
        row can already have a confident (if incomplete) match to a 2020+
        film sharing a title with an older one — the global cutoff must
        never run ahead of classify_match and swap it for the wrong older
        film just because the real match has no poster."""
        results = [
            result("Long Walk Home", "2021", poster=None),
            result("The Long Walk Home", "1990"),
        ]
        out, review = build_output(
            [row(Title="Long Walk Home", Vendor="DVD")], fetcher(results), sleep_fn=lambda s: None,
        )
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertIn("poster", review[0]["Reason"])
        self.assertEqual(out[0]["Image Src"], "")


if __name__ == "__main__":
    unittest.main()
