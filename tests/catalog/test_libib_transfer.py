import contextlib
import csv
import io
import json
import tempfile
import unittest
import unittest.mock
from collections import Counter
from datetime import date
from pathlib import Path
from unittest import mock

from catalog.cli import build_parser
from catalog.core import log
from catalog.libib import command, transfer
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS


# Approval codes are fingerprints of the exact change list (tested in
# test_plan); here every plan is approved with the fixed code "ok".
_approval = unittest.mock.patch("catalog.core.plan.fingerprint", return_value="ok")


def setUpModule():
    _approval.start()


def tearDownModule():
    _approval.stop()

BARCODE_HEADER = "id,item_type,barcode,title,collection,tags,call_number\n"


class TestMappingProblems(unittest.TestCase):
    def libib_matching(self, **overrides):
        auto = {"title": "Title", "description": "Description", "tags": "Tags", "price": "Price",
                "copies": "Copies", "call_number": "Call #", "publisher": "Publish Date"}
        auto.update(overrides)
        return [auto.get(c, "(no match found)") for c in LIBIB_MOVIE_COLUMNS]

    def test_libibs_auto_matching_of_our_header_is_accepted(self):
        self.assertEqual(transfer.mapping_problems(LIBIB_MOVIE_COLUMNS, self.libib_matching()), [])

    def test_a_data_column_on_the_wrong_field_is_refused(self):
        problems = transfer.mapping_problems(LIBIB_MOVIE_COLUMNS, self.libib_matching(call_number="DDC"))
        self.assertEqual(len(problems), 1)
        self.assertIn("call_number", problems[0])

    def test_a_different_number_of_matchers_is_refused(self):
        self.assertTrue(transfer.mapping_problems(LIBIB_MOVIE_COLUMNS, ["Title"]))


class TestHelpers(unittest.TestCase):
    def test_export_dir_numbers_a_second_folder_on_the_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = transfer.export_dir(tmp, date(2026, 9, 29))
            self.assertEqual(first.name, "2026-09-29")
            first.mkdir()
            self.assertEqual(transfer.export_dir(tmp, date(2026, 9, 29)).name, "2026-09-29-2")

    def test_verify_imported_sorts_ok_missing_and_duplicated(self):
        result = transfer.verify_imported(["a", "b", "c"], Counter({"a": 1, "c": 2}))
        self.assertEqual(result, {"ok": ["a"], "missing": ["b"], "duplicated": ["c"]})

    def test_call_counts_only_counts_the_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.csv"
            path.write_text(BARCODE_HEADER + "i1,movie,1,A,Rental Library,,111\n"
                            "i2,movie,2,B,Other,,222\n", encoding="utf-8")
            self.assertEqual(transfer.call_counts(path, "Rental Library"), Counter({"111": 1}))


class FakeLibib:
    """Stands in for the browser: holds call numbers, 'exports' them, 'imports' CSVs."""

    def __init__(self, calls=(), lag=0):
        self.calls = list(calls)
        self.uploads = []
        self.lag = lag          # polls before a background import lands
        self.pending = []

    def tick(self):
        self.lag -= 1
        if self.lag <= 0:
            self.calls += self.pending
            self.pending = []

    def exporter(self, email, password, dest):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        barcodes, library = dest / "barcodes_x.csv", dest / "library_x.csv"
        barcodes.write_text(BARCODE_HEADER + "".join(
            f"i{n},movie,{c},T,Rental Library,,{c}\n" for n, c in enumerate(self.calls)), encoding="utf-8")
        library.write_text("id,title,collection,call_number\n", encoding="utf-8")
        return barcodes, library

    def importer(self, email, password, csv_path, evidence_dir):
        rows = transfer.read_import_rows(csv_path)
        self.uploads.append([r["call_number"] for r in rows])
        if self.lag:
            self.pending += [r["call_number"] for r in rows]
        else:
            self.calls += [r["call_number"] for r in rows]


class TestImportCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sync, self.exports = root / "libib-sync", root / "exports"
        batch = self.sync / "batch-0001"
        batch.mkdir(parents=True)
        rows = [{c: "" for c in LIBIB_MOVIE_COLUMNS} | {"title": t, "call_number": c, "copies": "1"}
                for t, c in (("Jaws", "01111111"), ("Heat", "02222222"))]
        transfer.write_import_rows(batch / "import.csv", rows)
        (self.sync / "_state.json").write_text(json.dumps({
            "jaws": {"status": "queued", "batch": "batch-0001", "call_number": "01111111"},
            "heat": {"status": "queued", "batch": "batch-0001", "call_number": "02222222"}}), encoding="utf-8")
        self.env = mock.patch.dict("os.environ", {"LIBIB_EMAIL": "e", "LIBIB_PASSWORD": "p"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def run_import(self, libib, *extra):
        args = build_parser().parse_args(["libib", "import", "batch-0001", "--sync-dir", str(self.sync),
                                          "--exports-dir", str(self.exports), "-q", *extra])
        with contextlib.redirect_stdout(io.StringIO()):
            return command.run_import_command(args, exporter=libib.exporter, importer=libib.importer,
                                              sleep=lambda s: libib.tick())

    def state(self):
        return json.loads((self.sync / "_state.json").read_text(encoding="utf-8"))

    def test_dry_run_touches_nothing(self):
        libib = FakeLibib()
        self.assertEqual(self.run_import(libib, "--dry-run"), 0)
        self.assertEqual(libib.uploads, [])
        self.assertEqual(self.state()["jaws"]["status"], "queued")

    def test_imports_and_marks_what_the_after_export_confirms(self):
        libib = FakeLibib()
        self.assertEqual(self.run_import(libib, "--approve", "ok"), 0)
        self.assertEqual(libib.uploads, [["01111111", "02222222"]])
        self.assertEqual({h: e["status"] for h, e in self.state().items()}, {"jaws": "imported", "heat": "imported"})
        self.assertTrue(any(self.exports.iterdir()))  # the after-export is kept

    def test_next_step_hint_runs_the_fixer_with_the_libib_venv(self):
        libib = FakeLibib()
        with mock.patch.object(log, "summary") as summary:
            self.assertEqual(self.run_import(libib, "--approve", "ok"), 0)
        hints = [c.args[0] for c in summary.call_args_list if c.args[0].startswith("Next:")]
        self.assertEqual(hints, ["Next: .venv-libib/bin/python -m catalog libib fix batch-0001 --headless"])

    def test_a_rerun_never_imports_a_copy_libib_already_has(self):
        libib = FakeLibib(calls=["01111111"])  # a stopped earlier run got Jaws in
        self.assertEqual(self.run_import(libib, "--approve", "ok"), 0)
        self.assertEqual(libib.uploads, [["02222222"]])
        self.assertEqual(self.state()["jaws"]["status"], "imported")

    def test_waits_for_libibs_background_import(self):
        libib = FakeLibib(lag=2)
        self.assertEqual(self.run_import(libib, "--approve", "ok"), 0)
        self.assertEqual({e["status"] for e in self.state().values()}, {"imported"})

    def test_a_submitted_batch_is_verified_never_uploaded_again(self):
        libib = FakeLibib()
        libib.importer = lambda *a: None  # Libib has not processed it yet
        with mock.patch.object(transfer, "POLL_LIMIT_SECONDS", 0):
            self.assertEqual(self.run_import(libib, "--approve", "ok"), 1)
        self.assertTrue((self.sync / "batch-0001" / transfer.SUBMITTED_MARKER).exists())
        later = FakeLibib(calls=["01111111", "02222222"])  # it landed meanwhile
        self.assertEqual(self.run_import(later, "--approve", "ok"), 0)
        self.assertEqual(later.uploads, [])
        self.assertEqual({e["status"] for e in self.state().values()}, {"imported"})

    def test_an_import_libib_did_not_take_stays_queued_and_fails(self):
        libib = FakeLibib()
        libib.importer = lambda *a: None  # Libib accepted nothing
        with mock.patch.object(transfer, "POLL_LIMIT_SECONDS", 40):
            self.assertEqual(self.run_import(libib, "--approve", "ok"), 1)
        self.assertEqual(self.state()["jaws"]["status"], "queued")

    def test_refuses_a_batch_with_nothing_queued(self):
        state = self.state()
        state["jaws"]["status"] = "imported"
        state["heat"]["status"] = "imported"
        (self.sync / "_state.json").write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(Exception):
            self.run_import(FakeLibib(), "--approve", "ok")


class TestExportCommand(unittest.TestCase):
    def test_writes_a_dated_folder(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict("os.environ", {"LIBIB_EMAIL": "e", "LIBIB_PASSWORD": "p"}):
            args = build_parser().parse_args(["libib", "export", "--exports-dir", tmp, "-q"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(command.run_export_command(args, exporter=FakeLibib(["1"]).exporter), 0)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)
        log.setup_logging(None, 0, io.StringIO())


if __name__ == "__main__":
    unittest.main()


class FullFakeLibib:
    """Libib for `libib sync`: items keyed by call number, full-shape exports."""

    def __init__(self, items):
        self.items = dict(items)   # call_number -> {"title", "tags", "description"}
        self.uploads, self.fixed = [], []

    def exporter(self, email, password, dest):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        b, c = dest / "barcodes_x.csv", dest / "library_x.csv"
        with open(b, "w", newline="", encoding="utf-8") as fb, open(c, "w", newline="", encoding="utf-8") as fc:
            wb = csv.writer(fb)
            wc = csv.writer(fc)
            wb.writerow(["id", "item_type", "barcode", "title", "collection", "tags", "call_number"])
            wc.writerow(["id", "item_type", "title", "collection", "description", "call_number"])
            for n, (call, it) in enumerate(sorted(self.items.items())):
                wb.writerow([f"i{n}", "movie", call, it["title"], "Rental Library", it["tags"], call])
                wc.writerow([f"i{n}", "movie", it["title"], "Rental Library", it["description"], call])
        return b, c

    def importer(self, email, password, csv_path, evidence_dir):
        rows = transfer.read_import_rows(csv_path)
        self.uploads.append([r["call_number"] for r in rows])
        for r in rows:
            self.items[r["call_number"]] = {"title": r["title"], "tags": r["tags"], "description": r["description"]}

    def fixer(self, rows, report_path, email, password, headless):
        self.fixed.append([r["call_number"] for r in rows])
        for r in rows:
            self.items[r["call_number"]].update(title=r["title"], tags=r["tags"], description=r["description"])
        return [{"call_number": r["call_number"], "barcode_status": "skipped", "content_status": "updated",
                 "message": "content: changed: title, poster"} for r in rows]


class TestSyncCommand(unittest.TestCase):
    def setUp(self):
        from catalog.core.columns import GENRE_METAFIELD
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.sync, self.exports = root / "runs", root / "libib-sync", root / "exports"
        run = self.runs / "2026-09-29"
        run.mkdir(parents=True)
        self.sync.mkdir()

        def rental(handle, call, title):
            return {"Handle": handle, "Title": title, "Body (HTML)": f"<p>{title}.</p>",
                    "Image Src": f"https://cdn/{handle}.jpg",
                    "Variant Barcode": call, "Variant Price": "0", "Tags": "Rental, VHS, Horror", "Vendor": "VHS",
                    GENRE_METAFIELD: "horror", "Status": "active"}
        (run / "snapshot.json").write_text(json.dumps([rental("jaws", "01111111", "Jaws"),
                                                        rental("heat", "02222222", "Heat")]), encoding="utf-8")
        (run / "run-report.txt").write_text("done\n", encoding="utf-8")
        (self.sync / "_state.json").write_text(json.dumps(
            {"jaws": {"status": "done", "call_number": "01111111"}}), encoding="utf-8")
        # Jaws is in Libib with a stale title; Heat is not in Libib yet.
        self.libib = FullFakeLibib({"01111111": {"title": "Jaws (old)", "tags": "vhs, horror",
                                                 "description": "Jaws."}})
        self.env = mock.patch.dict("os.environ", {"LIBIB_EMAIL": "e", "LIBIB_PASSWORD": "p"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def run_sync(self, *extra):
        args = build_parser().parse_args(["libib", "sync", "--runs-dir", str(self.runs), "--sync-dir", str(self.sync),
                                          "--exports-dir", str(self.exports), "-q", *extra])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = command.run_sync_command(args, exporter=self.libib.exporter, importer=self.libib.importer,
                                            fixer=self.libib.fixer, download=lambda url, path: None,
                                            sleep=lambda s: None)
        return code, out.getvalue()

    def test_dry_run_lists_every_change_and_touches_nothing(self):
        code, out = self.run_sync("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("title: 'Jaws (old)' -> 'Jaws'", out)
        self.assertIn("02222222 Heat — NEW Libib item", out)
        self.assertIn("Approval code:", out)
        self.assertEqual((self.libib.uploads, self.libib.fixed), ([], []))

    def test_approved_run_fixes_imports_and_confirms(self):
        code, _ = self.run_sync("--approve", "ok")
        self.assertEqual(code, 0)
        self.assertEqual(self.libib.uploads, [["02222222"]])
        self.assertIn(["01111111"], self.libib.fixed)          # the drift fix
        self.assertIn(["02222222"], self.libib.fixed)          # the new batch
        self.assertEqual(self.libib.items["01111111"]["title"], "Jaws")
        state = json.loads((self.sync / "_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["heat"]["status"], "done")       # promoted by the confirming diff


class TestSelftestCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sync = Path(self.tmp.name)
        (self.sync / "_state.json").write_text(json.dumps({"jaws": {"status": "done", "call_number": "01111111"}}),
                                               encoding="utf-8")
        self.env = mock.patch.dict("os.environ", {"LIBIB_EMAIL": "e", "LIBIB_PASSWORD": "p"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def run_selftest(self, results):
        from catalog.libib.selftest import Check
        seen = []

        def runner(email, password, call, evidence, headless, include_import):
            seen.append((call, include_import))
            return [Check(name, ok) for name, ok in results]
        args = build_parser().parse_args(["libib", "selftest", "--sync-dir", str(self.sync), "-q"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = command.run_selftest_command(args, runner=runner)
        return code, out.getvalue(), seen

    def test_all_steps_passing_exits_0_on_a_synced_item(self):
        code, out, seen = self.run_selftest([("login", True), ("exports", True)])
        self.assertEqual(code, 0)
        self.assertEqual(seen, [("01111111", True)])
        self.assertIn("OK: all 2 steps work", out)

    def test_any_failing_step_exits_1_and_says_which(self):
        code, out, _ = self.run_selftest([("login", True), ("copies panel", False)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL  copies panel", out)
