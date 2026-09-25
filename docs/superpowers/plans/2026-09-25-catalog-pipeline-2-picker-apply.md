# Catalog Pipeline — Plan 2: Picker Push + Apply — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship stages 2 and 3: `python3 -m catalog picker push` adds the latest audit's picker products to the hosted review picker, and `python3 -m catalog apply` turns the audit's safe auto-fixes plus the client's picks into narrow Shopify import CSVs, both behind a show-the-plan-then-ask approval step.

**Architecture:** Adds `core/plan.py` (approval), `core/picks.py` (pick format + loaders), `core/git_sync.py` (moved from `formatting-scripts/`), `tmdb/candidates.py` (picker candidate ranking), `picker/` (page templates, queues, push) and `apply/` (merge, CSV grouping, command). Shared state and file formats live in `core/` so stages never import each other. The old `formatting-scripts/` stays untouched until Plan 4.

**Tech Stack:** Python 3.10+ standard library, `unittest`, git CLI, Shopify CLI (already used by audit), TMDB search API.

**Spec:** `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md` — §5 (picker push, pick schema, registry statuses), §6 (apply), §9 (plan and approval), §8 (logging). Plan 1 (`docs/superpowers/plans/2026-09-25-catalog-pipeline-1-foundation-audit.md`) is merged; read its "Decisions" section.

**This is plan 2 of 4.** Plan 3: Libib. Plan 4: client sheet move, delete `formatting-scripts/`, docs.

## Global Constraints

- Standard library only. Run every command from the repo root: `/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox`.
- Tests: `python3 -m unittest discover -s tests/catalog -p "test_*.py"` (baseline at plan start: **226 OK**) and the old suite `python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py"` (**348 OK**) must stay green. Do not modify `formatting-scripts/` or `tests/formatting_scripts/`.
- Stages never import each other: `picker/` and `apply/` may import only `core/`, `tmdb/`, `shopify/` (and themselves).
- Every command that changes anything outside its run folder shows a Plan and asks `Proceed? [y/N]` (default no). `--dry-run` shows the plan and changes nothing. `--yes` skips the prompt. **Not a terminal and no `--yes` → refuse, exit 2.**
- The pipeline never writes to Shopify. `apply` only writes CSVs the operator imports by hand.
- A pick carrying `fields` is rejected with an error, never silently ignored.
- No import CSV may contain a blank cell (every column in a file is one its rows change, or a required column restated with its live/final value).
- Tests never touch the network, the real `tools/review-picker/`, or the real registry: they pass temp dirs and fake fetchers/readers.
- No secrets in source; TMDB key only from `TMDB_API_KEY`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS
  ```

## Decisions made while planning (confirm at review)

1. **`apply` reads picks from `origin/main`, not the local branch.** The hosted picker's `/api/save-pick` commits picks to the branch Vercel deploys (`main`); local work happens on other branches with no upstream, so the spec's "pull `tools/review-picker/data/`" would read stale or no picks. `apply` runs `git fetch origin main` and reads each pick file with `git show origin/main:<path>` — no merge, no dirty-tree problem, any local branch. `--local-picks` reads the working tree instead. Config: `PICKER_REMOTE = "origin"`, `PICKER_BRANCH = "main"`.
2. **`picker push` only commits/pushes when the checkout is on `main`.** On any other branch it writes the queue files and says to publish them from `main` (pushing a feature branch would never reach Vercel).
3. **Pick format and git helpers live in `core/`** (`core/picks.py`, `core/git_sync.py`), not `picker/`, because both `picker push` and `apply` use them (same reasoning as Plan 1's registry move).
4. **Manual picks from the older batches (8.31, 9.2-gaps) only fill empty fields.** Their handles are not in the registry (it only tracks the two evergreen queues); a months-old manual pick must not overwrite data fixed since. Manual picks for handles the registry has as `queued` (the current cycle) overwrite, as the spec says.
5. **An empty manual pick (neither image nor description typed) is ignored**, not applied or resolved — the client clicked "Type it in myself" and never typed. The old batches contain these.
6. **A pick whose fields Shopify already has is marked `resolved`** directly (nothing to write).
7. **Tags get their own `tags.csv`; `genre.csv` holds Option1 + the genre metafield; `vendor.csv` holds Vendor.** The spec put Tags in both genre and vendor files; one field per file means no product ever gets two different Tags values from two files.
8. **Every file restates the product's *final* `Option1 Name` / `Option1 Value`** (after any `genre.csv` change), so the import order of the files doesn't matter.
9. **Alt-text-only changes go to `alt-text.csv`** (it must restate `Image Src`), separate from `image.csv`, so it can be held back until the dev-store check (Task 12) shows re-stating `Image Src` does not duplicate images.
10. **Same handle picked in two batches → the later batch in `batches.json` order wins.**
11. **`fix_visible` compares Tags and the genre metafield as sets and prices as numbers** (Plan 1 deferred minor #3 — required before apply records such values).

## Review Focus

1. **Picks exist only on `origin/main`** while the checkout is on a feature branch → `apply` must still see them. → Task 5 test `test_show_file_reads_a_committed_file_at_a_ref` (real temp git repo) and Task 11 test `test_apply_reads_picks_through_the_injected_reader`.
2. **Running `apply` twice on the same run** → second run must not re-apply handles already `applied`, and must not leave the first run's import CSVs mixed with the second's. → Task 11 test `test_second_apply_replaces_import_files_and_skips_applied`.
3. **A months-old manual pick for a product fixed since** → must not overwrite. → Task 9 test `test_legacy_manual_pick_only_fills_gaps`.
4. **Approval in a non-terminal** (Claude's Bash tool, cron) → refuse unless `--yes`, and write nothing. → Task 2 test `test_non_tty_without_yes_refuses`, Task 7 test `test_push_refuses_without_a_terminal`, Task 11 test `test_apply_refuses_without_a_terminal`.
5. **`picker push` on a feature branch** → no commit/push, clear message. → Task 5 test `test_sync_refuses_off_the_deploy_branch`.

---

### Task 0: Branch setup

**Files:** none.

- [ ] **Step 1: Branch and baseline**

```bash
git status --short                      # must be empty
git checkout fix/redirect-all-collection
git checkout -b refactor/catalog-pipeline-2
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -3
```
Expected: `Ran 226 tests … OK` and `Ran 348 tests … OK`.

---

### Task 1: Tolerant `fix_visible`

**Files:**
- Modify: `catalog/core/registry.py` (`fix_visible`)
- Test: `tests/catalog/test_registry.py`

**Interfaces:**
- Produces: `fix_visible(row, field, value) -> bool` — `Image Src`: non-empty; `Body (HTML)`: text equal; `Tags`: case-insensitive tag sets equal; `Genre (product.metafields.shopify.genre)`: handle sets equal; `Variant Price`: numerically equal (falls back to string compare if either isn't a number); anything else: stripped exact match.

- [ ] **Step 1: Write the failing tests** — insert above the final `if __name__ == "__main__":` block of `tests/catalog/test_registry.py`:

```python
class TestFixVisibleTolerance(unittest.TestCase):
    def test_tags_compare_as_sets_ignoring_order_and_case(self):
        self.assertTrue(fix_visible({"Tags": "Comedy, Rental, VHS"}, "Tags", "Rental, VHS, comedy"))
        self.assertFalse(fix_visible({"Tags": "Rental, VHS"}, "Tags", "Rental, VHS, Comedy"))

    def test_genre_metafield_compares_as_sets(self):
        field = "Genre (product.metafields.shopify.genre)"
        self.assertTrue(fix_visible({field: "drama; comedy"}, field, "comedy; drama"))
        self.assertFalse(fix_visible({field: "drama"}, field, "comedy; drama"))

    def test_price_compares_numerically(self):
        self.assertTrue(fix_visible({"Variant Price": "0.00"}, "Variant Price", "0"))
        self.assertFalse(fix_visible({"Variant Price": "4.00"}, "Variant Price", "0"))
        self.assertFalse(fix_visible({"Variant Price": "abc"}, "Variant Price", "0"))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_registry.py" 2>&1 | grep -E "^(FAIL|ERROR):|^Ran|^OK|^FAILED"`
Expected: FAIL on the tags, metafield and price tests.

- [ ] **Step 3: Replace `fix_visible` in `catalog/core/registry.py`** (and add the import)

Add below the existing `from catalog.core.text import norm_ws, strip_html` line:
```python
from catalog.core.columns import GENRE_METAFIELD
```
Replace the whole `fix_visible` function with:
```python
def _tag_set(value: str) -> set[str]:
    return {t.strip().lower() for t in (value or "").split(",") if t.strip()}


def _handle_set(value: str) -> set[str]:
    return {h.strip() for h in (value or "").split(";") if h.strip()}


def _same_number(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return a.strip() == b.strip()


def fix_visible(row: dict, field: str, value: str) -> bool:
    """Does the snapshot row show a value we applied? Shopify normalises what
    it stores (re-hosts images, sorts tags, prints prices as "0.00"), so each
    field is compared the way Shopify can change it."""
    current = row.get(field) or ""
    value = value or ""
    if field == "Image Src":
        return bool(current.strip())
    if field == "Body (HTML)":
        return norm_ws(strip_html(current)) == norm_ws(strip_html(value))
    if field == "Tags":
        return _tag_set(current) == _tag_set(value)
    if field == GENRE_METAFIELD:
        return _handle_set(current) == _handle_set(value)
    if field == "Variant Price":
        return _same_number(current, value)
    return current.strip() == value.strip()
```

- [ ] **Step 4: Run the suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add catalog/core/registry.py tests/catalog/test_registry.py
git commit -m "fix(catalog): fix_visible compares tags/metafield as sets and prices as numbers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 2: Approval — `core/plan.py`

**Files:**
- Create: `catalog/core/plan.py`
- Test: `tests/catalog/test_plan.py`

**Interfaces:**
- Consumes: `catalog.core.log` (`summary`), `CatalogError`.
- Produces: `catalog.core.plan`: `MAX_SAMPLES = 10`; `ApprovalRefused(CatalogError)`; `Plan(title: str, count: int, summary: list[str], samples: list[str] = [], warnings: list[str] = [], details_path: Path | None = None)` with `render() -> str`; `confirm(plan, *, dry_run: bool, assume_yes: bool, stdin=None, stdout=None) -> bool`; `add_approval_args(parser)` (adds `--dry-run`, `--yes`).

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_plan.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_plan.py" 2>&1 | grep -m1 "Error"`
Expected: `ModuleNotFoundError: No module named 'catalog.core.plan'`.

- [ ] **Step 3: Implement `catalog/core/plan.py`**

```python
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
```

- [ ] **Step 4: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add catalog/core/plan.py tests/catalog/test_plan.py
git commit -m "feat(catalog): approval step — plan, --dry-run, --yes, refuse without a terminal

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 3: Picker candidates — `tmdb/candidates.py`

**Files:**
- Create: `catalog/tmdb/candidates.py` (from `formatting-scripts/review_page.py` lines 27–131)
- Test: `tests/catalog/test_candidates.py` (ported lines 14–136 of `tests/formatting_scripts/test_review_page.py`)

**Interfaces:**
- Consumes: `catalog.tmdb.match` (`GLOBAL_YEAR_CUTOFF`, `REQUEST_DELAY_SECONDS`, `clean_title_and_year`, `filter_by_year_cutoff`, `genre_matches`, `search_tmdb`, `title_similarity`).
- Produces: `catalog.tmdb.candidates`: `MAX_CANDIDATES = 5`, `THUMB_BASE_URL`, `fetch_candidates(fetch_fn, title, year, genre="") -> list[dict]`, `collect_products(review_rows, fetch_fn, sleep_fn=time.sleep, progress_fn=...) -> list[dict]` (review rows use keys `Handle, Title, Vendor, Genre, Tags, Kind, Reason`), `rental_or_floor_sale(tags: str) -> str`.

- [ ] **Step 1: Port the tests (failing)**

```bash
{ cat <<'EOF'
import unittest

from catalog.tmdb.candidates import MAX_CANDIDATES, collect_products, fetch_candidates, rental_or_floor_sale
EOF
sed -n '14,136p' tests/formatting_scripts/test_review_page.py
cat <<'EOF'


if __name__ == "__main__":
    unittest.main()
EOF
} > tests/catalog/test_candidates.py
grep -n "^class " tests/catalog/test_candidates.py
```
Expected classes: `TestRentalOrFloorSale`, `TestFetchCandidates`, `TestCollectProducts` (the local-page classes `TestBuildPickerHtml`/`TestWritePicker` are intentionally not ported — that page is gone).

Run: `python3 -m unittest discover -s tests/catalog -p "test_candidates.py" 2>&1 | grep -m1 "Error"` → `ModuleNotFoundError: No module named 'catalog.tmdb.candidates'`.

- [ ] **Step 2: Build the module**

```bash
sed -n '27,28p;131p' formatting-scripts/review_page.py   # expect: MAX_CANDIDATES = 5 / THUMB_BASE_URL … / return ""
{ cat <<'EOF'
"""Picker candidates: the top TMDB results for a product, ranked for a human.

Moved from formatting-scripts/review_page.py (the ranking half). Its local
page generator is gone — the hosted picker replaced it.
"""

import time

from catalog.tmdb.match import (
    GLOBAL_YEAR_CUTOFF,
    REQUEST_DELAY_SECONDS,
    clean_title_and_year,
    filter_by_year_cutoff,
    genre_matches,
    search_tmdb,
    title_similarity,
)

EOF
sed -n '27,131p' formatting-scripts/review_page.py
} > catalog/tmdb/candidates.py
```

- [ ] **Step 3: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/tmdb/candidates.py tests/catalog/test_candidates.py
git commit -m "feat(catalog): picker candidate ranking moved to catalog.tmdb.candidates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 4: Picker page templates — `picker/page.py`

**Files:**
- Create: `catalog/picker/__init__.py` (empty), `catalog/picker/page.html`, `catalog/picker/launcher.html` (both extracted verbatim from the old generator), `catalog/picker/page.py`
- Test: `tests/catalog/test_picker_page.py` (ported lines 1–207 of `tests/formatting_scripts/test_hosted_review_page.py`), `tests/catalog/test_picker_page_seam.py` (temporary; deleted in Plan 4)

**Interfaces:**
- Produces: `catalog.picker.page`: `build_hosted_picker_html(products: list[dict], batch_id: str) -> str`, `build_launcher_html() -> str`. Placeholders in `page.html`: `__PRODUCTS_JSON__`, `__BATCH_ID_JSON__`, `__BATCH_ID_URL__`, `__PRODUCT_COUNT__`.

- [ ] **Step 1: Write the failing tests**

Port the HTML behaviour tests:
```bash
mkdir -p catalog/picker && touch catalog/picker/__init__.py
{ cat <<'EOF'
import unittest

from catalog.picker.page import build_hosted_picker_html
EOF
sed -n '8,207p' tests/formatting_scripts/test_hosted_review_page.py
cat <<'EOF'


if __name__ == "__main__":
    unittest.main()
EOF
} > tests/catalog/test_picker_page.py
grep -n "^class \|^from \|^import " tests/catalog/test_picker_page.py
```
Expected: imports only `unittest` and `catalog.picker.page`; classes `TestBuildHostedPickerHtml` … `TestRetryIsBoundedAndNotStale`.

`tests/catalog/test_picker_page_seam.py`:
```python
"""Temporary seam test: the template renderer must produce exactly what the old
f-string generator in formatting-scripts/hosted_review_page.py produced.
Deleted in Plan 4 together with formatting-scripts/."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

import hosted_review_page as old  # noqa: E402

from catalog.picker import page  # noqa: E402

PRODUCTS = [
    {"handle": "the-thing", "title": "The Thing", "vendor": "VHS", "genre": "horror", "tag": "Rental",
     "reason": "ambiguous match", "candidates": [
         {"id": 1, "title": "The Thing", "year": "1982", "overview": "An </script> in the overview.",
          "poster_path": "/p.jpg"}]},
    {"handle": "amelie-dvd-rental", "title": "Amélie", "vendor": "DVD", "genre": "foreign; comedy", "tag": "",
     "reason": "no TMDB match", "candidates": []},
]


class TestSeam(unittest.TestCase):
    def test_page_matches_the_old_generator(self):
        for products, batch in (([], "ambiguous-queue"), (PRODUCTS, "unmatched-queue"),
                                (PRODUCTS, "review-9.2-gaps"), (PRODUCTS[:1], "a.b_c-d")):
            with self.subTest(batch=batch, n=len(products)):
                self.assertEqual(page.build_hosted_picker_html(products, batch),
                                 old.build_hosted_picker_html(products, batch))

    def test_launcher_matches_the_old_generator(self):
        self.assertEqual(page.build_launcher_html(), old.build_launcher_html())

    def test_templates_carry_no_leftover_sentinel(self):
        html = page.build_hosted_picker_html(PRODUCTS, "ambiguous-queue")
        for token in ("__PRODUCTS_JSON__", "__BATCH_ID_JSON__", "__BATCH_ID_URL__", "__PRODUCT_COUNT__", "zzbatchzz"):
            self.assertNotIn(token, html)


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest discover -s tests/catalog -p "test_picker_page*.py" 2>&1 | grep -m2 "Error"` → `ModuleNotFoundError: No module named 'catalog.picker.page'` (twice).

- [ ] **Step 2: Extract the templates from the old generator (one-off, not committed as a script)**

```bash
python3 - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, "formatting-scripts")
from hosted_review_page import build_hosted_picker_html, build_launcher_html

html = build_hosted_picker_html([], "zzbatchzz")
for old, new in (
    ("const PRODUCTS = [];", "const PRODUCTS = __PRODUCTS_JSON__;"),
    ('const BATCH_ID = "zzbatchzz";', "const BATCH_ID = __BATCH_ID_JSON__;"),
    ("batch=zzbatchzz", "batch=__BATCH_ID_URL__"),
    ("— 0 products</title>", "— __PRODUCT_COUNT__ products</title>"),
):
    assert html.count(old) == 1, (old, html.count(old))
    html = html.replace(old, new)
assert "zzbatchzz" not in html
Path("catalog/picker/page.html").write_text(html, encoding="utf-8")
Path("catalog/picker/launcher.html").write_text(build_launcher_html(), encoding="utf-8")
print("templates written")
EOF
```
Expected: `templates written`. If an assert fires, stop: the old generator changed shape; re-derive the sentinel strings from `formatting-scripts/hosted_review_page.py` lines 45–110.

- [ ] **Step 3: Write `catalog/picker/page.py`**

```python
"""Render the hosted picker page and the launcher from their HTML templates.

Both templates were extracted verbatim from the old f-string generator
(formatting-scripts/hosted_review_page.py). Placeholders are plain __NAME__
tokens, so the HTML/JS needs no brace-escaping.
"""

import json
from pathlib import Path
from urllib.parse import quote

_HERE = Path(__file__).parent


def _template(name: str) -> str:
    return (_HERE / name).read_text(encoding="utf-8")


def build_hosted_picker_html(products: list[dict], batch_id: str) -> str:
    html = _template("page.html")
    html = html.replace("__BATCH_ID_JSON__", json.dumps(batch_id))
    html = html.replace("__BATCH_ID_URL__", quote(batch_id, safe=""))
    html = html.replace("__PRODUCT_COUNT__", str(len(products)))
    # Products last: the only user-controlled text, so nothing inside it can
    # be mistaken for a placeholder by a later replace. "</" is escaped so an
    # overview can't close the <script> tag.
    return html.replace("__PRODUCTS_JSON__", json.dumps(products).replace("</", "<\\/"))


def build_launcher_html() -> str:
    return _template("launcher.html")
```

- [ ] **Step 4: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add catalog/picker tests/catalog/test_picker_page.py tests/catalog/test_picker_page_seam.py
git commit -m "feat(catalog): picker page and launcher as HTML templates (seam-tested against the old generator)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 5: Git helpers — `core/git_sync.py` + picker config

**Files:**
- Create: `catalog/core/git_sync.py` (copy of `formatting-scripts/git_sync.py` + additions)
- Modify: `catalog/config.py` (picker remote/branch/rel)
- Test: `tests/catalog/test_git_sync.py` (ported + new)

**Interfaces:**
- Produces:
  - `catalog.config`: `PICKER_REL = "tools/review-picker"`, `PICKER_REMOTE = "origin"`, `PICKER_BRANCH = "main"`.
  - `catalog.core.git_sync`: `dirty_paths_outside(repo_root, allowed_prefix) -> list[str]`, `sync_review_picker(repo_root, tools_dir_rel, commit_message, log_fn=..., deploy_branch=None) -> dict`, **new** `current_branch(repo_root) -> str`, `fetch_branch(repo_root, remote, branch) -> None` (raises `RuntimeError`), `show_file(repo_root, ref, path) -> str | None`.

- [ ] **Step 1: Port tests and add new ones (failing)**

```bash
sed -e '/sys.path.insert(0, str(.*formatting-scripts/d' -e 's/^import git_sync$/from catalog.core import git_sync/' \
    tests/formatting_scripts/test_git_sync.py > tests/catalog/test_git_sync.py
grep -n "^from catalog\|^if __name__" tests/catalog/test_git_sync.py
```
Insert above the final `if __name__ == "__main__":` block:
```python
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


class TestDeployBranchGuard(unittest.TestCase):
    def test_sync_refuses_off_the_deploy_branch(self):
        with patch.object(git_sync, "current_branch", return_value="fix/something"), \
             patch.object(git_sync, "_run") as run_mock:
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg", deploy_branch="main")
        self.assertFalse(result["synced"])
        self.assertIn("fix/something", result["reason"])
        self.assertIn("main", result["reason"])
        run_mock.assert_not_called()

    def test_sync_proceeds_on_the_deploy_branch(self):
        def fake_run(args, cwd):
            return FakeResult(returncode=1 if args[1] == "diff" else 0)

        with patch.object(git_sync, "current_branch", return_value="main"), \
             patch.object(git_sync, "dirty_paths_outside", return_value=[]), \
             patch.object(git_sync, "_run", side_effect=fake_run):
            result = git_sync.sync_review_picker("/repo", "tools/review-picker", "msg", deploy_branch="main")
        self.assertTrue(result["synced"])
```

Run: `python3 -m unittest discover -s tests/catalog -p "test_git_sync.py" 2>&1 | grep -m1 "Error"` → `ImportError: cannot import name 'git_sync' from 'catalog.core'`.

- [ ] **Step 2: Copy the module and add the helpers**

```bash
cp formatting-scripts/git_sync.py catalog/core/git_sync.py
```
In `catalog/core/git_sync.py`:

Replace the docstring's first paragraph (lines 1–4, from `"""Auto pull/commit/push` through `never runs unless run.py actually queued something new.`) with:
```python
"""Git helpers for the review picker: auto pull/commit/push of
tools/review-picker after `picker push`, and reading the picker's pick files
straight from the deploy branch for `apply`. Tests never run real git
against this repo.
```

Replace the signature and first line of `sync_review_picker`:
```python
def sync_review_picker(repo_root, tools_dir_rel: str, commit_message: str, log_fn=lambda m: None) -> dict:
    """Pull, then commit + push tools_dir_rel if it has changes. Returns
    {"synced": bool, "reason": str, ...} — never raises for an expected
    failure (dirty tree, pull/commit/push failure); those are reported,
    not thrown, so a sync problem never looks like a run.py crash."""
    repo_root = Path(repo_root)
```
with:
```python
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
```
Append to the end of the file:
```python


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
```

Append to `catalog/config.py`:
```python

# The hosted review picker (Vercel) deploys tools/review-picker from this
# branch, and /api/save-pick commits the client's picks to it.
PICKER_REL = "tools/review-picker"
PICKER_REMOTE = "origin"
PICKER_BRANCH = "main"
```

- [ ] **Step 3: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/core/git_sync.py catalog/config.py tests/catalog/test_git_sync.py
git commit -m "feat(catalog): git helpers — picker sync with deploy-branch guard, fetch and show-at-ref

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 6: Picker queues — `picker/queues.py`

**Files:**
- Create: `catalog/picker/queues.py` (from `formatting-scripts/hosted_review_page.py` lines 27–43, 472–559, 634–635)
- Test: `tests/catalog/test_picker_queues.py`

**Interfaces:**
- Consumes: `collect_products` (Task 3), `build_hosted_picker_html`, `build_launcher_html` (Task 4), `filter_unknown`, `mark_queued` (`catalog.core.registry`).
- Produces: `catalog.picker.queues`: `BATCH_ID_PATTERN`, `validate_batch_id(batch_id) -> str`, `load_products(picker_dir, batch_id)`, `save_products(picker_dir, batch_id, products)`, `append_to_queue(review_rows, picker_dir, batch_id, fetch_fn, registry, sleep_fn=time.sleep, progress_fn=None) -> {"added": int, "batch_total": int}`, `update_manifest(picker_dir, batch_id, total) -> list[dict]`, `write_launcher(picker_dir)`.

- [ ] **Step 1: Write the failing test**

```bash
{ cat <<'EOF'
import json
import tempfile
import unittest
from pathlib import Path

from catalog.picker.page import build_launcher_html
from catalog.picker.queues import (
    BATCH_ID_PATTERN, append_to_queue, load_products, update_manifest, validate_batch_id, write_launcher,
)


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch

EOF
sed -n '288,380p' tests/formatting_scripts/test_hosted_review_page.py
cat <<'EOF'


class TestBatchIdValidation(unittest.TestCase):
    def test_accepts_the_batch_ids_the_api_accepts(self):
        for batch_id in ["out-x", "out-product_export_3", "ambiguous-queue", "a.b"]:
            self.assertEqual(validate_batch_id(batch_id), batch_id)

    def test_rejects_the_batch_ids_the_api_rejects(self):
        for batch_id in ["Out-X", "out x", "_leading", "-leading", "", "../secrets", "foo/bar", None]:
            with self.assertRaises(ValueError):
                validate_batch_id(batch_id)

    def test_append_rejects_a_bad_batch_id_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                append_to_queue([review_row("a")], Path(tmp), "Bad Batch", fetcher([]), {},
                                sleep_fn=lambda s: None)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_the_python_pattern_matches_the_javascript_one(self):
        js = (Path(__file__).resolve().parents[2]
              / "tools" / "review-picker" / "api" / "_github.js").read_text(encoding="utf-8")
        self.assertIn("const BATCH_ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/;", js)
        self.assertEqual(BATCH_ID_PATTERN.pattern, r"^[a-z0-9][a-z0-9._-]*$")

EOF
sed -n '431,455p' tests/formatting_scripts/test_hosted_review_page.py
cat <<'EOF'


if __name__ == "__main__":
    unittest.main()
EOF
} > tests/catalog/test_picker_queues.py
grep -n "^class " tests/catalog/test_picker_queues.py
```
Expected classes: `TestAppendToQueue`, `TestManifest`, `TestWriteLauncher`, `TestBatchIdValidation`, `TestLauncherHandlesFailedGetPicks`.

Run: `python3 -m unittest discover -s tests/catalog -p "test_picker_queues.py" 2>&1 | grep -m1 "Error"` → `ModuleNotFoundError: No module named 'catalog.picker.queues'`.

- [ ] **Step 2: Build the module**

```bash
sed -n '27p;472p;544p;634p' formatting-scripts/hosted_review_page.py
# expect: "# KEEP IN SYNC…" / "def _products_path(…" / "def update_manifest(…" / "def write_launcher(…"
{ cat <<'EOF'
"""The hosted picker's evergreen queues: add products, keep the manifest and
launcher current. Moved from formatting-scripts/hosted_review_page.py (the
per-batch write_hosted_picker is gone — picker push only appends to the two
evergreen queues).
"""

import json
import re
import time
from pathlib import Path

from catalog.core.registry import filter_unknown, mark_queued
from catalog.picker.page import build_hosted_picker_html, build_launcher_html
from catalog.tmdb.candidates import collect_products

EOF
sed -n '27,43p;472,559p;634,635p' formatting-scripts/hosted_review_page.py
} > catalog/picker/queues.py
python3 -c "import catalog.picker.queues as q; print(sorted(n for n in dir(q) if not n.startswith('__')))"
```
Expected names include `BATCH_ID_PATTERN`, `append_to_queue`, `load_products`, `save_products`, `update_manifest`, `validate_batch_id`, `write_launcher`, `_products_path`.

- [ ] **Step 3: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/picker/queues.py tests/catalog/test_picker_queues.py
git commit -m "feat(catalog): picker queue writer, manifest and launcher

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 7: `picker push` command

**Files:**
- Create: `catalog/picker/push.py`, `catalog/picker/command.py`
- Modify: `catalog/cli.py` (register)
- Test: `tests/catalog/test_picker_push.py`

**Interfaces:**
- Consumes: `append_to_queue` (Task 6), `Plan`, `confirm`, `add_approval_args`, `MAX_SAMPLES` (Task 2), `sync_review_picker` (Task 5), `resolve_run`, `load_registry`, `save_registry`, `is_known`, `TmdbCache`, `make_fetcher`, `config`.
- Produces:
  - `catalog.picker.push`: `QUEUE_FOR_KIND = {"ambiguous": "ambiguous-queue", "unmatched": "unmatched-queue"}`, `new_entries_by_queue(review, registry) -> dict[str, list[dict]]`, `push(entries_by_queue, picker_dir, registry, fetch_fn) -> dict[str, dict]`.
  - `catalog.picker.command`: `register(subparsers)`, `run_push_command(args, fetch_fn=None, sync_fn=sync_review_picker, stdin=None) -> int`. CLI: `python3 -m catalog picker push [--run ID] [--no-git-sync] [--dry-run] [--yes] [-v|-q]`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_picker_push.py`:

```python
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.cli import build_parser, main
from catalog.core import log
from catalog.picker import command
from catalog.picker.push import new_entries_by_queue


def entry(handle, kind="ambiguous", title="The Thing"):
    return {"Handle": handle, "Title": title, "Vendor": "VHS", "Genre": "horror",
            "Tags": "Rental, VHS, Horror", "Kind": kind, "Reason": "r"}


def fetch(query, year):
    return {"results": [{"id": 1, "title": query, "release_date": "1982-01-01",
                         "poster_path": "/p.jpg", "overview": "Overview."}]}


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class TestNewEntries(unittest.TestCase):
    def test_groups_by_queue_and_skips_known_and_repeated_handles(self):
        review = [entry("a"), entry("b", "unmatched"), entry("a"), entry("c")]
        grouped = new_entries_by_queue(review, {"c": {"status": "resolved"}})
        self.assertEqual([e["Handle"] for e in grouped["ambiguous-queue"]], ["a"])
        self.assertEqual([e["Handle"] for e in grouped["unmatched-queue"]], ["b"])


class TestPushCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        run = self.runs / "2026-09-25"
        run.mkdir(parents=True)
        (run / "review.json").write_text(json.dumps([entry("a"), entry("b", "unmatched")]), encoding="utf-8")
        (run / "run-report.txt").write_text("done\n", encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["picker", "push", "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "-q", *extra])

    def test_dry_run_writes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_push_command(self.args("--dry-run"), fetch_fn=fetch)
        self.assertEqual(code, 0)
        self.assertFalse(self.picker.exists())

    def test_push_refuses_without_a_terminal(self):
        err = io.StringIO()
        argv = ["picker", "push", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "-q"]
        with mock.patch("sys.stdin", FakeStdin(tty=False)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("--yes", err.getvalue())
        self.assertFalse(self.picker.exists())

    def test_yes_appends_to_both_queues_and_registers(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes", "--no-git-sync"), fetch_fn=fetch)
        registry = json.loads((self.picker / "data" / "_handle-index.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["a"], {"batch": "ambiguous-queue", "status": "queued"})
        self.assertEqual(registry["b"], {"batch": "unmatched-queue", "status": "queued"})
        self.assertTrue((self.picker / "ambiguous-queue" / "index.html").exists())
        self.assertTrue((self.picker / "unmatched-queue" / "index.html").exists())
        self.assertTrue((self.picker / "index.html").exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_answer_y_in_a_terminal_proceeds(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--no-git-sync"), fetch_fn=fetch, stdin=FakeStdin("y\n"))
        self.assertTrue((self.picker / "data" / "_handle-index.json").exists())

    def test_second_push_has_nothing_to_do_and_needs_no_key(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes", "--no-git-sync"), fetch_fn=fetch)
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = command.run_push_command(self.args("--no-git-sync"), stdin=FakeStdin(tty=False))
        self.assertEqual(code, 0)

    def test_picker_dir_outside_the_repo_skips_git_sync(self):
        calls = []
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_push_command(self.args("--yes"), fetch_fn=fetch,
                                     sync_fn=lambda *a, **k: calls.append(a) or {"synced": True})
        self.assertEqual(calls, [])

    def test_missing_key_fails_before_writing(self):
        err = io.StringIO()
        argv = ["picker", "push", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "-q", "--yes"]
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("TMDB_API_KEY", err.getvalue())
        self.assertFalse(self.picker.exists())


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest discover -s tests/catalog -p "test_picker_push.py" 2>&1 | grep -m1 "Error"` → `ImportError` (no `catalog.picker.command`).

- [ ] **Step 2: Write `catalog/picker/push.py`**

```python
"""Stage 2 core: which review.json products are new, and adding them to the
hosted picker's evergreen queues."""

from catalog.core import log
from catalog.core.registry import is_known
from catalog.picker.queues import append_to_queue

QUEUE_FOR_KIND = {"ambiguous": "ambiguous-queue", "unmatched": "unmatched-queue"}


def new_entries_by_queue(review: list[dict], registry: dict) -> dict[str, list[dict]]:
    """review.json entries the registry doesn't know yet, grouped by queue.
    The first entry for a handle wins."""
    grouped: dict[str, list[dict]] = {queue: [] for queue in QUEUE_FOR_KIND.values()}
    seen: set[str] = set()
    for entry in review:
        handle = entry["Handle"]
        if handle in seen or is_known(registry, handle):
            continue
        seen.add(handle)
        grouped[QUEUE_FOR_KIND[entry["Kind"]]].append(entry)
    return grouped


def push(entries_by_queue: dict[str, list[dict]], picker_dir, registry: dict, fetch_fn) -> dict[str, dict]:
    """Append each queue's new entries (fetching their TMDB candidates).
    Mutates `registry`; the caller saves it."""
    results = {}
    for queue, entries in entries_by_queue.items():
        if entries:
            results[queue] = append_to_queue(entries, picker_dir, queue, fetch_fn, registry,
                                             sleep_fn=lambda seconds: None, progress_fn=log.progress)
    return results
```

- [ ] **Step 3: Write `catalog/picker/command.py`**

```python
"""`python3 -m catalog picker push` — add the latest audit's picker products to
the hosted review picker, then commit + push tools/review-picker (on main)."""

import argparse
import json
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.git_sync import sync_review_picker
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.core.registry import load_registry, save_registry
from catalog.core.runs import resolve_run
from catalog.picker.push import new_entries_by_queue, push
from catalog.tmdb.cache import TmdbCache
from catalog.tmdb.client import make_fetcher


def register(subparsers) -> None:
    picker = subparsers.add_parser("picker", help="the hosted review picker")
    picker_sub = picker.add_subparsers(dest="picker_command", required=True, metavar="<picker command>")
    p = picker_sub.add_parser("push", help="add the latest audit's picker products to the hosted queues")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--no-git-sync", action="store_true", help="write the queue files but don't commit/push")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    add_approval_args(p)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_push_command)


def run_push_command(args, fetch_fn=None, sync_fn=sync_review_picker, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    log.setup_logging(run_dir / "picker-push.log", log.verbosity(args))
    log.header(f"picker push — audit run {run_dir.name}")

    review = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))
    picker_dir = Path(args.picker_dir)
    registry = load_registry(picker_dir)
    entries = new_entries_by_queue(review, registry)
    total = sum(len(v) for v in entries.values())
    message = (f"review-picker: +{len(entries['ambiguous-queue'])} ambiguous, "
               f"+{len(entries['unmatched-queue'])} unmatched (audit {run_dir.name})")

    raw_fetch = None
    if total and not args.dry_run:  # fail fast on a missing key, before asking
        raw_fetch = fetch_fn or make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))

    plan = Plan(
        title="picker push",
        count=total,
        summary=[f"{queue}: +{len(v)} cards" for queue, v in entries.items()]
        + [f"registry: {total} handles -> queued",
           "git: " + ("skipped (--no-git-sync)" if args.no_git_sync
                      else f'commit + push {config.PICKER_REL} on {config.PICKER_BRANCH}: "{message}"')],
        samples=[f"{e['Handle']} [{e['Kind']}] {e['Reason']}" for v in entries.values() for e in v],
    )
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0

    cache = TmdbCache(Path(args.runs_dir) / config.TMDB_CACHE_FILENAME)
    try:
        results = push(entries, picker_dir, registry, cache.wrap(raw_fetch))
    finally:
        cache.save()
    save_registry(picker_dir, registry)
    for queue, outcome in results.items():
        log.summary(f"{queue}: +{outcome['added']} (queue now {outcome['batch_total']})")

    if args.no_git_sync:
        log.summary(f"git sync skipped — commit and push {config.PICKER_REL} from {config.PICKER_BRANCH} to publish.")
        return 0
    try:
        rel = str(picker_dir.resolve().relative_to(config.REPO_ROOT))
    except ValueError:
        log.summary(f"{picker_dir} is outside the repo — git sync skipped.")
        return 0
    outcome = sync_fn(config.REPO_ROOT, rel, message, log_fn=log.summary, deploy_branch=config.PICKER_BRANCH)
    if not outcome.get("synced") and outcome.get("reason") != "nothing to commit":
        log.summary(f"Note: {rel} was updated locally but not published ({outcome.get('reason')}).")
    return 0
```

- [ ] **Step 4: Register in `catalog/cli.py`**

Replace:
```python
from catalog.audit import command as audit_command

COMMANDS: list = [audit_command]  # modules with register(subparsers), in help order
```
with:
```python
from catalog.audit import command as audit_command
from catalog.picker import command as picker_command

COMMANDS: list = [audit_command, picker_command]  # modules with register(subparsers), in help order
```

- [ ] **Step 5: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`; `python3 -m catalog picker push --help` lists `--run`, `--no-git-sync`, `--dry-run`, `--yes`.

- [ ] **Step 6: Commit**

```bash
git add catalog/picker/push.py catalog/picker/command.py catalog/cli.py tests/catalog/test_picker_push.py
git commit -m "feat(catalog): python3 -m catalog picker push

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 8: Pick format and loaders — `core/picks.py`

**Files:**
- Create: `catalog/core/picks.py`
- Test: `tests/catalog/test_picks.py`

**Interfaces:**
- Consumes: `show_file` (Task 5), `CatalogError`.
- Produces: `catalog.core.picks`: `CHOICES`, `PickError(CatalogError)`, `Pick(batch, handle, choice, poster_path="", overview="", image_src="")` (frozen dataclass), `parse_pick(raw, batch) -> Pick`, `load_picks(read_text) -> list[Pick]` (manifest order, then file order), `local_reader(picker_dir)`, `remote_reader(repo_root, ref, picker_rel)` — both return `read_text(rel_path) -> str | None`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_picks.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.core import picks as picks_mod
from catalog.core.picks import Pick, PickError, load_picks, local_reader, parse_pick, remote_reader


def reader(files: dict):
    return lambda rel: files.get(rel)


class TestParsePick(unittest.TestCase):
    def test_tmdb_pick(self):
        p = parse_pick({"handle": "a", "choice": "tmdb", "poster_path": "/p.jpg", "overview": " O. "}, "q")
        self.assertEqual(p, Pick("q", "a", "tmdb", "/p.jpg", "O.", ""))

    def test_manual_pick(self):
        p = parse_pick({"handle": "a", "choice": "manual", "image_src": "https://x", "overview": ""}, "q")
        self.assertEqual((p.choice, p.image_src, p.overview), ("manual", "https://x", ""))

    def test_skip_pick(self):
        self.assertEqual(parse_pick({"handle": "a", "choice": "skip"}, "q").choice, "skip")

    def test_fields_is_rejected_naming_batch_and_handle(self):
        with self.assertRaises(PickError) as ctx:
            parse_pick({"handle": "a", "choice": "manual", "fields": {"genre": "horror"}}, "ambiguous-queue")
        self.assertIn("ambiguous-queue/a", str(ctx.exception))
        self.assertIn("fields", str(ctx.exception))

    def test_unknown_choice_is_rejected(self):
        with self.assertRaises(PickError):
            parse_pick({"handle": "a", "choice": "maybe"}, "q")

    def test_missing_handle_is_rejected(self):
        for raw in ({"choice": "skip"}, {"handle": " ", "choice": "skip"}, "not a dict"):
            with self.assertRaises(PickError):
                parse_pick(raw, "q")

    def test_null_text_fields_become_empty(self):
        p = parse_pick({"handle": "a", "choice": "tmdb", "poster_path": None, "overview": None}, "q")
        self.assertEqual((p.poster_path, p.overview), ("", ""))


class TestLoadPicks(unittest.TestCase):
    def test_reads_every_batch_in_manifest_order(self):
        files = {
            "batches.json": json.dumps([{"batch_id": "old", "total": 1}, {"batch_id": "ambiguous-queue", "total": 2},
                                        {"batch_id": "missing", "total": 1}]),
            "data/old.json": json.dumps([{"handle": "a", "choice": "skip"}]),
            "data/ambiguous-queue.json": json.dumps([{"handle": "b", "choice": "tmdb", "poster_path": "/b.jpg"},
                                                     {"handle": "a", "choice": "tmdb", "poster_path": "/a.jpg"}]),
        }
        loaded = load_picks(reader(files))
        self.assertEqual([(p.batch, p.handle) for p in loaded],
                         [("old", "a"), ("ambiguous-queue", "b"), ("ambiguous-queue", "a")])

    def test_no_manifest_means_no_picks(self):
        self.assertEqual(load_picks(reader({})), [])


class TestReaders(unittest.TestCase):
    def test_local_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "q.json").write_text("[]", encoding="utf-8")
            read = local_reader(tmp)
            self.assertEqual(read("data/q.json"), "[]")
            self.assertIsNone(read("data/nope.json"))

    def test_remote_reader_prefixes_the_picker_path(self):
        with mock.patch.object(picks_mod, "show_file", return_value="[]") as show:
            self.assertEqual(remote_reader("/repo", "origin/main", "tools/review-picker")("data/q.json"), "[]")
        show.assert_called_once_with("/repo", "origin/main", "tools/review-picker/data/q.json")


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest discover -s tests/catalog -p "test_picks.py" 2>&1 | grep -m1 "Error"` → `ModuleNotFoundError: No module named 'catalog.core.picks'`.

- [ ] **Step 2: Implement `catalog/core/picks.py`**

```python
"""The client's picks, as saved by the hosted picker's /api/save-pick into
tools/review-picker/data/<batch>.json:

    {handle, choice: "tmdb" | "manual" | "skip", poster_path?, overview?, image_src?}

`fields` is reserved for future genre/type/format/price picks. Until apply
supports it, a pick carrying it is rejected — never silently ignored.
Note: /api/save-pick rebuilds each pick from an allowlist of keys, so the
future picker-fields feature must extend that allowlist too.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from catalog.core.git_sync import show_file
from catalog.errors import CatalogError

CHOICES = ("tmdb", "manual", "skip")


class PickError(CatalogError):
    """A saved pick this version of apply cannot safely interpret."""


@dataclass(frozen=True)
class Pick:
    batch: str
    handle: str
    choice: str
    poster_path: str = ""
    overview: str = ""
    image_src: str = ""


def _text(raw: dict, key: str) -> str:
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def parse_pick(raw, batch: str) -> Pick:
    if not isinstance(raw, dict) or not isinstance(raw.get("handle"), str) or not raw["handle"].strip():
        raise PickError(f"a pick in {batch} has no handle: {str(raw)[:200]}")
    handle = raw["handle"].strip()
    if "fields" in raw:
        raise PickError(f"{batch}/{handle}: this pick carries 'fields' (genre/type/format/price), "
                        "which apply does not support yet")
    if raw.get("choice") not in CHOICES:
        raise PickError(f"{batch}/{handle}: unknown choice {raw.get('choice')!r}")
    return Pick(batch, handle, raw["choice"], _text(raw, "poster_path"), _text(raw, "overview"),
                _text(raw, "image_src"))


def load_picks(read_text) -> list[Pick]:
    """Every pick from every batch listed in batches.json, in manifest order.
    read_text(path relative to the picker dir) -> str | None."""
    manifest = read_text("batches.json")
    if manifest is None:
        return []
    picks: list[Pick] = []
    for entry in json.loads(manifest):
        batch = entry["batch_id"]
        data = read_text(f"data/{batch}.json")
        if data is None:
            continue
        picks.extend(parse_pick(raw, batch) for raw in json.loads(data))
    return picks


def local_reader(picker_dir):
    picker_dir = Path(picker_dir)

    def read(rel: str) -> str | None:
        path = picker_dir / rel
        return path.read_text(encoding="utf-8") if path.exists() else None

    return read


def remote_reader(repo_root, ref: str, picker_rel: str):
    def read(rel: str) -> str | None:
        return show_file(repo_root, ref, f"{picker_rel}/{rel}")

    return read
```

- [ ] **Step 3: Run the suite** — `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/core/picks.py tests/catalog/test_picks.py
git commit -m "feat(catalog): pick format, validation and working-tree/deploy-branch loaders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 9: Merge auto-fixes and picks — `apply/merge.py`

**Files:**
- Create: `catalog/apply/__init__.py` (empty), `catalog/apply/merge.py`
- Test: `tests/catalog/test_apply_merge.py`

**Interfaces:**
- Consumes: `Pick` (Task 8), `strip_html`, `POSTER_BASE_URL`.
- Produces: `catalog.apply.merge`: `AUTO_FIX_SOURCE = "auto-fix"`, `CHANGE_COLUMNS = ["handle", "field", "before", "after", "source"]`, `Change(handle, field, before, after, source)` (frozen dataclass), `MergeResult(changes, applied, skipped, resolved, ignored)`, `merge(rows, autofix, picks, registry) -> MergeResult`. `applied: dict[handle, dict[field, value]]` holds only pick-sourced values (recorded in the registry); `ignored: list[tuple[handle, reason]]`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_apply_merge.py`:

```python
import unittest

from catalog.apply.merge import merge
from catalog.core.picks import Pick
from catalog.tmdb.match import POSTER_BASE_URL


def row(handle="the-thing", **overrides):
    base = {"Handle": handle, "Title": "The Thing", "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", "Option1 Name": "Genre", "Option1 Value": "Horror"}
    base.update(overrides)
    return base


def changes_of(result):
    return {(c.handle, c.field): (c.after, c.source) for c in result.changes}


QUEUED = {"the-thing": {"batch": "ambiguous-queue", "status": "queued"}}


class TestAutoFix(unittest.TestCase):
    def test_autofix_becomes_changes(self):
        result = merge([row()], {"the-thing": {"changes": {"Vendor": "Blu-Ray"}, "rules": ["format-alias"]}}, [], {})
        self.assertEqual(changes_of(result), {("the-thing", "Vendor"): ("Blu-Ray", "auto-fix")})

    def test_autofix_already_in_shopify_is_dropped(self):
        result = merge([row(Vendor="Blu-Ray")], {"the-thing": {"changes": {"Vendor": "Blu-Ray"}, "rules": []}}, [], {})
        self.assertEqual(result.changes, [])

    def test_autofix_for_a_vanished_product_is_ignored(self):
        result = merge([], {"gone": {"changes": {"Vendor": "VHS"}, "rules": []}}, [], {})
        self.assertEqual(result.ignored[0][0], "gone")


class TestPicks(unittest.TestCase):
    def test_tmdb_pick_fills_empty_fields_and_alt(self):
        result = merge([row()], {}, [Pick("ambiguous-queue", "the-thing", "tmdb", "/t.jpg", "A shapeshifter.")], QUEUED)
        c = changes_of(result)
        self.assertEqual(c[("the-thing", "Image Src")][0], f"{POSTER_BASE_URL}/t.jpg")
        self.assertEqual(c[("the-thing", "Image Alt Text")][0], "The Thing poster")
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>A shapeshifter.</p>")
        self.assertEqual(c[("the-thing", "Image Src")][1], "pick:ambiguous-queue")
        self.assertEqual(set(result.applied["the-thing"]), {"Image Src", "Image Alt Text", "Body (HTML)"})

    def test_tmdb_pick_never_overwrites(self):
        result = merge([row(**{"Image Src": "https://cdn/x.jpg", "Image Alt Text": "x"})], {},
                       [Pick("q", "the-thing", "tmdb", "/t.jpg", "")], QUEUED)
        self.assertEqual(result.changes, [])
        self.assertEqual(result.resolved, ["the-thing"])

    def test_current_cycle_manual_pick_overwrites(self):
        result = merge([row(**{"Image Src": "https://cdn/old.jpg", "Image Alt Text": "Old", "Body (HTML)": "<p>old</p>"})],
                       {}, [Pick("ambiguous-queue", "the-thing", "manual", image_src="https://new.jpg", overview="New.")],
                       QUEUED)
        c = changes_of(result)
        self.assertEqual(c[("the-thing", "Image Src")][0], "https://new.jpg")
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>New.</p>")
        self.assertNotIn(("the-thing", "Image Alt Text"), c)  # existing alt text kept

    def test_legacy_manual_pick_only_fills_gaps(self):
        result = merge([row(**{"Image Src": "https://cdn/fixed-since.jpg"})], {},
                       [Pick("review-9.2-gaps", "the-thing", "manual", image_src="https://old.jpg", overview="Old.")],
                       {})  # not in the registry: an older batch
        c = changes_of(result)
        self.assertNotIn(("the-thing", "Image Src"), c)
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>Old.</p>")

    def test_empty_manual_pick_is_ignored(self):
        result = merge([row()], {}, [Pick("q", "the-thing", "manual")], QUEUED)
        self.assertEqual(result.changes, [])
        self.assertEqual(result.applied, {})
        self.assertIn("empty manual pick", result.ignored[0][1])

    def test_skip_pick(self):
        result = merge([row()], {}, [Pick("q", "the-thing", "skip")], QUEUED)
        self.assertEqual(result.skipped, ["the-thing"])
        self.assertEqual(result.changes, [])

    def test_already_skipped_is_not_skipped_again(self):
        result = merge([row()], {}, [Pick("q", "the-thing", "skip")], {"the-thing": {"status": "skipped"}})
        self.assertEqual(result.skipped, [])

    def test_applied_or_resolved_handles_are_left_alone(self):
        for status in ("applied", "resolved"):
            with self.subTest(status=status):
                result = merge([row()], {}, [Pick("q", "the-thing", "tmdb", "/t.jpg", "O.")],
                               {"the-thing": {"status": status}})
                self.assertEqual(result.changes, [])

    def test_pick_for_a_product_not_in_the_snapshot_is_ignored(self):
        result = merge([], {}, [Pick("q", "gone", "tmdb", "/t.jpg", "O.")], {})
        self.assertEqual(result.ignored[0][0], "gone")

    def test_later_batch_wins_for_the_same_handle(self):
        picks = [Pick("old", "the-thing", "tmdb", "/old.jpg", ""), Pick("ambiguous-queue", "the-thing", "tmdb", "/new.jpg", "")]
        c = changes_of(merge([row()], {}, picks, QUEUED))
        self.assertEqual(c[("the-thing", "Image Src")], (f"{POSTER_BASE_URL}/new.jpg", "pick:ambiguous-queue"))

    def test_pick_beats_autofix_on_the_same_field(self):
        autofix = {"the-thing": {"changes": {"Image Src": f"{POSTER_BASE_URL}/auto.jpg"}, "rules": ["poster-missing"]}}
        c = changes_of(merge([row()], autofix, [Pick("q", "the-thing", "tmdb", "/picked.jpg", "")], QUEUED))
        self.assertEqual(c[("the-thing", "Image Src")], (f"{POSTER_BASE_URL}/picked.jpg", "pick:q"))

    def test_changes_are_sorted(self):
        result = merge([row("b"), row("a")], {"b": {"changes": {"Vendor": "DVD"}, "rules": []},
                                              "a": {"changes": {"Vendor": "DVD"}, "rules": []}}, [], {})
        self.assertEqual([c.handle for c in result.changes], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
```

Run → `ModuleNotFoundError: No module named 'catalog.apply'`.

- [ ] **Step 2: Implement `catalog/apply/merge.py`**

```python
"""Combine the audit's safe auto-fixes with the client's picks, checked
against the snapshot. Pure: data in, a MergeResult out.

Precedence: a pick beats an auto-fix on the same field. A tmdb pick only
fills empty fields. A manual pick overwrites when the handle is in the
current picker cycle (registry "queued"); a manual pick from an older batch
(not in the registry) only fills empty fields, so it can't undo a fix made
since. Handles already applied/resolved are left alone.
"""

from dataclasses import dataclass, field

from catalog.core.picks import Pick
from catalog.core.text import strip_html
from catalog.tmdb.match import POSTER_BASE_URL

AUTO_FIX_SOURCE = "auto-fix"
CHANGE_COLUMNS = ["handle", "field", "before", "after", "source"]


@dataclass(frozen=True)
class Change:
    handle: str
    field: str
    before: str
    after: str
    source: str  # "auto-fix" or "pick:<batch>"


@dataclass
class MergeResult:
    changes: list[Change] = field(default_factory=list)
    applied: dict = field(default_factory=dict)    # handle -> {field: value}, pick-sourced only
    skipped: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)  # picks Shopify already satisfies
    ignored: list[tuple[str, str]] = field(default_factory=list)


def _pick_values(pick: Pick, row: dict, current_cycle: bool) -> dict | None:
    """Fields this pick would set; None for an empty manual pick."""
    title = (row.get("Title") or "").strip()
    has_image = bool((row.get("Image Src") or "").strip())
    has_alt = bool((row.get("Image Alt Text") or "").strip())
    has_body = bool(strip_html(row.get("Body (HTML)", "")))
    if pick.choice == "manual":
        if not pick.image_src and not pick.overview:
            return None
        image, body, overwrite = pick.image_src, pick.overview, current_cycle
    else:
        image = f"{POSTER_BASE_URL}{pick.poster_path}" if pick.poster_path else ""
        body, overwrite = pick.overview, False

    values: dict = {}
    if image and (overwrite or not has_image):
        values["Image Src"] = image
        if not has_alt:
            values["Image Alt Text"] = f"{title} poster"
    if body and (overwrite or not has_body):
        values["Body (HTML)"] = f"<p>{body}</p>"
    return values


def merge(rows: list[dict], autofix: dict, picks: list[Pick], registry: dict) -> MergeResult:
    by_handle = {r["Handle"]: r for r in rows}
    result = MergeResult()
    planned: dict[tuple[str, str], Change] = {}

    for handle, entry in autofix.items():
        row = by_handle.get(handle)
        if row is None:
            result.ignored.append((handle, "auto-fix for a product no longer in the snapshot"))
            continue
        for field_name, after in entry["changes"].items():
            before = row.get(field_name, "") or ""
            if before != after:
                planned[(handle, field_name)] = Change(handle, field_name, before, after, AUTO_FIX_SOURCE)

    latest: dict[str, Pick] = {}
    for pick in picks:  # manifest order: a later batch wins
        latest[pick.handle] = pick

    for handle, pick in latest.items():
        status = (registry.get(handle) or {}).get("status")
        if status in ("applied", "resolved"):
            continue
        if pick.choice == "skip":
            if status != "skipped":
                result.skipped.append(handle)
            continue
        row = by_handle.get(handle)
        if row is None:
            result.ignored.append((handle, f"pick in {pick.batch} for a product not in the snapshot"))
            continue
        values = _pick_values(pick, row, current_cycle=(status == "queued"))
        if values is None:
            result.ignored.append((handle, f"empty manual pick in {pick.batch}"))
            continue
        if not values:
            result.resolved.append(handle)
            continue
        source = f"pick:{pick.batch}"
        for field_name, after in values.items():
            planned[(handle, field_name)] = Change(handle, field_name, row.get(field_name, "") or "", after, source)
        result.applied[handle] = values

    result.changes = sorted(planned.values(), key=lambda c: (c.handle, c.field))
    return result
```

- [ ] **Step 3: Run the suite** — `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/apply tests/catalog/test_apply_merge.py
git commit -m "feat(catalog): merge auto-fixes and client picks against the snapshot

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 10: Narrow import CSVs — `apply/csv_groups.py`

**Files:**
- Create: `catalog/apply/csv_groups.py`
- Test: `tests/catalog/test_csv_groups.py`

**Interfaces:**
- Consumes: `Change` (Task 9), `GENRE_METAFIELD`, `write_csv`.
- Produces: `catalog.apply.csv_groups`: `REQUIRED_COLUMNS = ["Handle", "Title", "Option1 Name", "Option1 Value"]`, `GROUP_COLUMNS: dict[str, list[str]]`, `build_import_files(changes, rows_by_handle) -> dict[str, tuple[list[str], list[dict]]]` (filename → (columns, rows)), `write_import_files(import_dir, files) -> list[Path]` (clears existing `*.csv` in `import_dir` first), `warnings_for(files) -> list[str]`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_csv_groups.py`:

```python
import csv
import tempfile
import unittest
from pathlib import Path

from catalog.apply.csv_groups import REQUIRED_COLUMNS, build_import_files, warnings_for, write_import_files
from catalog.apply.merge import Change
from catalog.core.columns import GENRE_METAFIELD


def row(handle, **overrides):
    base = {"Handle": handle, "Title": f"Title {handle}", "Option1 Name": "Genre", "Option1 Value": "Comedy",
            "Image Src": "", "Image Alt Text": "", "Body (HTML)": "", "Tags": "Rental, VHS, Comedy",
            "Vendor": "VHS", "Variant Price": "0.00", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


ROWS = {
    "img": row("img"),
    "alt": row("alt", **{"Image Src": "https://cdn/a.jpg"}),
    "desc": row("desc"),
    "genre": row("genre", **{"Option1 Name": "Title", "Option1 Value": "Default Title", GENRE_METAFIELD: ""}),
    "tags": row("tags", Tags="Rental, vhs, Comedy"),
    "vendor": row("vendor", Vendor="bluray"),
    "price": row("price", **{"Variant Price": ""}),
}
CHANGES = [
    Change("img", "Image Src", "", "https://tmdb/i.jpg", "pick:q"),
    Change("img", "Image Alt Text", "", "Title img poster", "pick:q"),
    Change("img", "Body (HTML)", "", "<p>x</p>", "pick:q"),
    Change("alt", "Image Alt Text", "", "Title alt poster", "auto-fix"),
    Change("desc", "Body (HTML)", "", "<p>d</p>", "auto-fix"),
    Change("genre", "Option1 Name", "Title", "Genre", "auto-fix"),
    Change("genre", "Option1 Value", "Default Title", "Comedy", "auto-fix"),
    Change("genre", GENRE_METAFIELD, "", "comedy", "auto-fix"),
    Change("tags", "Tags", "Rental, vhs, Comedy", "Rental, VHS, Comedy", "auto-fix"),
    Change("vendor", "Vendor", "bluray", "Blu-Ray", "auto-fix"),
    Change("price", "Variant Price", "", "0", "auto-fix"),
]


class TestBuildImportFiles(unittest.TestCase):
    def setUp(self):
        self.files = build_import_files(CHANGES, ROWS)

    def handles(self, name):
        return [r["Handle"] for r in self.files[name][1]]

    def test_each_change_lands_in_its_group(self):
        self.assertEqual(self.handles("image.csv"), ["img"])
        self.assertEqual(self.handles("alt-text.csv"), ["alt"])
        self.assertEqual(self.handles("description.csv"), ["desc", "img"])
        self.assertEqual(self.handles("genre.csv"), ["genre"])
        self.assertEqual(self.handles("tags.csv"), ["tags"])
        self.assertEqual(self.handles("vendor.csv"), ["vendor"])
        self.assertEqual(self.handles("price.csv"), ["price"])

    def test_only_needed_columns(self):
        self.assertEqual(self.files["description.csv"][0], REQUIRED_COLUMNS + ["Body (HTML)"])
        self.assertEqual(self.files["image.csv"][0], REQUIRED_COLUMNS + ["Image Src", "Image Alt Text"])
        self.assertEqual(self.files["genre.csv"][0], REQUIRED_COLUMNS + [GENRE_METAFIELD])

    def test_no_file_contains_a_blank_cell(self):
        for name, (columns, rows) in self.files.items():
            for r in rows:
                for column in columns:
                    with self.subTest(file=name, handle=r["Handle"], column=column):
                        self.assertTrue(str(r[column]).strip())

    def test_alt_text_file_restates_the_existing_image(self):
        self.assertEqual(self.files["alt-text.csv"][1][0]["Image Src"], "https://cdn/a.jpg")

    def test_genre_file_carries_the_new_option1(self):
        r = self.files["genre.csv"][1][0]
        self.assertEqual((r["Option1 Name"], r["Option1 Value"]), ("Genre", "Comedy"))

    def test_other_files_carry_the_final_option1_too(self):
        changes = CHANGES + [Change("genre", "Body (HTML)", "", "<p>g</p>", "auto-fix")]
        files = build_import_files(changes, ROWS)
        r = [x for x in files["description.csv"][1] if x["Handle"] == "genre"][0]
        self.assertEqual(r["Option1 Value"], "Comedy")

    def test_empty_groups_are_not_produced(self):
        files = build_import_files([Change("desc", "Body (HTML)", "", "<p>d</p>", "auto-fix")], ROWS)
        self.assertEqual(list(files), ["description.csv"])


class TestWarnings(unittest.TestCase):
    def test_warns_about_option1_and_image_restating(self):
        text = " ".join(warnings_for(build_import_files(CHANGES, ROWS)))
        self.assertIn("genre.csv", text)
        self.assertIn("alt-text.csv", text)

    def test_no_warnings_for_safe_files(self):
        self.assertEqual(warnings_for(build_import_files([Change("desc", "Body (HTML)", "", "<p>d</p>", "a")], ROWS)), [])


class TestWriteImportFiles(unittest.TestCase):
    def test_writes_files_and_clears_stale_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            import_dir = Path(tmp) / "import"
            import_dir.mkdir()
            (import_dir / "price.csv").write_text("stale", encoding="utf-8")
            paths = write_import_files(import_dir, build_import_files(CHANGES[:3], ROWS))
            self.assertEqual(sorted(p.name for p in import_dir.iterdir()), ["description.csv", "image.csv"])
            with open(import_dir / "image.csv", newline="", encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f)), REQUIRED_COLUMNS + ["Image Src", "Image Alt Text"])
            self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
```

Run → `ModuleNotFoundError: No module named 'catalog.apply.csv_groups'`.

- [ ] **Step 2: Implement `catalog/apply/csv_groups.py`**

```python
"""Turn planned changes into narrow Shopify import CSVs, one per field group.

Shopify leaves an absent column alone but clears a blank cell in a present
column. So each file carries only the columns its rows change, plus the
columns the importer requires on every row (Handle, Title, Option1 Name,
Option1 Value) restated with the product's *final* values — the same in
every file, so the files can be imported in any order.
"""

from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import write_csv

REQUIRED_COLUMNS = ["Handle", "Title", "Option1 Name", "Option1 Value"]

GROUP_COLUMNS = {
    "image.csv": ["Image Src", "Image Alt Text"],
    "alt-text.csv": ["Image Src", "Image Alt Text"],
    "description.csv": ["Body (HTML)"],
    "genre.csv": [GENRE_METAFIELD],
    "tags.csv": ["Tags"],
    "vendor.csv": ["Vendor"],
    "price.csv": ["Variant Price"],
}

_FIELD_GROUP = {
    "Image Src": "image.csv",
    "Body (HTML)": "description.csv",
    "Option1 Name": "genre.csv",
    "Option1 Value": "genre.csv",
    GENRE_METAFIELD: "genre.csv",
    "Tags": "tags.csv",
    "Vendor": "vendor.csv",
    "Variant Price": "price.csv",
}


def build_import_files(changes, rows_by_handle: dict) -> dict[str, tuple[list[str], list[dict]]]:
    final: dict[str, dict] = {}
    changed_fields: dict[str, set] = {}
    for change in changes:
        final.setdefault(change.handle, dict(rows_by_handle[change.handle]))[change.field] = change.after
        changed_fields.setdefault(change.handle, set()).add(change.field)

    members: dict[str, set] = {}
    for handle, fields in changed_fields.items():
        for field_name in fields:
            if field_name == "Image Alt Text":
                group = "image.csv" if "Image Src" in fields else "alt-text.csv"
            else:
                group = _FIELD_GROUP[field_name]
            members.setdefault(group, set()).add(handle)

    files = {}
    for group, extra in GROUP_COLUMNS.items():
        if group not in members:
            continue
        columns = REQUIRED_COLUMNS + [c for c in extra if c not in REQUIRED_COLUMNS]
        rows = [{c: final[h].get(c, "") for c in columns} for h in sorted(members[group])]
        files[group] = (columns, rows)
    return files


def warnings_for(files: dict) -> list[str]:
    warnings = []
    if "genre.csv" in files:
        warnings.append("genre.csv changes Option1 Name/Value — import it only after the dev-store check "
                        "(plan 2, Task 12) confirmed barcodes and inventory survive an Option1 change.")
    if "alt-text.csv" in files:
        warnings.append("alt-text.csv restates each product's existing Image Src — import it only after the "
                        "dev-store check confirmed this does not duplicate images.")
    return warnings


def write_import_files(import_dir, files: dict) -> list[Path]:
    import_dir = Path(import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)
    for stale in import_dir.glob("*.csv"):
        stale.unlink()
    paths = []
    for name, (columns, rows) in files.items():
        write_csv(import_dir / name, columns, rows)
        paths.append(import_dir / name)
    return paths
```

- [ ] **Step 3: Run the suite** — `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/apply/csv_groups.py tests/catalog/test_csv_groups.py
git commit -m "feat(catalog): narrow per-field-group Shopify import CSVs with no blank cells

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 11: `apply` command

**Files:**
- Create: `catalog/apply/command.py`
- Modify: `catalog/cli.py` (register), `catalog/README.md` (stages 2 and 3)
- Test: `tests/catalog/test_apply_command.py`

**Interfaces:**
- Consumes: `merge`, `CHANGE_COLUMNS` (Task 9), `build_import_files`, `warnings_for`, `write_import_files` (Task 10), `load_picks`, `local_reader`, `remote_reader` (Task 8), `fetch_branch` (Task 5), `Plan`, `confirm`, `add_approval_args` (Task 2), `resolve_run`, `load_snapshot`, `write_csv`, registry functions.
- Produces: `catalog.apply.command`: `register(subparsers)`, `run_command(args, read_text=None, stdin=None) -> int`. CLI: `python3 -m catalog apply [--run ID] [--local-picks] [--dry-run] [--yes] [-v|-q]`. Writes `runs/<id>/apply-plan.csv` (always, as the plan's full list), and on approval `runs/<id>/import/*.csv`, plus registry `applied` / `skipped` / `resolved`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_apply_command.py`:

```python
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.apply import command
from catalog.cli import build_parser, main
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD


def row(handle, **overrides):
    base = {"Handle": handle, "Title": handle.title(), "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Rental, VHS, Comedy", "Vendor": "VHS", "Option1 Name": "Genre", "Option1 Value": "Comedy",
            "Variant Price": "0.00", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class TestApplyCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        self.run = self.runs / "2026-09-25"
        self.run.mkdir(parents=True)
        (self.run / "snapshot.json").write_text(json.dumps([row("jaws"), row("heat", Vendor="bluray"), row("rocky")]),
                                                encoding="utf-8")
        (self.run / "autofix.json").write_text(json.dumps(
            {"heat": {"changes": {"Vendor": "Blu-Ray"}, "rules": ["format-alias"]}}), encoding="utf-8")
        (self.run / "run-report.txt").write_text("done\n", encoding="utf-8")
        (self.picker / "data").mkdir(parents=True)
        (self.picker / "batches.json").write_text(json.dumps([{"batch_id": "ambiguous-queue", "total": 2}]),
                                                  encoding="utf-8")
        (self.picker / "data" / "ambiguous-queue.json").write_text(json.dumps([
            {"handle": "jaws", "choice": "tmdb", "poster_path": "/jaws.jpg", "overview": "A shark."},
            {"handle": "rocky", "choice": "skip"},
        ]), encoding="utf-8")
        (self.picker / "data" / "_handle-index.json").write_text(json.dumps({
            "jaws": {"batch": "ambiguous-queue", "status": "queued"},
            "rocky": {"batch": "ambiguous-queue", "status": "queued"},
        }), encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "--local-picks", "-q", *extra])

    def registry(self):
        return json.loads((self.picker / "data" / "_handle-index.json").read_text(encoding="utf-8"))

    def test_dry_run_writes_the_plan_list_only(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--dry-run"))
        self.assertTrue((self.run / "apply-plan.csv").exists())
        self.assertFalse((self.run / "import").exists())
        self.assertEqual(self.registry()["jaws"]["status"], "queued")

    def test_yes_writes_import_files_and_updates_registry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
        names = sorted(p.name for p in (self.run / "import").iterdir())
        self.assertEqual(names, ["description.csv", "image.csv", "vendor.csv"])
        registry = self.registry()
        self.assertEqual(registry["jaws"]["status"], "applied")
        self.assertEqual(registry["jaws"]["run"], "2026-09-25")
        self.assertIn("Image Src", registry["jaws"]["values"])
        self.assertEqual(registry["rocky"]["status"], "skipped")
        self.assertNotIn("heat", registry)  # auto-fixes are not tracked in the registry
        with open(self.run / "apply-plan.csv", newline="", encoding="utf-8") as f:
            plan_rows = list(csv.DictReader(f))
        self.assertEqual({(r["handle"], r["source"]) for r in plan_rows},
                         {("heat", "auto-fix"), ("jaws", "pick:ambiguous-queue")})

    def test_apply_refuses_without_a_terminal(self):
        err = io.StringIO()
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q"]
        with mock.patch("sys.stdin", FakeStdin(tty=False)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertFalse((self.run / "import").exists())
        self.assertEqual(self.registry()["jaws"]["status"], "queued")

    def test_second_apply_replaces_import_files_and_skips_applied(self):
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--yes"))
            first_values = self.registry()["jaws"]["values"]
            # Nothing left: jaws is applied, rocky skipped, and the auto-fix is gone.
            (self.run / "autofix.json").write_text("{}", encoding="utf-8")
            command.run_command(self.args("--yes"))
        self.assertEqual(list((self.run / "import").glob("*.csv")), [])  # stale files cleared
        self.assertEqual(self.registry()["jaws"]["values"], first_values)  # not re-applied

    def test_apply_reads_picks_through_the_injected_reader(self):
        files = {"batches.json": json.dumps([{"batch_id": "ambiguous-queue", "total": 1}]),
                 "data/ambiguous-queue.json": json.dumps([{"handle": "rocky", "choice": "skip"}])}
        args = build_parser().parse_args(["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker),
                                          "-q", "--yes"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_text=files.get)
        self.assertEqual(self.registry()["rocky"]["status"], "skipped")
        self.assertEqual(self.registry()["jaws"]["status"], "queued")  # its pick wasn't in the reader

    def test_a_pick_with_fields_stops_apply(self):
        (self.picker / "data" / "ambiguous-queue.json").write_text(json.dumps([
            {"handle": "jaws", "choice": "manual", "fields": {"genre": "horror"}}]), encoding="utf-8")
        err = io.StringIO()
        argv = ["apply", "--runs-dir", str(self.runs), "--picker-dir", str(self.picker), "--local-picks", "-q", "--yes"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("ambiguous-queue/jaws", err.getvalue())


if __name__ == "__main__":
    unittest.main()
```

`test_second_apply_replaces_import_files_and_skips_applied` pins this behaviour: when a re-run has nothing left to change, the previous import CSVs are removed (so stale files never look current), and already-applied handles are not re-applied.

Run → `ImportError` (no `catalog.apply.command`).

- [ ] **Step 2: Implement `catalog/apply/command.py`**

```python
"""`python3 -m catalog apply` — turn the latest audit's auto-fixes plus the
client's picks into Shopify import CSVs (runs/<id>/import/*.csv).

Picks are read from the branch the hosted picker commits to (origin/main)
via git fetch + git show, so any local branch works; --local-picks reads the
working tree instead. Nothing is written to Shopify: you import the CSVs.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from catalog import config
from catalog.apply.csv_groups import build_import_files, warnings_for, write_import_files
from catalog.apply.merge import AUTO_FIX_SOURCE, CHANGE_COLUMNS, merge
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.git_sync import fetch_branch
from catalog.core.picks import load_picks, local_reader, remote_reader
from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.core.registry import load_registry, mark_applied, mark_resolved, mark_skipped, save_registry
from catalog.core.runs import resolve_run
from catalog.errors import CatalogError
from catalog.shopify.snapshot import load_snapshot


def register(subparsers) -> None:
    p = subparsers.add_parser("apply", help="turn auto-fixes and client picks into Shopify import CSVs")
    p.add_argument("--run", help="audit run id (default: the latest complete run)")
    p.add_argument("--local-picks", action="store_true",
                   help=f"read picks from the working tree instead of {config.PICKER_REMOTE}/{config.PICKER_BRANCH}")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    add_approval_args(p)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def _pick_reader(args, picker_dir: Path):
    if args.local_picks:
        return local_reader(picker_dir), f"working tree ({picker_dir})"
    ref = f"{config.PICKER_REMOTE}/{config.PICKER_BRANCH}"
    try:
        fetch_branch(config.REPO_ROOT, config.PICKER_REMOTE, config.PICKER_BRANCH)
    except RuntimeError as exc:
        raise CatalogError(f"{exc}\nRe-run with --local-picks to use the working tree's picks.") from None
    return remote_reader(config.REPO_ROOT, ref, config.PICKER_REL), ref


def run_command(args, read_text=None, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    log.setup_logging(run_dir / "apply.log", log.verbosity(args))
    log.header(f"apply — audit run {run_dir.name}")

    rows = load_snapshot(run_dir / "snapshot.json")
    autofix = json.loads((run_dir / "autofix.json").read_text(encoding="utf-8"))
    picker_dir = Path(args.picker_dir)
    if read_text is None:
        read_text, source = _pick_reader(args, picker_dir)
    else:
        source = "injected reader"
    picks = load_picks(read_text)
    log.summary(f"{len(picks)} picks read from {source}")

    registry = load_registry(picker_dir)
    result = merge(rows, autofix, picks, registry)
    files = build_import_files(result.changes, {r["Handle"]: r for r in rows})

    details = run_dir / "apply-plan.csv"
    write_csv(details, CHANGE_COLUMNS, [asdict(c) for c in result.changes])
    for handle, reason in result.ignored:
        log.detail(f"ignored {handle}: {reason}")

    from_picks = sum(1 for c in result.changes if c.source != AUTO_FIX_SOURCE)
    plan = Plan(
        title="apply",
        count=len(result.changes) + len(result.skipped) + len(result.resolved),
        summary=[f"import/{name}: {len(file_rows)} products" for name, (_, file_rows) in files.items()]
        + [f"changes: {len(result.changes)} ({len(result.changes) - from_picks} auto-fix, {from_picks} from picks)",
           f"registry: {len(result.applied)} -> applied, {len(result.skipped)} -> skipped, "
           f"{len(result.resolved)} -> resolved (already in Shopify)",
           f"ignored: {len(result.ignored)} (see apply.log with -v)"],
        samples=[f"{c.handle} {c.field}: {c.before[:40]!r} -> {c.after[:60]!r} ({c.source})" for c in result.changes],
        warnings=warnings_for(files),
        details_path=details,
    )
    import_dir = run_dir / "import"
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        if plan.count == 0 and import_dir.exists():
            write_import_files(import_dir, {})  # nothing left to import: clear stale files
        return 0

    paths = write_import_files(import_dir, files)
    for handle, values in result.applied.items():
        mark_applied(registry, handle, run_dir.name, values)
    for handle in result.skipped:
        mark_skipped(registry, handle)
    mark_resolved(registry, result.resolved)
    save_registry(picker_dir, registry)

    log.summary(f"wrote {len(paths)} file(s) to {import_dir}:")
    for path in paths:
        log.summary(f"  {path.name}")
    log.summary("Import each in Shopify admin → Products → Import, with 'Overwrite products with matching handles' on.")
    log.summary("The next audit confirms each applied pick landed (applied -> resolved).")
    log.summary(f"The registry changed locally ({config.PICKER_REL}/data/_handle-index.json) — "
                "it is published with the next `picker push`, or commit it yourself.")
    return 0
```

Register in `catalog/cli.py` — replace:
```python
from catalog.audit import command as audit_command
from catalog.picker import command as picker_command

COMMANDS: list = [audit_command, picker_command]  # modules with register(subparsers), in help order
```
with:
```python
from catalog.apply import command as apply_command
from catalog.audit import command as audit_command
from catalog.picker import command as picker_command

COMMANDS: list = [audit_command, picker_command, apply_command]  # modules with register(subparsers), in help order
```

- [ ] **Step 3: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`. Also run the old suite → `Ran 348 tests … OK`.

- [ ] **Step 4: Extend `catalog/README.md`** — insert after the Stage 1 section, before `## Tests`:

```markdown
## Approval

Every command that changes anything outside its run folder shows a plan first and asks
`Proceed? [y/N]`. `--dry-run` shows the plan and changes nothing; `--yes` approves without
asking. Outside a terminal (scripts, agents) the command refuses unless `--yes` is given.

## Stage 2 — picker push

    python3 -m catalog picker push            # uses the latest complete audit run
    python3 -m catalog picker push --dry-run

Adds the run's `review.json` products the registry doesn't know yet to the hosted
picker's `ambiguous-queue` / `unmatched-queue` (fetching TMDB candidates — needs
`TMDB_API_KEY`), marks them `queued`, then commits and pushes `tools/review-picker/`.
It only pushes from `main` (Vercel deploys `main`); on another branch it writes the files
and tells you to publish them. `--no-git-sync` never commits.

## Stage 3 — apply

    python3 -m catalog apply --dry-run        # see what would change
    python3 -m catalog apply                  # write runs/<id>/import/*.csv

Combines the run's `autofix.json` with the client's picks (read from `origin/main` — the
branch the picker saves to; `--local-picks` reads the working tree) and writes one CSV per
field group — `image`, `alt-text`, `description`, `genre`, `tags`, `vendor`, `price` —
each with only the columns it changes plus `Handle, Title, Option1 Name, Option1 Value`.
Import each in Shopify admin. `apply-plan.csv` lists every change (handle, field, before,
after, source). Picks become `applied` in the registry; the next audit promotes them to
`resolved` once Shopify shows them, or reports `applied-but-missing`.

Hold `genre.csv` and `alt-text.csv` until the dev-store check in
`claudedocs/2026-09-25-apply-import-verification.md` passes.
```

- [ ] **Step 5: Commit**

```bash
git add catalog/apply/command.py catalog/cli.py catalog/README.md tests/catalog/test_apply_command.py
git commit -m "feat(catalog): python3 -m catalog apply

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 12: Live dry runs and the dev-store import check

**Files:**
- Create: `claudedocs/2026-09-25-apply-import-verification.md`

**Interfaces:** none new.

- [ ] **Step 1: Production dry runs (read-only)**

```bash
python3 -m catalog picker push --dry-run
python3 -m catalog apply --dry-run
```
Expected: `picker push` shows `ambiguous-queue: +N`, `unmatched-queue: +N` (the latest run's review.json had 56 products) and changes nothing. `apply` fetches `origin/main`, reports picks read, per-file counts and the warnings, writes `runs/<id>/apply-plan.csv`, and changes nothing else. Record both outputs' summaries in the verification doc. Do **not** run either without `--dry-run` — publishing cards and writing the registry is the user's call.

- [ ] **Step 2: Build dev-store check files — ask the user first**

This step needs the user to import two small CSVs into the **dev store** admin. Ask before proceeding. Then:

```bash
python3 -m catalog audit --store lms-sandbox-lutsfahz.myshopify.com --skip-tmdb -q
python3 - <<'EOF'
import csv, json
from pathlib import Path
from catalog.core.runs import resolve_run
from catalog.core.columns import GENRE_METAFIELD
run = resolve_run("runs")
rows = json.load(open(run / "snapshot.json", encoding="utf-8"))
auto = json.load(open(run / "autofix.json", encoding="utf-8"))
print(run.name, "autofix handles:", list(auto)[:10])
for r in rows[:30]:
    print(r["Handle"], "|", r["Option1 Name"], "|", r["Option1 Value"], "|", r["Variant Barcode"], "|",
          r["Variant Inventory Tracker"], "|", bool(r["Image Src"]), "|", r[GENRE_METAFIELD])
EOF
```
Pick two dev products from that listing and show them to the user: **A** has an image (alt-text check); **B** has a barcode and a second canonical genre in its tags (Option1 check — its `Option1 Value` will be switched to that second genre; tell the user, since it's a real edit on the dev store). If no dev product has a barcode, ask the user to set a test barcode on B in the dev admin first. Then build the two files with the exact code `apply` uses:

```bash
python3 - <<'EOF'
import json
from catalog.apply.csv_groups import build_import_files, write_import_files
from catalog.apply.merge import Change
from catalog.core.runs import resolve_run
A, B, B_GENRE = "HANDLE_A", "HANDLE_B", "SECOND_GENRE_LABEL"   # fill in from the listing above
run = resolve_run("runs")
rows = {r["Handle"]: r for r in json.load(open(run / "snapshot.json", encoding="utf-8"))}
changes = [
    Change(A, "Image Alt Text", rows[A]["Image Alt Text"], f"{rows[A]['Title'].strip()} poster (devcheck)", "devcheck"),
    Change(B, "Option1 Name", rows[B]["Option1 Name"], "Genre", "devcheck"),
    Change(B, "Option1 Value", rows[B]["Option1 Value"], B_GENRE, "devcheck"),
]
changes = [c for c in changes if c.before != c.after]
for path in write_import_files(run / "devcheck", build_import_files(changes, rows)):
    print(path); print(path.read_text(encoding="utf-8"))
EOF
```

Record the "before" state of A and B with a read-only query (replace the handles):

```bash
shopify store execute -s lms-sandbox-lutsfahz.myshopify.com --json -q '{ a: productByHandle(handle: "HANDLE_A") { media(first: 10) { nodes { ... on MediaImage { image { url altText } } } } } b: productByHandle(handle: "HANDLE_B") { options { name values } variants(first: 5) { nodes { barcode inventoryQuantity selectedOptions { name value } inventoryItem { tracked } } } } }' < /dev/null
```

- [ ] **Step 3: The user imports; re-read and compare**

After the user imports both files in the dev store admin (Products → Import → overwrite matching handles), re-run the same query and compare. Pass criteria:
- Option1 check: same variant count, same barcode, same inventory tracked/quantity, Option1 now `Genre` / the primary genre.
- Alt-text check: same image count (no duplicate image), alt text updated.

- [ ] **Step 4: Record and commit**

Write `claudedocs/2026-09-25-apply-import-verification.md` with the dry-run summaries, the before/after values and a PASS/FAIL for each check. If a check FAILS, the `warnings_for` text stays and a follow-up task is raised before any production `genre.csv` / `alt-text.csv` import; if both PASS, keep the warnings (they point at this doc) — removing them is the user's call.

```bash
git add claudedocs/2026-09-25-apply-import-verification.md
git commit -m "docs(catalog): apply dry runs and dev-store import verification

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

## What Plans 3–4 build on

- `core/plan.py` — every Libib command that changes state or Libib uses `Plan` + `confirm` + `add_approval_args`.
- `core/git_sync.py`, `core/picks.py` — Plan 4 deletes `formatting-scripts/` and the seam test from Task 4.
- `cli.COMMANDS` — Plan 3 adds `libib`, Plan 4 adds `check-upload`.
