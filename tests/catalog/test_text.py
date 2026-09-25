import unittest

from catalog.core.text import norm_ws, strip_html


class TestText(unittest.TestCase):
    def test_strip_html_removes_tags_and_unescapes(self):
        self.assertEqual(strip_html("<p>Tom &amp; Jerry</p>"), "Tom & Jerry")

    def test_strip_html_handles_none(self):
        self.assertEqual(strip_html(None), "")

    def test_strip_html_empty_markup_is_empty(self):
        self.assertEqual(strip_html("<p> </p>"), "")

    def test_norm_ws_collapses_nbsp_and_runs(self):
        self.assertEqual(norm_ws("a\xa0 b\n\tc "), "a b c")


if __name__ == "__main__":
    unittest.main()
