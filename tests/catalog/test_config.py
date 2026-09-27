import unittest
from pathlib import Path

from catalog.config import DEFAULT_STORE, require_env
from catalog.errors import MissingEnvError


class TestConfig(unittest.TestCase):
    def test_default_store_is_production(self):
        self.assertEqual(DEFAULT_STORE, "p0wkgv-wy.myshopify.com")

    def test_require_env_returns_value(self):
        self.assertEqual(require_env("TMDB_API_KEY", {"TMDB_API_KEY": " abc "}), "abc")

    def test_require_env_names_the_missing_variable(self):
        with self.assertRaises(MissingEnvError) as ctx:
            require_env("TMDB_API_KEY", {}, env_file="/nonexistent/.env")
        self.assertIn("TMDB_API_KEY", str(ctx.exception))

    def test_blank_counts_as_missing(self):
        with self.assertRaises(MissingEnvError):
            require_env("TMDB_API_KEY", {"TMDB_API_KEY": "  "}, env_file="/nonexistent/.env")


class TestDotEnv(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tmp.name) / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_the_dotenv_file_when_not_exported(self):
        self.env_file.write_text("# secrets\nTMDB_API_KEY='abc123'\nexport LIBIB_EMAIL=\"me@x.com\"\n\nBAD LINE\n",
                                 encoding="utf-8")
        self.assertEqual(require_env("TMDB_API_KEY", {}, env_file=self.env_file), "abc123")
        self.assertEqual(require_env("LIBIB_EMAIL", {}, env_file=self.env_file), "me@x.com")

    def test_an_exported_value_wins(self):
        self.env_file.write_text("TMDB_API_KEY=from-file\n", encoding="utf-8")
        self.assertEqual(require_env("TMDB_API_KEY", {"TMDB_API_KEY": "exported"}, env_file=self.env_file), "exported")

    def test_missing_everywhere_names_the_file(self):
        with self.assertRaises(MissingEnvError) as ctx:
            require_env("LIBIB_PASSWORD", {}, env_file=self.env_file)
        self.assertIn(".env", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
