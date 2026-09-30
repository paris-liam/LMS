import ast
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import CatalogError
from catalog.libib import fix
from catalog.libib.fix import apply_report, confirmed_remaps, drift_ready_rows, drift_targets, read_ready

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
        for name in ("def login(", "def sync_item(", "def ensure_rental_library_scope(", "def set_call_number(",
                     'row.get("old_call_number")'):
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


class TestCallNumberRemap(unittest.TestCase):
    DRIFT = [{"handle": "a", "field": "call_number", "shopify": "90000001", "libib": "191-AAA-001A"},
             {"handle": "a", "field": "poster", "shopify": "https://x", "libib": "unconfirmed"},
             {"handle": "b", "field": "call_number", "shopify": "90000002", "libib": "191-BBB-001A"},
             {"handle": "c", "field": "call_number", "shopify": "90000003", "libib": "00112378"}]
    MAP = [{"handle": "a", "old_barcode": "191-AAA-001A", "new_barcode": "90000001"},
           {"handle": "b", "old_barcode": "191-BBB-001A", "new_barcode": "90000999"},  # new number disagrees
           {"handle": "z", "old_barcode": "00112378", "new_barcode": "90000003"}]      # someone else's pair

    def test_only_an_exact_handle_old_new_pair_is_confirmed(self):
        self.assertEqual(confirmed_remaps(self.DRIFT, self.MAP), {"a": "191-AAA-001A"})

    def test_confirmed_remaps_become_fixable(self):
        fields, manual = drift_targets(self.DRIFT, {"a": "191-AAA-001A"})
        self.assertEqual(fields, {"a": {"call_number", "poster"}})
        self.assertEqual(manual, ["b", "c"])

    def test_ready_rows_carry_the_old_call_number(self):
        rows_by_handle = {"a": rental("a", "90000001"), "d": rental("d", "04444444")}
        ready = drift_ready_rows({"a": {"call_number"}, "d": {"title"}}, rows_by_handle, {}, {"a": "191-AAA-001A"})
        self.assertEqual({r["call_number"]: r["old_call_number"] for r in ready},
                         {"90000001": "191-AAA-001A", "04444444": ""})


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


class SyncWithRetriesTests(unittest.TestCase):
    def run_with(self, outcomes):
        calls, pauses = [], []

        def sync(page, row):
            calls.append(row)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        result = fix.sync_with_retries(sync, "page", {"call_number": "1"}, pause=lambda: pauses.append(1))
        return result, len(calls), len(pauses)

    def test_success_first_time_is_not_retried(self):
        self.assertEqual(self.run_with([("updated", "updated", "ok")]), (("updated", "updated", "ok"), 1, 0))

    def test_error_then_success_is_retried(self):
        result, calls, pauses = self.run_with([("error", "error", "no item found"), ("updated", "skipped", "ok")])
        self.assertEqual((result, calls, pauses), (("updated", "skipped", "ok"), 2, 1))

    def test_exception_is_retried_and_last_error_reported(self):
        result, calls, pauses = self.run_with([TimeoutError("slow"), ("error", "error", "page did not load"),
                                               ("skipped", "error", "could not reopen item")])
        self.assertEqual((result, calls, pauses), (("skipped", "error", "could not reopen item"), 3, 2))


if __name__ == "__main__":
    unittest.main()
