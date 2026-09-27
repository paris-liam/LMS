import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from catalog import config
from catalog.audit import command
from catalog.cli import build_parser, main
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.runs import COMPLETE_MARKER, list_runs, resolve_run

HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Option1 Name", "Option1 Value",
          "Variant Price", "Variant Barcode", "Variant Inventory Tracker", "Image Src", "Image Alt Text",
          GENRE_METAFIELD]


def product(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
            "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active", "Option1 Name": "Genre",
            "Option1 Value": "Comedy", "Variant Price": "0", "Variant Barcode": "01577790",
            "Variant Inventory Tracker": "shopify", "Image Src": "https://cdn/r.jpg",
            "Image Alt Text": "Rushmore poster", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


CATALOGUE = [
    product(),
    product(Handle="heat-vhs-rental", Title="Heat", Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor",
            GENRE_METAFIELD: "", "Variant Barcode": "02000000"}),
    product(Handle="jaws-dvd-rental", Title="Jaws", **{"Image Src": "", "Image Alt Text": "", "Variant Barcode": "03000000"}),
    product(Handle="dup-dvd-floor-sale", Title="Dup", Tags="Floor Sale, DVD, Drama", Vendor="DVD",
            **{"Option1 Value": "Drama", GENRE_METAFIELD: "drama", "Variant Price": "5", "Variant Barcode": "01577790"}),
    product(Handle="old-vhs-rental", Title="Old", Status="archived", **{"Variant Barcode": "04000000"}),
]


class TestAuditCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        self.export = root / "export.csv"
        with open(self.export, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(CATALOGUE)

    def tearDown(self):
        from catalog.core import log
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["audit", "--from-export", str(self.export), "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "-q", *extra])

    def fetch(self, query, year):
        if query == "Jaws":
            return {"results": [{"title": "Jaws", "release_date": "1975-06-20", "poster_path": "/jaws.jpg",
                                 "overview": "A shark.", "genre_ids": [], "popularity": 50}]}
        return {"results": []}

    def test_end_to_end_from_export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.args(), fetch_fn=self.fetch, today=date(2026, 9, 25))
        self.assertEqual(code, 0)
        run_dir = resolve_run(self.runs)
        self.assertEqual(run_dir.name, "2026-09-25")
        snapshot = json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot), 4)  # archived product excluded
        with open(run_dir / "findings.csv", newline="", encoding="utf-8") as f:
            rules = {(r["handle"], r["rule"]) for r in csv.DictReader(f)}
        self.assertIn(("heat-vhs-rental", "genre-alias"), rules)
        self.assertIn(("rushmore-vhs-rental", "rental-barcode-duplicate"), rules)
        self.assertNotIn(("dup-dvd-floor-sale", "rental-barcode-duplicate"), rules)
        autofix = json.loads((run_dir / "autofix.json").read_text(encoding="utf-8"))
        self.assertTrue(autofix["jaws-dvd-rental"]["changes"]["Image Src"].endswith("/jaws.jpg"))
        report = (run_dir / COMPLETE_MARKER).read_text(encoding="utf-8")
        self.assertIn("archived: 1", report)
        self.assertIn("1 fetches", report)
        self.assertTrue((run_dir / "audit.log").exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_skip_tmdb_needs_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.args("--skip-tmdb"), today=date(2026, 9, 25))
        self.assertEqual(code, 0)

    def test_missing_key_fails_before_reading_anything(self):
        err = io.StringIO()
        argv = ["audit", "--from-export", str(self.export), "--runs-dir", str(self.runs),
                "--picker-dir", str(self.picker)]
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(config, "ENV_FILE", Path("/nonexistent/.env")), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("TMDB_API_KEY", err.getvalue())
        self.assertEqual(list_runs(self.runs), [])  # no run folder left behind

    def test_interrupt_saves_cache_and_leaves_run_incomplete(self):
        calls = []

        def fetch(query, year):
            calls.append(query)
            raise KeyboardInterrupt

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            command.run_command(self.args(), fetch_fn=fetch, today=date(2026, 9, 25))
        run_dir = list_runs(self.runs)[0]
        self.assertFalse((run_dir / COMPLETE_MARKER).exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_registry_saved_only_when_promoted(self):
        self.picker.joinpath("data").mkdir(parents=True)
        registry_file = self.picker / "data" / "_handle-index.json"
        registry_file.write_text(json.dumps({"rushmore-vhs-rental": {
            "status": "applied", "run": "r0", "values": {"Image Src": "https://x"}}}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--skip-tmdb"), today=date(2026, 9, 25))
        saved = json.loads(registry_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["rushmore-vhs-rental"]["status"], "resolved")

    def test_api_path_uses_injected_reader(self):
        from catalog.shopify.export_reader import read_export
        rows = read_export(self.export)
        args = build_parser().parse_args(["audit", "--store", "dev.myshopify.com", "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "--skip-tmdb", "-q"])
        seen = []
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_api=lambda store: seen.append(store) or rows, today=date(2026, 9, 25))
        self.assertEqual(seen, ["dev.myshopify.com"])
        self.assertIn("api dev.myshopify.com", (resolve_run(self.runs) / COMPLETE_MARKER).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
