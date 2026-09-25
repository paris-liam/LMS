import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import SNAPSHOT_COLUMNS
from catalog.shopify.snapshot import (
    blank_row, exclusion_reason, filter_catalogue, load_snapshot, write_snapshot,
)


def row(**overrides):
    base = blank_row()
    base.update({"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Status": "active",
                 "Vendor": "VHS", "Tags": "Rental, VHS, Comedy"})
    base.update(overrides)
    return base


class TestSnapshot(unittest.TestCase):
    def test_blank_row_has_every_column(self):
        self.assertEqual(list(blank_row()), SNAPSHOT_COLUMNS)

    def test_movie_is_kept(self):
        self.assertIsNone(exclusion_reason(row()))

    def test_retail_template_excluded(self):
        self.assertEqual(exclusion_reason(row(**{"Template Suffix": "retail"})), "retail template")

    def test_archived_excluded(self):
        self.assertEqual(exclusion_reason(row(Status="archived")), "archived")

    def test_draft_kept(self):
        self.assertIsNone(exclusion_reason(row(Status="draft")))

    def test_membership_vendor_excluded(self):
        self.assertEqual(exclusion_reason(row(Vendor="Supercycle")), "membership plan")

    def test_online_store_tag_excluded_case_insensitively(self):
        self.assertEqual(exclusion_reason(row(Tags="Apparel, Online-Store")), "online-store item")

    def test_filter_counts_reasons(self):
        kept, excluded = filter_catalogue([row(), row(Status="archived"), row(Status="archived")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, {"archived": 2})

    def test_round_trip_keeps_leading_zero_barcode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            write_snapshot(path, [row(**{"Variant Barcode": "01577790", "Title": "Amélie"})])
            loaded = load_snapshot(path)
        self.assertEqual(loaded[0]["Variant Barcode"], "01577790")
        self.assertEqual(loaded[0]["Title"], "Amélie")


if __name__ == "__main__":
    unittest.main()
