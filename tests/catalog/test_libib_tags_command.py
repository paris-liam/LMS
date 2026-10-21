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
    """`changes` new rentals, already tagged new-arrival in Shopify, whose Libib items lack the tag."""

    def __init__(self, changes=0, libib_rows=None, shopify_error=False, libib_statuses=None, unmatched=0, picks=0,
                 join_ids=None):
        self.changes, self.shopify_error, self.unmatched, self.picks = changes, shopify_error, unmatched, picks
        self.join_ids = join_ids or {}
        self.lookups, self.link_writes = [], []
        self.libib_rows = changes if libib_rows is None else libib_rows
        self.libib_statuses = libib_statuses
        self.calls = []

    def read_shopify(self):
        self.calls.append("read_shopify")
        if self.shopify_error:
            raise RuntimeError("[{'message': 'Throttled'}]")
        rentals = [Product(f"gid://p/{i}", f"Movie {i}", ("Rental", "new-arrival"), (barcode(i),), "VHS",
                           f"2026-10-{1 + i % 28:02d}T{i // 28:02d}:00:00Z") for i in range(self.changes)]
        # Shopify always has rentals (zero is refused as a bad read); this one isn't in Libib.
        rentals.append(Product("gid://p/x", "Not In Libib", ("Rental",), ("55550000",), "VHS", "2026-01-01T00:00:00Z"))
        picked = [Product(f"gid://f/{i}", f"Floor {i}", ("Floor Sale",), ()) for i in range(self.picks)]
        picked += [Product(f"gid://u/{i}", f"Lost {i}", ("Rental",), (f"7777{i:04d}",)) for i in range(self.unmatched)]
        return ShopifyState(tuple(rentals), tuple(picked), (), tuple(rentals[:self.changes]))

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

    def lookup_join_id(self, code):
        self.lookups.append(code)
        return self.join_ids.get(code, [])

    def write_join_ids(self, changes):
        self.link_writes += changes
        return [{"title": c.title, "action": "set", "status": "updated", "message": "ok"} for c in changes]

    def deps(self):
        return tags_command.TagDeps(self.read_shopify, self.export_libib, self.write_shopify, self.edit_libib,
                                    self.lookup_join_id, self.write_join_ids, sleep=lambda s: None)


class RotationFakes(Fakes):
    """A big upload day: 50 new titles push out the 50 that Libib and Shopify
    tag today, and Flow 1 has also tagged 100 more uploads outside the window."""

    def __init__(self, **options):
        super().__init__(changes=100, **options)

    def read_shopify(self):
        self.calls.append("read_shopify")
        tagged = ("Rental", "new-arrival")
        rentals = [Product(f"gid://p/{i}", f"Movie {i}", tagged, (barcode(i),), "VHS",
                           f"2026-10-{'01' if i < 50 else '20'}T{i % 24:02d}:00:00Z") for i in range(100)]
        rentals += [Product(f"gid://x/{i}", f"Extra {i}", tagged, (f"5555{i:04d}",), "VHS", "2026-10-20T00:00:00Z")
                    for i in range(100)]
        return ShopifyState(tuple(rentals), (), (), tuple(rentals))

    def export_libib(self, dest):
        barcodes, library = super().export_libib(dest)
        rows = list(csv.DictReader(open(barcodes, encoding="utf-8")))
        for row in rows[:50]:
            row["tags"] = "vhs, new arrival"
        with open(barcodes, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(BARCODE_REQUIRED))
            w.writeheader()
            w.writerows(rows)
        return barcodes, library


class TaggedFakes(Fakes):
    """Like Fakes, but Libib already carries `new arrival` on every item."""

    def export_libib(self, dest):
        barcodes, library = super().export_libib(dest)
        rows = list(csv.DictReader(open(barcodes, encoding="utf-8")))
        with open(barcodes, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(BARCODE_REQUIRED))
            w.writeheader()
            w.writerows(row | {"tags": "vhs, new arrival"} for row in rows)
        return barcodes, library


class TestTagsCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def run_tags(self, flags, stdin=None, fakes_class=None, **fake_options):
        self.fakes = (fakes_class or Fakes)(**fake_options)
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
        self.assertIn("3 Libib edits is over the unattended limit of 2", self.out)

    def test_max_changes_default_comes_from_settings(self):
        settings = Path(self.tmp.name) / "tag_settings.json"
        settings.write_text('{"new_arrivals": {"count": 50, "max_age_days": null}, "max_changes": 2}',
                            encoding="utf-8")
        self.assertEqual(self.run_tags(["--unattended", "--settings", str(settings)], changes=3), 2)
        self.assertEqual(self.run_tags(["--unattended", "--settings", str(settings)], changes=2), 0)

    def test_shipped_settings_allow_a_full_rotation(self):
        # 100 Libib edits + 150 Shopify trims: the limit counts Libib edits only, since
        # Shopify trims grow with upload volume and the next run corrects any bad one.
        self.fakes = RotationFakes()
        args = build_parser().parse_args(["libib", "tags", "--unattended", "--report-dir", self.tmp.name, "-q"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = tags_command.run_tags_command(args, self.fakes.deps())
        self.assertEqual(code, 0)
        self.assertIn("edit_libib", self.fakes.calls)

    def test_summary_names_the_new_arrival_rule(self):
        self.run_tags(["--dry-run"], changes=1)
        self.assertIn("newest 50 titles", self.out)

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
        self.run_tags(["--dry-run"], changes=3, unmatched=1, join_ids={barcode(0): ["555"], barcode(1): ["6", "7"]})
        self.assertEqual(len(self.fakes.lookups), 3)
        for code in (barcode(0), barcode(1), barcode(2), "77770000"):
            self.assertNotIn(code, self.out)

    def test_dry_run_lists_link_changes_without_writing(self):
        self.assertEqual(self.run_tags(["--dry-run"], changes=1, join_ids={barcode(0): ["555"]}), 0)
        self.assertIn("link     set 555", self.out)
        self.assertIn("Libib links: 1 looked up, 1 to change", self.out)
        self.assertEqual(self.fakes.link_writes, [])

    def test_approved_run_writes_links(self):
        self.assertEqual(self.run_tags(["--approve", "ok"], changes=1, join_ids={barcode(0): ["555"]}), 0)
        self.assertEqual([c.new for c in self.fakes.link_writes], [555])

    def test_unattended_limit_ignores_link_writes(self):
        # Libib and Shopify already carry the tag, so the only change is the link.
        code = self.run_tags(["--unattended", "--max-changes", "0"], fakes_class=TaggedFakes, changes=1,
                             join_ids={barcode(0): ["555"]})
        self.assertEqual(code, 0)
        self.assertNotIn("edit_libib", self.fakes.calls)
        self.assertEqual([c.new for c in self.fakes.link_writes], [555])

    def test_plan_lists_title_item_and_tag(self):
        self.run_tags(["--dry-run"], changes=1)
        self.assertIn("+ new arrival", self.out)
        self.assertIn("Movie 0", self.out)
        self.assertIn("item0", self.out)


if __name__ == "__main__":
    unittest.main()
