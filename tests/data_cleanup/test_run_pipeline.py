import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from catalog_common import write_csv
from reformat_movies import FIXED_CATEGORY, FIXED_VENDOR, FORMAT_COLUMN, GENRE_COLUMN
from run_pipeline import process_group, reformat_rows, run

NO_SLEEP = lambda seconds: None

FIELDNAMES = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
    "Tags", "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
    "Variant SKU", "Variant Barcode", "Image Src", "Image Position",
    GENRE_COLUMN, FORMAT_COLUMN,
]


def make_row(**overrides):
    row = {name: "" for name in FIELDNAMES}
    row.update({
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Vendor": "Little Movie Store",
        "Product Category": "Media > Videos",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
    })
    row.update(overrides)
    return row


class TestProcessGroupDoneAndResolved(unittest.TestCase):
    def test_done_product_passes_through_untouched(self):
        group = [make_row(**{GENRE_COLUMN: "drama", "Tags": "Drama"})]
        bucket, out_rows, entry = process_group("some-movie", group)
        self.assertEqual(bucket, "done")
        self.assertEqual(out_rows, group)
        self.assertIsNone(entry)

    def test_done_product_with_stale_review_tag_gets_tag_removed(self):
        group = [make_row(**{GENRE_COLUMN: "drama", "Tags": "Drama, Needs Review"})]
        bucket, out_rows, entry = process_group("some-movie", group)
        self.assertEqual(bucket, "resolved")
        self.assertEqual(out_rows[0]["Tags"], "Drama")
        self.assertIsNone(entry)

    def test_supercycle_plan_passes_through(self):
        group = [make_row(**{"Handle": "membership", "Type": "Supercycle Plan"})]
        bucket, out_rows, entry = process_group("membership", group)
        self.assertEqual(bucket, "plan")
        self.assertEqual(out_rows, group)
        self.assertIsNone(entry)


class TestProcessGroupRawShapes(unittest.TestCase):
    def test_genre_shape_gets_resale_transform(self):
        group = [make_row(**{
            "Handle": "raw-resale", "Vendor": "DVD", "Product Category": "",
            "Option1 Name": "Genre", "Option1 Value": "Comedy",
        })]
        bucket, out_rows, entry = process_group("raw-resale", group)
        self.assertEqual(bucket, "resale")
        self.assertEqual(out_rows[0][GENRE_COLUMN], "comedy")
        self.assertEqual(out_rows[0][FORMAT_COLUMN], "dvd")
        self.assertEqual(out_rows[0]["Vendor"], FIXED_VENDOR)
        self.assertEqual(out_rows[0]["Option1 Name"], "Title")

    def test_genre_shape_transform_strips_stale_review_tag(self):
        group = [make_row(**{
            "Handle": "was-flagged", "Vendor": "DVD", "Tags": "Needs Review",
            "Option1 Name": "Genre", "Option1 Value": "Comedy",
        })]
        bucket, out_rows, _ = process_group("was-flagged", group)
        self.assertEqual(bucket, "resale")
        self.assertNotIn("Needs Review", out_rows[0]["Tags"])

    def test_condition_shape_transform_strips_stale_review_tag(self):
        group = [make_row(**{
            "Handle": "was-flagged-rental", "Vendor": "DVD", "Tags": "Drama, Needs Review",
            "Option1 Name": "Condition", "Option1 Value": "Good",
            "Variant Barcode": "191-DVD0001",
        })]
        bucket, out_rows, _ = process_group("was-flagged-rental", group)
        self.assertEqual(bucket, "circaos")
        self.assertNotIn("Needs Review", out_rows[0]["Tags"])
        self.assertIn("CircaOS Import", out_rows[0]["Tags"])

    def test_corrupt_genre_value_is_flagged(self):
        group = [make_row(**{
            "Handle": "corrupt", "Option1 Name": "Genre", "Option1 Value": "#VALUE!",
        })]
        bucket, out_rows, entry = process_group("corrupt", group)
        self.assertEqual(bucket, "flagged-new")
        self.assertIn("Needs Review", out_rows[0]["Tags"])
        self.assertEqual(entry["Status"], "new")
        self.assertIn("#VALUE!", entry["Reason"])

    def test_condition_shape_gets_circaos_transform_with_multi_copy_split(self):
        group = [
            make_row(**{
                "Handle": "rental", "Vendor": "DVD", "Tags": "Drama",
                "Option1 Name": "Condition", "Option1 Value": "Good",
                "Variant Barcode": "191-DVD0001",
            }),
            make_row(**{
                "Handle": "rental", "Title": "", "Vendor": "DVD", "Tags": "",
                "Option1 Name": "Condition", "Option1 Value": "Fair",
                "Variant Barcode": "191-VHS0002",
            }),
        ]
        bucket, out_rows, entry = process_group("rental", group)
        self.assertEqual(bucket, "circaos")
        self.assertEqual(len(out_rows), 2)
        self.assertEqual({r["Handle"] for r in out_rows}, {"rental-dvd", "rental-vhs"})
        for r in out_rows:
            self.assertEqual(r[GENRE_COLUMN], "drama")
            self.assertIn("CircaOS Import", r["Tags"])

    def test_condition_shape_without_genre_tag_is_flagged(self):
        group = [make_row(**{
            "Handle": "mystery-rental", "Tags": "Rental",
            "Option1 Name": "Condition", "Option1 Value": "Good",
        })]
        bucket, out_rows, entry = process_group("mystery-rental", group)
        self.assertEqual(bucket, "flagged-new")
        self.assertEqual(entry["Status"], "new")


class TestProcessGroupRecovery(unittest.TestCase):
    def test_recovers_genre_from_tags_and_fixes_vendor_and_format(self):
        group = [make_row(**{
            "Handle": "recoverable", "Vendor": "VHS", "Product Category": "",
            "Tags": "Horror, CircaOS Import, Needs Review",
            "Variant Barcode": "191-VHS0009",
        })]
        bucket, out_rows, entry = process_group("recoverable", group)
        self.assertEqual(bucket, "recovered")
        primary = out_rows[0]
        self.assertEqual(primary[GENRE_COLUMN], "horror")
        self.assertEqual(primary[FORMAT_COLUMN], "vhs")
        self.assertEqual(primary["Vendor"], FIXED_VENDOR)
        self.assertEqual(primary["Product Category"], FIXED_CATEGORY)
        self.assertNotIn("Needs Review", primary["Tags"])
        self.assertIn("CircaOS Import", primary["Tags"])

    def test_recovery_keeps_existing_format_metafield(self):
        group = [make_row(**{
            "Handle": "has-format", "Tags": "Comedy",
            FORMAT_COLUMN: "blu-ray", "Vendor": "DVD",
        })]
        bucket, out_rows, _ = process_group("has-format", group)
        self.assertEqual(bucket, "recovered")
        self.assertEqual(out_rows[0][FORMAT_COLUMN], "blu-ray")

    def test_unrecoverable_product_is_newly_flagged(self):
        group = [make_row(**{"Handle": "hopeless", "Tags": "Rare Finds"})]
        bucket, out_rows, entry = process_group("hopeless", group)
        self.assertEqual(bucket, "flagged-new")
        self.assertEqual(out_rows[0]["Tags"], "Rare Finds, Needs Review")
        self.assertEqual(entry["Status"], "new")

    def test_already_flagged_unrecoverable_product_stays_flagged_without_duplicate_tag(self):
        group = [make_row(**{"Handle": "hopeless", "Tags": "Needs Review"})]
        bucket, out_rows, entry = process_group("hopeless", group)
        self.assertEqual(bucket, "flagged-still")
        self.assertEqual(out_rows[0]["Tags"], "Needs Review")
        self.assertEqual(entry["Status"], "still-flagged")


class TestReformatRows(unittest.TestCase):
    def full_fixture_rows(self):
        return [
            make_row(**{"Handle": "done-movie", GENRE_COLUMN: "drama"}),
            make_row(**{"Handle": "stale-tag-movie", GENRE_COLUMN: "comedy", "Tags": "Needs Review"}),
            make_row(**{
                "Handle": "raw-resale", "Vendor": "DVD",
                "Option1 Name": "Genre", "Option1 Value": "Comedy",
            }),
            make_row(**{
                "Handle": "rental", "Vendor": "DVD", "Tags": "Drama",
                "Option1 Name": "Condition", "Option1 Value": "Good",
                "Variant Barcode": "191-DVD0001",
            }),
            make_row(**{"Handle": "recoverable", "Vendor": "VHS", "Tags": "Horror"}),
            make_row(**{"Handle": "hopeless", "Tags": "Rare Finds"}),
            make_row(**{"Handle": "still-hopeless", "Tags": "Needs Review"}),
            make_row(**{"Handle": "membership", "Type": "Supercycle Plan"}),
        ]

    def test_counts_every_bucket_and_reports_review_rows(self):
        rows = self.full_fixture_rows()
        new_fieldnames, output_rows, review_rows, counts = reformat_rows(rows, FIELDNAMES)
        self.assertEqual(counts, {
            "plan": 1, "resale": 1, "circaos": 1, "done": 1,
            "resolved": 1, "recovered": 1, "flagged-new": 1, "flagged-still": 1,
        })
        self.assertEqual(len(output_rows), len(rows))
        self.assertEqual(
            [(r["Handle"], r["Status"]) for r in review_rows],
            [("hopeless", "new"), ("still-hopeless", "still-flagged")],
        )

    def test_is_idempotent_on_its_own_output(self):
        rows = self.full_fixture_rows()
        _, first_pass, _, _ = reformat_rows(rows, FIELDNAMES)
        _, second_pass, review_rows, counts = reformat_rows(first_pass, FIELDNAMES)
        self.assertEqual(second_pass, first_pass)
        self.assertEqual(counts["resale"], 0)
        self.assertEqual(counts["circaos"], 0)
        self.assertEqual(counts["recovered"], 0)
        self.assertEqual(counts["flagged-new"], 0)
        self.assertEqual(counts["flagged-still"], 2)
        self.assertEqual(counts["done"], 5)

    def test_inserts_format_column_when_missing(self):
        fieldnames = [n for n in FIELDNAMES if n != FORMAT_COLUMN]
        rows = [{k: v for k, v in make_row(**{GENRE_COLUMN: "drama"}).items() if k != FORMAT_COLUMN}]
        new_fieldnames, _, _, _ = reformat_rows(rows, fieldnames)
        genre_index = new_fieldnames.index(GENRE_COLUMN)
        self.assertEqual(new_fieldnames[genre_index + 1], FORMAT_COLUMN)

    def test_flags_duplicate_output_handles(self):
        rows = [
            # already-reformatted product occupying "rental-bluray"
            make_row(**{"Handle": "rental-bluray", GENRE_COLUMN: "drama"}),
            # raw multi-copy product whose split also produces "rental-bluray"
            make_row(**{
                "Handle": "rental", "Vendor": "DVD", "Tags": "Drama",
                "Option1 Name": "Condition", "Option1 Value": "Good",
                "Variant Barcode": "191-BLR0001",
            }),
            make_row(**{
                "Handle": "rental", "Title": "", "Vendor": "DVD",
                "Option1 Name": "Condition", "Option1 Value": "Fair",
                "Variant Barcode": "191-DVD0002",
            }),
        ]
        lines = []
        _, _, review_rows, counts = reformat_rows(rows, FIELDNAMES, log_fn=lines.append)
        self.assertEqual(counts["duplicate-handle"], 1)
        dup_rows = [r for r in review_rows if r["Status"] == "duplicate"]
        self.assertEqual(len(dup_rows), 1)
        self.assertEqual(dup_rows[0]["Handle"], "rental-bluray")
        self.assertIn("rental", dup_rows[0]["Reason"])
        self.assertTrue(any("WARNING" in line for line in lines))

    def test_no_duplicate_flag_on_clean_input(self):
        _, _, review_rows, counts = reformat_rows(self.full_fixture_rows(), FIELDNAMES)
        self.assertNotIn("duplicate-handle", counts)
        self.assertFalse(any(r["Status"] == "duplicate" for r in review_rows))

    def test_logs_one_line_per_acted_on_product_only(self):
        lines = []
        reformat_rows(self.full_fixture_rows(), FIELDNAMES, log_fn=lines.append)
        logged_handles = [line.split("]")[0].strip("[") for line in lines]
        self.assertEqual(
            logged_handles,
            ["stale-tag-movie", "raw-resale", "rental", "recoverable", "hopeless", "still-hopeless"],
        )
        # untouched products (done-movie, membership) produce no per-product line
        self.assertFalse(any("done-movie" in line or "membership" in line for line in lines))


def make_result(title, overview="A long enough overview describing the film in detail.", poster_path="/p.jpg"):
    return {"title": title, "release_date": "", "overview": overview, "poster_path": poster_path}


class TestRunEndToEnd(unittest.TestCase):
    def write_fixture(self, outdir):
        rows = [
            make_row(**{
                "Handle": "raw-resale", "Title": "Bambi", "Vendor": "DVD",
                "Option1 Name": "Genre", "Option1 Value": "Comedy",
            }),
            make_row(**{
                "Handle": "done-movie", "Title": "Totally Fictional Movie XYZ",
                GENRE_COLUMN: "drama",
            }),
        ]
        path = outdir / "export.csv"
        write_csv(path, FIELDNAMES, rows)
        return path

    def fetch_fn(self, query, year):
        if query == "Bambi":
            return {"results": [make_result("Bambi")]}
        return {"results": []}

    def test_full_run_chains_reformat_tmdb_and_picker(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            input_path = self.write_fixture(outdir)
            lines = []

            result = run(
                input_path, outdir,
                fetch_fn=self.fetch_fn, sleep_fn=NO_SLEEP, log_fn=lines.append,
            )

            self.assertEqual(result["reformat"]["resale"], 1)
            self.assertEqual(result["reformat"]["done"], 1)
            self.assertEqual(result["tmdb"]["review"], 1)
            self.assertEqual(result["picker"]["products"], 1)

            for name in [
                "reformatted.csv", "reformat-review.csv", "tmdb-filled.csv",
                "tmdb-needs-review.csv", "tmdb-changed.csv",
                "tmdb-changed-before.csv", "tmdb-changes.html",
                "tmdb-review-picker.html",
            ]:
                self.assertTrue((outdir / name).exists(), f"missing {name}")

            joined = "\n".join(lines)
            self.assertIn("== Stage 1: reformat ==", joined)
            self.assertIn("== Stage 2: TMDB fill ==", joined)
            self.assertIn("== Stage 3: review picker ==", joined)

    def test_skip_tmdb_stops_after_stage_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            input_path = self.write_fixture(outdir)
            lines = []

            result = run(input_path, outdir, skip_tmdb=True, log_fn=lines.append)

            self.assertIsNone(result["tmdb"])
            self.assertIsNone(result["picker"])
            self.assertTrue((outdir / "reformatted.csv").exists())
            self.assertFalse((outdir / "tmdb-filled.csv").exists())
            self.assertIn("skipped (--skip-tmdb)", "\n".join(lines))

    def test_missing_api_key_without_fetch_fn_skips_tmdb(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            input_path = self.write_fixture(outdir)
            lines = []

            result = run(input_path, outdir, api_key=None, log_fn=lines.append)

            self.assertIsNone(result["tmdb"])
            self.assertFalse((outdir / "tmdb-filled.csv").exists())
            self.assertIn("TMDB_API_KEY not set", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
