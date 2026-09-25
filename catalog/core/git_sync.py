"""Git helpers for the review picker: auto pull/commit/push of
tools/review-picker after `picker push`, and reading the picker's pick files
straight from the deploy branch for `apply`. Tests never run real git
against this repo.

Deliberately conservative: refuses to pull if there's uncommitted work
anywhere outside the review-picker directory (a pull could tangle with
unrelated in-progress edits), never force-pushes, never skips hooks, and
reports a failure at any step rather than retrying or masking it — the
CSV outputs from run.py are already written by the time this runs, so a
sync failure here never costs you the normalization/TMDB-fill work.
"""

import subprocess
from pathlib import Path


def _run(args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def dirty_paths_outside(repo_root, allowed_prefix: str) -> list[str]:
    """Paths (relative to repo_root) with uncommitted changes that are NOT
    under allowed_prefix. Empty list means the tree is clean enough to pull."""
    result = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stderr.strip()}")

    prefix = allowed_prefix.rstrip("/") + "/"
    outside = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Porcelain format: "XY path" or "XY old -> new" for renames.
        path = line[3:].strip()
        for part in path.split(" -> "):
            part = part.strip().strip('"')
            if not part.startswith(prefix):
                outside.append(path)
                break
    return outside


def sync_review_picker(repo_root, tools_dir_rel: str, commit_message: str, log_fn=lambda m: None,
                       deploy_branch: str | None = None) -> dict:
    """Pull, then commit + push tools_dir_rel if it has changes. Returns
    {"synced": bool, "reason": str, ...} — never raises for an expected
    failure (wrong branch, dirty tree, pull/commit/push failure); those are
    reported, not thrown. With deploy_branch set, refuses unless the checkout
    is on that branch (pushing any other branch never reaches the host)."""
    repo_root = Path(repo_root)

    if deploy_branch is not None:
        try:
            branch = current_branch(repo_root)
        except RuntimeError as exc:
            return {"synced": False, "reason": "git rev-parse failed", "detail": str(exc)}
        if branch != deploy_branch:
            reason = f"on branch {branch}; the picker deploys from {deploy_branch}"
            log_fn(f"git sync skipped: {reason} — publish {tools_dir_rel} from {deploy_branch}.")
            return {"synced": False, "reason": reason}

    try:
        outside = dirty_paths_outside(repo_root, tools_dir_rel)
    except RuntimeError as exc:
        log_fn(f"git sync skipped: {exc}")
        return {"synced": False, "reason": "git status failed", "detail": str(exc)}

    if outside:
        log_fn(
            f"git sync skipped: uncommitted changes outside {tools_dir_rel} "
            f"({len(outside)} path(s)) — resolve those first, {tools_dir_rel} "
            "changes are left uncommitted for you to sync by hand."
        )
        return {"synced": False, "reason": "dirty tree outside review-picker", "paths": outside}

    pull = _run(["git", "pull", "--no-rebase"], cwd=repo_root)
    if pull.returncode != 0:
        log_fn(f"git sync skipped: git pull failed:\n{pull.stderr.strip()}")
        return {"synced": False, "reason": "pull failed", "detail": pull.stderr.strip()}

    add = _run(["git", "add", tools_dir_rel], cwd=repo_root)
    if add.returncode != 0:
        log_fn(f"git sync skipped: git add failed:\n{add.stderr.strip()}")
        return {"synced": False, "reason": "add failed", "detail": add.stderr.strip()}

    staged = _run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
    if staged.returncode == 0:
        # Nothing actually changed under tools_dir_rel (e.g. merge-produced
        # identical content) -- nothing to commit, not an error.
        return {"synced": False, "reason": "nothing to commit"}

    commit = _run(["git", "commit", "-m", commit_message], cwd=repo_root)
    if commit.returncode != 0:
        log_fn(f"git sync: commit failed (changes remain staged):\n{commit.stderr.strip()}")
        return {"synced": False, "reason": "commit failed", "detail": commit.stderr.strip()}

    push = _run(["git", "push"], cwd=repo_root)
    if push.returncode != 0:
        log_fn(
            "git sync: push failed (commit was made locally, not pushed):\n"
            f"{push.stderr.strip()}"
        )
        return {"synced": False, "reason": "push failed", "detail": push.stderr.strip()}

    log_fn(f"git sync: pulled, committed, and pushed {tools_dir_rel}")
    return {"synced": True}


def current_branch(repo_root) -> str:
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {result.stderr.strip()}")
    return result.stdout.strip()


def fetch_branch(repo_root, remote: str, branch: str) -> None:
    result = _run(["git", "fetch", remote, branch], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"git fetch {remote} {branch} failed: {result.stderr.strip()}")


def show_file(repo_root, ref: str, path: str) -> str | None:
    """A file's contents at `ref`, or None if it doesn't exist there."""
    result = _run(["git", "show", f"{ref}:{path}"], cwd=repo_root)
    return result.stdout if result.returncode == 0 else None
