import io
import json
import unittest
from urllib.parse import parse_qs, urlparse

from catalog.tmdb.client import make_fetcher


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestClient(unittest.TestCase):
    def test_builds_query_and_sleeps_after_each_request(self):
        seen, sleeps = [], []

        def urlopen(url, timeout):
            seen.append(url)
            return FakeResponse(json.dumps({"results": [1]}).encode())

        fetch = make_fetcher("KEY", sleep_fn=sleeps.append, urlopen=urlopen)
        self.assertEqual(fetch("Rushmore", 1998), {"results": [1]})
        params = parse_qs(urlparse(seen[0]).query)
        self.assertEqual(params["query"], ["Rushmore"])
        self.assertEqual(params["primary_release_year"], ["1998"])
        self.assertEqual(params["api_key"], ["KEY"])
        self.assertEqual(len(sleeps), 1)

    def test_no_year_param_when_year_is_none(self):
        seen = []
        fetch = make_fetcher("KEY", sleep_fn=lambda s: None,
                             urlopen=lambda url, timeout: seen.append(url) or FakeResponse(b'{"results": []}'))
        fetch("Rushmore", None)
        self.assertNotIn("primary_release_year", seen[0])

    def test_sleeps_even_when_request_fails(self):
        sleeps = []

        def urlopen(url, timeout):
            raise OSError("down")

        fetch = make_fetcher("KEY", sleep_fn=sleeps.append, urlopen=urlopen)
        with self.assertRaises(OSError):
            fetch("Rushmore", None)
        self.assertEqual(len(sleeps), 1)

    def test_401_raises_an_auth_error(self):
        import urllib.error
        from catalog.errors import CatalogError

        def urlopen(url, timeout):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

        fetch = make_fetcher("BAD", sleep_fn=lambda s: None, urlopen=urlopen)
        with self.assertRaises(CatalogError) as ctx:
            fetch("Rushmore", None)
        self.assertIn("TMDB_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
