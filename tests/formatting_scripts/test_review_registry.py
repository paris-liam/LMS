import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from review_registry import (
    filter_unknown, is_known, load_registry, mark_queued, mark_resolved, save_registry,
)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_registry_missing_file_is_empty(self):
        self.assertEqual(load_registry(self.tools_dir), {})

    def test_save_then_load_round_trips(self):
        registry = {}
        mark_queued(registry, ["a", "b"], "ambiguous-queue")
        save_registry(self.tools_dir, registry)
        self.assertEqual(load_registry(self.tools_dir), registry)

    def test_is_known_true_for_queued_and_resolved(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        self.assertTrue(is_known(registry, "a"))
        mark_resolved(registry, ["a"])
        self.assertTrue(is_known(registry, "a"))
        self.assertFalse(is_known(registry, "b"))

    def test_mark_resolved_updates_status_in_place(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        mark_resolved(registry, ["a"])
        self.assertEqual(registry["a"]["status"], "resolved")
        self.assertEqual(registry["a"]["batch"], "ambiguous-queue")  # batch preserved

    def test_mark_resolved_on_an_unqueued_handle_still_marks_it(self):
        registry = {}
        mark_resolved(registry, ["a"])
        self.assertEqual(registry["a"]["status"], "resolved")

    def test_filter_unknown_drops_queued_and_resolved_handles(self):
        registry = {}
        mark_queued(registry, ["a"], "ambiguous-queue")
        mark_resolved(registry, ["b"])
        rows = [{"Handle": "a"}, {"Handle": "b"}, {"Handle": "c"}]
        self.assertEqual(filter_unknown(rows, registry), [{"Handle": "c"}])


if __name__ == "__main__":
    unittest.main()
