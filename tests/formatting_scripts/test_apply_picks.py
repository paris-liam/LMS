import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from apply_picks import apply_picks
from tmdb_fill import POSTER_BASE_URL


def row(**overrides):
    base = {"Handle": "the-thing-4k-floor-sale", "Title": "The Thing",
            "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Floor Sale, 4K, Horror"}
    base.update(overrides)
    return base


class TestApplyPicks(unittest.TestCase):
    def test_a_tmdb_pick_fills_image_and_description(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "A crew is hunted by a shapeshifter."}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(out[0]["Image Src"], f"{POSTER_BASE_URL}/t.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>A crew is hunted by a shapeshifter.</p>")
        self.assertEqual(counts["applied"], 1)

    def test_a_tmdb_pick_does_not_overwrite_existing_data(self):
        existing = row(**{"Image Src": "https://example.com/mine.jpg",
                          "Body (HTML)": "<p>A description already written by hand.</p>"})
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "Overwrite me."}]
        out, _ = apply_picks([existing], picks)
        self.assertEqual(out[0]["Image Src"], "https://example.com/mine.jpg")
        self.assertIn("already written", out[0]["Body (HTML)"])

    def test_a_manual_pick_overrides_unconditionally(self):
        existing = row(**{"Image Src": "https://example.com/old.jpg"})
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "manual",
                  "image_src": "https://example.com/new.jpg", "overview": "Mine."}]
        out, _ = apply_picks([existing], picks)
        self.assertEqual(out[0]["Image Src"], "https://example.com/new.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>Mine.</p>")

    def test_a_tmdb_pick_sets_alt_text_from_the_title(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "A crew is hunted by a shapeshifter."}]
        out, _ = apply_picks([row()], picks)
        self.assertEqual(out[0]["Image Alt Text"], "The Thing poster")

    def test_a_manual_pick_sets_alt_text_from_the_title(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "manual",
                  "image_src": "https://example.com/new.jpg", "overview": "Mine."}]
        out, _ = apply_picks([row()], picks)
        self.assertEqual(out[0]["Image Alt Text"], "The Thing poster")

    def test_a_pick_never_overwrites_existing_alt_text(self):
        existing = row(**{"Image Alt Text": "A hand-written alt text"})
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "Overwrite me."}]
        out, _ = apply_picks([existing], picks)
        self.assertEqual(out[0]["Image Alt Text"], "A hand-written alt text")

    def test_a_skip_pick_changes_nothing_and_writes_no_tag(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "skip"}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(out[0], row())
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["applied"], 0)

    def test_a_pick_for_an_unknown_handle_is_counted_not_crashed_on(self):
        picks = [{"handle": "not-in-this-file", "choice": "skip"}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(len(out), 1)
        self.assertEqual(counts["unknown"], 1)

    def test_rows_without_a_pick_pass_through_untouched(self):
        out, _ = apply_picks([row(), row(Handle="other")], [])
        self.assertEqual(len(out), 2)

    def test_a_blank_status_is_filled_with_active_regardless_of_pick(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "skip"}]
        out, _ = apply_picks([row(Status="")], picks)
        self.assertEqual(out[0]["Status"], "active")

    def test_an_existing_status_is_left_alone(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "skip"}]
        out, _ = apply_picks([row(Status="draft")], picks)
        self.assertEqual(out[0]["Status"], "draft")


if __name__ == "__main__":
    unittest.main()
