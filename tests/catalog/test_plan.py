import argparse
import io
import unittest
from pathlib import Path

from catalog.core import log
from catalog.core.plan import ApprovalRefused, Plan, add_approval_args, confirm


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def plan(count=3):
    return Plan(title="apply", count=count, summary=["image.csv: 3 products"],
                samples=[f"h{n}: Image Src '' -> 'x'" for n in range(12)],
                warnings=["genre.csv changes Option1"], details_path=Path("runs/r/apply-plan.csv"))


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        log.setup_logging(None, 0, self.out)

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())

    def test_render_shows_summary_warnings_capped_samples_and_details(self):
        text = plan().render()
        self.assertIn("== apply ==", text)
        self.assertIn("image.csv: 3 products", text)
        self.assertIn("genre.csv changes Option1", text)
        self.assertIn("h9:", text)
        self.assertNotIn("h10:", text)
        self.assertIn("(+2 more)", text)
        self.assertIn("runs/r/apply-plan.csv", text)

    def test_dry_run_never_proceeds_and_never_prompts(self):
        stdout = io.StringIO()
        self.assertFalse(confirm(plan(), dry_run=True, assume_yes=True, stdin=FakeStdin("y\n"), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Dry run", self.out.getvalue())

    def test_yes_proceeds_without_prompting(self):
        stdout = io.StringIO()
        self.assertTrue(confirm(plan(), dry_run=False, assume_yes=True, stdin=FakeStdin(tty=False), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")

    def test_answer_y_proceeds(self):
        stdout = io.StringIO()
        self.assertTrue(confirm(plan(), dry_run=False, assume_yes=False, stdin=FakeStdin("y\n"), stdout=stdout))
        self.assertIn("Proceed? [y/N]", stdout.getvalue())

    def test_blank_answer_declines(self):
        self.assertFalse(confirm(plan(), dry_run=False, assume_yes=False, stdin=FakeStdin("\n"), stdout=io.StringIO()))

    def test_non_tty_without_yes_refuses(self):
        with self.assertRaises(ApprovalRefused) as ctx:
            confirm(plan(), dry_run=False, assume_yes=False, stdin=FakeStdin(tty=False), stdout=io.StringIO())
        self.assertIn("--yes", str(ctx.exception))
        self.assertIn("--dry-run", str(ctx.exception))

    def test_nothing_to_do_never_prompts(self):
        stdout = io.StringIO()
        self.assertFalse(confirm(plan(count=0), dry_run=False, assume_yes=False, stdin=FakeStdin(tty=False), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Nothing to change", self.out.getvalue())

    def test_flags(self):
        parser = argparse.ArgumentParser()
        add_approval_args(parser)
        args = parser.parse_args(["--dry-run", "--yes"])
        self.assertTrue(args.dry_run and args.yes)


if __name__ == "__main__":
    unittest.main()
