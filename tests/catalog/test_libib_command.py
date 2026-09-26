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


if __name__ == "__main__":
    unittest.main()
