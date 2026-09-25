import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.cli import build_parser, main
from catalog.core import log
from catalog.picker import command
from catalog.picker.push import new_entries_by_queue


def entry(handle, kind="ambiguous", title="The Thing"):
    return {"Handle": handle, "Title": title, "Vendor": "VHS", "Genre": "horror",
            "Tags": "Rental, VHS, Horror", "Kind": kind, "Reason": "r"}


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
    def test_groups_by_queue_and_skips_known_and_repeated_handles(self):
        review = [entry("a"), entry("b", "unmatched"), entry("a"), entry("c")]
        grouped = new_entries_by_queue(review, {"c": {"status": "resolved"}})
        self.assertEqual([e["Handle"] for e in grouped["ambiguous-queue"]], ["a"])
        self.assertEqual([e["Handle"] for e in grouped["unmatched-queue"]], ["b"])


class TestPushCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        run = self.runs / "2026-09-25"
        run.mkdir(parents=True)
        (run / "review.json").write_text(json.dumps([entry("a"), entry("b", "unmatched")]), encoding="utf-8")
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
        self.assertIn("--yes", err.getvalue())
        self.assertFalse(self.picker.exists())

    def test_yes_appends_to_both_queues_and_registers(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes", "--no-git-sync"), fetch_fn=fetch)
        registry = json.loads((self.picker / "data" / "_handle-index.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["a"], {"batch": "ambiguous-queue", "status": "queued"})
        self.assertEqual(registry["b"], {"batch": "unmatched-queue", "status": "queued"})
        self.assertTrue((self.picker / "ambiguous-queue" / "index.html").exists())
        self.assertTrue((self.picker / "unmatched-queue" / "index.html").exists())
        self.assertTrue((self.picker / "index.html").exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_answer_y_in_a_terminal_proceeds(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--no-git-sync"), fetch_fn=fetch, stdin=FakeStdin("y\n"))
        self.assertTrue((self.picker / "data" / "_handle-index.json").exists())

    def test_second_push_has_nothing_to_do_and_needs_no_key(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes", "--no-git-sync"), fetch_fn=fetch)
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = command.run_push_command(self.args("--no-git-sync"), stdin=FakeStdin(tty=False))
        self.assertEqual(code, 0)

    def test_picker_dir_outside_the_repo_skips_git_sync(self):
        calls = []
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes"), fetch_fn=fetch,
                                     sync_fn=lambda *a, **k: calls.append(a) or {"synced": True})
        self.assertEqual(calls, [])

    def test_missing_key_fails_before_writing(self):
        err = io.StringIO()
        argv = ["picker", "push", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "-q", "--yes"]
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("TMDB_API_KEY", err.getvalue())
        self.assertFalse(self.picker.exists())


if __name__ == "__main__":
    unittest.main()
