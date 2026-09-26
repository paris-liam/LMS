import json
import tempfile
import unittest
from pathlib import Path

from catalog.errors import InputShapeError
from catalog.libib.state import counts_by_status, load_state, migrate_poster_src, save_state, set_status


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_and_missing_file(self):
        self.assertEqual(load_state(self.dir), {})
        state = {}
        set_status(state, "a", "queued", batch="batch-0001", call_number="01577790")
        save_state(self.dir, state)
        self.assertEqual(load_state(self.dir), {"a": {"status": "queued", "batch": "batch-0001",
                                                      "call_number": "01577790"}})

    def test_bad_json_is_an_input_error(self):
        (self.dir / "_state.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(InputShapeError):
            load_state(self.dir)

    def test_counts(self):
        self.assertEqual(counts_by_status({"a": {"status": "done"}, "b": {"status": "done"}, "c": {"status": "queued"}}),
                         {"done": 2, "queued": 1})

    def test_migrate_poster_src_from_old_poster_confirmed(self):
        state = {"a": {"status": "done", "poster_confirmed": True},
                 "b": {"status": "done", "poster_confirmed": False},
                 "c": {"status": "done", "poster_confirmed": True, "poster_src": "https://kept"},
                 "d": {"status": "done", "poster_confirmed": True}}
        rows = {"a": {"Image Src": "https://cdn/a.jpg"}, "b": {"Image Src": "https://cdn/b.jpg"},
                "c": {"Image Src": "https://cdn/c.jpg"}}
        self.assertEqual(migrate_poster_src(state, rows), 1)
        self.assertEqual(state["a"]["poster_src"], "https://cdn/a.jpg")
        self.assertNotIn("poster_src", state["b"])
        self.assertEqual(state["c"]["poster_src"], "https://kept")
        self.assertNotIn("poster_src", state["d"])  # not in the snapshot


if __name__ == "__main__":
    unittest.main()
