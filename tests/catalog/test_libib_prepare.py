import csv
import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS
from catalog.libib.prepare import download_posters, image_ext, next_batch_id, write_batch


def rental(handle, barcode, image="https://cdn/x.jpg?v=1"):
    return {"Handle": handle, "Title": handle.title(), "Body (HTML)": "<p>D.</p>", "Image Src": image,
            "Variant Barcode": barcode, "Variant Price": "0", "Tags": "Rental, VHS", "Vendor": "VHS",
            GENRE_METAFIELD: "horror"}


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_batch_id(self):
        self.assertEqual(next_batch_id(self.dir), "batch-0001")
        (self.dir / "batch-0009").mkdir()
        (self.dir / "batch-0010").mkdir()
        (self.dir / "drift-2026-09-25").mkdir()
        (self.dir / "batch-notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(next_batch_id(self.dir), "batch-0011")

    def test_image_ext(self):
        self.assertEqual(image_ext("https://cdn/a.PNG?v=3"), "png")
        self.assertEqual(image_ext("https://cdn/a"), "jpg")
        self.assertEqual(image_ext("https://cdn/a.jpeg"), "jpeg")

    def test_download_posters_reports_failures(self):
        def download(url, path):
            if "bad" in url:
                raise OSError("404")
            Path(path).write_bytes(b"img")

        rows = [rental("a", "01111111"), rental("b", "02222222", image="https://cdn/bad.jpg")]
        paths, failed = download_posters(rows, self.dir, download)
        self.assertEqual(paths, {"01111111": str(self.dir / "01111111.jpg")})
        self.assertEqual(failed, ["02222222"])

    def test_write_batch(self):
        rows = [rental("a", "01111111"), rental("b", "02222222")]
        write_batch(self.dir, rows, {"01111111": "libib-sync/batch-0001/01111111.jpg"})
        with open(self.dir / "import.csv", newline="", encoding="utf-8") as f:
            imported = list(csv.DictReader(f))
        with open(self.dir / "ready.csv", newline="", encoding="utf-8") as f:
            ready = list(csv.DictReader(f))
        self.assertEqual(list(imported[0]), LIBIB_MOVIE_COLUMNS)
        self.assertEqual([r["call_number"] for r in imported], ["01111111", "02222222"])
        self.assertEqual(list(ready[0]), READY_COLUMNS)
        self.assertEqual([r["image_path"] for r in ready], ["libib-sync/batch-0001/01111111.jpg", ""])


if __name__ == "__main__":
    unittest.main()
