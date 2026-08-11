import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from review_page import MAX_CANDIDATES, build_picker_html, collect_products, write_picker


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


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
        self.assertIn('"skip"', html)
        self.assertNotIn("needs_data", html)
        self.assertNotIn("needs data", html)

    def test_escapes_content_that_could_close_the_script_tag(self):
        html = build_picker_html([
            {"handle": "x", "title": "X", "reason": "r",
             "candidates": [{"id": 1, "title": "</script><b>x</b>", "year": "1999",
                             "overview": "", "poster_path": ""}]}
        ])
        self.assertNotIn("</script><b>", html)


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
