import csv
import json
import tempfile
import unittest
from pathlib import Path

from catalog.audit.findings import AUTO_FIX, MANUAL, PICKER
from catalog.audit.run import build_report, collect_autofix, run_audit, write_outputs
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.runs import COMPLETE_MARKER
from catalog.shopify.snapshot import blank_row
from catalog.tmdb.match import POSTER_BASE_URL


def movie(**overrides):
    base = blank_row()
    base.update({
        "Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
        "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
        "Image Src": "https://cdn/r.jpg", "Image Alt Text": "Rushmore poster",
        "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0.00",
        "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
        "Variant Count": "1", GENRE_METAFIELD: "comedy",
    })
    base.update(overrides)
    return base


def tmdb(title, year, poster="/p.jpg", overview="An overview.", popularity=5):
    return {"title": title, "release_date": f"{year}-01-01", "poster_path": poster,
            "overview": overview, "genre_ids": [], "popularity": popularity}


def fetcher(by_title, calls=None):
    def fetch(query, year):
        if calls is not None:
            calls.append(query)
        return {"results": by_title.get(query, [])}
    return fetch


def rules_for(result, handle):
    return {(f.rule, f.field, f.bucket) for f in result.findings if f.handle == handle}


class TestContentStep(unittest.TestCase):
    def test_confident_match_autofills_poster_and_alt(self):
        row = movie(**{"Image Src": "", "Image Alt Text": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998)]}))
        changes = result.autofix["rushmore-vhs-rental"]["changes"]
        self.assertEqual(changes["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(changes["Image Alt Text"], "Rushmore (1998) poster")
        self.assertEqual(result.review, [])

    def test_confident_match_autofills_description(self):
        row = movie(**{"Body (HTML)": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998, overview="A precocious teen.")]}))
        self.assertEqual(result.autofix["rushmore-vhs-rental"]["changes"]["Body (HTML)"], "<p>A precocious teen.</p>")

    def test_confident_match_without_poster_goes_to_unmatched(self):
        row = movie(**{"Image Src": "", "Image Alt Text": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998, poster="")]}))
        self.assertEqual(result.review[0]["Kind"], "unmatched")
        self.assertIn(("poster-missing", "Image Src", PICKER), rules_for(result, "rushmore-vhs-rental"))

    def test_ambiguous_goes_to_ambiguous_queue(self):
        row = movie(Title="Mandela", **{"Image Src": "", "Image Alt Text": "", GENRE_METAFIELD: ""},
                    Tags="Rental, VHS, Drama", **{"Option1 Value": "Drama"})
        result = run_audit([row], {}, fetcher({"Mandela": [tmdb("Mandela", 1996), tmdb("Mandela", 1987)]}))
        self.assertEqual(len(result.review), 1)
        entry = result.review[0]
        self.assertEqual(entry["Kind"], "ambiguous")
        self.assertEqual(set(entry), {"Handle", "Title", "Vendor", "Genre", "Tags", "Kind", "Reason"})

    def test_no_match_goes_to_unmatched_queue(self):
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, fetcher({}))
        self.assertEqual(result.review[0]["Kind"], "unmatched")

    def test_request_failure_is_manual_and_not_queued(self):
        def boom(query, year):
            raise OSError("down")
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, boom)
        self.assertIn(("tmdb-request-failed", "Image Src", MANUAL), rules_for(result, "rushmore-vhs-rental"))
        self.assertEqual(result.review, [])

    def test_queued_handle_is_not_searched_again(self):
        calls = []
        registry = {"rushmore-vhs-rental": {"batch": "ambiguous-queue", "status": "queued"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}, calls))
        self.assertEqual(calls, [])
        self.assertEqual(result.review, [])
        finding = [f for f in result.findings if f.rule == "poster-missing"][0]
        self.assertEqual((finding.bucket, finding.detail), (PICKER, "already queued in ambiguous-queue"))

    def test_skipped_handle_is_client_skipped(self):
        registry = {"rushmore-vhs-rental": {"batch": "q", "status": "skipped"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}))
        self.assertIn(("client-skipped", "Image Src", MANUAL), rules_for(result, "rushmore-vhs-rental"))

    def test_legacy_resolved_but_still_missing(self):
        registry = {"rushmore-vhs-rental": {"batch": "q", "status": "resolved"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}))
        finding = [f for f in result.findings if f.rule == "applied-but-missing"][0]
        self.assertIn("old pipeline", finding.detail)

    def test_multi_variant_skips_tmdb(self):
        calls = []
        run_audit([movie(**{"Image Src": "", "Variant Count": "2"})], {}, fetcher({}, calls))
        self.assertEqual(calls, [])

    def test_skip_tmdb_lists_picker_findings_without_review_entries(self):
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, None)
        finding = [f for f in result.findings if f.rule == "poster-missing"][0]
        self.assertEqual((finding.bucket, finding.detail), (PICKER, "not matched (--skip-tmdb)"))
        self.assertEqual(result.review, [])


class TestRegistryStep(unittest.TestCase):
    def test_visible_fix_is_promoted(self):
        registry = {"rushmore-vhs-rental": {"status": "applied", "run": "r1", "values": {"Image Src": "u"}}}
        result = run_audit([movie()], registry, None)
        self.assertEqual(result.promoted, ["rushmore-vhs-rental"])
        self.assertEqual(registry["rushmore-vhs-rental"]["status"], "resolved")

    def test_invisible_fix_is_applied_but_missing(self):
        registry = {"rushmore-vhs-rental": {"status": "applied", "run": "r1", "values": {"Body (HTML)": "<p>New.</p>"}}}
        result = run_audit([movie()], registry, None)
        finding = [f for f in result.findings if f.rule == "applied-but-missing"][0]
        self.assertIn("r1", finding.detail)


class TestCollectAutofix(unittest.TestCase):
    def test_merges_fields_and_rules(self):
        result = run_audit([movie(Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor", GENRE_METAFIELD: ""})], {}, None)
        entry = result.autofix["rushmore-vhs-rental"]
        self.assertEqual(entry["changes"]["Tags"], "Rental, VHS, Horror")
        self.assertEqual(entry["changes"][GENRE_METAFIELD], "horror")
        self.assertEqual(set(entry["rules"]), {"genre-alias", "option1-genre", "genre-metafield-sync"})

    def test_conflicting_values_raise(self):
        from catalog.audit.findings import Finding
        a = Finding("h", "t", "Rental", "r1", "Vendor", "", "VHS", AUTO_FIX)
        b = Finding("h", "t", "Rental", "r2", "Vendor", "", "DVD", AUTO_FIX)
        with self.assertRaises(ValueError):
            collect_autofix([a, b])


class TestOutputs(unittest.TestCase):
    def test_writes_every_file_and_marks_complete_last(self):
        rows = [movie(), movie(Handle="bad", Tags="VHS, Comedy", **{"Variant Barcode": "1"})]
        result = run_audit(rows, {}, None)
        report = build_report(result, source="export test.csv", audited=2,
                              excluded={"archived": 3}, tmdb_status="skipped (--skip-tmdb)")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_outputs(run_dir, rows, result, report)
            names = sorted(p.name for p in run_dir.iterdir())
            self.assertEqual(names, ["autofix.json", "findings.csv", "review.json", COMPLETE_MARKER, "snapshot.json"])
            with open(run_dir / "findings.csv", newline="", encoding="utf-8") as f:
                found = list(csv.DictReader(f))
            self.assertTrue(all(r["handle"] == "bad" for r in found))
            self.assertEqual(json.loads((run_dir / "review.json").read_text(encoding="utf-8")), [])
        self.assertIn("type-missing", report)
        self.assertIn("archived: 3", report)
        self.assertIn("skipped (--skip-tmdb)", report)


if __name__ == "__main__":
    unittest.main()
