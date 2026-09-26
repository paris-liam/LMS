import tempfile
import unittest
from pathlib import Path

from catalog.errors import InputShapeError
from catalog.libib.exports import load_libib

BARCODE_HEADER = "id,item_type,barcode,title,collection,tags,call_number"
COLLECTION_HEADER = "id,item_type,title,collection,description,call_number"


class TestLoadLibib(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.barcodes = self.dir / "barcodes.csv"
        self.collection = self.dir / "collection.csv"
        self.barcodes.write_text("\n".join([
            BARCODE_HEADER,
            'a1,movie, 01577790 ,Jaws,Rental Library,"vhs, horror",01577790',
            "a2,movie,2010000000007,Old Item,Rental Library,,",
            "a3,movie,09999999,Elsewhere,Untracked,,09999999",
        ]) + "\n", encoding="utf-8")
        self.collection.write_text("\n".join([
            COLLECTION_HEADER,
            'a1,movie,Jaws,Rental Library,"A shark,\nat sea.",01577790',
            "a2,movie,Old Item,Rental Library,,",
        ]) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_joins_description_and_filters_the_collection(self):
        items = load_libib(self.barcodes, self.collection)
        self.assertEqual([i["id"] for i in items], ["a1", "a2"])
        self.assertEqual(items[0]["barcode"], "01577790")
        self.assertEqual(items[0]["description"], "A shark,\nat sea.")
        self.assertEqual(items[1]["call_number"], "")
        self.assertEqual(items[1]["description"], "")

    def test_all_collections(self):
        self.assertEqual(len(load_libib(self.barcodes, self.collection, collection=None)), 3)

    def test_bom_header_is_read(self):
        self.barcodes.write_text("﻿" + self.barcodes.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(len(load_libib(self.barcodes, self.collection)), 2)

    def test_missing_column_names_the_file(self):
        self.barcodes.write_text("id,title\na1,Jaws\n", encoding="utf-8")
        with self.assertRaises(InputShapeError) as ctx:
            load_libib(self.barcodes, self.collection)
        self.assertIn("barcodes.csv", str(ctx.exception))
        self.assertIn("call_number", str(ctx.exception))

    def test_missing_file_is_an_input_error(self):
        with self.assertRaises(InputShapeError):
            load_libib(self.dir / "nope.csv", self.collection)


if __name__ == "__main__":
    unittest.main()
