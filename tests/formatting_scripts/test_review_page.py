import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from review_page import MAX_CANDIDATES, build_picker_html, collect_products, fetch_candidates, write_picker


def result(title, year="1982", popularity=0.0, vote_count=0, genre_ids=None):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview.",
            "popularity": popularity, "vote_count": vote_count,
            "genre_ids": genre_ids or []}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


class TestFetchCandidates(unittest.TestCase):
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

    def test_a_failed_request_yields_a_card_with_no_candidates(self):
        def boom(query, year):
            raise RuntimeError("network down")

        products = collect_products(
            [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
            boom, sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["candidates"], [])


class TestBuildPickerHtml(unittest.TestCase):
    def test_offers_skip_rather_than_a_needs_data_tag(self):
        html = build_picker_html([{"handle": "x", "title": "X", "reason": "r", "candidates": []}])
        self.assertIn('choice: "skip"', html)
        self.assertNotIn("needs_data", html)
        self.assertNotIn("needs data", html)

    def test_escapes_content_that_could_close_the_script_tag(self):
        html = build_picker_html([
            {"handle": "x", "title": "X", "reason": "r",
             "candidates": [{"id": 1, "title": "</script><b>x</b>", "year": "1999",
                             "overview": "", "poster_path": ""}]}
        ])
        self.assertNotIn("</script><b>", html)

    def test_renders_vendor_and_genre_tags_when_present(self):
        html = build_picker_html([
            {"handle": "x", "title": "X", "vendor": "VHS", "genre": "comedy",
             "reason": "r", "candidates": []}
        ])
        self.assertIn('"vendor":"VHS"', html.replace(" ", ""))
        self.assertIn('"genre":"comedy"', html.replace(" ", ""))

    def test_omits_tags_entirely_when_vendor_and_genre_are_blank(self):
        html = build_picker_html([
            {"handle": "x", "title": "X", "vendor": "", "genre": "",
             "reason": "r", "candidates": []}
        ])
        self.assertIn("tagsHtml", html)  # the conditional exists in the template
        self.assertIn("filter(Boolean)", html)  # blanks are dropped, not rendered empty

    def test_storage_keys_are_namespaced_by_batch_id(self):
        """Pages sharing an origin (e.g. one static server) share
        localStorage by key, not by file path. Without a per-batch
        namespace, one batch's picks — and its decided counter — would
        leak into every other batch's picker page."""
        html = build_picker_html(
            [{"handle": "x", "title": "X", "reason": "r", "candidates": []}],
            batch_id="out-product_export_3",
        )
        self.assertIn('"tmdb-review-picks::" + BATCH_ID', html)
        self.assertIn('"out-product_export_3"', html)


class TestWritePicker(unittest.TestCase):
    def test_writes_the_page_and_reports_a_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts = write_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tmp, fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(counts["products"], 1)
            self.assertTrue((Path(tmp) / "review-picker.html").exists())


if __name__ == "__main__":
    unittest.main()
