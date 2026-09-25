"""Show what a command is about to change, then ask before changing it.

Every command that writes outside its own run folder builds a Plan and calls
confirm(). --dry-run shows the plan and stops. --yes approves without asking.
Without a terminal to ask in, and without --yes, the command refuses — so
nothing (including an agent running the command) can approve by accident.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from catalog.core import log
from catalog.errors import CatalogError

MAX_SAMPLES = 10


class ApprovalRefused(CatalogError):
    """Approval was needed but there was no terminal to ask in and no --yes."""


@dataclass
class Plan:
    title: str
    count: int                       # how many changes; 0 means nothing to do
    summary: list[str]
    samples: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details_path: Path | None = None

    def render(self) -> str:
        lines = [f"== {self.title} =="]
        lines += [f"  {line}" for line in self.summary]
        lines += [f"  ! {warning}" for warning in self.warnings]
        if self.samples:
            lines.append("  sample:")
            lines += [f"    {s}" for s in self.samples[:MAX_SAMPLES]]
            if len(self.samples) > MAX_SAMPLES:
                lines.append(f"    (+{len(self.samples) - MAX_SAMPLES} more)")
        if self.details_path is not None:
            lines.append(f"  Full list: {self.details_path}")
        return "\n".join(lines)


def confirm(plan: Plan, *, dry_run: bool, assume_yes: bool, stdin=None, stdout=None) -> bool:
    for line in plan.render().splitlines():
        log.summary(line)
    if plan.count == 0:
        log.summary("Nothing to change.")
        return False
    if dry_run:
        log.summary("Dry run — nothing was changed.")
        return False
    if assume_yes:
        log.summary("Approved with --yes.")
        return True
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if not stdin.isatty():
        raise ApprovalRefused(
            "this command changes files and needs approval, but it is not running in a terminal. "
            "Re-run with --dry-run to preview, or --yes to approve."
        )
    stdout.write("Proceed? [y/N] ")
    stdout.flush()
    approved = stdin.readline().strip().lower() in ("y", "yes")
    log.summary("Approved." if approved else "Declined — nothing was changed.")
    return approved


def add_approval_args(parser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="show the plan and change nothing")
    parser.add_argument("--yes", action="store_true", help="approve without asking (required when not in a terminal)")
