import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

import run as run_module
from columns import EXPORT_COLUMNS, TEMPLATE_COLUMNS

TEMPLATE_HEADER = TEMPLATE_COLUMNS + ["Format", "Genre 1", "Genre 2", "Genre 3", "Year", "Extra tags"]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def template_input_row(title, genre="Comedy", fmt="VHS", tags="Rental, VHS, Comedy"):
    row = {name: "" for name in TEMPLATE_HEADER}
    row.update({"Title": title, "Tags": tags, "Format": fmt, "Genre 1": genre, "Year": "1998"})
    return row


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fake_fetch(query, year):
    return {"results": [{"title": query, "release_date": "1998-01-01",
                         "poster_path": "/p.jpg",
                         "overview": "An overview that is long enough to count as a description."}]}


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # Ambiguous/unmatched rows now queue into tools/review-picker — point
        # every run_module.run() call in this test class at an isolated tmp
        # dir instead of the real repo's tools/review-picker by default.
        self.tools_dir = self.dir / "tools-review-picker"
        self._real_default_tools_dir = run_module.DEFAULT_TOOLS_DIR
        run_module.DEFAULT_TOOLS_DIR = self.tools_dir

    def tearDown(self):
        run_module.DEFAULT_TOOLS_DIR = self._real_default_tools_dir
        self.tmp.cleanup()

    def test_output_dir_is_derived_from_the_input_name(self):
        self.assertEqual(
            run_module.output_dir_for(Path("/x/products_export_1.csv")).name,
            "out-products_export_1",
        )

    def test_produces_upload_and_report_for_a_clean_template_batch(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        outdir = Path(result["outdir"])

        upload = read_csv(outdir / "upload.csv")
        self.assertEqual(result["shape"], "template")
        self.assertEqual(result["clean"], 1)
        self.assertEqual(list(upload[0]), TEMPLATE_COLUMNS)
        self.assertEqual(upload[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(upload[0]["Image Src"], "https://image.tmdb.org/t/p/w1280/p.jpg")
        self.assertTrue((outdir / "run-report.txt").exists())

    def test_broken_rows_land_in_issues_with_a_reason_and_the_original_columns(self):
        """A row missing genre/format/type/price still uploads (tagged
        Issue_*, see test_normalize.py); only genuinely bad data — here, a
        product tagged as both Rental and Floor Sale — still blocks."""
        path = self.dir / "batch.csv"
        good = template_input_row("Rushmore")
        bad = template_input_row("Mystery", tags="Rental, Floor Sale, VHS, Comedy")
        write_csv(path, TEMPLATE_HEADER, [good, bad])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        outdir = Path(result["outdir"])

        issues = read_csv(outdir / "issues.csv")
        self.assertEqual(result["issues"], 1)
        self.assertEqual(issues[0]["Title"], "Mystery")
        self.assertIn("tagged as both", issues[0]["Reason"])
        self.assertIn("Genre 1", issues[0])  # helper columns survive for editing
        self.assertEqual(len(read_csv(outdir / "upload.csv")), 1)

    def test_a_corrected_issues_file_is_a_valid_input(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER,
                  [template_input_row("Mystery", tags="Rental, Floor Sale, VHS, Comedy")])
        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)

        issues_path = Path(first["outdir"]) / "issues.csv"
        rows = read_csv(issues_path)
        rows[0]["Tags"] = "Rental, VHS, Comedy"
        write_csv(issues_path, list(rows[0]), rows)

        second = run_module.run(issues_path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        self.assertEqual(second["issues"], 0)
        self.assertEqual(second["clean"], 1)
        upload = read_csv(Path(second["outdir"]) / "upload.csv")
        self.assertEqual(upload[0]["Handle"], "mystery-vhs-rental")

    def test_unmatched_rows_are_queued_not_written_locally(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        result = run_module.run(
            path, fetch_fn=lambda q, y: {"results": []}, sleep_fn=lambda s: None
        )
        outdir = Path(result["outdir"])
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(result["unmatched_queued"], 1)
        self.assertFalse((outdir / "tmdb-unmatched.csv").exists())

        products_path = self.tools_dir / "data" / "unmatched-queue.products.json"
        products = json.loads(products_path.read_text(encoding="utf-8"))
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["title"], "Rushmore")
        self.assertEqual(products[0]["candidates"], [])  # no TMDB results -> manual-only card

    def test_unmatched_rows_dont_duplicate_a_product_with_multiple_reasons(self):
        """A product missing both a poster and an overview must still queue
        once, not once per reason — otherwise the operator fixes one row,
        re-runs, and finds a duplicate card waiting for them."""
        def no_poster_no_overview(query, year):
            return {"results": [{"title": query, "release_date": "1998-01-01",
                                 "poster_path": "", "overview": ""}]}

        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        result = run_module.run(
            path, fetch_fn=no_poster_no_overview, sleep_fn=lambda s: None
        )
        self.assertEqual(result["unmatched_queued"], 1)
        products_path = self.tools_dir / "data" / "unmatched-queue.products.json"
        products = json.loads(products_path.read_text(encoding="utf-8"))
        self.assertEqual(len(products), 1)

    def test_ambiguous_rows_are_queued_in_the_hosted_picker(self):
        def ambiguous(query, year):
            return {"results": [
                {"title": "The Thing", "release_date": "1982-01-01", "poster_path": "/a.jpg", "overview": "A."},
                {"title": "The Thing", "release_date": "2011-01-01", "poster_path": "/b.jpg", "overview": "B."},
            ]}

        path = self.dir / "batch.csv"
        row = template_input_row("The Thing", genre="Horror", fmt="DVD", tags="Rental, DVD, Horror")
        row["Year"] = ""
        write_csv(path, TEMPLATE_HEADER, [row])

        result = run_module.run(path, fetch_fn=ambiguous, sleep_fn=lambda s: None)
        self.assertEqual(result["ambiguous"], 1)
        self.assertEqual(result["ambiguous_queued"], 1)
        self.assertFalse((Path(result["outdir"]) / "review-picker.html").exists())
        self.assertTrue((self.tools_dir / "ambiguous-queue" / "index.html").exists())

    def test_a_handle_already_queued_is_not_added_again(self):
        """Re-running on data that overlaps a handle already sitting in the
        queue must not create a duplicate card for it."""
        def ambiguous(query, year):
            return {"results": [
                {"title": "The Thing", "release_date": "1982-01-01", "poster_path": "/a.jpg", "overview": "A."},
                {"title": "The Thing", "release_date": "2011-01-01", "poster_path": "/b.jpg", "overview": "B."},
            ]}

        path = self.dir / "batch.csv"
        row = template_input_row("The Thing", genre="Horror", fmt="DVD", tags="Rental, DVD, Horror")
        row["Year"] = ""
        write_csv(path, TEMPLATE_HEADER, [row])

        first = run_module.run(path, fetch_fn=ambiguous, sleep_fn=lambda s: None,
                                outdir=self.dir / "out-first")
        self.assertEqual(first["ambiguous_queued"], 1)

        second = run_module.run(path, fetch_fn=ambiguous, sleep_fn=lambda s: None,
                                 outdir=self.dir / "out-second")
        self.assertEqual(second["ambiguous"], 1)  # still seen this run...
        self.assertEqual(second["ambiguous_queued"], 0)  # ...but not re-queued

        products_path = self.tools_dir / "data" / "ambiguous-queue.products.json"
        products = json.loads(products_path.read_text(encoding="utf-8"))
        self.assertEqual(len(products), 1)

    def test_skip_tmdb_leaves_descriptions_empty_and_makes_no_requests(self):
        calls = []

        def counting(query, year):
            calls.append(query)
            return {"results": []}

        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])
        result = run_module.run(path, skip_tmdb=True, fetch_fn=counting, sleep_fn=lambda s: None)
        self.assertEqual(calls, [])
        upload = read_csv(Path(result["outdir"]) / "upload.csv")
        self.assertEqual(upload[0]["Body (HTML)"], "")

    def test_rerunning_over_its_own_upload_changes_nothing(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])
        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        first_upload = Path(first["outdir"]) / "upload.csv"
        first_text = first_upload.read_text(encoding="utf-8")

        second = run_module.run(first_upload, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        second_text = (Path(second["outdir"]) / "upload.csv").read_text(encoding="utf-8")

        self.assertEqual(second["issues"], 0)
        self.assertEqual(first_text, second_text)

    def test_a_taxonomy_word_in_extra_tags_round_trips_byte_identically(self):
        """An operator who put a genre word in Extra tags (client-guide-
        anticipated mistake) must not get a re-run that keeps changing the
        file: the Extra tags helper column has to reject taxonomy words the
        same way the Tags column does."""
        path = self.dir / "batch.csv"
        row = template_input_row("Rushmore")
        row["Extra tags"] = "Holiday"
        write_csv(path, TEMPLATE_HEADER, [row])

        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        first_upload = Path(first["outdir"]) / "upload.csv"
        first_text = first_upload.read_text(encoding="utf-8")

        second = run_module.run(first_upload, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        second_text = (Path(second["outdir"]) / "upload.csv").read_text(encoding="utf-8")

        self.assertEqual(second["issues"], 0)
        self.assertEqual(first_text, second_text)

    def test_an_unrecognised_header_fails_loudly(self):
        path = self.dir / "junk.csv"
        write_csv(path, ["Name", "Price"], [{"Name": "x", "Price": "1"}])
        with self.assertRaises(run_module.UnknownShapeError):
            run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)

    def test_rerunning_a_multi_genre_export_over_its_own_upload_changes_nothing(self):
        # Fix round 1: Option1 Value only ever carries genres[0] on output.
        # A second pass that consulted Option1 Value before Tags used to see
        # just that one genre and silently drop the rest. Regression test
        # for the resolve_genres union fix (formatting-scripts/resolve.py).
        header = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
                  "Tags", "Published", "Option1 Name", "Option1 Value",
                  "Variant Inventory Tracker", "Variant Inventory Qty",
                  "Variant Inventory Policy", "Variant Fulfillment Service",
                  "Variant Price", "Variant Barcode", "Image Src", "Image Position",
                  "Image Alt Text"]
        row = {name: "" for name in header}
        row.update({"Handle": "double-feature", "Title": "Double Feature", "Vendor": "DVD",
                    "Body (HTML)": "<p>A double feature.</p>",
                    "Tags": "Floor Sale, Action, Comedy", "Option1 Name": "Condition",
                    "Option1 Value": "Action, Comedy", "Variant Price": "9.99",
                    "Variant Barcode": "88302844",
                    "Image Src": "https://cdn.shopify.com/double-feature.jpg"})
        # Image Src / Body (HTML) are pre-filled so the TMDB stage is a
        # no-op (group already complete) — this test isolates the genre
        # union fix from unrelated TMDB-fill behaviour.
        path = self.dir / "multi-genre.csv"
        write_csv(path, header, [row])

        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        first_upload = Path(first["outdir"]) / "upload.csv"
        first_rows = read_csv(first_upload)
        self.assertEqual(first["issues"], 0)
        self.assertEqual(first_rows[0]["Tags"], "Floor Sale, DVD, Action, Comedy, Formatted")
        first_text = first_upload.read_text(encoding="utf-8")

        second = run_module.run(first_upload, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        second_text = (Path(second["outdir"]) / "upload.csv").read_text(encoding="utf-8")

        self.assertEqual(second["issues"], 0)
        self.assertEqual(first_text, second_text)

    def test_rerunning_an_export_row_tmdb_filled_with_no_image_changes_nothing(self):
        # Fix round 2: normalize._build_row used to default a blank Image
        # Position to "1" whenever Image Src was non-empty. An export row
        # with no image gets its Image Src filled by the TMDB stage, so
        # the *first* run leaves Image Position blank (normalize ran before
        # the fill) while a *second* run's normalize pass sees the now
        # non-empty Image Src and defaults Image Position to "1" — a
        # different upload.csv from the same input. Image Position must
        # only ever pass through the source value.
        header = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
                  "Tags", "Published", "Option1 Name", "Option1 Value",
                  "Variant Inventory Tracker", "Variant Inventory Qty",
                  "Variant Inventory Policy", "Variant Fulfillment Service",
                  "Variant Price", "Variant Barcode", "Image Src", "Image Position",
                  "Image Alt Text"]
        row = {name: "" for name in header}
        row.update({"Handle": "legend-of-zorro", "Title": "Legend of Zorro", "Vendor": "DVD",
                    "Tags": "Floor Sale, Action", "Option1 Name": "Condition",
                    "Option1 Value": "Standard", "Variant Price": "9.99",
                    "Variant Barcode": "88302842"})
        path = self.dir / "no-image.csv"
        write_csv(path, header, [row])

        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        first_upload = Path(first["outdir"]) / "upload.csv"
        first_rows = read_csv(first_upload)
        self.assertEqual(first["issues"], 0)
        self.assertNotEqual(first_rows[0]["Image Src"], "")  # TMDB filled it
        first_text = first_upload.read_text(encoding="utf-8")

        second = run_module.run(first_upload, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        second_text = (Path(second["outdir"]) / "upload.csv").read_text(encoding="utf-8")

        self.assertEqual(second["issues"], 0)
        self.assertEqual(first_text, second_text)

    def test_export_input_keeps_handles_and_barcodes(self):
        header = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
                  "Tags", "Published", "Option1 Name", "Option1 Value",
                  "Variant Inventory Tracker", "Variant Inventory Qty",
                  "Variant Inventory Policy", "Variant Fulfillment Service",
                  "Variant Price", "Variant Barcode", "Image Src", "Image Position",
                  "Image Alt Text"]
        row = {name: "" for name in header}
        row.update({"Handle": "legend-of-zorro", "Title": "Legend of Zorro", "Vendor": "DVD",
                    "Tags": "Floor Sale, Action", "Option1 Name": "Condition",
                    "Option1 Value": "Standard", "Variant Price": "9.99",
                    "Variant Barcode": "88302842"})
        path = self.dir / "export.csv"
        write_csv(path, header, [row])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        upload = read_csv(Path(result["outdir"]) / "upload.csv")
        self.assertEqual(result["shape"], "export")
        self.assertEqual(list(upload[0]), EXPORT_COLUMNS)
        self.assertEqual(upload[0]["Handle"], "legend-of-zorro")
        self.assertEqual(upload[0]["Variant Barcode"], "88302842")
        self.assertEqual(upload[0]["Option1 Value"], "Action")


class TestNoCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_cache_re_fetches_a_query_already_in_the_cache_file(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        calls = []

        def counting_fetch(query, year):
            calls.append(query)
            return fake_fetch(query, year)

        first = run_module.run(path, fetch_fn=counting_fetch, sleep_fn=lambda s: None)
        self.assertEqual(len(calls), 1)
        cache_path = Path(first["outdir"]) / run_module.CACHE_FILENAME
        self.assertTrue(cache_path.exists())

        # Re-run with --no-cache: even though the query is already cached,
        # it must be re-fetched.
        run_module.run(
            path, fetch_fn=counting_fetch, sleep_fn=lambda s: None, no_cache=True,
        )
        self.assertEqual(len(calls), 2)

    def test_no_cache_leaves_the_existing_cache_file_byte_identical(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        cache_path = Path(first["outdir"]) / run_module.CACHE_FILENAME
        before = cache_path.read_bytes()

        run_module.run(
            path, fetch_fn=fake_fetch, sleep_fn=lambda s: None, no_cache=True,
        )
        after = cache_path.read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
