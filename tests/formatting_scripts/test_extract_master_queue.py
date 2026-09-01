import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from extract_master_queue import collect_master_rows


def entry(handle, source_folder):
    return {"handle": handle, "source_folder": source_folder}


class TestCollectMasterRows(unittest.TestCase):
    def test_single_folder_same_shape_round_trips_the_row(self):
        rows_by_folder = {
            "batch-a": (["Handle", "Title"], [{"Handle": "h1", "Title": "Rushmore"}]),
        }
        header, rows, missing = collect_master_rows([entry("h1", "batch-a")], rows_by_folder)
        self.assertEqual(header, ["Handle", "Title"])
        self.assertEqual(rows, [{"Handle": "h1", "Title": "Rushmore"}])
        self.assertEqual(missing, [])

    def test_two_folders_with_different_columns_produce_a_union_header(self):
        """A narrower batch's rows get blank cells for the wider batch's
        extra columns, rather than the extra columns being dropped."""
        rows_by_folder = {
            "narrow": (["Handle", "Title"], [{"Handle": "h1", "Title": "Rushmore"}]),
            "wide": (["Handle", "Title", "SEO Title"],
                     [{"Handle": "h2", "Title": "Communion", "SEO Title": "Communion (1989)"}]),
        }
        entries = [entry("h1", "narrow"), entry("h2", "wide")]
        header, rows, missing = collect_master_rows(entries, rows_by_folder)
        self.assertEqual(header, ["Handle", "Title", "SEO Title"])
        self.assertEqual(rows[0], {"Handle": "h1", "Title": "Rushmore", "SEO Title": ""})
        self.assertEqual(rows[1], {"Handle": "h2", "Title": "Communion", "SEO Title": "Communion (1989)"})
        self.assertEqual(missing, [])

    def test_rows_come_out_in_entry_order_not_folder_order(self):
        rows_by_folder = {
            "batch-a": (["Handle"], [{"Handle": "h1"}, {"Handle": "h2"}]),
        }
        entries = [entry("h2", "batch-a"), entry("h1", "batch-a")]
        _, rows, _ = collect_master_rows(entries, rows_by_folder)
        self.assertEqual([r["Handle"] for r in rows], ["h2", "h1"])

    def test_a_handle_missing_from_its_batchs_rows_is_reported_not_raised(self):
        rows_by_folder = {"batch-a": (["Handle"], [{"Handle": "h1"}])}
        entries = [entry("h1", "batch-a"), entry("ghost", "batch-a")]
        header, rows, missing = collect_master_rows(entries, rows_by_folder)
        self.assertEqual([r["Handle"] for r in rows], ["h1"])
        self.assertEqual(missing, [entry("ghost", "batch-a")])

    def test_a_handle_appearing_twice_in_entries_is_only_emitted_once(self):
        """The queue can list the same handle from two source batches (the
        known cross-batch duplication) — the master upload list only needs
        one base row per handle."""
        rows_by_folder = {
            "batch-a": (["Handle"], [{"Handle": "h1"}]),
            "batch-b": (["Handle"], [{"Handle": "h1"}]),
        }
        entries = [entry("h1", "batch-a"), entry("h1", "batch-b")]
        _, rows, _ = collect_master_rows(entries, rows_by_folder)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
