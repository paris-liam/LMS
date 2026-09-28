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


def dirty_paths_outside(repo_root, allowed_prefix) -> list[str]:
    """Paths (relative to repo_root) with uncommitted changes that are NOT
    under allowed_prefix (a path, or a list of them). Empty list means the
    tree is clean enough to pull."""
    result = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stderr.strip()}")

    prefixes = [allowed_prefix] if isinstance(allowed_prefix, str) else list(allowed_prefix)
    prefixes = tuple(p.rstrip("/") + "/" for p in prefixes)
    outside = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Porcelain format: "XY path" or "XY old -> new" for renames.
        path = line[3:].strip()
        for part in path.split(" -> "):
            part = part.strip().strip('"')
            if not part.startswith(prefixes):
                outside.append(path)
                break
    return outside


def sync_review_picker(repo_root, tools_dir_rel, commit_message: str, log_fn=lambda m: None,
                       deploy_branch: str | None = None, remote: str = "origin") -> dict:
    """Pull, then commit + push tools_dir_rel (a path, or a list of them) if
    it has changes. Returns {"synced": bool, "reason": str, ...} — never
    raises for an expected failure (dirty tree, pull/commit/push failure);
    those are reported, not thrown.

    With deploy_branch set, the result is published to that branch from
    whatever branch is checked out (a cloud session works on its own
    branch): merge remote/deploy_branch in, commit, then push HEAD to
    remote/deploy_branch — always a fast-forward, never a force. If the push
    is refused, the commit stays on the current branch."""
    repo_root = Path(repo_root)
    paths = [tools_dir_rel] if isinstance(tools_dir_rel, str) else list(tools_dir_rel)
    label = ", ".join(paths)

    try:
        outside = dirty_paths_outside(repo_root, paths)
    except RuntimeError as exc:
        log_fn(f"git sync skipped: {exc}")
        return {"synced": False, "reason": "git status failed", "detail": str(exc)}

    if outside:
        log_fn(
            f"git sync skipped: uncommitted changes outside {label} "
            f"({len(outside)} path(s)) — resolve those first, {label} "
            "changes are left uncommitted for you to sync by hand."
        )
        return {"synced": False, "reason": "dirty tree outside review-picker", "paths": outside}

    pull_args = ["git", "pull", "--no-rebase"] + ([remote, deploy_branch] if deploy_branch else [])
    pull = _run(pull_args, cwd=repo_root)
    if pull.returncode != 0:
        log_fn(f"git sync skipped: git pull failed:\n{pull.stderr.strip()}")
        return {"synced": False, "reason": "pull failed", "detail": pull.stderr.strip()}

    add = _run(["git", "add", "--", *paths], cwd=repo_root)
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

    push_args = ["git", "push"] + ([remote, f"HEAD:{deploy_branch}"] if deploy_branch else [])
    push = _run(push_args, cwd=repo_root)
    if push.returncode != 0:
        log_fn(
            "git sync: push failed (commit was made locally, not pushed):\n"
            f"{push.stderr.strip()}"
        )
        return {"synced": False, "reason": "push failed", "detail": push.stderr.strip()}

    log_fn(f"git sync: pulled, committed, and pushed {label}" + (f" to {deploy_branch}" if deploy_branch else ""))
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
