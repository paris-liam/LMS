import base64
import gzip
import unittest

from catalog.errors import InputShapeError
from catalog.rental_sync.prepare import MAX_FILE_BYTES, decode_upload, load_uploads, prepare

BARCODES = "\n".join([
    "id,item_type,barcode,title,collection,tags,call_number,created",
    'a1,movie,2010000000014,Jaws,Rental Library,"vhs, horror",,2026-10-14 10:00:00',
    'a2,movie,2010000000021,Heat,Rental Library,"dvd, horor",,2026-10-14 09:00:00',
    'a3,movie,20144890,Old Rental,Rental Library,"vhs, drama",20144890,2026-09-16',
    'a4,movie,2010000000038,Already There,Rental Library,"vhs, comedy",,2026-10-13',
]) + "\n"
LIBRARY = "\n".join([
    "id,item_type,title,collection,description,call_number",
    "a1,movie,Jaws,Rental Library,A shark.,",
    "a2,movie,Heat,Rental Library,A heist.,",
    "a3,movie,Old Rental,Rental Library,Old.,20144890",
    "a4,movie,Already There,Rental Library,Here.,",
]) + "\n"


def encode(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data)).decode()


class TestDecodeUpload(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(decode_upload(encode(b"id,barcode\n"), "Barcodes export"), b"id,barcode\n")

    def test_not_base64(self):
        with self.assertRaisesRegex(InputShapeError, "Barcodes export upload is unreadable"):
            decode_upload("%%%not base64%%%", "Barcodes export")

    def test_not_gzip(self):
        with self.assertRaisesRegex(InputShapeError, "Library export upload is unreadable"):
            decode_upload(base64.b64encode(b"plain text").decode(), "Library export")

    def test_over_the_limit_after_decompressing(self):
        with self.assertRaisesRegex(InputShapeError, "over 5 MB"):
            decode_upload(encode(b"x" * (MAX_FILE_BYTES + 1)), "Library export")

    def test_truncated_stream(self):
        raw = gzip.compress(b"id,barcode\n" + b"a,2010000000014\n" * 5000)
        with self.assertRaisesRegex(InputShapeError, "Library export upload is unreadable"):
            decode_upload(base64.b64encode(raw[: len(raw) // 2]).decode(), "Library export")

    def test_missing(self):
        with self.assertRaisesRegex(InputShapeError, "Choose the Barcodes export"):
            decode_upload("", "Barcodes export")


class TestLoadUploads(unittest.TestCase):
    def test_loads_and_joins(self):
        items = load_uploads(BARCODES.encode(), LIBRARY.encode())
        self.assertEqual([i["barcode"] for i in items], ["2010000000014", "2010000000021", "20144890", "2010000000038"])
        self.assertEqual(items[0]["description"], "A shark.")
        self.assertEqual(items[0]["created"], "2026-10-14 10:00:00")

    def test_bom_crlf_and_multiline_description(self):
        barcodes = ("﻿" + BARCODES.replace("\n", "\r\n")).encode("utf-8")
        library = ("﻿" + LIBRARY.replace("a1,movie,Jaws,Rental Library,A shark.,",
                                              'a1,movie,Jaws,Rental Library,"A shark,\r\nat sea.",')
                   .replace("\n", "\r\n")).encode("utf-8")
        items = load_uploads(barcodes, library)
        self.assertEqual(items[0]["barcode"], "2010000000014")
        self.assertEqual(" ".join(items[0]["description"].split()), "A shark, at sea.")

    def test_swapped_files(self):
        with self.assertRaisesRegex(InputShapeError, "swapped"):
            load_uploads(LIBRARY.encode(), BARCODES.encode())

    def test_wrong_file_names_the_box(self):
        with self.assertRaisesRegex(InputShapeError, "Barcodes export.csv is missing column"):
            load_uploads(b"id,title\n1,x\n", LIBRARY.encode())

    def test_not_text(self):
        with self.assertRaisesRegex(InputShapeError, "isn't a CSV"):
            load_uploads(b"\xff\xfe\x00\x01\x02", LIBRARY.encode())


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.items = load_uploads(BARCODES.encode(), LIBRARY.encode())

    def test_split(self):
        result = prepare(self.items, {"2010000000038"})
        self.assertEqual([c["title"] for c in result["ready"]], ["Jaws"])
        self.assertEqual([c["title"] for c in result["set_aside"]], ["Heat"])
        self.assertEqual(result["already_in_shopify"], 1)
        self.assertEqual(result["not_new_flow"], 1)

    def test_legacy_201_eight_digit_is_out_of_scope(self):
        result = prepare(self.items, set())
        barcodes = {c["barcode"] for c in result["ready"] + result["set_aside"]}
        self.assertNotIn("20144890", barcodes)

    def test_order_is_created_then_title(self):
        result = prepare(self.items, set())
        self.assertEqual([c["title"] for c in result["ready"]], ["Already There", "Jaws"])

    def test_duplicate_barcode_sets_both_aside(self):
        dup = dict(self.items[0], id="a9", title="Jaws Again")
        result = prepare(self.items + [dup], set())
        aside = [c for c in result["set_aside"] if c["barcode"] == "2010000000014"]
        self.assertEqual(len(aside), 2)
        self.assertIn("barcode 2010000000014 is on 2 Libib copies", aside[0]["set_aside"])
        self.assertNotIn("2010000000014", [c["barcode"] for c in result["ready"]])

    def test_nothing_new(self):
        result = prepare(self.items, {"2010000000014", "2010000000021", "2010000000038"})
        self.assertEqual((result["ready"], result["set_aside"], result["already_in_shopify"]), ([], [], 3))


if __name__ == "__main__":
    unittest.main()
