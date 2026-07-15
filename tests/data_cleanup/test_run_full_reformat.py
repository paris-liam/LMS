import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from run_full_reformat import (
    NEEDS_REVIEW_TAG,
    CIRCAOS_IMPORT_TAG,
    add_tags,
    merge_review_rows,
    build_passthrough_rows,
    build_combined_upload,
)
from reformat_movies import FORMAT_COLUMN


class TestAddTags(unittest.TestCase):
    def test_appends_multiple_tags(self):
        self.assertEqual(
            add_tags("Rental", [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG]),
            "Rental, CircaOS Import, Needs Review",
        )

    def test_does_not_duplicate_existing_tags(self):
        self.assertEqual(
            add_tags(f"Rental, {NEEDS_REVIEW_TAG}", [NEEDS_REVIEW_TAG]),
            f"Rental, {NEEDS_REVIEW_TAG}",
        )


class TestMergeReviewRows(unittest.TestCase):
    def test_adds_batch_column(self):
        resale = [{"Handle": "a", "Title": "A", "Reason": "no genre set"}]
        circaos = [{"Handle": "b", "Title": "B", "Reason": "no genre-like tag found in Tags"}]
        merged = merge_review_rows(resale, circaos)
        self.assertEqual(merged[0]["Batch"], "resale")
        self.assertEqual(merged[1]["Batch"], "circaos")
        self.assertEqual(merged[0]["Handle"], "a")
        self.assertEqual(merged[1]["Reason"], "no genre-like tag found in Tags")


class TestBuildPassthroughRows(unittest.TestCase):
    def test_single_row_handle_preserves_fields_and_appends_tag(self):
        groups = {
            "some-movie": [
                {"Handle": "some-movie", "Vendor": "VHS", "Tags": "Comedy, Floor Sale"}
            ]
        }
        rows = build_passthrough_rows("some-movie", groups, [NEEDS_REVIEW_TAG])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Vendor"], "VHS")
        self.assertEqual(rows[0]["Tags"], "Comedy, Floor Sale, Needs Review")

    def test_multi_row_handle_only_tags_first_row(self):
        groups = {
            "multi": [
                {"Handle": "multi", "Vendor": "VHS", "Tags": "Rental"},
                {"Handle": "multi", "Vendor": "", "Tags": ""},
            ]
        }
        rows = build_passthrough_rows("multi", groups, [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Tags"], "Rental, CircaOS Import, Needs Review")
        self.assertEqual(rows[1]["Tags"], "")
        self.assertEqual(rows[1]["Vendor"], "")

    def test_adds_blank_format_column_if_absent(self):
        groups = {"some-movie": [{"Handle": "some-movie", "Vendor": "VHS", "Tags": ""}]}
        rows = build_passthrough_rows("some-movie", groups, [NEEDS_REVIEW_TAG])
        self.assertEqual(rows[0][FORMAT_COLUMN], "")


class TestBuildCombinedUpload(unittest.TestCase):
    def test_combines_output_and_passthrough_review_rows(self):
        resale_output = [{"Handle": "resale-in-scope", "Tags": "Comedy"}]
        circaos_output = [{"Handle": "circaos-in-scope", "Tags": "Thriller, CircaOS Import"}]
        resale_review = [{"Handle": "resale-review", "Title": "R", "Reason": "no genre"}]
        circaos_review = [{"Handle": "circaos-review", "Title": "C", "Reason": "no tag"}]
        groups = {
            "resale-review": [{"Handle": "resale-review", "Vendor": "VHS", "Tags": "Action"}],
            "circaos-review": [{"Handle": "circaos-review", "Vendor": "DVD", "Tags": "Rental"}],
        }
        combined = build_combined_upload(
            resale_output, circaos_output, resale_review, circaos_review, groups
        )
        by_handle = {r["Handle"]: r for r in combined}
        self.assertEqual(len(combined), 4)
        self.assertEqual(by_handle["resale-in-scope"]["Tags"], "Comedy")
        self.assertEqual(by_handle["circaos-in-scope"]["Tags"], "Thriller, CircaOS Import")
        self.assertEqual(by_handle["resale-review"]["Tags"], "Action, Needs Review")
        self.assertEqual(by_handle["circaos-review"]["Tags"], "Rental, CircaOS Import, Needs Review")


if __name__ == "__main__":
    unittest.main()
