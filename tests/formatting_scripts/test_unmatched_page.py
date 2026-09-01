import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from unmatched_page import (
    build_unmatched_html,
    genre_label,
    google_search_url,
    load_unmatched_products,
)


class TestGenreLabel(unittest.TestCase):
    def test_maps_a_known_handle_back_to_its_label(self):
        self.assertEqual(genre_label("romantic-comedy"), "Romantic Comedy")

    def test_falls_back_to_the_raw_slug_for_an_unmapped_value(self):
        self.assertEqual(genre_label("mystery-thriller"), "mystery-thriller")

    def test_blank_is_blank(self):
        self.assertEqual(genre_label(""), "")

    def test_uses_only_the_first_of_multiple_semicolon_joined_genres(self):
        self.assertEqual(genre_label("comedy; drama"), "Comedy")


class TestGoogleSearchUrl(unittest.TestCase):
    def test_builds_a_query_from_title_and_genre(self):
        url = google_search_url("Reindeer Games", "Action")
        self.assertTrue(url.startswith("https://www.google.com/search?q="))
        self.assertIn("Reindeer%20Games%20Action", url)


class TestLoadUnmatchedProducts(unittest.TestCase):
    def test_dedupes_by_handle_and_maps_genre(self):
        rows = [
            {"Handle": "a", "Title": "A", "Genre (product.metafields.shopify.genre)": "comedy"},
            {"Handle": "a", "Title": "A", "Genre (product.metafields.shopify.genre)": "comedy"},
            {"Handle": "b", "Title": "B", "Genre (product.metafields.shopify.genre)": "horror"},
        ]
        products = load_unmatched_products(rows)
        self.assertEqual([p["handle"] for p in products], ["a", "b"])
        self.assertEqual(products[1]["genre"], "Horror")

    def test_skips_rows_with_no_handle(self):
        rows = [{"Handle": "", "Title": "X", "Genre (product.metafields.shopify.genre)": ""}]
        self.assertEqual(load_unmatched_products(rows), [])


class TestBuildUnmatchedHtml(unittest.TestCase):
    def test_escapes_content_that_could_close_the_script_tag(self):
        html = build_unmatched_html([{"handle": "x", "title": "</script><b>x</b>", "genre": "comedy"}])
        self.assertNotIn("</script><b>", html)

    def test_export_shape_matches_apply_picks_manual_format(self):
        """The exported JSON must be a drop-in for apply_picks.py's manual
        pick handling: {handle, choice: "manual", image_src, overview}."""
        html = build_unmatched_html([{"handle": "x", "title": "X", "genre": "comedy"}])
        self.assertIn('choice: "manual"', html)
        self.assertIn("image_src:", html)
        self.assertIn("overview:", html)

    def test_storage_key_is_the_same_manual_key_used_by_the_ambiguous_picker(self):
        """Sharing the tmdb-review-manual:: key means a handle filled in
        via review-picker.html's manual entry and one filled in here don't
        silently diverge if the same batch_id is reused."""
        html = build_unmatched_html([], batch_id="review-queue-8.31")
        self.assertIn('"tmdb-review-manual::" + BATCH_ID', html)
        self.assertIn('"review-queue-8.31"', html)


if __name__ == "__main__":
    unittest.main()
