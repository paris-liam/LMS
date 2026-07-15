import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from tmdb_review_page import (
    fetch_candidates,
    build_picker_html,
    collect_products,
    run,
)

NO_SLEEP = lambda seconds: None


def make_result(title, year=None, overview="An overview.", poster_path="/poster.jpg", tmdb_id=1):
    return {
        "id": tmdb_id,
        "title": title,
        "release_date": f"{year}-01-01" if year else "",
        "overview": overview,
        "poster_path": poster_path,
    }


class TestFetchCandidates(unittest.TestCase):
    def test_maps_fields_and_caps_at_five(self):
        results = [make_result(f"Movie {i}", 1990 + i, tmdb_id=i) for i in range(8)]
        candidates = fetch_candidates(lambda q, y: {"results": results}, "Movie", None)
        self.assertEqual(len(candidates), 5)
        self.assertEqual(candidates[0], {
            "id": 0,
            "title": "Movie 0",
            "year": "1990",
            "overview": "An overview.",
            "poster_path": "/poster.jpg",
        })

    def test_handles_missing_poster_and_overview(self):
        results = [make_result("Movie", overview=None, poster_path=None)]
        candidates = fetch_candidates(lambda q, y: {"results": results}, "Movie", None)
        self.assertEqual(candidates[0]["overview"], "")
        self.assertEqual(candidates[0]["poster_path"], "")

    def test_year_fallback_via_search_tmdb(self):
        calls = []

        def fetch(query, year):
            calls.append(year)
            if year is not None:
                return {"results": []}
            return {"results": [make_result("Movie")]}

        candidates = fetch_candidates(fetch, "Movie", 1994)
        self.assertEqual(calls, [1994, None])
        self.assertEqual(len(candidates), 1)


class TestCollectProducts(unittest.TestCase):
    def test_dedupes_review_rows_by_handle_merging_reasons(self):
        review_rows = [
            {"Handle": "a-movie", "Title": "A Movie", "Reason": "matched but no TMDB poster"},
            {"Handle": "a-movie", "Title": "A Movie", "Reason": "matched but no TMDB overview"},
            {"Handle": "b-movie", "Title": "B Movie (1994)", "Reason": "no TMDB match"},
        ]

        def fetch(query, year):
            return {"results": [make_result(query)]}

        products = collect_products(review_rows, fetch, sleep_fn=NO_SLEEP)
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["handle"], "a-movie")
        self.assertEqual(
            products[0]["reason"],
            "matched but no TMDB poster; matched but no TMDB overview",
        )

    def test_searches_with_cleaned_title_and_year(self):
        calls = []

        def fetch(query, year):
            calls.append((query, year))
            return {"results": []}

        collect_products(
            [{"Handle": "b-movie", "Title": "B Movie (1994)", "Reason": "no TMDB match"}],
            fetch,
            sleep_fn=NO_SLEEP,
        )
        # first call uses the cleaned title and parsed year; the empty result
        # then triggers search_tmdb's no-year fallback
        self.assertEqual(calls, [("B Movie", 1994), ("B Movie", None)])

    def test_failed_fetch_yields_product_with_no_candidates(self):
        def fetch(query, year):
            raise RuntimeError("boom")

        products = collect_products(
            [{"Handle": "a-movie", "Title": "A Movie", "Reason": "no TMDB match"}],
            fetch,
            sleep_fn=NO_SLEEP,
        )
        self.assertEqual(products[0]["candidates"], [])


class TestBuildPickerHtml(unittest.TestCase):
    def make_product(self, **overrides):
        product = {
            "handle": "a-movie",
            "title": "A Movie",
            "reason": "no TMDB match",
            "candidates": [
                {"id": 1, "title": "A Movie", "year": "1994", "overview": "Plot.", "poster_path": "/p.jpg"},
            ],
        }
        product.update(overrides)
        return product

    def test_contains_handle_needs_data_option_and_export(self):
        html_text = build_picker_html([self.make_product()])
        self.assertIn("a-movie", html_text)
        self.assertIn("needs data", html_text)
        self.assertIn("tmdb-picks.json", html_text)

    def test_contains_manual_entry_option(self):
        html_text = build_picker_html([self.make_product()])
        self.assertIn('value="manual"', html_text)
        self.assertIn("manual-image", html_text)
        self.assertIn("manual-overview", html_text)

    def test_script_tag_cannot_be_broken_by_overview_text(self):
        product = self.make_product(candidates=[{
            "id": 1,
            "title": "Evil",
            "year": "2000",
            "overview": "bad</script><script>alert(1)</script>",
            "poster_path": "",
        }])
        html_text = build_picker_html([product])
        self.assertNotIn("</script><script>alert(1)</script>", html_text)

    def test_embedded_json_round_trips(self):
        product = self.make_product()
        html_text = build_picker_html([product])
        start = html_text.index("const PRODUCTS = ") + len("const PRODUCTS = ")
        end = html_text.index(";\n", start)
        parsed = json.loads(html_text[start:end].replace("<\\/", "</"))
        self.assertEqual(parsed, [product])


class TestRun(unittest.TestCase):
    def test_writes_picker_html_from_review_csv(self):
        def fetch(query, year):
            return {"results": [make_result(query)]}

        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "tmdb-needs-review.csv"
            review_path.write_text(
                'Handle,Title,Reason\na-movie,A Movie,no TMDB match\n',
                encoding="utf-8",
            )
            counts = run(review_path, Path(tmp), api_key="unused", fetch_fn=fetch, sleep_fn=NO_SLEEP)
            self.assertEqual(counts, {"products": 1})
            html_text = (Path(tmp) / "tmdb-review-picker.html").read_text(encoding="utf-8")
            self.assertIn("a-movie", html_text)


if __name__ == "__main__":
    unittest.main()
