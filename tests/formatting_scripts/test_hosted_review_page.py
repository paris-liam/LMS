import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from hosted_review_page import build_hosted_picker_html


def sample_product():
    return {
        "handle": "the-thing", "title": "The Thing", "vendor": "VHS", "genre": "horror",
        "reason": "ambiguous match", "candidates": [
            {"id": 1, "title": "The Thing", "year": "1982", "overview": "Overview.", "poster_path": "/p.jpg"},
        ],
    }


class TestBuildHostedPickerHtml(unittest.TestCase):
    def test_embeds_the_batch_id(self):
        html = build_hosted_picker_html([sample_product()], "out-product_export_3")
        self.assertIn('"out-product_export_3"', html)

    def test_embeds_product_json(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn('"the-thing"', html)
        self.assertIn('"The Thing"', html)

    def test_has_no_export_button(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertNotIn("Export picks", html)
        self.assertNotIn("tmdb-picks.json", html)

    def test_references_the_save_pick_endpoint(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn("/api/save-pick", html)

    def test_references_the_get_picks_endpoint_with_batch_id(self):
        html = build_hosted_picker_html([sample_product()], "my-batch")
        self.assertIn("/api/get-picks?batch=my-batch", html)

    def test_escapes_closing_script_tags_in_overview_text(self):
        product = sample_product()
        product["candidates"][0]["overview"] = "a </script><script>alert(1)</script> b"
        html = build_hosted_picker_html([product], "batch")
        self.assertNotIn("</script><script>alert", html)

    def test_has_a_plain_language_header(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn("save automatically", html.lower())


import json
import tempfile
from pathlib import Path

from hosted_review_page import write_hosted_picker


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


class TestWriteHostedPicker(unittest.TestCase):
    def test_writes_the_batch_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_hosted_picker(
                [{"Handle": "the-thing", "Title": "The Thing", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("The Thing")]), sleep_fn=lambda s: None,
            )
            page = tools_dir / "out-x" / "index.html"
            self.assertTrue(page.exists())
            self.assertIn("the-thing", page.read_text(encoding="utf-8"))

    def test_creates_an_empty_data_file_for_a_new_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            data_file = tools_dir / "data" / "out-x.json"
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), [])

    def test_does_not_clobber_an_existing_data_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            data_dir = tools_dir / "data"
            data_dir.mkdir(parents=True)
            existing = [{"handle": "x", "choice": "skip"}]
            (data_dir / "out-x.json").write_text(json.dumps(existing), encoding="utf-8")

            write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(json.loads((data_dir / "out-x.json").read_text(encoding="utf-8")), existing)

    def test_returns_the_product_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dict = write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"},
                 {"Handle": "y", "Title": "Y", "Kind": "ambiguous", "Reason": "r"}],
                Path(tmp), "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(result_dict["products"], 2)


if __name__ == "__main__":
    unittest.main()
