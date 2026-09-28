import csv
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.runs import new_run
from catalog.errors import InputShapeError
from catalog.shopify.snapshot import blank_row, write_snapshot
from catalog.tmdb import lookup_command
from catalog.tmdb.lookup import LOOKUP_COLUMNS, has_tag, lookup


def movie(handle, title, tags, **overrides):
    row = blank_row()
    row.update({"Handle": handle, "Title": title, "Tags": tags, "Vendor": "DVD", GENRE_METAFIELD: "horror"})
    row.update(overrides)
    return row


def tmdb(title, year, **extra):
    return {"id": extra.pop("id", 1), "title": title, "release_date": f"{year}-01-01", "poster_path": "/p.jpg",
            "overview": "An overview.", "genre_ids": [27], "popularity": 5, **extra}


def fetcher(by_query, calls=None):
    def fetch(query, year):
        if calls is not None:
            calls.append(query)
        return {"results": by_query.get(query, [])}
    return fetch


class TestHasTag(unittest.TestCase):
    def test_matches_whole_tags_ignoring_case_and_spaces(self):
        self.assertTrue(has_tag({"Tags": "Rental, Staff Picks, Horror"}, "staff picks"))
        self.assertFalse(has_tag({"Tags": "Rental, Staff Picks II"}, "Staff Picks"))
        self.assertFalse(has_tag({"Tags": ""}, "Staff Picks"))


class TestLookup(unittest.TestCase):
    def test_only_tagged_products_are_looked_up_even_with_a_poster(self):
        rows = [movie("the-thing-dvd", "The Thing", "Rental, Staff Picks", **{"Image Src": "https://cdn/x.jpg"}),
                movie("jaws-dvd", "Jaws", "Rental")]
        calls = []
        out = lookup(rows, "staff picks", fetcher({"The Thing": [tmdb("The Thing", 1982, id=1091)]}, calls))
        self.assertEqual(calls, ["The Thing"])
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(list(r), LOOKUP_COLUMNS)
        self.assertEqual((r["Handle"], r["Match"], r["TMDB Title"], r["TMDB Year"], r["TMDB ID"]),
                         ("the-thing-dvd", "confident", "The Thing", "1982", "1091"))
        self.assertEqual(r["Poster URL"], "https://image.tmdb.org/t/p/w1280/p.jpg")
        self.assertEqual((r["Has Poster"], r["Has Description"]), ("yes", "no"))

    def test_no_match_leaves_tmdb_columns_blank(self):
        out = lookup([movie("x-dvd", "Nothing Here", "Staff Picks")], "Staff Picks", fetcher({}))
        self.assertEqual(out[0]["Match"], "none")
        self.assertEqual((out[0]["TMDB Title"], out[0]["Poster URL"]), ("", ""))


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name)
        run = new_run(self.runs, date(2026, 9, 28))
        write_snapshot(run / "snapshot.json", [movie("the-thing-dvd", "The Thing", "Staff Picks"),
                                               movie("jaws-dvd", "Jaws", "Rental")])
        (run / "run-report.txt").write_text("done", encoding="utf-8")
        self.run_dir = run

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, tag):
        return Namespace(tag=tag, run=None, no_cache=True, runs_dir=str(self.runs), verbose=False, quiet=True)

    def test_writes_a_csv_in_the_run_folder(self):
        code = lookup_command.run_command(self.args("Staff Picks"),
                                          fetch_fn=fetcher({"The Thing": [tmdb("The Thing", 1982)]}))
        self.assertEqual(code, 0)
        path = self.run_dir / "tmdb-lookup-staff-picks.csv"
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["Handle"] for r in rows], ["the-thing-dvd"])

    def test_unknown_tag_is_an_input_error(self):
        with self.assertRaises(InputShapeError):
            lookup_command.run_command(self.args("Nope"), fetch_fn=fetcher({}))


if __name__ == "__main__":
    unittest.main()
