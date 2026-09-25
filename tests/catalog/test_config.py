import unittest

from catalog.config import DEFAULT_STORE, require_env
from catalog.errors import MissingEnvError


class TestConfig(unittest.TestCase):
    def test_default_store_is_production(self):
        self.assertEqual(DEFAULT_STORE, "p0wkgv-wy.myshopify.com")

    def test_require_env_returns_value(self):
        self.assertEqual(require_env("TMDB_API_KEY", {"TMDB_API_KEY": " abc "}), "abc")

    def test_require_env_names_the_missing_variable(self):
        with self.assertRaises(MissingEnvError) as ctx:
            require_env("TMDB_API_KEY", {})
        self.assertIn("TMDB_API_KEY", str(ctx.exception))

    def test_blank_counts_as_missing(self):
        with self.assertRaises(MissingEnvError):
            require_env("TMDB_API_KEY", {"TMDB_API_KEY": "  "})


if __name__ == "__main__":
    unittest.main()
