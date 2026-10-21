import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.cli import build_parser
from catalog.core import log
from catalog.core.plan import ApprovalRefused
from catalog.errors import InputShapeError
from catalog.libib import tags_command
from catalog.libib.exports import BARCODE_REQUIRED, COLLECTION_REQUIRED
from catalog.libib.tags import Product, ShopifyState

_approval = mock.patch("catalog.core.plan.fingerprint", return_value="ok")


def setUpModule():
    _approval.start()


def tearDownModule():
    _approval.stop()


def barcode(i):
    return f"9202{i:04d}"


class Fakes:
    """`changes` rentals tagged new-arrival in Shopify whose Libib items lack the tag."""

    def __init__(self, changes=0, libib_rows=None, shopify_error=False, libib_statuses=None, unmatched=0, picks=0):
        self.changes, self.shopify_error, self.unmatched, self.picks = changes, shopify_error, unmatched, picks
        self.libib_rows = changes if libib_rows is None else libib_rows
        self.libib_statuses = libib_statuses
        self.calls = []

    def read_shopify(self):
        self.calls.append("read_shopify")
        if self.shopify_error:
            raise RuntimeError("[{'message': 'Throttled'}]")
        products = [Product(f"gid://p/{i}", f"Movie {i}", ("Rental", "new-arrival"), (barcode(i),))
                    for i in range(self.changes)]
        products += [Product(f"gid://u/{i}", f"Lost {i}", ("Rental", "new-arrival"), (f"7777{i:04d}",))
                     for i in range(self.unmatched)]
        picked = [Product(f"gid://f/{i}", f"Floor {i}", ("Floor Sale",), ()) for i in range(self.picks)]
        return ShopifyState(tuple(products), tuple(picked), ())

    def export_libib(self, dest):
        self.calls.append("export_libib")
        dest = Path(dest)
        barcodes, library = dest / "barcodes.csv", dest / "library.csv"
        with open(barcodes, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(BARCODE_REQUIRED))
            w.writeheader()
            for i in range(self.libib_rows):
                w.writerow({"id": f"item{i}", "title": f"Movie {i}", "barcode": barcode(i), "call_number": barcode(i),
                            "tags": "vhs, horror", "collection": "Rental Library"})
        with open(library, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(COLLECTION_REQUIRED))
            w.writeheader()
            for i in range(self.libib_rows):
                w.writerow({"id": f"item{i}", "description": ""})
        return barcodes, library

    def write_shopify(self, changes):
        self.calls.append("write_shopify")
        return [{"title": c.title, "action": c.action, "status": "updated", "message": "ok"} for c in changes]

    def edit_libib(self, changes, report_path):
        self.calls.append("edit_libib")
        statuses = self.libib_statuses or ["updated"] * len(changes)
        return [{"item_id": c.item_id, "title": c.title, "status": s, "message": "ok"} for c, s in zip(changes, statuses)]

    def deps(self):
        return tags_command.TagDeps(self.read_shopify, self.export_libib, self.write_shopify, self.edit_libib)


class TestTagsCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def run_tags(self, flags, stdin=None, **fake_options):
        self.fakes = Fakes(**fake_options)
        args = build_parser().parse_args(["libib", "tags", *flags, "--report-dir", self.tmp.name, "-q"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                code = tags_command.run_tags_command(args, self.fakes.deps(), stdin=stdin)
            finally:
                self.out = out.getvalue()
        return code

    def test_unattended_under_limit_applies_without_prompt(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=2, picks=1), 0)
        self.assertIn("edit_libib", self.fakes.calls)
        self.assertIn("write_shopify", self.fakes.calls)

    def test_unattended_over_limit_changes_nothing_and_exits_2(self):
        self.assertEqual(self.run_tags(["--unattended", "--max-changes", "2"], changes=3), 2)
        self.assertNotIn("edit_libib", self.fakes.calls)
        self.assertNotIn("write_shopify", self.fakes.calls)
        self.assertIn("over the unattended limit of 2", self.out)

    def test_default_limit_is_25(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=26), 2)
        self.assertEqual(self.run_tags(["--unattended"], changes=25), 0)

    def test_over_limit_proceeds_with_approval_code(self):
        self.assertEqual(self.run_tags(["--approve", "ok"], changes=30), 0)
        self.assertIn("edit_libib", self.fakes.calls)

    def test_dry_run_changes_nothing(self):
        self.assertEqual(self.run_tags(["--dry-run"], changes=3), 0)
        self.assertNotIn("edit_libib", self.fakes.calls)
        self.assertNotIn("write_shopify", self.fakes.calls)
        self.assertIn("Approval code", self.out)

    def test_no_terminal_and_no_flag_refuses(self):
        with self.assertRaises(ApprovalRefused):
            self.run_tags([], changes=1, stdin=io.StringIO())
        self.assertNotIn("edit_libib", self.fakes.calls)

    def test_unattended_and_approve_are_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["libib", "tags", "--unattended", "--approve", "ok"])

    def test_shopify_only_change_skips_browser(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=0, libib_rows=1, picks=1), 0)
        self.assertEqual(self.fakes.calls, ["read_shopify", "export_libib", "write_shopify"])
        self.assertIn("+ community-pick", self.out)

    def test_nothing_to_change_skips_browser(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=0, libib_rows=2), 0)
        self.assertNotIn("edit_libib", self.fakes.calls)

    def test_empty_libib_export_aborts_before_writes(self):
        with self.assertRaises(InputShapeError):
            self.run_tags(["--unattended"], changes=2, libib_rows=0)
        self.assertNotIn("write_shopify", self.fakes.calls)
        self.assertNotIn("edit_libib", self.fakes.calls)

    def test_shopify_read_error_aborts_before_export(self):
        with self.assertRaises(RuntimeError):
            self.run_tags(["--unattended"], shopify_error=True)
        self.assertNotIn("export_libib", self.fakes.calls)

    def test_any_item_error_exits_1(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=2, libib_statuses=["updated", "error"]), 1)

    def test_unmatched_products_are_listed_but_do_not_fail(self):
        self.assertEqual(self.run_tags(["--unattended"], changes=1, unmatched=1), 0)
        self.assertIn("Lost 0", self.out)

    def test_output_never_contains_barcodes(self):
        self.run_tags(["--dry-run"], changes=2, unmatched=1)
        for code in (barcode(0), barcode(1), "77770000"):
            self.assertNotIn(code, self.out)

    def test_plan_lists_title_item_and_tag(self):
        self.run_tags(["--dry-run"], changes=1)
        self.assertIn("+ new arrival", self.out)
        self.assertIn("Movie 0", self.out)
        self.assertIn("item0", self.out)


if __name__ == "__main__":
    unittest.main()
