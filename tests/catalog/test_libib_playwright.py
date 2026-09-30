import builtins
import unittest
from pathlib import Path
from unittest import mock

from catalog.errors import CatalogError
from catalog.libib import fix, selftest, transfer


def no_playwright():
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    return mock.patch("builtins.__import__", side_effect=fake)


class TestWithoutPlaywright(unittest.TestCase):
    """Every browser command names the Libib venv instead of a raw ImportError."""

    def assert_names_the_venv(self, command, call):
        with no_playwright(), self.assertRaises(CatalogError) as ctx:
            call()
        self.assertIn(f".venv-libib/bin/python -m catalog libib {command}", str(ctx.exception))

    def test_export(self):
        self.assert_names_the_venv("export", lambda: transfer.run_browser_export("e", "p", Path("/tmp")))

    def test_import(self):
        self.assert_names_the_venv(
            "import", lambda: transfer.run_browser_import("e", "p", Path("/tmp/i.csv"), Path("/tmp")))

    def test_selftest(self):
        self.assert_names_the_venv("selftest", lambda: selftest.run_selftest("e", "p", "01111111", Path("/tmp")))

    def test_fix(self):
        self.assert_names_the_venv(
            "fix", lambda: fix.run_fixer([{"call_number": "01111111"}], Path("/tmp/r.csv"), "e", "p", True))


if __name__ == "__main__":
    unittest.main()
