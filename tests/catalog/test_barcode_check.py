import contextlib
import io
import unittest
from datetime import date
from types import SimpleNamespace

from catalog.shopify.barcode_check import read_variants, run_command, shared_barcodes


def _variant(barcode, created, handle):
    return {"barcode": barcode, "created": created, "handle": handle, "title": handle.title(), "tags": []}


VARIANTS = [
    _variant("71735546", "2026-07-06", "beyond-the-sea"),
    _variant("71735546", "2026-07-08", "dude-wheres-my-car"),
    _variant("34579450", "2026-07-09", "the-generals-daughter"),
    _variant("34579450", "2026-10-19", "nacho-libre"),
    _variant("11111111", "2026-10-19", "unique"),
    _variant("", "2026-10-19", "no-barcode"),
    _variant("", "2026-10-19", "no-barcode-either"),
]


class TestSharedBarcodes(unittest.TestCase):
    def test_lists_only_barcodes_on_two_or_more_variants(self):
        shared = shared_barcodes(VARIANTS)
        self.assertEqual(list(shared), ["34579450", "71735546"])
        self.assertEqual([v["handle"] for v in shared["34579450"]], ["the-generals-daughter", "nacho-libre"])

    def test_since_keeps_clashes_with_a_new_variant(self):
        self.assertEqual(list(shared_barcodes(VARIANTS, date(2026, 10, 19))), ["34579450"])


class TestReadVariants(unittest.TestCase):
    def test_pages_through_and_flattens(self):
        pages = [
            {"data": {"productVariants": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"}, "nodes": [
                {"barcode": " 1 ", "createdAt": "2026-10-19T12:00:00Z",
                 "product": {"handle": "a", "title": "A", "tags": ["Floor Sale"]}}]}}},
            {"data": {"productVariants": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
                {"barcode": None, "createdAt": "2026-10-20T12:00:00Z",
                 "product": {"handle": "b", "title": "B", "tags": []}}]}}},
        ]
        cursors = []

        def execute(store, path, variables):
            cursors.append(variables["cursor"])
            return pages[len(cursors) - 1]

        variants = read_variants("x.myshopify.com", execute)
        self.assertEqual(cursors, [None, "c1"])
        self.assertEqual(variants[0], {"barcode": "1", "created": "2026-10-19", "handle": "a", "title": "A",
                                       "tags": ["Floor Sale"]})
        self.assertEqual(variants[1]["barcode"], "")


class TestCommand(unittest.TestCase):
    def _run(self, since):
        args = SimpleNamespace(store="x.myshopify.com", since=since)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_command(args, read=lambda store: VARIANTS)
        return code, out.getvalue()

    def test_exit_1_and_lists_both_sides(self):
        code, out = self._run("2026-10-19")
        self.assertEqual(code, 1)
        self.assertIn("34579450", out)
        self.assertIn("the-generals-daughter", out)
        self.assertNotIn("71735546", out)

    def test_exit_0_when_nothing_new_clashes(self):
        code, out = self._run("2026-10-20")
        self.assertEqual(code, 0)
        self.assertIn("no shared barcodes", out)


if __name__ == "__main__":
    unittest.main()
