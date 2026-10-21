import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

from catalog.backup.compare import compare_exports
from catalog.cli import build_parser


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


class CompareExportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def make(self, name, header, rows):
        return write_csv(self.dir / name, header, rows)

    def test_identical_files_have_no_differences(self):
        header = ["Handle", "Title", "Vendor"]
        rows = [["a", "Alpha", "DVD"], ["a", "", ""], ["b", "Beta", "VHS"]]
        ours = self.make("ours.csv", header, rows)
        theirs = self.make("theirs.csv", header, rows)
        self.assertEqual(compare_exports(ours, theirs, set()), [])

    def test_reports_header_and_value_differences(self):
        ours = self.make("ours.csv", ["Handle", "Title", "Extra"], [["a", "Alpha", "x"]])
        theirs = self.make("theirs.csv", ["Handle", "Title", "Vendor"], [["a", "Alpho", "DVD"]])
        out = compare_exports(ours, theirs, set())
        self.assertIn("Extra", out[0])
        self.assertIn("Vendor", out[1])
        self.assertIn("a row 1 Title: ours=Alpha theirs=Alpho", out)

    def test_ignores_listed_columns(self):
        header = ["Handle", "Title", "Inventory"]
        ours = self.make("ours.csv", header, [["a", "Alpha", "1"]])
        theirs = self.make("theirs.csv", header, [["a", "Alpha", "9"]])
        self.assertEqual(len(compare_exports(ours, theirs, set())), 1)
        self.assertEqual(compare_exports(ours, theirs, {"Inventory"}), [])

    def test_reports_missing_handles_both_ways(self):
        header = ["Handle", "Title"]
        ours = self.make("ours.csv", header, [["a", "A"], ["only-ours", "O"]])
        theirs = self.make("theirs.csv", header, [["a", "A"], ["only-theirs", "T"]])
        out = compare_exports(ours, theirs, set())
        self.assertTrue(any("only-ours" in line and "missing from theirs" in line for line in out))
        self.assertTrue(any("only-theirs" in line and "missing from ours" in line for line in out))

    def test_caps_output_at_200_lines_plus_count(self):
        header = ["Handle", "Title"]
        ours = self.make("ours.csv", header, [[f"h{i}", "x"] for i in range(300)])
        theirs = self.make("theirs.csv", header, [[f"h{i}", "y"] for i in range(300)])
        out = compare_exports(ours, theirs, set())
        self.assertEqual(len(out), 201)
        self.assertIn("300", out[-1])

    def test_row_count_difference_for_one_handle(self):
        header = ["Handle", "Title"]
        ours = self.make("ours.csv", header, [["a", "A"], ["a", "extra"]])
        theirs = self.make("theirs.csv", header, [["a", "A"]])
        out = compare_exports(ours, theirs, set())
        self.assertTrue(any("a row 2" in line for line in out))


class CompareCommandTests(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            a = write_csv(d / "a.csv", ["Handle", "Title"], [["h", "x"]])
            same = write_csv(d / "same.csv", ["Handle", "Title"], [["h", "x"]])
            diff = write_csv(d / "diff.csv", ["Handle", "Title"], [["h", "y"]])

            def run(*argv):
                args = build_parser().parse_args(["backup-compare", *argv])
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    code = args.func(args)
                return code, buf.getvalue()

            self.assertEqual(run(str(a), str(same))[0], 0)
            code, text = run(str(a), str(diff))
            self.assertEqual(code, 1)
            self.assertIn("ours=x theirs=y", text)
            self.assertEqual(run(str(a), str(diff), "--ignore", "Title", "--ignore", "Other")[0], 0)


if __name__ == "__main__":
    unittest.main()
