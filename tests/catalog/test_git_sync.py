import sys
import unittest
from pathlib import Path
from unittest.mock import patch


from catalog.core import git_sync


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


import subprocess
import tempfile


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


class TestBranchHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "a.json").write_text('[{"handle": "x"}]', encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "tools" / "a.json").write_text("[]", encoding="utf-8")
        git(self.repo, "commit", "-qam", "feature change")

    def tearDown(self):
        self.tmp.cleanup()

    def test_current_branch(self):
        self.assertEqual(git_sync.current_branch(self.repo), "feature")

    def test_show_file_reads_a_committed_file_at_a_ref(self):
        self.assertEqual(git_sync.show_file(self.repo, "main", "tools/a.json"), '[{"handle": "x"}]')
        self.assertEqual(git_sync.show_file(self.repo, "feature", "tools/a.json"), "[]")

    def test_show_file_missing_is_none(self):
        self.assertIsNone(git_sync.show_file(self.repo, "main", "tools/nope.json"))

    def test_fetch_failure_raises(self):
        with self.assertRaises(RuntimeError):
            git_sync.fetch_branch(self.repo, "no-such-remote", "main")


class TestPublishToDeployBranch(unittest.TestCase):
    """Real git: a bare "origin", and a clone working on a cloud-style branch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin, self.seed, self.work = root / "origin.git", root / "seed", root / "work"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(root, "clone", "-q", str(self.origin), str(self.seed))
        for repo in (self.seed,):
            git(repo, "config", "user.email", "t@example.com")
            git(repo, "config", "user.name", "t")
        (self.seed / "tools").mkdir()
        (self.seed / "tools" / "a.json").write_text("[]", encoding="utf-8")
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-q", "-m", "init")
        git(self.seed, "push", "-q", "origin", "main")
        git(root, "clone", "-q", str(self.origin), str(self.work))
        git(self.work, "config", "user.email", "t@example.com")
        git(self.work, "config", "user.name", "t")
        git(self.work, "checkout", "-q", "-b", "claude/session-1")

    def tearDown(self):
        self.tmp.cleanup()

    def origin_main_file(self, path):
        return git(self.origin, "show", f"main:{path}")

    def test_publishes_from_a_session_branch_to_main(self):
        # main moved on since the session branched (e.g. the client saved a pick)
        (self.seed / "tools" / "pick.json").write_text("{}", encoding="utf-8")
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-q", "-m", "pick")
        git(self.seed, "push", "-q", "origin", "main")

        (self.work / "tools" / "a.json").write_text('["new"]', encoding="utf-8")
        result = git_sync.sync_review_picker(self.work, "tools", "picker update", deploy_branch="main")
        self.assertTrue(result["synced"], result)
        self.assertEqual(self.origin_main_file("tools/a.json"), '["new"]')
        self.assertEqual(self.origin_main_file("tools/pick.json"), "{}")  # nothing on main was lost
        self.assertEqual(git_sync.current_branch(self.work), "claude/session-1")

    def test_publishes_several_paths_together(self):
        (self.work / "tools" / "a.json").write_text('["new"]', encoding="utf-8")
        (self.work / "imports").mkdir()
        (self.work / "imports" / "x.csv").write_text("Handle\nh\n", encoding="utf-8")
        result = git_sync.sync_review_picker(self.work, ["tools", "imports"], "apply", deploy_branch="main")
        self.assertTrue(result["synced"], result)
        self.assertEqual(self.origin_main_file("imports/x.csv"), "Handle\nh\n")

    def test_a_rejected_push_keeps_the_commit_on_the_branch(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "refuse")
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'pushes to main are not allowed' >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        (self.work / "tools" / "a.json").write_text('["new"]', encoding="utf-8")
        result = git_sync.sync_review_picker(self.work, "tools", "picker update", deploy_branch="main")
        self.assertFalse(result["synced"])
        self.assertEqual(result["reason"], "push failed")
        self.assertIn("picker update", git(self.work, "log", "-1", "--format=%s"))


class TestDirtyPathsOutsideSeveral(unittest.TestCase):
    def test_changes_under_any_allowed_prefix_are_clean(self):
        status = " M tools/review-picker/x.json\n?? imports/2026-09-28/genre.csv\n M catalog/x.py\n"
        with patch.object(git_sync, "_run", return_value=FakeResult(stdout=status)):
            outside = git_sync.dirty_paths_outside("/repo", ["tools/review-picker", "imports"])
        self.assertEqual(outside, ["catalog/x.py"])


if __name__ == "__main__":
    unittest.main()
