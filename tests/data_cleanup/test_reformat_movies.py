import sys
import unittest
from pathlib import Path
import csv
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from reformat_movies import (
    FIXED_VENDOR,
    FIXED_CATEGORY,
    GENRE_COLUMN,
    FORMAT_COLUMN,
    classify_row,
    transform_group,
    group_rows_by_handle,
    build_output,
    main,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_export.csv"


def load_fixture():
    with open(FIXTURE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Vendor": "VHS",
        "Product Category": "Uncategorized",
        "Type": "",
        "Tags": "Comedy, Floor Sale",
        "Option1 Name": "Genre",
        "Option1 Value": "Comedy",
        "Variant Barcode": "12345",
        "Image Src": "https://img/1.jpg",
        "Image Position": "1",
        GENRE_COLUMN: "",
    }
    row.update(overrides)
    return row


class TestClassifyRow(unittest.TestCase):
    def test_genre_option_is_in_scope(self):
        status, reason = classify_row(make_row())
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)

    def test_value_error_genre_is_flagged_for_review(self):
        status, reason = classify_row(make_row(**{"Option1 Value": "#VALUE!"}))
        self.assertEqual(status, "review")
        self.assertIn("#VALUE!", reason)

    def test_unrecognized_genre_value_is_flagged_for_review(self):
        status, reason = classify_row(make_row(**{"Option1 Value": "Not A Real Genre"}))
        self.assertEqual(status, "review")
        self.assertIn("Not A Real Genre", reason)

    def test_title_only_variant_is_flagged_for_review(self):
        status, reason = classify_row(
            make_row(**{"Option1 Name": "Title", "Option1 Value": "Default Title"})
        )
        self.assertEqual(status, "review")
        self.assertIn("no genre set", reason)

    def test_condition_option_is_skipped(self):
        status, reason = classify_row(
            make_row(**{"Option1 Name": "Condition", "Option1 Value": "Standard"})
        )
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)

    def test_supercycle_plan_type_is_skipped(self):
        status, reason = classify_row(make_row(**{"Type": "Supercycle Plan"}))
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)

    def test_extra_image_row_is_skipped(self):
        # Extra image rows for an already-classified product have blank Option1 Name.
        status, reason = classify_row(make_row(**{"Option1 Name": ""}))
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)


class TestTransformGroup(unittest.TestCase):
    def test_simple_product_gets_full_transform(self):
        rows = [make_row(Vendor="VHS", **{"Option1 Value": "Comedy"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)
        first = transformed[0]
        self.assertEqual(first["Vendor"], FIXED_VENDOR)
        self.assertEqual(first["Product Category"], FIXED_CATEGORY)
        self.assertEqual(first["Option1 Name"], "Title")
        self.assertEqual(first["Option1 Value"], "Default Title")
        self.assertEqual(first[GENRE_COLUMN], "comedy")
        self.assertEqual(first[FORMAT_COLUMN], "vhs")

    def test_compound_4k_value_sets_both_fields(self):
        rows = [make_row(Vendor="Blu-Ray", **{"Option1 Value": "4K, Action"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "in_scope")
        first = transformed[0]
        self.assertEqual(first[GENRE_COLUMN], "action")
        self.assertEqual(first[FORMAT_COLUMN], "4-k")

    def test_junk_vendor_leaves_format_blank(self):
        rows = [make_row(Vendor="Walt Disney", **{"Option1 Value": "Drama"})]
        status, transformed, reason = transform_group(rows)
        first = transformed[0]
        self.assertEqual(first[GENRE_COLUMN], "drama")
        self.assertEqual(first[FORMAT_COLUMN], "")

    def test_extra_image_rows_pass_through_unchanged(self):
        primary = make_row(Vendor="DVD", **{"Option1 Value": "Comedy", "Image Position": "1"})
        image_2 = {"Handle": "some-movie", "Image Src": "https://img/2.jpg", "Image Position": "2"}
        image_3 = {"Handle": "some-movie", "Image Src": "https://img/3.jpg", "Image Position": "3"}
        status, transformed, reason = transform_group([primary, image_2, image_3])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(transformed), 3)
        self.assertEqual(transformed[1], image_2)
        self.assertEqual(transformed[2], image_3)

    def test_review_group_returns_no_transformed_rows(self):
        rows = [make_row(**{"Option1 Value": "#VALUE!"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "review")
        self.assertIsNone(transformed)
        self.assertIn("#VALUE!", reason)

    def test_skip_group_returns_no_transformed_rows(self):
        rows = [make_row(**{"Option1 Name": "Condition"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "skip")
        self.assertIsNone(transformed)


class TestGroupRowsByHandle(unittest.TestCase):
    def test_groups_preserve_order_and_multi_row_products(self):
        fieldnames, rows = load_fixture()
        groups = group_rows_by_handle(rows)
        handles = [handle for handle, _ in groups]
        self.assertEqual(handles[0], "simple-comedy-vhs")
        multi = dict(groups)["multi-image-product"]
        self.assertEqual(len(multi), 3)
        self.assertEqual(multi[0]["Image Position"], "1")
        self.assertEqual(multi[1]["Image Position"], "2")
        self.assertEqual(multi[2]["Image Position"], "3")


class TestBuildOutput(unittest.TestCase):
    def setUp(self):
        self.fieldnames, self.rows = load_fixture()
        self.new_fieldnames, self.output_rows, self.review_rows = build_output(
            self.rows, self.fieldnames
        )

    def test_adds_media_format_column(self):
        self.assertIn(FORMAT_COLUMN, self.new_fieldnames)

    def test_in_scope_products_are_in_output(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        self.assertIn("simple-comedy-vhs", output_handles)
        self.assertIn("junk-vendor-drama", output_handles)
        self.assertIn("compound-4k-action", output_handles)
        self.assertIn("foreign-typo-check", output_handles)

    def test_multi_image_product_keeps_all_three_rows(self):
        rows = [r for r in self.output_rows if r["Handle"] == "multi-image-product"]
        self.assertEqual(len(rows), 3)

    def test_foreign_typo_is_corrected(self):
        row = next(r for r in self.output_rows if r["Handle"] == "foreign-typo-check")
        self.assertEqual(row[GENRE_COLUMN], "foreign")

    def test_out_of_scope_rows_excluded_entirely(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        self.assertNotIn("rental-condition-row", output_handles)
        self.assertNotIn("rental-condition-row", review_handles)
        self.assertNotIn("supercycle-plan", output_handles)
        self.assertNotIn("supercycle-plan", review_handles)

    def test_bad_rows_go_to_review_not_output(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        self.assertNotIn("badvalue-row", output_handles)
        self.assertIn("badvalue-row", review_handles)
        self.assertNotIn("title-only-row", output_handles)
        self.assertIn("title-only-row", review_handles)


class TestMain(unittest.TestCase):
    def test_writes_output_and_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "movies-reformatted.csv"
            review_path = Path(tmp) / "needs-review.csv"
            n_out, n_review = main(FIXTURE_PATH, output_path, review_path)

            self.assertTrue(output_path.exists())
            self.assertTrue(review_path.exists())
            self.assertEqual(n_review, 2)

            with open(output_path, newline="", encoding="utf-8") as f:
                out_rows = list(csv.DictReader(f))
            self.assertEqual(len(out_rows), n_out)
            self.assertIn(FORMAT_COLUMN, out_rows[0].keys())

            with open(review_path, newline="", encoding="utf-8") as f:
                review_rows = list(csv.DictReader(f))
            reasons = {row["Handle"]: row["Reason"] for row in review_rows}
            self.assertIn("#VALUE!", reasons["badvalue-row"])
            self.assertIn("no genre set", reasons["title-only-row"])


if __name__ == "__main__":
    unittest.main()
