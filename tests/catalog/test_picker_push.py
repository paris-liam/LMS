import contextlib
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest import mock

from catalog import config
from catalog.cli import build_parser, main
from catalog.core import log
from catalog.picker import command
from catalog.picker.push import new_entries_by_queue


# Approval codes are fingerprints of the exact change list (tested in
# test_plan); here every plan is approved with the fixed code "ok".
_approval = unittest.mock.patch("catalog.core.plan.fingerprint", return_value="ok")


def setUpModule():
    _approval.start()


def tearDownModule():
    _approval.stop()


def entry(handle, kind="ambiguous", title="The Thing", tags="Rental, VHS, Horror"):
    return {"Handle": handle, "Title": title, "Vendor": "VHS", "Genre": "horror",
            "Tags": tags, "Kind": kind, "Reason": "r"}


def fetch(query, year):
    return {"results": [{"id": 1, "title": query, "release_date": "1982-01-01",
                         "poster_path": "/p.jpg", "overview": "Overview."}]}


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class TestNewEntries(unittest.TestCase):
    def test_groups_by_type_not_by_kind_and_skips_known_and_repeated_handles(self):
        review = [entry("a"), entry("b", "unmatched"), entry("a"), entry("c"),
                  entry("f", tags="Floor Sale, DVD"), entry("u", tags="DVD")]
        grouped = new_entries_by_queue(review, {"c": {"status": "resolved"}})
        self.assertEqual([e["Handle"] for e in grouped["rentals"]], ["a", "b"])
        self.assertEqual([e["Handle"] for e in grouped["floor-sale-01"]], ["f"])
        self.assertEqual([e["Handle"] for e in grouped["untyped"]], ["u"])

    def test_floor_sales_fill_groups_of_100_continuing_the_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / "floor-sale-01.products.json").write_text(json.dumps([{"handle": "x"}] * 100))
            (data / "floor-sale-02.products.json").write_text(json.dumps([{"handle": "y"}] * 99))
            review = [entry(f"f{i}", tags="Floor Sale") for i in range(102)]
            grouped = new_entries_by_queue(review, {}, tmp)
        self.assertEqual({k: len(v) for k, v in grouped.items()}, {"floor-sale-02": 1, "floor-sale-03": 100, "floor-sale-04": 1})

    def test_first_floor_sale_group_is_01(self):
        review = [entry(f"f{i}", tags="Floor Sale") for i in range(101)]
        grouped = new_entries_by_queue(review, {})
        self.assertEqual({k: len(v) for k, v in grouped.items()}, {"floor-sale-01": 100, "floor-sale-02": 1})


class TestPushCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        run = self.runs / "2026-09-25"
        run.mkdir(parents=True)
        (run / "review.json").write_text(json.dumps([entry("a"), entry("b", "unmatched", tags="Floor Sale")]), encoding="utf-8")
        (run / "run-report.txt").write_text("done\n", encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["picker", "push", "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "-q", *extra])

    def test_dry_run_writes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_push_command(self.args("--dry-run"), fetch_fn=fetch)
        self.assertEqual(code, 0)
        self.assertFalse(self.picker.exists())

    def test_push_refuses_without_a_terminal(self):
        err = io.StringIO()
        argv = ["picker", "push", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "-q"]
        with mock.patch.dict("os.environ", {"TMDB_API_KEY": "k"}), mock.patch("sys.stdin", FakeStdin(tty=False)), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("--approve", err.getvalue())
        self.assertFalse(self.picker.exists())

    def test_yes_appends_to_rentals_and_floor_sale_and_registers(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--approve", "ok", "--no-git-sync"), fetch_fn=fetch)
        registry = json.loads((self.picker / "data" / "_handle-index.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["a"], {"batch": "rentals", "status": "queued"})
        self.assertEqual(registry["b"], {"batch": "floor-sale-01", "status": "queued"})
        self.assertTrue((self.picker / "rentals" / "index.html").exists())
        self.assertTrue((self.picker / "floor-sale-01" / "index.html").exists())
        self.assertTrue((self.picker / "index.html").exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_answer_y_in_a_terminal_proceeds(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--no-git-sync"), fetch_fn=fetch, stdin=FakeStdin("y\n"))
        self.assertTrue((self.picker / "data" / "_handle-index.json").exists())

    def test_second_push_has_nothing_to_do_and_needs_no_key(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--approve", "ok", "--no-git-sync"), fetch_fn=fetch)
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = command.run_push_command(self.args("--no-git-sync"), stdin=FakeStdin(tty=False))
        self.assertEqual(code, 0)

    def test_picker_dir_outside_the_repo_skips_git_sync(self):
        calls = []
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--approve", "ok"), fetch_fn=fetch,
                                     sync_fn=lambda *a, **k: calls.append(a) or {"synced": True})
        self.assertEqual(calls, [])

    def test_missing_key_fails_before_writing(self):
        err = io.StringIO()
        argv = ["picker", "push", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "-q", "--approve", "ok"]
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(config, "ENV_FILE", Path("/nonexistent/.env")), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("TMDB_API_KEY", err.getvalue())
        self.assertFalse(self.picker.exists())


if __name__ == "__main__":
    unittest.main()
