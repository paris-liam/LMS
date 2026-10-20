import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from catalog.cli import main
from catalog.core.runs import COMPLETE_MARKER
from catalog.duplicates.match import (
    CERTAIN, LIKELY, REVIEW, edition_pairs, find_groups, fuzzy_match, normalize_title, poster_key,
)
from catalog.shopify.reader import node_to_row

DESC = "A long enough description of the film that it counts as evidence for a match."


def movie(handle, title, vendor="VHS", kind="Rental", body=DESC, image="", status="active", qty="1"):
    return {"Handle": handle, "Title": title, "Vendor": vendor, "Tags": kind, "Body (HTML)": body,
            "Image Src": image, "Status": status, "Variant Inventory Qty": qty, "Variant Barcode": "",
            "Created At": ""}


def groups_of(rows):
    groups, _ = find_groups(rows)
    return {tuple(sorted(r["Handle"] for r in g["members"])): g for g in groups}


class TestNormalizeTitle(unittest.TestCase):
    def test_punctuation_article_and_ampersand(self):
        self.assertEqual(normalize_title("The Grifters"), normalize_title("Grifters"))
        self.assertEqual(normalize_title("My Boyfriend's Back"), normalize_title("My Boyfriends Back"))
        self.assertEqual(normalize_title("Sid & Nancy"), normalize_title("Sid and Nancy"))
        self.assertEqual(normalize_title("Léon"), "leon")

    def test_format_words_year_and_editions_are_removed(self):
        self.assertEqual(normalize_title("Hostel (DVD)"), "hostel")
        self.assertEqual(normalize_title("Dune (1984)"), "dune")
        self.assertEqual(normalize_title("Troy [Limited Edition] [Blu-ray]"), "troy")

    def test_numbers_are_kept(self):
        self.assertNotEqual(normalize_title("Rocky II"), normalize_title("Rocky III"))
        self.assertNotEqual(normalize_title("101 Dalmatians"), normalize_title("102 Dalmatians"))


class TestFuzzy(unittest.TestCase):
    def test_typos_match(self):
        for a, b in [("Cowbows and Aliens", "Cowboys and Aliens"), ("101 Dalmations", "101 Dalmatians"),
                     ("Unknown Origin", "Unknown Origins"), ("Memoires of a Geisha", "Memoirs of a Geisha")]:
            self.assertTrue(fuzzy_match(normalize_title(a), normalize_title(b)), (a, b))

    def test_different_numbers_never_match(self):
        for a, b in [("101 Dalmatians", "102 Dalmatians"), ("Malevolence 2", "Malevolence 3"),
                     ("Halloween II", "Halloween III")]:
            self.assertFalse(fuzzy_match(normalize_title(a), normalize_title(b)), (a, b))

    def test_short_titles_are_not_fuzzed(self):
        self.assertFalse(fuzzy_match("saw", "sam"))


class TestPosterKey(unittest.TestCase):
    def test_reupload_suffix_is_removed(self):
        a = "https://cdn.shopify.com/s/files/1/x/files/9I7gV6wRbGnbfI3XOKjHeLMjYEo.jpg?v=1"
        b = ("https://cdn.shopify.com/s/files/1/x/files/"
             "9I7gV6wRbGnbfI3XOKjHeLMjYEo_4ed7590b-d817-42e5-81ae-4eaaac0ee99e.jpg?v=2")
        self.assertEqual(poster_key({"Image Src": a}), poster_key({"Image Src": b}))


class TestGrouping(unittest.TestCase):
    def test_exact_title_with_same_description_is_certain(self):
        g = groups_of([movie("a", "Matilda"), movie("b", "Matilda")])[("a", "b")]
        self.assertEqual((g["tier"], g["confidence"]), (1, CERTAIN))

    def test_exact_title_without_evidence_is_likely(self):
        g = groups_of([movie("a", "Hellboy", body=""), movie("b", "Hellboy", body="")])[("a", "b")]
        self.assertEqual(g["confidence"], LIKELY)

    def test_typo_with_evidence_is_likely_and_without_is_review(self):
        with_evidence = groups_of([movie("a", "Casino Royal"), movie("b", "Casino Royale")])[("a", "b")]
        self.assertEqual((with_evidence["tier"], with_evidence["confidence"]), (3, LIKELY))
        bare = groups_of([movie("a", "Casino Royal", body=""), movie("b", "Casino Royale", body="")])
        self.assertEqual(bare[("a", "b")]["confidence"], REVIEW)

    def test_formats_types_editions_and_box_sets_stay_apart(self):
        rows = [movie("vhs", "Heat"), movie("dvd", "Heat", vendor="DVD"),
                movie("sale", "Heat", kind="Floor Sale"),
                movie("ext", "Heat (Extended Edition)"), movie("set", "Heat / Ronin")]
        self.assertEqual(groups_of(rows), {})

    def test_different_years_go_to_review(self):
        rows = [movie("a", "Planet of the Apes (1968)"), movie("b", "Planet of the Apes (2001)")]
        self.assertEqual(groups_of(rows)[("a", "b")]["confidence"], REVIEW)

    def test_placeholder_posters_are_not_evidence(self):
        placeholder = "https://cdn.shopify.com/files/placeholder.jpg"
        rows = [movie(h, t, body="", image=placeholder)
                for h, t in [("a", "Logan"), ("b", "Logan"), ("c", "Heat"), ("d", "Saw"), ("e", "Pi")]]
        self.assertEqual(groups_of(rows)[("a", "b")]["confidence"], LIKELY)

    def test_unclassifiable_vendor_is_listed_not_grouped(self):
        groups, unclassifiable = find_groups([movie("a", "Tote", vendor="Little Movie Store"),
                                              movie("b", "Tote", vendor="Little Movie Store")])
        self.assertEqual(groups, [])
        self.assertEqual(len(unclassifiable), 2)

    def test_edition_pairs_are_listed(self):
        pairs = edition_pairs([movie("a", "Titanic"), movie("b", "Titanic Collector's Edition")])
        self.assertEqual(len(pairs), 1)


class TestSnapshotFields(unittest.TestCase):
    def test_reader_records_quantity_and_created_at(self):
        node = {"handle": "h", "createdAt": "2026-09-29T10:00:00Z",
                "variants": {"nodes": [{"inventoryQuantity": 3, "inventoryItem": {"tracked": True}}]}}
        row = node_to_row(node)
        self.assertEqual(row["Variant Inventory Qty"], "3")
        self.assertEqual(row["Created At"], "2026-09-29T10:00:00Z")


class TestCommand(unittest.TestCase):
    def test_writes_three_files_into_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "2026-10-02"
            run.mkdir()
            (run / COMPLETE_MARKER).write_text("done")
            rows = [movie("a", "Matilda", qty="2"), movie("b", "Matilda"), movie("c", "Heat", kind="Floor Sale")]
            (run / "snapshot.json").write_text(json.dumps(rows))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["duplicates", "--runs-dir", tmp]), 0)
            summary = (run / "duplicates-summary.txt").read_text()
            self.assertIn("3 products -> 2 (1 fewer)", summary)
            self.assertIn("quantity > 1): 1", summary)
            self.assertIn("Matilda", (run / "duplicates.csv").read_text())
            self.assertTrue((run / "duplicate-editions.csv").exists())


if __name__ == "__main__":
    unittest.main()
