import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from apply_review_picks import NEEDS_DATA_TAG, apply_picks, run
from tmdb_fill import POSTER_BASE_URL


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Tags": "Drama",
        "Body (HTML)": "",
        "Image Src": "",
    }
    row.update(overrides)
    return row


class TestApplyPicks(unittest.TestCase):
    def test_tmdb_pick_fills_missing_image_and_description(self):
        rows = [make_row()]
        picks = [{"handle": "some-movie", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "Plot."}]
        output_rows, counts = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>Plot.</p>")
        self.assertEqual(counts["applied"], 1)

    def test_tmdb_pick_never_replaces_existing_image(self):
        rows = [make_row(**{"Image Src": "https://img/existing.jpg"})]
        picks = [{"handle": "some-movie", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "Plot."}]
        output_rows, _ = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Image Src"], "https://img/existing.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>Plot.</p>")

    def test_tmdb_pick_leaves_good_description_unless_circaos(self):
        good_body = "<p>" + ("A" * 50) + "</p>"
        rows = [
            make_row(**{"Handle": "plain", "Body (HTML)": good_body}),
            make_row(**{"Handle": "circa", "Body (HTML)": good_body, "Tags": "CircaOS Import"}),
        ]
        picks = [
            {"handle": "plain", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "New."},
            {"handle": "circa", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "New."},
        ]
        output_rows, _ = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Body (HTML)"], good_body)
        self.assertEqual(output_rows[1]["Body (HTML)"], "<p>New.</p>")

    def test_tmdb_pick_with_empty_fields_fills_nothing(self):
        rows = [make_row()]
        picks = [{"handle": "some-movie", "choice": "tmdb", "poster_path": "", "overview": ""}]
        output_rows, _ = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Image Src"], "")
        self.assertEqual(output_rows[0]["Body (HTML)"], "")

    def test_needs_data_choice_appends_tag_without_duplicating(self):
        rows = [
            make_row(**{"Handle": "a", "Tags": "Drama"}),
            make_row(**{"Handle": "b", "Tags": f"Drama, {NEEDS_DATA_TAG}"}),
        ]
        picks = [
            {"handle": "a", "choice": "needs_data"},
            {"handle": "b", "choice": "needs_data"},
        ]
        output_rows, counts = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Tags"], f"Drama, {NEEDS_DATA_TAG}")
        self.assertEqual(output_rows[1]["Tags"], f"Drama, {NEEDS_DATA_TAG}")
        self.assertEqual(counts["tagged"], 2)

    def test_multi_row_handle_only_modifies_primary_row(self):
        rows = [
            make_row(**{"Handle": "multi"}),
            make_row(**{"Handle": "multi", "Title": ""}),
        ]
        picks = [{"handle": "multi", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "Plot."}]
        output_rows, _ = apply_picks(rows, picks)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(output_rows[1]["Image Src"], "")

    def test_unknown_handle_is_counted_not_fatal(self):
        rows = [make_row()]
        picks = [{"handle": "not-in-csv", "choice": "needs_data"}]
        output_rows, counts = apply_picks(rows, picks)
        self.assertEqual(output_rows, rows)
        self.assertEqual(counts["unknown"], 1)

    def test_unpicked_rows_pass_through_unchanged(self):
        rows = [make_row(), make_row(**{"Handle": "other"})]
        output_rows, counts = apply_picks(rows, [])
        self.assertEqual(output_rows, rows)
        self.assertEqual(counts, {"applied": 0, "tagged": 0, "unknown": 0})


class TestRun(unittest.TestCase):
    def test_reads_picks_and_writes_applied_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            base_path = tmp / "base.csv"
            base_path.write_text(
                "Handle,Title,Tags,Body (HTML),Image Src\n"
                "a-movie,A Movie,Drama,,\n",
                encoding="utf-8",
            )
            picks_path = tmp / "tmdb-picks.json"
            picks_path.write_text(json.dumps([
                {"handle": "a-movie", "choice": "tmdb", "poster_path": "/p.jpg", "overview": "Plot."},
            ]), encoding="utf-8")

            counts = run(picks_path, base_path, tmp)
            self.assertEqual(counts, {"applied": 1, "tagged": 0, "unknown": 0})

            applied = (tmp / "picks-applied.csv").read_text(encoding="utf-8")
            self.assertIn(f"{POSTER_BASE_URL}/p.jpg", applied)
            self.assertIn("<p>Plot.</p>", applied)


if __name__ == "__main__":
    unittest.main()
