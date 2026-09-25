"""Run folders: runs/<YYYY-MM-DD>[-N]/, one per audit.

A run is complete once COMPLETE_MARKER exists (audit writes it last), so a
crashed or interrupted audit is never picked up as "the latest run".
"""

import re
from datetime import date
from pathlib import Path

from catalog.errors import NoRunError

COMPLETE_MARKER = "run-report.txt"
RUN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")


def _sort_key(path: Path):
    match = RUN_NAME.match(path.name)
    return (match.group(1), int(match.group(2) or 1))


def list_runs(runs_dir) -> list[Path]:
    """Every run folder (complete or not), oldest first."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    runs = [p for p in runs_dir.iterdir() if p.is_dir() and RUN_NAME.match(p.name)]
    return sorted(runs, key=_sort_key)


def new_run(runs_dir, today: date) -> Path:
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    base = today.isoformat()
    candidate = runs_dir / base
    index = 2
    while candidate.exists():
        candidate = runs_dir / f"{base}-{index}"
        index += 1
    candidate.mkdir()
    return candidate


def resolve_run(runs_dir, run_id: str | None = None) -> Path:
    """The named run, or the latest complete one."""
    if run_id:
        path = Path(runs_dir) / run_id
        if not path.is_dir():
            raise NoRunError(f"run {run_id!r} not found in {runs_dir}")
        return path
    complete = [p for p in list_runs(runs_dir) if (p / COMPLETE_MARKER).exists()]
    if not complete:
        raise NoRunError(f"no completed audit run in {runs_dir} — run `python3 -m catalog audit` first")
    return complete[-1]
