import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

import git_sync


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestDirtyPathsOutside(unittest.TestCase):
    def test_all_changes_inside_allowed_prefix_is_clean(self):
        status = " M tools/review-picker/batches.json\n?? tools/review-picker/data/x.json\n"
        with patch.object(git_sync, "_run", return_value=FakeResult(stdout=status)):
            self.assertEqual(git_sync.dirty_paths_outside("/repo", "tools/review-picker"), [])

    def test_a_change_outside_the_prefix_is_reported(self):
        status = " M formatting-scripts/run.py\n M tools/review-picker/batches.json\n"
        with patch.object(git_sync, "_run", return_value=FakeResult(stdout=status)):
            outside = git_sync.dirty_paths_outside("/repo", "tools/review-picker")
            self.assertEqual(len(outside), 1)
            self.assertIn("run.py", outside[0])

    def test_a_rename_is_checked_on_both_sides(self):
        status = "R  old-file.py -> tools/review-picker/new-file.py\n"
        with patch.object(git_sync, "_run", return_value=FakeResult(stdout=status)):
            outside = git_sync.dirty_paths_outside("/repo", "tools/review-picker")
            self.assertEqual(len(outside), 1)

    def test_empty_status_is_clean(self):
        with patch.object(git_sync, "_run", return_value=FakeResult(stdout="")):
            self.assertEqual(git_sync.dirty_paths_outside("/repo", "tools/review-picker"), [])

    def test_git_status_failure_raises(self):
        with patch.object(git_sync, "_run", return_value=FakeResult(returncode=1, stderr="fatal: not a repo")):
            with self.assertRaises(RuntimeError):
                git_sync.dirty_paths_outside("/repo", "tools/review-picker")


class TestSyncReviewPicker(unittest.TestCase):
    def test_dirty_tree_outside_skips_pull_entirely(self):
        with patch.object(git_sync, "dirty_paths_outside", return_value=["formatting-scripts/run.py"]), \
             patch.object(git_sync, "_run") as run_mock:
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")
            self.assertFalse(result["synced"])
            self.assertEqual(result["reason"], "dirty tree outside review-picker")
            run_mock.assert_not_called()

    def test_pull_failure_stops_before_commit(self):
        calls = []

        def fake_run(args, cwd):
            calls.append(args[1])
            if args[1] == "pull":
                return FakeResult(returncode=1, stderr="conflict")
            return FakeResult(returncode=0)

        with patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")
            self.assertFalse(result["synced"])
            self.assertEqual(result["reason"], "pull failed")
            self.assertEqual(calls, ["pull"])

    def test_nothing_staged_after_add_is_not_an_error(self):
        def fake_run(args, cwd):
            if args[1] == "diff":
                return FakeResult(returncode=0)  # quiet diff = nothing staged
            return FakeResult(returncode=0)

        with patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")
            self.assertFalse(result["synced"])
            self.assertEqual(result["reason"], "nothing to commit")

    def test_push_failure_reports_commit_was_kept_locally(self):
        def fake_run(args, cwd):
            if args[1] == "diff":
                return FakeResult(returncode=1)  # something staged
            if args[1] == "push":
                return FakeResult(returncode=1, stderr="rejected")
            return FakeResult(returncode=0)

        with patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")
            self.assertFalse(result["synced"])
            self.assertEqual(result["reason"], "push failed")

    def test_full_success_path(self):
        def fake_run(args, cwd):
            if args[1] == "diff":
                return FakeResult(returncode=1)  # something staged
            return FakeResult(returncode=0)

        with patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")
            self.assertTrue(result["synced"])

    def test_never_passes_force_or_no_verify_to_any_git_call(self):
        seen_args = []

        def fake_run(args, cwd):
            seen_args.append(args)
            if args[1] == "diff":
                return FakeResult(returncode=1)
            return FakeResult(returncode=0)

        with patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            git_sync.sync_review_picker("/repo", "tools/review-picker", "msg")

        flat = [arg for call in seen_args for arg in call]
        self.assertNotIn("--force", flat)
        self.assertNotIn("-f", flat)
        self.assertNotIn("--no-verify", flat)


if __name__ == "__main__":
    unittest.main()
