import unittest

from catalog.tmdb.match import (
    POSTER_BASE_URL,
    MatchResult,
    alt_text_for,
    classify_match,
    clean_title_and_year,
    match_product,
    poster_url,
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

    def test_overview_hint_breaks_a_tie_genre_and_popularity_cannot(self):
        """Real catalogue case: "Rear Window" has several exact-title
        remakes with no genre data and no decisive popularity gap in TMDB's
        own numbers. Our stored description names Hitchcock/Stewart/Kelly
        verbatim, which only the 1954 original's overview shares."""
        results = [
            result("Rear Window", "1954", popularity=14.9,
                   overview="A wheelchair-bound photographer spies on his neighbors from his "
                             "apartment window and becomes convinced one of them has committed murder."),
            result("Rear Window", "1998", popularity=3.4,
                   overview="A paraplegic photographer becomes convinced a neighbor has been murdered."),
        ]
        hint = ("A photographer confined to his apartment becomes convinced he's witnessed a "
                "murder while spying on his neighbors. Directed by Alfred Hitchcock and "
                "starring James Stewart and Grace Kelly.")
        best, kind = classify_match("Rear Window", None, results, overview_hint=hint)
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1954")

    def test_overview_hint_does_not_manufacture_a_match_when_too_close(self):
        """Two candidates with near-identical overview overlap must still
        go to the picker -- the margin has to be decisive, not just
        nonzero."""
        results = [
            result("Communion", "1989", overview="A man has a close encounter with aliens at night."),
            result("Communion", "2013", overview="A woman has a close encounter with aliens at night."),
        ]
        _, kind = classify_match(
            "Communion", None, results,
            overview_hint="Someone has a close encounter with aliens at night.",
        )
        self.assertEqual(kind, "ambiguous")

    def test_no_overview_hint_leaves_existing_behavior_unchanged(self):
        """Default (no hint passed) must behave exactly as before -- this
        pins backward compatibility for every existing caller."""
        results = [
            result("Paradise Alley", "1978", popularity=25.0),
            result("Paradise Alley", "1962", popularity=1.0),
        ]
        best, kind = classify_match("Paradise Alley", None, results, genre="drama")
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1978")




class TestMatchProduct(unittest.TestCase):
    def test_confident_single_match(self):
        m = match_product(row(), fetcher([result("Rushmore", "1998", genre_ids=[35])]))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(poster_url(m.best), f"{POSTER_BASE_URL}/p.jpg")

    def test_no_results_is_none(self):
        m = match_product(row(), fetcher([]))
        self.assertEqual((m.kind, m.reason), ("none", "no TMDB match"))

    def test_tie_is_ambiguous_and_names_best(self):
        tied = [result("Mandela", "1996", popularity=5), result("Mandela", "1987", popularity=5)]
        m = match_product(row(Title="Mandela", **{"Genre (product.metafields.shopify.genre)": ""}), fetcher(tied))
        self.assertEqual(m.kind, "ambiguous")
        self.assertIn("Mandela", m.reason)

    def test_request_failure_is_error_not_none(self):
        def boom(query, year):
            raise OSError("network down")
        m = match_product(row(), boom)
        self.assertEqual(m.kind, "error")
        self.assertIn("network down", m.reason)

    def test_vhs_year_cutoff_breaks_a_remake_tie(self):
        # A same-titled 2014 remake ties the 1987 original on title; VHS rows drop post-2008 candidates.
        tied = [result("RoboCop", "1987", popularity=5), result("RoboCop", "2014", popularity=5)]
        m = match_product(row(Title="RoboCop", Vendor="VHS", **{"Genre (product.metafields.shopify.genre)": ""}),
                          fetcher(tied))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(m.best["release_date"][:4], "1987")

    def test_description_breaks_a_tie(self):
        tied = [result("Rear Window", "1954", overview="A photographer in a wheelchair spies on his neighbors and suspects murder.", popularity=5),
                result("Rear Window", "1998", overview="A paralysed architect remake set in a modern apartment.", popularity=5)]
        body = "<p>Laid up with a broken leg, a photographer spies on his neighbors and becomes convinced of a murder.</p>"
        m = match_product(row(Title="Rear Window", **{"Body (HTML)": body, "Genre (product.metafields.shopify.genre)": ""}),
                          fetcher(tied))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(m.best["release_date"][:4], "1954")

    def test_alt_text_uses_match_year(self):
        self.assertEqual(alt_text_for("Rushmore (Special Edition)", {"release_date": "1998-12-11"}), "Rushmore (1998) poster")
        self.assertEqual(alt_text_for("Rushmore", {"release_date": ""}), "Rushmore poster")

    def test_poster_url_blank_without_path(self):
        self.assertEqual(poster_url({"poster_path": ""}), "")
        self.assertEqual(poster_url(None), "")

    def test_invalid_key_stops_the_audit(self):
        from catalog.errors import CatalogError

        def bad_key(query, year):
            raise CatalogError("TMDB rejected TMDB_API_KEY (401)")
        with self.assertRaises(CatalogError):
            match_product(row(), bad_key)


if __name__ == "__main__":
    unittest.main()
