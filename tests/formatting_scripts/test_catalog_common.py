import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from catalog_common import write_csv


class TestWriteCsv(unittest.TestCase):
    def test_a_row_with_a_none_restkey_raises_a_clear_error_not_a_stack_trace(self):
        """csv.DictReader stashes any fields past the header under a None
        key when a source row has more columns than its header. Writing
        that row back out used to crash with a raw
        'dict contains fields not in fieldnames: None' ValueError — give
        the operator a message naming the row and the problem instead."""
        rows = [{"Handle": "the-thing-dvd-rental", "Title": "The Thing", None: ["extra", "stuff"]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            with self.assertRaises(ValueError) as ctx:
                write_csv(path, ["Handle", "Title"], rows)
            message = str(ctx.exception)
            self.assertIn("the-thing-dvd-rental", message)
            self.assertIn("more fields than the CSV header", message)
            self.assertFalse(path.exists())

    def test_normal_rows_still_write_fine(self):
        rows = [{"Handle": "the-thing-dvd-rental", "Title": "The Thing"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(path, ["Handle", "Title"], rows)
            self.assertIn("The Thing", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
