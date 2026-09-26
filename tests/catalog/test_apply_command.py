import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.apply import command
from catalog.cli import build_parser, main
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD


def row(handle, **overrides):
    base = {"Handle": handle, "Title": handle.title(), "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Rental, VHS, Comedy", "Vendor": "VHS", "Option1 Name": "Genre", "Option1 Value": "Comedy",
            "Variant Price": "0.00", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class TestApplyCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        self.run = self.runs / "2026-09-25"
        self.run.mkdir(parents=True)
        (self.run / "snapshot.json").write_text(json.dumps([row("jaws"), row("heat", Vendor="bluray"), row("rocky")]),
                                                encoding="utf-8")
        (self.run / "autofix.json").write_text(json.dumps(
            {"heat": {"changes": {"Vendor": "Blu-Ray"}, "rules": ["format-alias"]}}), encoding="utf-8")
        (self.run / "run-report.txt").write_text("done\n", encoding="utf-8")
        (self.picker / "data").mkdir(parents=True)
        (self.picker / "batches.json").write_text(json.dumps([{"batch_id": "ambiguous-queue", "total": 2}]),
                                                  encoding="utf-8")
        (self.picker / "data" / "ambiguous-queue.json").write_text(json.dumps([
            {"handle": "jaws", "choice": "tmdb", "poster_path": "/jaws.jpg", "overview": "A shark."},
            {"handle": "rocky", "choice": "skip"},
        ]), encoding="utf-8")
        (self.picker / "data" / "_handle-index.json").write_text(json.dumps({
            "jaws": {"batch": "ambiguous-queue", "status": "queued"},
            "rocky": {"batch": "ambiguous-queue", "status": "queued"},
        }), encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "--local-picks", "-q", *extra])

    def registry(self):
        return json.loads((self.picker / "data" / "_handle-index.json").read_text(encoding="utf-8"))

    def test_dry_run_writes_the_plan_list_only(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--dry-run"))
        self.assertTrue((self.run / "apply-plan.csv").exists())
        self.assertFalse((self.run / "import").exists())
        self.assertEqual(self.registry()["jaws"]["status"], "queued")

    def test_yes_writes_import_files_and_updates_registry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
        names = sorted(p.name for p in (self.run / "import").iterdir())
        self.assertEqual(names, ["description.csv", "image.csv", "vendor.csv"])
        registry = self.registry()
        self.assertEqual(registry["jaws"]["status"], "applied")
        self.assertEqual(registry["jaws"]["run"], "2026-09-25")
        self.assertIn("Image Src", registry["jaws"]["values"])
        self.assertEqual(registry["rocky"]["status"], "skipped")
        self.assertNotIn("heat", registry)  # auto-fixes are not tracked in the registry
        with open(self.run / "apply-plan.csv", newline="", encoding="utf-8") as f:
            plan_rows = list(csv.DictReader(f))
        self.assertEqual({(r["handle"], r["source"]) for r in plan_rows},
                         {("heat", "auto-fix"), ("jaws", "pick:ambiguous-queue")})

    def test_apply_refuses_without_a_terminal(self):
        err = io.StringIO()
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q"]
        with mock.patch("sys.stdin", FakeStdin(tty=False)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertFalse((self.run / "import").exists())
        self.assertEqual(self.registry()["jaws"]["status"], "queued")

    def test_second_apply_on_the_same_run_rewrites_the_full_set(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
            first = {p.name: p.read_text(encoding="utf-8") for p in (self.run / "import").iterdir()}
            first_values = self.registry()["jaws"]["values"]
            command.run_command(self.args("--yes"))
        second = {p.name: p.read_text(encoding="utf-8") for p in (self.run / "import").iterdir()}
        self.assertEqual(second, first)  # the applied pick rows are rebuilt, not lost
        self.assertEqual(self.registry()["jaws"]["values"], first_values)

    def test_dry_run_after_apply_keeps_the_import_files(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
            before = sorted(p.name for p in (self.run / "import").iterdir())
            command.run_command(self.args("--dry-run"))
        self.assertEqual(sorted(p.name for p in (self.run / "import").iterdir()), before)

    def test_a_dropped_autofix_leaves_its_file_out_on_the_next_apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
            (self.run / "autofix.json").write_text("{}", encoding="utf-8")
            command.run_command(self.args("--yes"))
        self.assertEqual(sorted(p.name for p in (self.run / "import").iterdir()), ["description.csv", "image.csv"])

    def test_closing_message_says_to_commit_the_registry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
        self.assertIn("commit", (self.run / "apply.log").read_text(encoding="utf-8"))
        self.assertNotIn("published with the next", (self.run / "apply.log").read_text(encoding="utf-8"))

    def test_remote_registry_marks_cards_queued_on_main(self):
        snapshot = json.loads((self.run / "snapshot.json").read_text(encoding="utf-8"))
        for r in snapshot:
            if r["Handle"] == "heat":
                r["Image Src"] = "https://cdn/old.jpg"
        (self.run / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
        files = {"batches.json": json.dumps([{"batch_id": "ambiguous-queue", "total": 1}]),
                 "data/ambiguous-queue.json": json.dumps([{"handle": "heat", "choice": "manual",
                                                           "image_src": "https://new.jpg", "overview": ""}]),
                 "data/_handle-index.json": json.dumps({"heat": {"batch": "ambiguous-queue", "status": "queued"}})}
        args = build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "-q", "--yes"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_text=files.get)
        with open(self.run / "import" / "image.csv", newline="", encoding="utf-8") as f:
            self.assertEqual([r["Image Src"] for r in csv.DictReader(f)], ["https://new.jpg"])  # overwrote: current cycle
        self.assertIn("differs", (self.run / "apply.log").read_text(encoding="utf-8"))

    def test_apply_reads_picks_through_the_injected_reader(self):
        files = {"batches.json": json.dumps([{"batch_id": "ambiguous-queue", "total": 1}]),
                 "data/ambiguous-queue.json": json.dumps([{"handle": "rocky", "choice": "skip"}])}
        args = build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "-q", "--yes"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_text=files.get)
        self.assertEqual(self.registry()["rocky"]["status"], "skipped")
        self.assertEqual(self.registry()["jaws"]["status"], "queued")  # its pick wasn't in the reader

    def test_a_pick_with_fields_stops_apply(self):
        (self.picker / "data" / "ambiguous-queue.json").write_text(json.dumps([
            {"handle": "jaws", "choice": "manual", "fields": {"genre": "horror"}}]), encoding="utf-8")
        err = io.StringIO()
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q", "--yes"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("ambiguous-queue/jaws", err.getvalue())


if __name__ == "__main__":
    unittest.main()
