import argparse
import io
import unittest
import unittest.mock
from pathlib import Path

from catalog.core import log
from catalog.core.plan import ApprovalRefused, Plan, add_approval_args, confirm, fingerprint


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def plan(count=3, samples=None):
    return Plan(title="apply", count=count, summary=["image.csv: 3 products"],
                samples=samples if samples is not None else [f"h{n}: Image Src '' -> 'x'" for n in range(12)],
                warnings=["genre.csv changes Option1"], details_path=Path("runs/r/apply-plan.csv"))


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        log.setup_logging(None, 0, self.out)

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())

    def test_render_lists_every_change_not_a_sample(self):
        text = plan().render()
        self.assertIn("== apply ==", text)
        self.assertIn("image.csv: 3 products", text)
        self.assertIn("genre.csv changes Option1", text)
        self.assertIn("changes (12):", text)
        self.assertIn("h11:", text)            # the last one too
        self.assertNotIn("more)", text)
        self.assertIn("runs/r/apply-plan.csv", text)

    def test_dry_run_prints_an_approval_code_and_never_proceeds(self):
        stdout = io.StringIO()
        self.assertFalse(confirm(plan(), dry_run=True, stdin=FakeStdin("y\n"), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Dry run", self.out.getvalue())
        self.assertIn(f"--approve {fingerprint(plan())}", self.out.getvalue())

    def test_the_matching_code_proceeds_without_prompting(self):
        stdout = io.StringIO()
        self.assertTrue(confirm(plan(), dry_run=False, approve=fingerprint(plan()),
                                stdin=FakeStdin(tty=False), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")

    def test_a_code_for_a_different_list_refuses(self):
        reviewed = fingerprint(plan())
        changed = plan(samples=[f"h{n}: Image Src '' -> 'x'" for n in range(13)])  # one more change appeared
        with self.assertRaises(ApprovalRefused) as ctx:
            confirm(changed, dry_run=False, approve=reviewed, stdin=FakeStdin(tty=False), stdout=io.StringIO())
        self.assertIn("does not match", str(ctx.exception))

    def test_the_code_depends_on_every_change(self):
        a = plan(samples=["h1: Vendor 'x' -> 'VHS'"])
        b = plan(samples=["h1: Vendor 'x' -> 'DVD'"])
        self.assertNotEqual(fingerprint(a), fingerprint(b))

    def test_answer_y_in_a_terminal_proceeds(self):
        stdout = io.StringIO()
        self.assertTrue(confirm(plan(), dry_run=False, stdin=FakeStdin("y\n"), stdout=stdout))
        self.assertIn("Make these 3 changes? [y/N]", stdout.getvalue())

    def test_blank_answer_declines(self):
        self.assertFalse(confirm(plan(), dry_run=False, stdin=FakeStdin("\n"), stdout=io.StringIO()))

    def test_no_terminal_and_no_code_refuses(self):
        with self.assertRaises(ApprovalRefused) as ctx:
            confirm(plan(), dry_run=False, stdin=FakeStdin(tty=False), stdout=io.StringIO())
        self.assertIn("--dry-run", str(ctx.exception))
        self.assertIn("--approve", str(ctx.exception))

    def test_preapproved_step_proceeds_but_still_prints_its_list(self):
        self.assertTrue(confirm(plan(), dry_run=False, preapproved=True, stdin=FakeStdin(tty=False)))
        self.assertIn("h11:", self.out.getvalue())

    def test_nothing_to_do_never_prompts(self):
        stdout = io.StringIO()
        self.assertFalse(confirm(plan(count=0), dry_run=False, stdin=FakeStdin(tty=False), stdout=stdout))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Nothing to change", self.out.getvalue())

    def test_flags_have_no_blanket_yes(self):
        parser = argparse.ArgumentParser()
        add_approval_args(parser)
        args = parser.parse_args(["--dry-run", "--approve", "abc"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.approve, "abc")
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            parser.parse_args(["--yes"])


if __name__ == "__main__":
    unittest.main()
