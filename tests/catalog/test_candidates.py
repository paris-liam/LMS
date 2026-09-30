import unittest

from catalog.tmdb.candidates import MAX_CANDIDATES, collect_products, fetch_candidates, rental_or_floor_sale
def result(title, year="1982", popularity=0.0, vote_count=0, genre_ids=None):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview.",
            "popularity": popularity, "vote_count": vote_count,
            "genre_ids": genre_ids or []}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


class TestRentalOrFloorSale(unittest.TestCase):
    def test_recognizes_rental(self):
        self.assertEqual(rental_or_floor_sale("Rental, DVD, action"), "Rental")

    def test_recognizes_floor_sale(self):
        self.assertEqual(rental_or_floor_sale("Floor Sale, VHS, comedy"), "Floor Sale")

    def test_blank_when_neither_present(self):
        self.assertEqual(rental_or_floor_sale("DVD, action"), "")

    def test_blank_for_empty_tags(self):
        self.assertEqual(rental_or_floor_sale(""), "")


class TestFetchCandidates(unittest.TestCase):
    def test_keeps_recent_candidates(self):
        """The store stocks new releases, so a 2021 film is a real option
        for the reviewer alongside the 1982 one."""
        old = result("The Thing", "1982")
        new = result("The Thing", "2021")
        candidates = fetch_candidates(fetcher([old, new]), "The Thing", None)
        self.assertEqual(sorted(c["year"] for c in candidates), ["1982", "2021"])

    def test_keeps_a_2020_plus_candidate_when_the_title_has_an_explicit_year(self):
        """An explicit title year (passed through from clean_title_and_year)
        means the row itself claims that date — don't second-guess it."""
        candidates = fetch_candidates(fetcher([result("Recent Movie", "2021")]), "Recent Movie", 2021)
        self.assertEqual(len(candidates), 1)

    def test_orders_equally_titled_candidates_by_popularity(self):
        """Obscure titles losing to a popular same-named title is the most
        common failure mode — among equal title scores, popularity breaks
        the tie for what the human sees first."""
        obscure = result("The Thing", "1982", popularity=5.0)
        popular = result("The Thing", "2011", popularity=90.0)
        candidates = fetch_candidates(fetcher([obscure, popular]), "The Thing", None)
        self.assertEqual(candidates[0]["year"], "2011")

    def test_genre_match_outranks_popularity(self):
        """A genre mismatch should override popularity when they conflict —
        the plain-title-match candidate is more popular, but the
        genre-matching one should still come first."""
        horror_genre_id = 27
        wrong_genre_popular = result("It", "2017", popularity=200.0, genre_ids=[35])
        right_genre_obscure = result("It", "1990", popularity=10.0, genre_ids=[horror_genre_id])
        candidates = fetch_candidates(
            fetcher([wrong_genre_popular, right_genre_obscure]), "It", None, genre="horror",
        )
        self.assertEqual(candidates[0]["year"], "1990")

    def test_popularity_does_not_disturb_a_clear_title_score_difference(self):
        """A weaker title match must not jump ahead just because it's more
        popular — popularity only breaks ties among close scores."""
        strong_match = result("Rushmore", "1998", popularity=1.0)
        weak_match_but_popular = result("Rush Hour", "1998", popularity=500.0)
        candidates = fetch_candidates(
            fetcher([weak_match_but_popular, strong_match]), "Rushmore", None,
        )
        self.assertEqual(candidates[0]["title"], "Rushmore")


class TestCollectProducts(unittest.TestCase):
    def test_caps_candidates_at_five(self):
        many = [result(f"The Thing {n}") for n in range(9)]
        products = collect_products(
            [{"Handle": "the-thing", "Title": "The Thing", "Kind": "ambiguous", "Reason": "ambiguous match"}],
            fetcher(many), sleep_fn=lambda s: None,
        )
        self.assertEqual(MAX_CANDIDATES, 5)
        self.assertEqual(len(products[0]["candidates"]), 5)

    def test_merges_multiple_reasons_for_one_handle(self):
        rows = [
            {"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "no poster"},
            {"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "no overview"},
        ]
        products = collect_products(rows, fetcher([result("X")]), sleep_fn=lambda s: None)
        self.assertEqual(len(products), 1)
        self.assertIn("no poster", products[0]["reason"])
        self.assertIn("no overview", products[0]["reason"])

    def test_carries_vendor_and_genre_through_from_the_review_row(self):
        products = collect_products(
            [{"Handle": "x", "Title": "X", "Vendor": "DVD", "Genre": "horror",
              "Kind": "ambiguous", "Reason": "r"}],
            fetcher([result("X")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["vendor"], "DVD")
        self.assertEqual(products[0]["genre"], "horror")

    def test_carries_what_is_missing_through_from_the_review_row(self):
        products = collect_products(
            [{"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "r", "Missing": ["Image Src"]}],
            fetcher([result("X")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["missing"], ["Image Src"])

    def test_missing_defaults_to_empty_for_older_review_rows(self):
        products = collect_products([{"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "r"}],
                                    fetcher([result("X")]), sleep_fn=lambda s: None)
        self.assertEqual(products[0]["missing"], [])

    def test_carries_the_rental_or_floor_sale_tag_through_from_the_review_row(self):
        products = collect_products(
            [{"Handle": "x", "Title": "X", "Tags": "Rental, DVD, action",
              "Kind": "ambiguous", "Reason": "r"}],
            fetcher([result("X")]), sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["tag"], "Rental")

    def test_a_failed_request_yields_a_card_with_no_candidates(self):
        def boom(query, year):
            raise RuntimeError("network down")

        products = collect_products(
            [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
            boom, sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["candidates"], [])




class TestInvalidKey(unittest.TestCase):
    def test_an_invalid_key_stops_collection_instead_of_empty_cards(self):
        from catalog.errors import CatalogError

        def bad_key(query, year):
            raise CatalogError("TMDB rejected TMDB_API_KEY (HTTP 401)")

        with self.assertRaises(CatalogError):
            collect_products([{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                             bad_key, sleep_fn=lambda s: None)


if __name__ == "__main__":
    unittest.main()
