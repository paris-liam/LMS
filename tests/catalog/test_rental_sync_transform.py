import unittest

from catalog.core.barcodes import is_new_flow_barcode
from catalog.rental_sync.transform import edit_distance, misspelling_of, transform, vocabulary


def item(**overrides):
    base = {"barcode": "2010000000014", "title": "Jaws", "tags": "horror, vhs",
            "description": "A shark.", "created": "2026-10-14 10:00:00"}
    base.update(overrides)
    return base


class TestBarcodes(unittest.TestCase):
    def test_new_flow_barcode(self):
        self.assertTrue(is_new_flow_barcode("2010000000014"))
        self.assertTrue(is_new_flow_barcode(" 2010000000014 "))
        self.assertFalse(is_new_flow_barcode("20144890"))        # legacy 8-digit that starts 201
        self.assertFalse(is_new_flow_barcode("2020000000014"))
        self.assertFalse(is_new_flow_barcode("201000000001"))    # 12 digits
        self.assertFalse(is_new_flow_barcode(""))
        self.assertFalse(is_new_flow_barcode(None))


class TestTransform(unittest.TestCase):
    def test_clean_copy(self):
        copy = transform(item())
        self.assertEqual(copy["title"], "Jaws")
        self.assertEqual(copy["format"], "VHS")
        self.assertEqual(copy["genres"], [{"handle": "horror", "name": "Horror"}])
        self.assertEqual(copy["extra_tags"], [])
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["warnings"], [])
        self.assertEqual(copy["libib"], item())

    def test_every_format_maps_to_vendor(self):
        expected = {"vhs": "VHS", "dvd": "DVD", "blu-ray": "Blu-Ray", "4k": "4K",
                    "laserdisc": "Laserdisc", "betamax": "Betamax"}
        for tag, vendor in expected.items():
            self.assertEqual(transform(item(tags=f"{tag}, drama"))["format"], vendor)

    def test_genre_order_is_libib_order_and_names_come_from_the_taxonomy(self):
        copy = transform(item(tags="kids-family, sci-fi, vhs"))
        self.assertEqual(copy["genres"], [{"handle": "kids-family", "name": "Kids & Family"},
                                          {"handle": "sci-fi", "name": "Sci-Fi"}])

    def test_whitespace_collapsed(self):
        copy = transform(item(title="  The   Thing ", description=" A\n  shapeshifter. "))
        self.assertEqual((copy["title"], copy["description"]), ("The Thing", "A shapeshifter."))

    def test_messy_tag_string(self):
        copy = transform(item(tags="VHS, vhs ,Horror,, Kids & Family"))
        self.assertEqual(copy["format"], "VHS")
        self.assertEqual([g["handle"] for g in copy["genres"]], ["horror", "kids-family"])
        self.assertEqual(copy["set_aside"], [])
        spaced = transform(item(tags="Blu Ray, sci fi, SCI_FI"))
        self.assertEqual((spaced["format"], [g["handle"] for g in spaced["genres"]]), ("Blu-Ray", ["sci-fi"]))
        self.assertEqual(spaced["set_aside"], [])

    def test_blank_title_sets_aside(self):
        self.assertIn("title is blank", transform(item(title="   "))["set_aside"])

    def test_no_format_sets_aside(self):
        copy = transform(item(tags="horror"))
        self.assertEqual((copy["format"], copy["set_aside"]), ("", ["no format tag"]))

    def test_two_formats_set_aside(self):
        copy = transform(item(tags="vhs, dvd, horror"))
        self.assertEqual(copy["format"], "")
        self.assertEqual(copy["set_aside"], ["more than one format tag (VHS, DVD)"])

    def test_no_genre_sets_aside(self):
        self.assertEqual(transform(item(tags="vhs"))["set_aside"], ["no genre tag"])

    def test_misspellings_set_aside_and_name_the_term(self):
        for tag, meant in (("horor", "horror"), ("bluray", "blu-ray"), ("scifi", "sci-fi"),
                           ("thrillers", "thriller"), ("dvds", "dvd"), ("ld", "laserdisc"), ("kids", "kids-family")):
            copy = transform(item(tags=f"vhs, drama, {tag}"))
            self.assertEqual(copy["set_aside"], [f"tag '{tag}' looks like a misspelling of '{meant}'"], tag)
            self.assertEqual(copy["extra_tags"], [], tag)

    def test_real_extra_tags_pass_through_with_a_warning(self):
        copy = transform(item(tags="vhs, horror, criterion, OOP, signed, music"))
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["extra_tags"], ["criterion", "OOP", "signed", "music"])
        self.assertEqual(copy["warnings"], ["extra tags: criterion, OOP, signed, music"])

    def test_warnings(self):
        copy = transform(item(title="Jaws [VHS]", description="",
                              tags="vhs, horror, drama, action, comedy"))
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["warnings"], ["title may need cleanup", "4 genres — usually 1–3", "no description"])
        self.assertIn("title may need cleanup", transform(item(title="Heat (Special Edition)"))["warnings"])


class TestHelpers(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance("horror", "horror"), 0)
        self.assertEqual(edit_distance("horor", "horror"), 1)
        self.assertEqual(edit_distance("hororr", "horror"), 1)   # adjacent swap counts once
        self.assertEqual(edit_distance("music", "musical"), 2)

    def test_misspelling_of_ignores_short_and_far_tags(self):
        self.assertIsNone(misspelling_of("oop"))
        self.assertIsNone(misspelling_of("criterion"))
        self.assertIsNone(misspelling_of("music"))   # 5 letters: only 1 edit allowed

    def test_vocabulary(self):
        vocab = vocabulary()
        self.assertEqual(vocab["formats"], ["vhs", "dvd", "blu-ray", "4k", "laserdisc", "betamax"])
        self.assertIn("kids-family", vocab["genres"])
        self.assertEqual(len(vocab["genres"]), 15)


if __name__ == "__main__":
    unittest.main()
