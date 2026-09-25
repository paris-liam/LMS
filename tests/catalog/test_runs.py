import tempfile
import unittest
from datetime import date
from pathlib import Path

from catalog.core.runs import COMPLETE_MARKER, list_runs, new_run, resolve_run
from catalog.errors import NoRunError


def complete(path: Path) -> Path:
    (path / COMPLETE_MARKER).write_text("done\n", encoding="utf-8")
    return path


class TestRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name) / "runs"

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_run_uses_the_date(self):
        path = new_run(self.runs, date(2026, 9, 25))
        self.assertEqual(path.name, "2026-09-25")
        self.assertTrue(path.is_dir())

    def test_second_run_same_day_gets_a_suffix(self):
        new_run(self.runs, date(2026, 9, 25))
        self.assertEqual(new_run(self.runs, date(2026, 9, 25)).name, "2026-09-25-2")
        self.assertEqual(new_run(self.runs, date(2026, 9, 25)).name, "2026-09-25-3")

    def test_latest_sorts_numerically_not_lexically(self):
        for _ in range(10):
            complete(new_run(self.runs, date(2026, 9, 25)))
        self.assertEqual(resolve_run(self.runs).name, "2026-09-25-10")

    def test_latest_prefers_later_date(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 26)))
        self.assertEqual(resolve_run(self.runs).name, "2026-09-26")

    def test_latest_skips_incomplete_runs(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        new_run(self.runs, date(2026, 9, 26))  # crashed: no run-report.txt
        self.assertEqual(resolve_run(self.runs).name, "2026-09-25")

    def test_ignores_dotfiles_and_foreign_dirs(self):
        self.runs.mkdir(parents=True)
        (self.runs / ".tmdb-cache.json").write_text("{}", encoding="utf-8")
        (self.runs / "scratch").mkdir()
        complete(new_run(self.runs, date(2026, 9, 25)))
        self.assertEqual([p.name for p in list_runs(self.runs)], ["2026-09-25"])

    def test_no_runs_raises_with_next_command(self):
        with self.assertRaises(NoRunError) as ctx:
            resolve_run(self.runs)
        self.assertIn("python3 -m catalog audit", str(ctx.exception))

    def test_explicit_run_id(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 26)))
        self.assertEqual(resolve_run(self.runs, "2026-09-25").name, "2026-09-25")

    def test_explicit_missing_run_id_raises(self):
        with self.assertRaises(NoRunError):
            resolve_run(self.runs, "2026-01-01")


if __name__ == "__main__":
    unittest.main()
