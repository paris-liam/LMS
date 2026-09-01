import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from master_resolve import build_fill_rows, resolve_queue
from run_master_resolve import collect_rows_by_handle, make_needs_lookup, make_product_fields_lookup


def entry(handle, title, genre="", vendor="VHS", source_folder="out-x"):
    return {"handle": handle, "title": title, "genre": genre, "vendor": vendor,
            "source_folder": source_folder}


def result(title, year="1998", poster="/p.jpg", overview="An overview long enough to count.",
           genre_ids=None, popularity=0):
    return {"title": title, "release_date": f"{year}-01-01" if year else "",
            "poster_path": poster or "", "overview": overview,
            "genre_ids": genre_ids or [], "popularity": popularity}


def fields(title="Rushmore", option1_name="Genre", option1_value="Comedy"):
    return {"Title": title, "Option1 Name": option1_name, "Option1 Value": option1_value}


class TestResolveQueue(unittest.TestCase):
    def test_a_confidently_resolvable_entry_moves_to_resolved(self):
        e = entry("jagged-edge", "Jagged Edge", genre="thriller")
        results = [result("Jagged Edge", "1985"), result("Jagged Edge", year="", poster=None)]
        resolved, still_ambiguous = resolve_queue([e], lambda entry: results)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["entry"], e)
        self.assertEqual(resolved[0]["best"]["release_date"][:4], "1985")
        self.assertEqual(still_ambiguous, [])

    def test_a_genuinely_ambiguous_entry_stays_in_still_ambiguous(self):
        """DVD (unlike VHS) gets no format-based year cutoff, so two
        same-titled candidates with no other distinguishing signal stay
        genuinely ambiguous."""
        e = entry("the-thing", "The Thing", genre="horror", vendor="DVD")
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        resolved, still_ambiguous = resolve_queue([e], lambda entry: results)
        self.assertEqual(resolved, [])
        self.assertEqual(still_ambiguous, [e])

    def test_an_entry_with_no_cached_results_stays_in_still_ambiguous(self):
        """results_lookup returning None/empty means nothing was cached for
        this query — leave it untouched rather than treating it as unmatched."""
        e = entry("mystery-title", "Mystery Title")
        resolved, still_ambiguous = resolve_queue([e], lambda entry: None)
        self.assertEqual(resolved, [])
        self.assertEqual(still_ambiguous, [e])

    def test_vhs_year_cutoff_still_applies_during_master_resolution(self):
        """Regression: the format-aware cutoff retry from build_output must
        carry over here too, not just plain classify_match."""
        e = entry("rushmore", "Rushmore", vendor="VHS")
        results = [result("Rushmore", "1998"), result("Rushmore", "2009")]
        resolved, still_ambiguous = resolve_queue([e], lambda entry: results)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["best"]["release_date"][:4], "1998")


class TestBuildFillRows(unittest.TestCase):
    def test_a_product_needing_both_fields_gets_both(self):
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster="/p.jpg", overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(
            resolved, lambda handle: (True, True),
            lambda handle: fields(title="Rushmore (Widescreen)", option1_name="Genre", option1_value="Comedy"),
        )
        self.assertEqual(len(image_rows), 1)
        row = image_rows[0]
        self.assertEqual(row["Handle"], "rushmore")
        self.assertEqual(row["Title"], "Rushmore (Widescreen)")
        self.assertEqual(row["Option1 Name"], "Genre")
        self.assertEqual(row["Option1 Value"], "Comedy")
        self.assertEqual(row["Image Src"], "https://image.tmdb.org/t/p/w1280/p.jpg")
        self.assertEqual(row["Image Alt Text"], "Rushmore (1998) poster")
        self.assertEqual(len(desc_rows), 1)
        self.assertEqual(desc_rows[0]["Title"], "Rushmore (Widescreen)")
        self.assertEqual(desc_rows[0]["Option1 Name"], "Genre")
        self.assertEqual(desc_rows[0]["Option1 Value"], "Comedy")
        self.assertEqual(desc_rows[0]["Body (HTML)"], "<p>A good movie.</p>")

    def test_a_product_that_already_has_a_description_only_gets_the_image_row(self):
        """The single most important guarantee here: never emit a
        description row for a product that isn't missing one — a blank
        cell in a present CSV column would wipe the real description on
        import."""
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster="/p.jpg", overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(resolved, lambda handle: (True, False), lambda handle: fields())
        self.assertEqual(len(image_rows), 1)
        self.assertEqual(desc_rows, [])

    def test_a_product_that_already_has_an_image_only_gets_the_description_row(self):
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster="/p.jpg", overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(resolved, lambda handle: (False, True), lambda handle: fields())
        self.assertEqual(image_rows, [])
        self.assertEqual(len(desc_rows), 1)

    def test_no_row_written_when_the_matched_candidate_lacks_that_field(self):
        """A confident title/year match with no poster on TMDB's side must
        not produce an empty Image Src row."""
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster=None, overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(resolved, lambda handle: (True, True), lambda handle: fields())
        self.assertEqual(image_rows, [])
        self.assertEqual(len(desc_rows), 1)

    def test_alt_text_omits_the_year_when_the_match_has_none(self):
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", year="", poster="/p.jpg", overview="x")}]
        image_rows, _ = build_fill_rows(resolved, lambda handle: (True, True), lambda handle: fields())
        self.assertEqual(image_rows[0]["Image Alt Text"], "Rushmore poster")

    def test_no_row_written_when_product_fields_are_unknown(self):
        """A handle build_fill_rows has no base product fields for
        (shouldn't normally happen — needs_lookup already excludes unknown
        handles — but if it ever does, never write a row missing the
        Option1 Name/Value Shopify's importer requires to identify which
        variant is being updated)."""
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster="/p.jpg", overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(resolved, lambda handle: (True, True), lambda handle: None)
        self.assertEqual(image_rows, [])
        self.assertEqual(desc_rows, [])

    def test_no_row_written_when_option1_value_is_blank(self):
        resolved = [{"entry": entry("rushmore", "Rushmore"),
                     "best": result("Rushmore", "1998", poster="/p.jpg", overview="A good movie.")}]
        image_rows, desc_rows = build_fill_rows(
            resolved, lambda handle: (True, True), lambda handle: fields(option1_value=""),
        )
        self.assertEqual(image_rows, [])
        self.assertEqual(desc_rows, [])


class TestMakeNeedsLookup(unittest.TestCase):
    def test_a_handle_present_in_only_one_batch_reports_that_rows_blanks(self):
        rows_by_handle = collect_rows_by_handle(
            {"batch-a": {"h": {"Image Src": "", "Body (HTML)": "<p>x</p>"}}}
        )
        lookup = make_needs_lookup(rows_by_handle)
        self.assertEqual(lookup("h"), (True, False))

    def test_a_handle_blank_in_every_copy_across_batches_is_reported_blank(self):
        rows_by_handle = collect_rows_by_handle({
            "batch-a": {"h": {"Image Src": "", "Body (HTML)": ""}},
            "batch-b": {"h": {"Image Src": "", "Body (HTML)": ""}},
        })
        lookup = make_needs_lookup(rows_by_handle)
        self.assertEqual(lookup("h"), (True, True))

    def test_a_handle_already_filled_in_even_one_batch_copy_is_reported_not_blank(self):
        """Regression: this must be deterministic and conservative — if any
        known copy of the handle already has real data, treat the field as
        filled rather than picking one copy at random (dict-update order
        over a set is non-deterministic across Python processes)."""
        rows_by_handle = collect_rows_by_handle({
            "batch-a": {"h": {"Image Src": "", "Body (HTML)": ""}},
            "batch-b": {"h": {"Image Src": "https://example.com/real.jpg", "Body (HTML)": ""}},
        })
        lookup = make_needs_lookup(rows_by_handle)
        self.assertEqual(lookup("h"), (False, True))

    def test_an_unknown_handle_is_reported_not_blank(self):
        """No row anywhere means nothing to safely conclude — never write a
        fill for a handle we have no base data for."""
        rows_by_handle = collect_rows_by_handle({"batch-a": {}})
        lookup = make_needs_lookup(rows_by_handle)
        self.assertEqual(lookup("missing"), (False, False))


class TestMakeProductFieldsLookup(unittest.TestCase):
    def test_returns_title_and_option1_from_the_known_copy(self):
        rows_by_handle = collect_rows_by_handle(
            {"batch-a": {"h": {"Title": "Rushmore", "Option1 Name": "Genre", "Option1 Value": "Comedy"}}}
        )
        lookup = make_product_fields_lookup(rows_by_handle)
        self.assertEqual(
            lookup("h"), {"Title": "Rushmore", "Option1 Name": "Genre", "Option1 Value": "Comedy"},
        )

    def test_falls_back_to_another_copy_when_the_first_is_missing_option1_value(self):
        rows_by_handle = collect_rows_by_handle({
            "batch-a": {"h": {"Title": "Rushmore", "Option1 Name": "Genre", "Option1 Value": ""}},
            "batch-b": {"h": {"Title": "Rushmore", "Option1 Name": "Genre", "Option1 Value": "Comedy"}},
        })
        lookup = make_product_fields_lookup(rows_by_handle)
        self.assertEqual(lookup("h")["Option1 Value"], "Comedy")

    def test_an_unknown_handle_returns_none(self):
        lookup = make_product_fields_lookup({})
        self.assertIsNone(lookup("missing"))


if __name__ == "__main__":
    unittest.main()
