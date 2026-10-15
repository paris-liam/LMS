import unittest
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import CatalogError
from catalog.rental_sync.posters import lookup_poster
from catalog.rental_sync.transform import transform
from catalog.tmdb.match import POSTER_BASE_URL, MatchResult

COPY = transform({"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror, thriller",
                  "description": "A shark.", "created": ""})
BEST = {"title": "Jaws", "release_date": "1975-06-20", "poster_path": "/jaws.jpg"}


def lookup(result):
    with mock.patch("catalog.rental_sync.posters.match_product", return_value=result) as matcher:
        out = lookup_poster(COPY, fetch_fn=lambda q, y: {})
    return out, matcher.call_args.args[0]


class TestLookupPoster(unittest.TestCase):
    def test_row_shape_sent_to_the_matcher(self):
        _, row = lookup(MatchResult("none", None, "no TMDB match"))
        self.assertEqual(row, {"Title": "Jaws", "Body (HTML)": "A shark.", "Vendor": "VHS",
                               GENRE_METAFIELD: "horror; thriller"})

    def test_confident(self):
        out, _ = lookup(MatchResult("confident", BEST, "confident TMDB match"))
        self.assertEqual(out, {"barcode": "2010000000014", "kind": "confident", "url": f"{POSTER_BASE_URL}/jaws.jpg",
                               "alt": "Jaws (1975) poster", "candidate": {"title": "Jaws", "year": "1975"},
                               "reason": "confident TMDB match"})

    def test_ambiguous_is_unsure(self):
        out, _ = lookup(MatchResult("ambiguous", BEST, "ambiguous match"))
        self.assertEqual((out["kind"], out["url"]), ("unsure", f"{POSTER_BASE_URL}/jaws.jpg"))

    def test_match_without_a_poster_is_none(self):
        out, _ = lookup(MatchResult("confident", dict(BEST, poster_path=None), "confident TMDB match"))
        self.assertEqual((out["kind"], out["url"], out["reason"]), ("none", "", "TMDB has no poster for this film"))

    def test_none_and_error(self):
        self.assertEqual(lookup(MatchResult("none", None, "no TMDB match"))[0]["kind"], "none")
        out, _ = lookup(MatchResult("error", None, "TMDB request failed: timeout"))
        self.assertEqual((out["kind"], out["reason"]), ("error", "TMDB request failed: timeout"))

    def test_bad_key_propagates(self):
        with mock.patch("catalog.rental_sync.posters.match_product", side_effect=CatalogError("TMDB rejected")):
            with self.assertRaises(CatalogError):
                lookup_poster(COPY, fetch_fn=lambda q, y: {})


if __name__ == "__main__":
    unittest.main()
