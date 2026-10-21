import tempfile
import unittest
from pathlib import Path

from catalog.backup.libib import backup_libib

BARCODES = b"\xef\xbb\xbfid,barcode,title\r\n1,111,A\r\n2,222,B\r\n3,333,C\r\n"
LIBRARY = b"\xef\xbb\xbfid,title,call_number\r\n1,A,111\r\n2,B,222\r\n"


def _fake_export(barcodes=BARCODES, library=LIBRARY):
    def export(dest):
        b, l = Path(dest) / "barcodes.csv", Path(dest) / "library.csv"
        b.write_bytes(barcodes)
        l.write_bytes(library)
        return b, l
    return export


class BackupLibibTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_copies_exports_byte_for_byte(self):
        result = backup_libib(self.out, _fake_export())
        self.assertTrue(result.ok)
        self.assertEqual((self.out / "libib" / "barcodes.csv").read_bytes(), BARCODES)
        self.assertEqual((self.out / "libib" / "library.csv").read_bytes(), LIBRARY)

    def test_summary_counts_both_files(self):
        result = backup_libib(self.out, _fake_export())
        self.assertEqual((result.name, result.summary), ("libib", "3/2 rows"))

    def test_bad_library_export_keeps_both_old_files(self):
        target = self.out / "libib"
        target.mkdir()
        (target / "barcodes.csv").write_bytes(b"old-b")
        (target / "library.csv").write_bytes(b"old-l")
        result = backup_libib(self.out, _fake_export(library=b"<html><body>Login</body></html>"))
        self.assertFalse(result.ok)
        self.assertEqual(result.summary, "FAILED")
        self.assertIn("library.csv", result.error)
        self.assertEqual((target / "barcodes.csv").read_bytes(), b"old-b")
        self.assertEqual((target / "library.csv").read_bytes(), b"old-l")

    def test_export_exception_is_a_failed_result(self):
        def export(dest):
            raise RuntimeError("boom\nsecond line")
        result = backup_libib(self.out, export)
        self.assertFalse(result.ok)
        self.assertEqual(result.summary, "FAILED")
        self.assertEqual(result.error, "RuntimeError: boom second line")
        self.assertFalse((self.out / "libib").exists())

    def test_playwright_timeout_has_a_plain_message(self):
        class TimeoutError(Exception):
            __module__ = "playwright._impl._errors"
        def export(dest):
            raise TimeoutError("Timeout 30000ms exceeded")
        result = backup_libib(self.out, export)
        self.assertEqual(result.error, "Libib login or export timed out")


if __name__ == "__main__":
    unittest.main()
