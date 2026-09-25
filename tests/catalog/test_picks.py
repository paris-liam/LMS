import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.core import picks as picks_mod
from catalog.core.picks import Pick, PickError, load_picks, local_reader, parse_pick, remote_reader


def reader(files: dict):
    return lambda rel: files.get(rel)


class TestParsePick(unittest.TestCase):
    def test_tmdb_pick(self):
        p = parse_pick({"handle": "a", "choice": "tmdb", "poster_path": "/p.jpg", "overview": " O. "}, "q")
        self.assertEqual(p, Pick("q", "a", "tmdb", "/p.jpg", "O.", ""))

    def test_manual_pick(self):
        p = parse_pick({"handle": "a", "choice": "manual", "image_src": "https://x", "overview": ""}, "q")
        self.assertEqual((p.choice, p.image_src, p.overview), ("manual", "https://x", ""))

    def test_skip_pick(self):
        self.assertEqual(parse_pick({"handle": "a", "choice": "skip"}, "q").choice, "skip")

    def test_fields_is_rejected_naming_batch_and_handle(self):
        with self.assertRaises(PickError) as ctx:
            parse_pick({"handle": "a", "choice": "manual", "fields": {"genre": "horror"}}, "ambiguous-queue")
        self.assertIn("ambiguous-queue/a", str(ctx.exception))
        self.assertIn("fields", str(ctx.exception))

    def test_unknown_choice_is_rejected(self):
        with self.assertRaises(PickError):
            parse_pick({"handle": "a", "choice": "maybe"}, "q")

    def test_missing_handle_is_rejected(self):
        for raw in ({"choice": "skip"}, {"handle": " ", "choice": "skip"}, "not a dict"):
            with self.assertRaises(PickError):
                parse_pick(raw, "q")

    def test_null_text_fields_become_empty(self):
        p = parse_pick({"handle": "a", "choice": "tmdb", "poster_path": None, "overview": None}, "q")
        self.assertEqual((p.poster_path, p.overview), ("", ""))


class TestLoadPicks(unittest.TestCase):
    def test_reads_every_batch_in_manifest_order(self):
        files = {
            "batches.json": json.dumps([{"batch_id": "old", "total": 1}, {"batch_id": "ambiguous-queue", "total": 2},
                                        {"batch_id": "missing", "total": 1}]),
            "data/old.json": json.dumps([{"handle": "a", "choice": "skip"}]),
            "data/ambiguous-queue.json": json.dumps([{"handle": "b", "choice": "tmdb", "poster_path": "/b.jpg"},
                                                     {"handle": "a", "choice": "tmdb", "poster_path": "/a.jpg"}]),
        }
        loaded = load_picks(reader(files))
        self.assertEqual([(p.batch, p.handle) for p in loaded],
                         [("old", "a"), ("ambiguous-queue", "b"), ("ambiguous-queue", "a")])

    def test_no_manifest_means_no_picks(self):
        self.assertEqual(load_picks(reader({})), [])


class TestReaders(unittest.TestCase):
    def test_local_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "q.json").write_text("[]", encoding="utf-8")
            read = local_reader(tmp)
            self.assertEqual(read("data/q.json"), "[]")
            self.assertIsNone(read("data/nope.json"))

    def test_remote_reader_prefixes_the_picker_path(self):
        with mock.patch.object(picks_mod, "show_file", return_value="[]") as show:
            self.assertEqual(remote_reader("/repo", "origin/main", "tools/review-picker")("data/q.json"), "[]")
        show.assert_called_once_with("/repo", "origin/main", "tools/review-picker/data/q.json")


if __name__ == "__main__":
    unittest.main()
