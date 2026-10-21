import tempfile
import unittest
from pathlib import Path

from catalog.backup.guard import (
    LIBIB_BARCODES_REQUIRED,
    SHOPIFY_REQUIRED,
    SourceResult,
    check_csv,
)
from catalog.errors import InputShapeError


def _write(tmp, text, name="x.csv"):
    path = Path(tmp) / name
    path.write_text(text, encoding="utf-8")
    return path


class CheckCsvTests(unittest.TestCase):
    def test_counts_data_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "id,barcode,title\n1,a,A\n2,b,B\n3,c,C\n")
            self.assertEqual(check_csv(p, LIBIB_BARCODES_REQUIRED), 3)

    def test_field_larger_than_csv_default_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, 'Handle,Title,Status,Body (HTML)\nh,T,active,"' + "x" * 140_000 + '"\n')
            self.assertEqual(check_csv(p, SHOPIFY_REQUIRED), 1)

    def test_missing_required_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "id,title\n1,A\n")
            with self.assertRaises(InputShapeError) as cm:
                check_csv(p, LIBIB_BARCODES_REQUIRED)
            self.assertIn("barcode", str(cm.exception))
            self.assertIn("x.csv", str(cm.exception))

    def test_zero_rows_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "Handle,Title,Status\n")
            with self.assertRaises(InputShapeError):
                check_csv(p, SHOPIFY_REQUIRED)

    def test_html_page_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "<!DOCTYPE html><html><body>Login</body></html>\n")
            with self.assertRaises(InputShapeError) as cm:
                check_csv(p, LIBIB_BARCODES_REQUIRED)
            self.assertNotIn("Login", str(cm.exception))

    def test_counts_rows_with_embedded_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, 'Handle,Title,Status\nh,"line1\nline2",active\n')
            self.assertEqual(check_csv(p, SHOPIFY_REQUIRED), 1)

    def test_non_utf8_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "b.csv"
            p.write_bytes(b"id,barcode,title\n\xff\xfe,a,b\n")
            with self.assertRaises(InputShapeError):
                check_csv(p, LIBIB_BARCODES_REQUIRED)

    def test_source_result_defaults(self):
        r = SourceResult("libib", True, "1/1 rows")
        self.assertEqual(r.error, "")


if __name__ == "__main__":
    unittest.main()
