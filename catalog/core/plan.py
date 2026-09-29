"""Show every change a command is about to make, then ask before making it.

Every command that writes to Libib, Shopify, the picker or shared state
builds a Plan and calls confirm(). The plan lists EVERY change — nothing is
summarised away as "+N more" — and the same list is saved beside the run.

Approval is always explicit and always tied to the exact list shown:

- In a terminal, the full list is printed and the command asks "Proceed?".
- Anywhere else (an agent, a script), run with --dry-run first: it prints the
  full list and an approval code — a fingerprint of that list. Re-run with
  --approve <code> to make exactly those changes. If anything differs from
  what was reviewed (new products, a changed value), the code no longer
  matches and the command refuses.

There is no blanket "--yes": a code can only approve the list it came from.
"""

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from catalog.core import log
from catalog.errors import CatalogError


class ApprovalRefused(CatalogError):
    """Approval was needed and not given for exactly this plan."""


@dataclass
class Plan:
    title: str
    count: int                       # how many changes; 0 means nothing to do
    summary: list[str]
    samples: list[str] = field(default_factory=list)   # one line per change — ALL of them are shown
    warnings: list[str] = field(default_factory=list)
    details_path: Path | None = None

    def render(self) -> str:
        lines = [f"== {self.title} =="]
        lines += [f"  {line}" for line in self.summary]
        lines += [f"  ! {warning}" for warning in self.warnings]
        if self.samples:
            lines.append(f"  changes ({len(self.samples)}):")
            lines += [f"    {s}" for s in self.samples]
        if self.details_path is not None:
            lines.append(f"  Full detail: {self.details_path}")
        return "\n".join(lines)


def fingerprint(plan: Plan) -> str:
    """Approval code: a short hash of everything the plan says it will do."""
    text = "\n".join([plan.title, *plan.summary, *plan.samples])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def confirm(plan: Plan, *, dry_run: bool, approve: str | None = None, stdin=None, stdout=None,
            preapproved: bool = False) -> bool:
    """True when the plan may go ahead. `preapproved` is only for a step inside
    a command whose own, larger plan (which listed these changes) was approved."""
    for line in plan.render().splitlines():
        log.summary(line)
    if plan.count == 0:
        log.summary("Nothing to change.")
        return False
    if preapproved:
        return True
    code = fingerprint(plan)
    if dry_run:
        log.summary("Dry run — nothing was changed.")
        log.summary(f"Approval code: {code}  (re-run with --approve {code} to make exactly these changes)")
        return False
    if approve:
        if approve.strip() != code:
            raise ApprovalRefused(
                f"approval code {approve!r} does not match this plan ({code}) — the changes differ from the "
                "ones reviewed. Nothing was changed. Run --dry-run again and review the new list.")
        log.summary(f"Approved with code {code}.")
        return True
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if not stdin.isatty():
        raise ApprovalRefused(
            "this command makes changes and needs approval, but it is not running in a terminal. "
            "Run it with --dry-run, review the full list, then re-run with --approve <code>.")
    stdout.write(f"Make these {plan.count} changes? [y/N] ")
    stdout.flush()
    approved = stdin.readline().strip().lower() in ("y", "yes")
    log.summary("Approved." if approved else "Declined — nothing was changed.")
    return approved


def add_approval_args(parser) -> None:
    parser.add_argument("--dry-run", action="store_true",
                        help="list every change and print an approval code; change nothing")
    parser.add_argument("--approve", metavar="CODE",
                        help="make the changes a --dry-run listed (the code it printed); refuses if they differ")
