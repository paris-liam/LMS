import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from tmdb_cache import TmdbCache


class TestTmdbCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".tmdb-cache.json"
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fetcher(self, query, year):
        self.calls.append((query, year))
        return {"results": [{"title": query}]}

    def test_first_call_hits_the_fetcher(self):
        cache = TmdbCache(self.path)
        fetch = cache.wrap(self.fetcher)
        self.assertEqual(fetch("Rushmore", 1998)["results"][0]["title"], "Rushmore")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(cache.misses, 1)

    def test_repeat_call_costs_no_fetch(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("Rushmore", 1998)
        fetch("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_case_and_whitespace_insensitive_key(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("Rushmore", 1998)
        fetch("  rushmore ", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_different_year_is_a_different_query(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("The Thing", 1982)
        fetch("The Thing", 2011)
        fetch("The Thing", None)
        self.assertEqual(len(self.calls), 3)

    def test_survives_a_save_and_reload(self):
        cache = TmdbCache(self.path)
        cache.wrap(self.fetcher)("Rushmore", 1998)
        cache.save()

        reloaded = TmdbCache(self.path)
        reloaded.wrap(self.fetcher)("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(reloaded.hits, 1)

    def test_a_corrupt_cache_file_starts_empty_instead_of_crashing(self):
        self.path.write_text("{not json", encoding="utf-8")
        cache = TmdbCache(self.path)
        cache.wrap(self.fetcher)("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_a_failing_fetch_is_not_cached(self):
        def boom(query, year):
            raise RuntimeError("network down")

        cache = TmdbCache(self.path)
        fetch = cache.wrap(boom)
        with self.assertRaises(RuntimeError):
            fetch("Rushmore", 1998)
        cache.save()
        self.assertEqual(json.loads(self.path.read_text()), {})


if __name__ == "__main__":
    unittest.main()
