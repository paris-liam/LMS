import unittest

from catalog.rental_sync.libib_duplicates import find_libib_duplicates, same_title


def row(id, title, tags="dvd, horror", created="2026-10-01", barcode="2010000000014"):
    return {"id": id, "title": title, "barcode": barcode, "call_number": "", "tags": tags,
            "description": "", "collection": "Rental Library", "created": created}


class TestSameTitle(unittest.TestCase):
    def test_exact_and_normalized(self):
        self.assertTrue(same_title("The Godfather", "Godfather"))
        self.assertTrue(same_title("The Godfather", "Godfather, The"))
        self.assertTrue(same_title("Jaws", "JAWS"))

    def test_fuzzy_typo(self):
        self.assertTrue(same_title("Terminator 2 Judgment Day", "Terminator 2 Judgement Day"))

    def test_sequel_number_differs(self):
        self.assertFalse(same_title("Rocky II", "Rocky III"))

    def test_edition_differs(self):
        self.assertFalse(same_title("Alien", "Alien Director's Cut"))

    def test_conflicting_years(self):
        self.assertFalse(same_title("Halloween (1978)", "Halloween (2018)"))

    def test_same_title_no_years_matches(self):
        self.assertTrue(same_title("Halloween", "Halloween"))

    def test_one_side_year_still_matches(self):
        self.assertTrue(same_title("Halloween (1978)", "Halloween"))


class TestFindLibibDuplicates(unittest.TestCase):
    def test_flags_new_item_matching_old_item(self):
        items = [row("old", "Jaws", created="2026-09-01"), row("new", "Jaws", created="2026-10-14")]
        found = find_libib_duplicates(items, {"new"})
        self.assertEqual(list(found), ["new"])
        self.assertEqual(found["new"]["item_id"], "old")
        self.assertEqual(found["new"]["title"], "Jaws")
        self.assertEqual(found["new"]["format"], "DVD")
        self.assertEqual(found["new"]["genres"], ["Horror"])

    def test_different_format_not_flagged(self):
        items = [row("old", "Jaws", tags="dvd, horror"), row("new", "Jaws", tags="vhs, horror")]
        self.assertEqual(find_libib_duplicates(items, {"new"}), {})

    def test_only_candidates_flagged(self):
        items = [row("old", "Jaws", created="2026-09-01"), row("new", "Jaws", created="2026-10-14")]
        self.assertNotIn("old", find_libib_duplicates(items, {"new"}))
        self.assertEqual(find_libib_duplicates(items, set()), {})

    def test_both_new_flags_only_later(self):
        items = [row("a", "Jaws", created="2026-10-14"), row("b", "Jaws", created="2026-10-15")]
        found = find_libib_duplicates(items, {"a", "b"})
        self.assertEqual(list(found), ["b"])
        self.assertEqual(found["b"]["item_id"], "a")

    def test_set_aside_wins_over_flags(self):
        items = [row("old", "Jaws"), row("new", "Jaws", tags="dvd, horor")]
        self.assertEqual(find_libib_duplicates(items, {"new"}), {})

    def test_summary_counts_copies(self):
        items = [row("old", "Jaws", created="2026-09-01"), row("old", "Jaws", created="2026-09-02"),
                 row("new", "Jaws", created="2026-10-14")]
        found = find_libib_duplicates(items, {"new"})
        self.assertEqual(found["new"]["copies"], 2)
        self.assertEqual(found["new"]["created"], "2026-09-01")

    def test_several_matches_picks_earliest(self):
        items = [row("m2", "Jaws", created="2026-09-05"), row("m1", "Jaws", created="2026-09-01"),
                 row("new", "Jaws", created="2026-10-14")]
        self.assertEqual(find_libib_duplicates(items, {"new"})["new"]["item_id"], "m1")


if __name__ == "__main__":
    unittest.main()
