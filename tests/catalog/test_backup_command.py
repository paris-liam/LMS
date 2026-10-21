import contextlib
import io
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from catalog.backup import command
from catalog.backup.guard import SourceResult
from catalog.cli import build_parser

DAY = date(2026, 10, 22)
LIBIB_OK = SourceResult("libib", True, "3962/3962 rows")
SHOPIFY_OK = SourceResult("shopify", True, "7031 products")
LIBIB_BAD = SourceResult("libib", False, "FAILED", "login timed out")


class SummaryLineTest(unittest.TestCase):
    def test_summary_line_both_ok(self):
        self.assertEqual(command.summary_line([LIBIB_OK, SHOPIFY_OK], DAY),
                         "Backup 2026-10-22 — libib 3962/3962 rows, shopify 7031 products")

    def test_summary_line_libib_failed(self):
        self.assertEqual(command.summary_line([LIBIB_BAD, SHOPIFY_OK], DAY),
                         "Backup 2026-10-22 — libib FAILED, shopify 7031 products")


class RunBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.message = Path(self.tmp.name) / "message.txt"

    def run_cmd(self, libib, shopify, *extra):
        calls = []

        def wrap(name, result):
            def fn(out):
                calls.append(name)
                return result
            return fn

        args = build_parser().parse_args(
            ["backup", "--out", self.tmp.name, "--message-file", str(self.message), "--date", "2026-10-22", *extra])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = command.run_backup(args, command.BackupDeps(wrap("libib", libib), wrap("shopify", shopify)))
        return code, calls, buf.getvalue()

    def test_runs_shopify_even_when_libib_fails(self):
        code, calls, out = self.run_cmd(LIBIB_BAD, SourceResult("shopify", True, "2 products"))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["libib", "shopify"])
        self.assertIn("libib FAILED, shopify 2 products", self.message.read_text())
        self.assertIn("libib: FAILED — login timed out", out)

    def test_missing_env_fails_that_source_only(self):
        from catalog.errors import MissingEnvError
        args = build_parser().parse_args(["backup", "--out", self.tmp.name])

        def boom(out):
            raise MissingEnvError("LIBIB_EMAIL is not set.")

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = command.run_backup(args, command.BackupDeps(boom, lambda out: SHOPIFY_OK))
        self.assertEqual(code, 1)
        self.assertIn("shopify: 7031 products", buf.getvalue())
        self.assertIn("libib: FAILED — LIBIB_EMAIL is not set.", buf.getvalue())

    def test_non_catalog_error_still_writes_message_file(self):
        args = build_parser().parse_args(["backup", "--out", self.tmp.name, "--message-file", str(self.message),
                                          "--date", "2026-10-22"])
        calls = []

        def libib(out):
            calls.append("libib")
            return LIBIB_OK

        def boom(out):
            raise TimeoutError("read timed out")

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = command.run_backup(args, command.BackupDeps(libib, boom))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["libib"])
        self.assertIn("shopify FAILED", self.message.read_text())
        self.assertIn("shopify: FAILED — TimeoutError: read timed out", buf.getvalue())

    def test_all_ok_returns_zero(self):
        code, _, out = self.run_cmd(LIBIB_OK, SHOPIFY_OK)
        self.assertEqual(code, 0)
        self.assertIn("libib: 3962/3962 rows", out)

    def test_only_flag_runs_one_source(self):
        code, calls, _ = self.run_cmd(LIBIB_OK, SHOPIFY_OK, "--only", "shopify")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["shopify"])
        self.assertNotIn("libib", self.message.read_text())

    def test_output_has_no_row_contents(self):
        _, _, out = self.run_cmd(LIBIB_BAD, SHOPIFY_OK)
        lines = [l for l in out.splitlines() if l]
        for name in ("libib", "shopify"):
            self.assertEqual(len([l for l in lines if re.match(rf"^{name}: ", l)]), 1)


class DefaultDepsTest(unittest.TestCase):
    def test_shopify_bulk_timeout_is_well_under_job_timeout(self):
        from unittest import mock
        args = build_parser().parse_args(["backup", "--out", "x"])
        seen = {}

        def fake_read_store(execute, store, **kwargs):
            seen.update(kwargs)
            return [], [], []

        with mock.patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "i", "SHOPIFY_CLIENT_SECRET": "s"}), \
                mock.patch("catalog.shopify.api.request_token", return_value="tok"), \
                mock.patch("catalog.shopify.api.make_executor", return_value=lambda *a: None), \
                mock.patch.object(command, "read_store", fake_read_store), \
                mock.patch.object(command, "backup_shopify", lambda out, read: (read(), SHOPIFY_OK)[1]):
            command.default_deps(args).shopify(Path("x"))
        self.assertEqual(seen.get("timeout_seconds"), 900)
        self.assertEqual(command.BULK_TIMEOUT_SECONDS, 900)


class ParserTest(unittest.TestCase):
    def test_parser_registers_backup(self):
        args = build_parser().parse_args(["backup", "--out", "x"])
        self.assertTrue(hasattr(args, "func"))


if __name__ == "__main__":
    unittest.main()
