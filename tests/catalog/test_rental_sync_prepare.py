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

    def test_legacy_item_with_a_201_barcode_is_not_new_flow(self):
        legacy = dict(self.items[0], id="a8", barcode="2010000000045", call_number="191-VHSJAW-001A")
        result = prepare(self.items + [legacy], set())
        barcodes = {c["barcode"] for c in result["ready"] + result["set_aside"]}
        self.assertNotIn("2010000000045", barcodes)
        self.assertEqual(result["not_new_flow"], 2)

    def test_copy_carries_item_id(self):
        result = prepare(self.items, set())
        self.assertEqual(result["ready"][1]["item_id"], "a1")
        self.assertEqual(result["ready"][1]["siblings_in_shopify"], [])
        self.assertIsNone(result["ready"][1]["match"])

    def test_new_copy_of_synced_item_lists_siblings(self):
        extra = dict(self.items[3], barcode="2010000000045")
        result = prepare(self.items + [extra], {"2010000000038"})
        copy = next(c for c in result["ready"] if c["barcode"] == "2010000000045")
        self.assertEqual(copy["item_id"], "a4")
        self.assertEqual(copy["siblings_in_shopify"], ["2010000000038"])
        self.assertIsNone(copy["libib_duplicate"])

    def test_new_copy_of_legacy_item_lists_legacy_siblings(self):
        old = dict(self.items[3], id="c1", title="Fences", barcode="79859194")
        new = dict(old, barcode="2010000000045")
        result = prepare(self.items + [old, new], set())
        copy = next(c for c in result["ready"] if c["barcode"] == "2010000000045")
        self.assertEqual(copy["legacy_siblings"], ["79859194"])
        self.assertEqual(copy["siblings_in_shopify"], [])
        self.assertNotIn("79859194", {c["barcode"] for c in result["ready"] + result["set_aside"]})

    def test_legacy_sibling_is_its_call_number(self):
        old = dict(self.items[3], id="c1", title="Fences", barcode="2010000000052", call_number="20144891")
        new = dict(old, barcode="2010000000045", call_number="")
        result = prepare(self.items + [old, new], set())
        copy = next(c for c in result["ready"] if c["barcode"] == "2010000000045")
        self.assertEqual(copy["legacy_siblings"], ["20144891"])

    def test_item_with_legacy_copies_is_not_a_libib_duplicate(self):
        old = dict(self.items[0], id="c1", barcode="79859194", created="2026-10-20")
        new = dict(old, barcode="2010000000045")
        result = prepare(self.items + [old, new], set())
        copy = next(c for c in result["ready"] if c["barcode"] == "2010000000045")
        self.assertIsNone(copy["libib_duplicate"])

    def test_new_item_has_no_legacy_siblings(self):
        result = prepare(self.items, set())
        self.assertEqual([c["legacy_siblings"] for c in result["ready"]], [[], []])

    def test_duplicate_item_flagged(self):
        twin = dict(self.items[0], id="b1", barcode="2010000000052", created="2026-10-20")
        result = prepare(self.items + [twin], set())
        copy = next(c for c in result["ready"] if c["item_id"] == "b1")
        self.assertEqual(copy["libib_duplicate"]["item_id"], "a1")
        original = next(c for c in result["ready"] if c["item_id"] == "a1")
        self.assertIsNone(original["libib_duplicate"])

    def test_nothing_new(self):
        result = prepare(self.items, {"2010000000014", "2010000000021", "2010000000038"})
        self.assertEqual((result["ready"], result["set_aside"], result["already_in_shopify"]), ([], [], 3))


if __name__ == "__main__":
    unittest.main()
