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


if __name__ == "__main__":
    unittest.main()
