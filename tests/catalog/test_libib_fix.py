import ast
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import CatalogError
from catalog.libib import fix
from catalog.libib.fix import apply_report, drift_ready_rows, drift_targets, read_ready

BROWSER = Path(__file__).resolve().parents[2] / "catalog" / "libib" / "browser.py"


def rental(handle, barcode):
    return {"Handle": handle, "Title": handle.title(), "Body (HTML)": "<p>D.</p>", "Image Src": f"https://cdn/{handle}.jpg",
            "Variant Barcode": barcode, "Tags": "Rental, VHS", "Vendor": "VHS", GENRE_METAFIELD: "horror"}


def result(call, barcode="updated", content="updated", message="barcode: ok | content: changed: title"):
    return {"call_number": call, "barcode_status": barcode, "content_status": content, "message": message}


class TestBrowserModule(unittest.TestCase):
    def test_parses_holds_no_credentials_and_imports_nothing_old(self):
        source = BROWSER.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("LIBIB_PASSWORD", source)
        self.assertNotIn("@littlemoviestore.com", source)
        self.assertNotIn("from libib_fields", source)
        self.assertIn("from catalog.libib.fields import normalized_tag_set", source)
        for name in ("def login(", "def sync_item(", "def ensure_rental_library_scope("):
            self.assertIn(name, source)


class TestDrift(unittest.TestCase):
    def test_targets_split_fixable_from_manual(self):
        rows = [{"handle": "a", "field": "title"}, {"handle": "a", "field": "poster"},
                {"handle": "b", "field": "call_number"}, {"handle": "b", "field": "title"}]
        fields, manual = drift_targets(rows)
        self.assertEqual(fields, {"a": {"title", "poster"}})
        self.assertEqual(manual, ["b"])

    def test_ready_rows_only_upload_a_poster_for_poster_drift(self):
        rows_by_handle = {"a": rental("a", "01111111"), "b": rental("b", "02222222")}
        ready = drift_ready_rows({"a": {"poster"}, "b": {"title"}}, rows_by_handle, {"01111111": "/tmp/a.jpg"})
        self.assertEqual({r["call_number"]: r["image_path"] for r in ready}, {"01111111": "/tmp/a.jpg", "02222222": ""})


class TestApplyReport(unittest.TestCase):
    def test_outcomes(self):
        rows = {h: rental(h, c) for h, c in (("a", "01111111"), ("b", "02222222"), ("c", "03333333"))}
        state = {"a": {"status": "queued", "batch": "batch-0001"}, "b": {"status": "done"},
                 "c": {"status": "imported", "note": "old"}}
        results = [result("01111111", message="barcode: ok | content: changed: poster"),
                   result("02222222"),
                   result("03333333", barcode="error", message="Barcode already exists"),
                   result("09999999")]
        counts = apply_report(state, results, {"01111111": "a", "02222222": "b", "03333333": "c"}, rows)
        self.assertEqual(state["a"]["status"], "imported")
        self.assertEqual(state["a"]["poster_src"], "https://cdn/a.jpg")
        self.assertEqual(state["b"]["status"], "done")  # a drift fix never downgrades done
        self.assertEqual(state["c"]["status"], "needs-review")
        self.assertIn("Barcode already exists", state["c"]["note"])
        self.assertEqual(counts, {"ok": 2, "needs_review": 1, "posters": 1, "untracked": 1})


class TestReadReady(unittest.TestCase):
    def test_skips_rows_without_a_call_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ready.csv"
            path.write_text("call_number,title,description,tags,image_path\n01111111,A,,,\n,B,,,\n", encoding="utf-8")
            self.assertEqual([r["title"] for r in read_ready(path)], ["A"])


class TestRunFixer(unittest.TestCase):
    def test_run_fixer_without_playwright_names_the_venv(self):
        real_import = builtins.__import__

        def no_playwright(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=no_playwright):
            with self.assertRaises(CatalogError) as ctx:
                fix.run_fixer([{"call_number": "01111111"}], Path("/tmp/r.csv"), "e", "p", True)
        self.assertIn(".venv-libib", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
