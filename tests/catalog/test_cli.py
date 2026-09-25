import contextlib
import io
import unittest

from catalog.cli import main


class TestCli(unittest.TestCase):
    def test_help_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("catalog", out.getvalue())

    def test_unknown_command_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main(["nonsense"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
