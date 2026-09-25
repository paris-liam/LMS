import argparse
import io
import tempfile
import unittest
from pathlib import Path

from catalog.core import log


def lines(stream: io.StringIO) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line]


class TestLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "run" / "audit.log"

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())  # release the file handler
        self.tmp.cleanup()

    def emit_all(self):
        log.header("audit")
        log.progress(1, 2, "Rushmore", "filled image")
        log.detail("rule genre-alias fired")
        log.summary("3 findings")

    def test_normal_shows_progress_not_detail(self):
        out = io.StringIO()
        log.setup_logging(None, 0, out)
        self.emit_all()
        self.assertEqual(lines(out), ["== audit ==", "[1/2] Rushmore: filled image", "3 findings"])

    def test_quiet_shows_headers_and_summary_only(self):
        out = io.StringIO()
        log.setup_logging(None, -1, out)
        self.emit_all()
        self.assertEqual(lines(out), ["== audit ==", "3 findings"])

    def test_verbose_shows_detail(self):
        out = io.StringIO()
        log.setup_logging(None, 1, out)
        self.emit_all()
        self.assertIn("rule genre-alias fired", lines(out))

    def test_file_gets_everything_even_when_quiet(self):
        log.setup_logging(self.log_path, -1, io.StringIO())
        self.emit_all()
        text = self.log_path.read_text(encoding="utf-8")
        for fragment in ("== audit ==", "[1/2] Rushmore", "rule genre-alias fired", "3 findings"):
            self.assertIn(fragment, text)

    def test_setup_twice_does_not_duplicate_lines(self):
        out = io.StringIO()
        log.setup_logging(None, 0, io.StringIO())
        log.setup_logging(None, 0, out)
        log.summary("once")
        self.assertEqual(lines(out), ["once"])

    def test_verbosity_flags(self):
        parser = argparse.ArgumentParser()
        log.add_verbosity_args(parser)
        self.assertEqual(log.verbosity(parser.parse_args([])), 0)
        self.assertEqual(log.verbosity(parser.parse_args(["-q"])), -1)
        self.assertEqual(log.verbosity(parser.parse_args(["--verbose"])), 1)


if __name__ == "__main__":
    unittest.main()
