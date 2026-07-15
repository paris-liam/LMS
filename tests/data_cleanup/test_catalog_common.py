import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from catalog_common import (
    add_tags,
    group_rows_by_handle,
    has_tag,
    load_export,
    remove_tag,
    split_tags,
    write_csv,
)


class TestTagHelpers(unittest.TestCase):
    def test_split_tags_strips_and_drops_empties(self):
        self.assertEqual(split_tags(" Drama , , Rental "), ["Drama", "Rental"])

    def test_split_tags_handles_none_and_empty(self):
        self.assertEqual(split_tags(None), [])
        self.assertEqual(split_tags(""), [])

    def test_has_tag_exact_match_only(self):
        self.assertTrue(has_tag("Drama, Needs Review", "Needs Review"))
        self.assertFalse(has_tag("Needs Review Soon", "Needs Review"))

    def test_add_tags_appends_without_duplicating(self):
        self.assertEqual(add_tags("Drama", ["Rental", "Drama"]), "Drama, Rental")

    def test_remove_tag(self):
        self.assertEqual(remove_tag("Drama, Needs Review, Rental", "Needs Review"), "Drama, Rental")
        self.assertEqual(remove_tag("Drama", "Not Present"), "Drama")


class TestGroupRowsByHandle(unittest.TestCase):
    def test_groups_preserve_order(self):
        rows = [
            {"Handle": "a", "x": "1"},
            {"Handle": "b", "x": "2"},
            {"Handle": "a", "x": "3"},
        ]
        groups = group_rows_by_handle(rows)
        self.assertEqual([h for h, _ in groups], ["a", "b"])
        self.assertEqual([r["x"] for r in groups[0][1]], ["1", "3"])


class TestCsvIo(unittest.TestCase):
    def test_round_trip(self):
        fieldnames = ["Handle", "Title"]
        rows = [{"Handle": "a", "Title": 'Movie, with "quotes"'}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.csv"
            write_csv(path, fieldnames, rows)
            loaded_fieldnames, loaded_rows = load_export(path)
            self.assertEqual(loaded_fieldnames, fieldnames)
            self.assertEqual(loaded_rows, rows)


if __name__ == "__main__":
    unittest.main()
