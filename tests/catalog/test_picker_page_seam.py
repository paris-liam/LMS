"""Temporary seam test: the template renderer must produce exactly what the old
f-string generator in formatting-scripts/hosted_review_page.py produced.
Deleted in Plan 4 together with formatting-scripts/."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

import hosted_review_page as old  # noqa: E402

from catalog.picker import page  # noqa: E402

PRODUCTS = [
    {"handle": "the-thing", "title": "The Thing", "vendor": "VHS", "genre": "horror", "tag": "Rental",
     "reason": "ambiguous match", "candidates": [
         {"id": 1, "title": "The Thing", "year": "1982", "overview": "An </script> in the overview.",
          "poster_path": "/p.jpg"}]},
    {"handle": "amelie-dvd-rental", "title": "Amélie", "vendor": "DVD", "genre": "foreign; comedy", "tag": "",
     "reason": "no TMDB match", "candidates": []},
]


class TestSeam(unittest.TestCase):
    def test_page_matches_the_old_generator(self):
        for products, batch in (([], "ambiguous-queue"), (PRODUCTS, "unmatched-queue"),
                                (PRODUCTS, "review-9.2-gaps"), (PRODUCTS[:1], "a.b_c-d")):
            with self.subTest(batch=batch, n=len(products)):
                self.assertEqual(page.build_hosted_picker_html(products, batch),
                                 old.build_hosted_picker_html(products, batch))

    def test_launcher_matches_the_old_generator(self):
        self.assertEqual(page.build_launcher_html(), old.build_launcher_html())

    def test_templates_carry_no_leftover_sentinel(self):
        html = page.build_hosted_picker_html(PRODUCTS, "ambiguous-queue")
        for token in ("__PRODUCTS_JSON__", "__BATCH_ID_JSON__", "__BATCH_ID_URL__", "__PRODUCT_COUNT__", "zzbatchzz"):
            self.assertNotIn(token, html)


if __name__ == "__main__":
    unittest.main()
