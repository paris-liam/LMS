import contextlib
import csv
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest import mock

from catalog.apply import command
from catalog.cli import build_parser, main
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD


# Approval codes are fingerprints of the exact change list (tested in
# test_plan); here every plan is approved with the fixed code "ok".
_approval = unittest.mock.patch("catalog.core.plan.fingerprint", return_value="ok")


def setUpModule():
    _approval.start()


def tearDownModule():
    _approval.stop()


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
                                          "--imports-dir", str(self.imports), "--local-picks", "-q", "--via", "csv", *extra])

    @property
    def imports(self):
        return Path(self.tmp.name) / "imports"

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
            command.run_command(self.args("--approve", "ok"))
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
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q", "--via", "csv"]
        with mock.patch("sys.stdin", FakeStdin(tty=False)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertFalse((self.run / "import").exists())
        self.assertEqual(self.registry()["jaws"]["status"], "queued")

    def test_second_apply_on_the_same_run_rewrites_the_full_set(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"))
            first = {p.name: p.read_text(encoding="utf-8") for p in (self.run / "import").iterdir()}
            first_values = self.registry()["jaws"]["values"]
            command.run_command(self.args("--approve", "ok"))
        second = {p.name: p.read_text(encoding="utf-8") for p in (self.run / "import").iterdir()}
        self.assertEqual(second, first)  # the applied pick rows are rebuilt, not lost
        self.assertEqual(self.registry()["jaws"]["values"], first_values)

    def test_dry_run_after_apply_keeps_the_import_files(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"))
            before = sorted(p.name for p in (self.run / "import").iterdir())
            command.run_command(self.args("--dry-run"))
        self.assertEqual(sorted(p.name for p in (self.run / "import").iterdir()), before)

    def test_a_dropped_autofix_leaves_its_file_out_on_the_next_apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"))
            (self.run / "autofix.json").write_text("{}", encoding="utf-8")
            command.run_command(self.args("--approve", "ok"))
        self.assertEqual(sorted(p.name for p in (self.run / "import").iterdir()), ["description.csv", "image.csv"])

    def test_closing_message_says_to_commit_the_registry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"))
        self.assertIn("commit", (self.run / "apply.log").read_text(encoding="utf-8"))
        self.assertNotIn("published with the next", (self.run / "apply.log").read_text(encoding="utf-8"))

    def test_import_files_are_copied_to_the_imports_folder(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"))
            (self.run / "autofix.json").write_text("{}", encoding="utf-8")
            command.run_command(self.args("--approve", "ok"))  # vendor fix gone: its copy must go too
        self.assertEqual(sorted(p.name for p in (self.imports / "2026-09-25").iterdir()),
                         ["description.csv", "image.csv"])

    def test_publishes_the_registry_and_imports_to_main(self):
        calls = []

        def sync(repo_root, paths, message, log_fn=None, deploy_branch=None, remote=None):
            calls.append((paths, deploy_branch, remote, message))
            return {"synced": True}

        with mock.patch.object(command.config, "REPO_ROOT", Path(self.tmp.name)), \
                contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok"), sync_fn=sync)
        self.assertEqual(calls[0][:3], (["picker", "imports"], "main", "origin"))
        self.assertIn("2026-09-25", calls[0][3])

    def test_no_git_sync_publishes_nothing(self):
        calls = []
        with mock.patch.object(command.config, "REPO_ROOT", Path(self.tmp.name)), \
                contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--approve", "ok", "--no-git-sync"), sync_fn=lambda *a, **k: calls.append(a))
        self.assertEqual(calls, [])
        self.assertTrue((self.imports / "2026-09-25" / "image.csv").exists())

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
                                          "-q", "--via", "csv", "--approve", "ok"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_text=files.get)
        with open(self.run / "import" / "image.csv", newline="", encoding="utf-8") as f:
            self.assertEqual([r["Image Src"] for r in csv.DictReader(f)], ["https://new.jpg"])  # overwrote: current cycle
        self.assertIn("differs", (self.run / "apply.log").read_text(encoding="utf-8"))

    def test_apply_reads_picks_through_the_injected_reader(self):
        files = {"batches.json": json.dumps([{"batch_id": "ambiguous-queue", "total": 1}]),
                 "data/ambiguous-queue.json": json.dumps([{"handle": "rocky", "choice": "skip"}])}
        args = build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "-q", "--via", "csv", "--approve", "ok"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_text=files.get)
        self.assertEqual(self.registry()["rocky"]["status"], "skipped")
        self.assertEqual(self.registry()["jaws"]["status"], "queued")  # its pick wasn't in the reader

    def test_a_pick_with_fields_stops_apply(self):
        (self.picker / "data" / "ambiguous-queue.json").write_text(json.dumps([
            {"handle": "jaws", "choice": "manual", "fields": {"genre": "horror"}}]), encoding="utf-8")
        err = io.StringIO()
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q", "--via", "csv", "--approve", "ok"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("ambiguous-queue/jaws", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestApplyViaApi(TestApplyCommand):
    """apply --via api: the same plan, written through a (fake) Shopify store."""

    def store(self, **kw):
        from tests_fake_store import FakeStore, product  # noqa: E402  (sibling test module)
        return FakeStore({"jaws": product("p1", Tags="Rental, VHS, Comedy"),
                          "heat": product("p2", Vendor="bluray"),
                          "rocky": product("p3")}, **kw)

    def api_args(self, *extra):
        return build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "--imports-dir", str(self.imports), "--local-picks", "-q",
                                          "--no-git-sync", *extra])

    def test_writes_to_shopify_and_marks_the_registry(self):
        store = self.store()
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.api_args("--approve", "ok"), store_factory=lambda: store)
        self.assertEqual(code, 0)
        self.assertEqual(store.products["heat"]["fields"]["Vendor"], "Blu-Ray")
        self.assertEqual(store.products["jaws"]["images"][0]["src"], "https://image.tmdb.org/t/p/w1280/jaws.jpg")
        self.assertFalse((self.run / "import").exists())       # no CSVs in api mode
        self.assertEqual(self.registry()["jaws"]["status"], "applied")
        with open(self.run / "apply-report.csv", newline="", encoding="utf-8") as f:
            self.assertEqual({r["status"] for r in csv.DictReader(f)}, {"written"})

    def test_dry_run_writes_nothing(self):
        store = self.store()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.api_args("--dry-run"), store_factory=lambda: store)
        self.assertEqual(store.writes, [])

    def test_a_failed_product_is_not_marked_applied_and_exits_1(self):
        store = self.store(fail={"jaws"})
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.api_args("--approve", "ok"), store_factory=lambda: store)
        self.assertEqual(code, 1)
        self.assertEqual(self.registry()["jaws"]["status"], "queued")
        self.assertEqual(store.products["heat"]["fields"]["Vendor"], "Blu-Ray")
