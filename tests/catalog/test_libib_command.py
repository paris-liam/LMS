import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from catalog.cli import build_parser
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.libib import command


def rental(handle, barcode, **overrides):
    base = {"Handle": handle, "Title": handle.title(), "Body (HTML)": f"<p>{handle}.</p>",
            "Image Src": f"https://cdn/{handle}.jpg", "Variant Barcode": barcode, "Variant Price": "0",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", GENRE_METAFIELD: "horror", "Status": "active"}
    base.update(overrides)
    return base


class LibibCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.sync = root / "runs", root / "libib-sync"
        self.run = self.runs / "2026-09-25"
        self.run.mkdir(parents=True)
        self.sync.mkdir()
        rows = [rental("jaws", "01111111"), rental("heat", "02222222"), rental("alien", "03333333"),
                rental("blank", "")]
        (self.run / "snapshot.json").write_text(json.dumps(rows), encoding="utf-8")
        (self.run / "run-report.txt").write_text("done\n", encoding="utf-8")
        self.barcodes, self.collection = root / "b.csv", root / "c.csv"
        self.barcodes.write_text(
            "id,item_type,barcode,title,collection,tags,call_number\n"
            'i1,movie,01111111,Jaws,Rental Library,"vhs, horror",01111111\n'
            'i2,movie,02222222,Heat (old),Rental Library,"vhs, horror",02222222\n'
            "i3,movie,07777777,Orphan,Rental Library,,07777777\n", encoding="utf-8")
        self.collection.write_text(
            "id,item_type,title,collection,description,call_number\n"
            "i1,movie,Jaws,Rental Library,jaws.,01111111\n"
            "i2,movie,Heat,Rental Library,heat.,02222222\n"
            "i3,movie,Orphan,Rental Library,,07777777\n", encoding="utf-8")
        (self.sync / "_state.json").write_text(json.dumps({
            "jaws": {"status": "imported", "batch": "batch-0001", "call_number": "01111111", "poster_confirmed": True}}),
            encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def parse(self, *argv):
        return build_parser().parse_args(["libib", *argv, "--runs-dir", str(self.runs), "--sync-dir", str(self.sync), "-q"])

    def diff(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return command.run_diff_command(self.parse("diff", "--barcode-export", str(self.barcodes),
                                                       "--collection-export", str(self.collection)))

    def read(self, name):
        with open(self.run / "libib" / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def state(self):
        return json.loads((self.sync / "_state.json").read_text(encoding="utf-8"))


class TestDiffCommand(LibibCase):
    def test_writes_every_output_and_updates_state(self):
        self.assertEqual(self.diff(), 0)
        self.assertEqual({(d["handle"], d["field"]) for d in self.read("drift.csv")}, {("heat", "title")})
        self.assertEqual([e["handle"] for e in self.read("eligible.csv")], ["alien"])
        self.assertEqual([o["id"] for o in self.read("orphans.csv")], ["i3"])
        self.assertEqual([b["handle"] for b in self.read("blocked.csv")], ["blank"])
        state = self.state()
        self.assertEqual(state["jaws"]["status"], "done")                      # promoted
        self.assertEqual(state["jaws"]["poster_src"], "https://cdn/jaws.jpg")  # migrated
        before = json.loads((self.run / "libib" / "state-before.json").read_text(encoding="utf-8"))
        self.assertEqual(before["jaws"]["status"], "imported")
        report = (self.run / "libib" / "libib-report.txt").read_text(encoding="utf-8")
        for fragment in ("in sync:", "drift:", "eligible:", "orphans:", "blocked:", "promoted"):
            self.assertIn(fragment, report)


class TestStatusCommand(LibibCase):
    def test_status_counts(self):
        args = build_parser().parse_args(["libib", "status", "--sync-dir", str(self.sync)])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(command.run_status_command(args), 0)
        self.assertIn("imported: 1", out.getvalue())


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def fake_download(url, path):
    Path(path).write_bytes(b"img")


class TestPrepareCommand(LibibCase):
    def test_needs_a_diff_first(self):
        from catalog.errors import NoRunError
        with self.assertRaises(NoRunError):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)

    def test_dry_run_writes_nothing(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--dry-run"), download=fake_download)
        self.assertFalse((self.sync / "batch-0001").exists())

    def test_yes_builds_the_batch_and_queues(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
        batch = self.sync / "batch-0001"
        self.assertEqual(sorted(p.name for p in batch.iterdir()), ["03333333.jpg", "import.csv", "ready.csv"])
        self.assertEqual(self.state()["alien"],
                         {"status": "queued", "batch": "batch-0001", "call_number": "03333333"})

    def test_prepare_skips_handles_queued_since_the_diff(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
        self.assertFalse((self.sync / "batch-0002").exists())

    def test_refuses_without_a_terminal(self):
        from catalog.core.plan import ApprovalRefused
        self.diff()
        with self.assertRaises(ApprovalRefused), contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare"), download=fake_download, stdin=FakeStdin(tty=False))
        self.assertFalse((self.sync / "batch-0001").exists())


class TestMarkImportedCommand(LibibCase):
    def test_marks_only_that_batchs_queued_handles(self):
        (self.sync / "_state.json").write_text(json.dumps({
            "a": {"status": "queued", "batch": "batch-0002"}, "b": {"status": "queued", "batch": "batch-0003"},
            "c": {"status": "done", "batch": "batch-0002"}}), encoding="utf-8")
        args = build_parser().parse_args(["libib", "mark-imported", "batch-0002", "--sync-dir", str(self.sync),
                                          "-q", "--yes"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_mark_imported_command(args)
        state = self.state()
        self.assertEqual((state["a"]["status"], state["b"]["status"], state["c"]["status"]),
                         ("imported", "queued", "done"))


if __name__ == "__main__":
    unittest.main()
