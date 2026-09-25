# Catalog Pipeline — Plan 1: Foundation + Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `catalog/` package and ship stage 1: `python3 -m catalog audit` reads the Shopify movie catalogue (API or export CSV), runs every audit rule, auto-fixes what is safe via TMDB, and writes a run folder with findings, auto-fixes and picker entries.

**Architecture:** A new standard-library Python package `catalog/` at the repo root, built beside the untouched `formatting-scripts/` (which keeps working until Plan 4 deletes it). Shared pieces live in `catalog/core/`; the Shopify reader in `catalog/shopify/`; the TMDB matcher in `catalog/tmdb/`; stage 1 in `catalog/audit/`. Proven logic (taxonomy, resolvers, matcher, cache, registry) is copied over with its tests; new logic is test-first.

**Tech Stack:** Python 3.10+ (3.14 installed) standard library only, `unittest`, Shopify CLI 4.8+ (`shopify store execute`), TMDB search API.

**Spec:** `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md` (§2 architecture, §3 snapshot, §4 audit, §8 logging, §10 migration/testing). Read it before starting.

**This is plan 1 of 4.** Plan 2: picker push + apply (+ `core/plan.py` approval). Plan 3: Libib. Plan 4: move `client_sheet/`, delete `formatting-scripts/` and `tests/data_cleanup/`, update docs. Plans 2–4 are written after this one lands, against the real interfaces it produces.

## Global Constraints

- Standard library only in everything this plan creates. No new dependencies.
- Run every command from the repo root: `/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox`.
- New tests live in `tests/catalog/`, run with: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`.
- The old suite must keep passing throughout: `python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py"` — **baseline 2026-09-25: 348 tests, OK.**
- Do not modify anything under `formatting-scripts/` or `tests/formatting_scripts/` in this plan.
- No secrets in source. TMDB key comes only from env var `TMDB_API_KEY`.
- The pipeline never writes to Shopify. The API reader only runs read queries (`read_products` scope).
- Default store: production `p0wkgv-wy.myshopify.com`; `--store` overrides. Tests never call a real store or TMDB.
- Findings buckets are exactly: `auto-fix`, `picker`, `manual`.
- Rental barcode rule: every product tagged `Rental` has a barcode matching `^[0-9]{8}$` that appears on no other movie (Rental **or** Floor Sale). Floor Sale barcodes have no rules.
- Only `audit` in this plan writes outside its run folder: the shared TMDB cache (`runs/.tmdb-cache.json`) and registry promotion (`applied` → `resolved`) in `tools/review-picker/data/_handle-index.json`.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Decisions made while planning (confirm at review)

These fill gaps the spec left open. Each is small and reversible.

1. **Archived products are excluded** from the snapshot (alongside `retail`-template and non-catalogue products). They are off-sale; auditing them adds noise and their barcodes should not block live rentals.
2. **The registry moves to `catalog/core/registry.py`** (spec said `picker/registry.py`). Audit, picker push and apply all read it; putting it in `core/` keeps the "stages never import each other" rule.
3. **`type-alias` is an auto-fix rule** (spec listed genre/format aliases only). A misspelt `floorsale` tag resolves fine internally but breaks the storefront's `Floor Sale` tag filter, so it is fixed like the others.
4. **`option1-genre` is an auto-fix rule**: when `Option1 Value` isn't the primary genre (misspelt, compound like `4K, Action`, or `Default Title`), propose the canonical genre and `Option1 Name = Genre`. This is the change the spec's dev-store verification (Plan 2) must clear before `genre.csv` is ever imported.
5. **A run counts as complete only once `run-report.txt` exists.** "Latest run" skips incomplete folders, so a crashed/interrupted audit never feeds a later stage.
6. **The matcher now passes the product's own description as the overview tiebreak hint** (the old `build_output` passed nothing). Only products missing a poster but having a description benefit; it can only turn an ambiguous tie into a confident match.
7. **Legacy `resolved` registry entries whose field is still empty** are reported as `applied-but-missing` (detail: "marked resolved by the old pipeline"), because the old `apply_picks` marked handles resolved without an import ever being confirmed.

## Review Focus

1. **A production product with no variants, no media, a video as first media, or no genre metafield** must become a snapshot row with blank fields, never a crash. → Task 5 test `test_node_with_nothing_optional`.
2. **An interrupted audit** (Ctrl-C mid-TMDB, network drop) must keep the TMDB fetches made so far and must not leave a half-written run that later stages treat as "latest". → Task 6 test `test_saves_every_n_misses`, Task 1 test `test_latest_skips_incomplete_runs`, Task 10 test `test_interrupt_saves_cache_and_leaves_run_incomplete`.
3. **Barcodes with leading zeros or stray whitespace** (`"01577790"`, `" 01577790 "`) must pass the 8-digit check and match each other for duplicate detection; a 7-digit barcode must fail. → Task 8 tests `test_rental_barcode_whitespace_is_tolerated`, `test_rental_barcode_seven_digits`, Task 9 test `test_duplicate_ignores_surrounding_whitespace`.
4. **A multi-variant product** must get no auto-fixes and no TMDB lookup (a CSV fix on a multi-variant product can merge or clobber variants). → Task 8 test `test_multi_variant_gets_no_autofix`, Task 9 test `test_multi_variant_skips_tmdb`.
5. **An image Shopify re-hosted on its CDN** after import must count as "fix visible", so an applied poster is promoted to `resolved`, not reported missing forever. → Task 7 test `test_image_src_counts_as_visible_when_rehosted`.

---

### Task 0: Branch setup

**Files:** none.

- [ ] **Step 1: Check out the refactor branch and bring in the spec + this plan**

The spec and this plan were committed on `fix/redirect-all-collection`. `refactor/catalog-pipeline` already exists at that branch's previous tip.

```bash
git status --short            # must be empty
git checkout refactor/catalog-pipeline
git merge --ff-only fix/redirect-all-collection
git log --oneline -3          # top commits include the spec and this plan
```

- [ ] **Step 2: Record the baseline**

```bash
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -3
```
Expected: `Ran 348 tests` … `OK`. If not 348/OK, stop and report — the baseline moved.

---

### Task 1: Package skeleton — errors, config, runs, text, CLI

**Files:**
- Create: `catalog/__init__.py`, `catalog/__main__.py`, `catalog/errors.py`, `catalog/config.py`, `catalog/cli.py`
- Create: `catalog/core/__init__.py`, `catalog/core/runs.py`, `catalog/core/text.py`
- Modify: `.gitignore` (add `runs/`)
- Test: `tests/catalog/test_runs.py`, `tests/catalog/test_text.py`, `tests/catalog/test_config.py`, `tests/catalog/test_cli.py`

**Interfaces:**
- Produces:
  - `catalog.errors`: `CatalogError(Exception)`, `MissingEnvError(CatalogError)`, `NoRunError(CatalogError)`, `InputShapeError(CatalogError)`, `ShopifyError(CatalogError)`
  - `catalog.config`: `REPO_ROOT: Path`, `DEFAULT_STORE = "p0wkgv-wy.myshopify.com"`, `RUNS_DIR: Path`, `TMDB_CACHE_FILENAME = ".tmdb-cache.json"`, `PICKER_DIR: Path`, `LIBIB_SYNC_DIR: Path`, `ENV_TMDB_API_KEY`, `ENV_LIBIB_EMAIL`, `ENV_LIBIB_PASSWORD`, `require_env(name, environ=None) -> str`
  - `catalog.core.runs`: `COMPLETE_MARKER = "run-report.txt"`, `list_runs(runs_dir) -> list[Path]`, `new_run(runs_dir, today: date) -> Path`, `resolve_run(runs_dir, run_id: str | None = None) -> Path`
  - `catalog.core.text`: `strip_html(text) -> str`, `norm_ws(text) -> str`
  - `catalog.cli`: `build_parser() -> ArgumentParser`, `main(argv=None) -> int`, `COMMANDS: list` (modules exposing `register(subparsers)`)

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_runs.py`:
```python
import tempfile
import unittest
from datetime import date
from pathlib import Path

from catalog.core.runs import COMPLETE_MARKER, list_runs, new_run, resolve_run
from catalog.errors import NoRunError


def complete(path: Path) -> Path:
    (path / COMPLETE_MARKER).write_text("done\n", encoding="utf-8")
    return path


class TestRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name) / "runs"

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_run_uses_the_date(self):
        path = new_run(self.runs, date(2026, 9, 25))
        self.assertEqual(path.name, "2026-09-25")
        self.assertTrue(path.is_dir())

    def test_second_run_same_day_gets_a_suffix(self):
        new_run(self.runs, date(2026, 9, 25))
        self.assertEqual(new_run(self.runs, date(2026, 9, 25)).name, "2026-09-25-2")
        self.assertEqual(new_run(self.runs, date(2026, 9, 25)).name, "2026-09-25-3")

    def test_latest_sorts_numerically_not_lexically(self):
        for _ in range(10):
            complete(new_run(self.runs, date(2026, 9, 25)))
        self.assertEqual(resolve_run(self.runs).name, "2026-09-25-10")

    def test_latest_prefers_later_date(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 26)))
        self.assertEqual(resolve_run(self.runs).name, "2026-09-26")

    def test_latest_skips_incomplete_runs(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        new_run(self.runs, date(2026, 9, 26))  # crashed: no run-report.txt
        self.assertEqual(resolve_run(self.runs).name, "2026-09-25")

    def test_ignores_dotfiles_and_foreign_dirs(self):
        self.runs.mkdir(parents=True)
        (self.runs / ".tmdb-cache.json").write_text("{}", encoding="utf-8")
        (self.runs / "scratch").mkdir()
        complete(new_run(self.runs, date(2026, 9, 25)))
        self.assertEqual([p.name for p in list_runs(self.runs)], ["2026-09-25"])

    def test_no_runs_raises_with_next_command(self):
        with self.assertRaises(NoRunError) as ctx:
            resolve_run(self.runs)
        self.assertIn("python3 -m catalog audit", str(ctx.exception))

    def test_explicit_run_id(self):
        complete(new_run(self.runs, date(2026, 9, 25)))
        complete(new_run(self.runs, date(2026, 9, 26)))
        self.assertEqual(resolve_run(self.runs, "2026-09-25").name, "2026-09-25")

    def test_explicit_missing_run_id_raises(self):
        with self.assertRaises(NoRunError):
            resolve_run(self.runs, "2026-01-01")


if __name__ == "__main__":
    unittest.main()
```

`tests/catalog/test_text.py`:
```python
import unittest

from catalog.core.text import norm_ws, strip_html


class TestText(unittest.TestCase):
    def test_strip_html_removes_tags_and_unescapes(self):
        self.assertEqual(strip_html("<p>Tom &amp; Jerry</p>"), "Tom & Jerry")

    def test_strip_html_handles_none(self):
        self.assertEqual(strip_html(None), "")

    def test_strip_html_empty_markup_is_empty(self):
        self.assertEqual(strip_html("<p> </p>"), "")

    def test_norm_ws_collapses_nbsp_and_runs(self):
        self.assertEqual(norm_ws("a\xa0 b\n\tc "), "a b c")


if __name__ == "__main__":
    unittest.main()
```

`tests/catalog/test_config.py`:
```python
import unittest

from catalog.config import DEFAULT_STORE, require_env
from catalog.errors import MissingEnvError


class TestConfig(unittest.TestCase):
    def test_default_store_is_production(self):
        self.assertEqual(DEFAULT_STORE, "p0wkgv-wy.myshopify.com")

    def test_require_env_returns_value(self):
        self.assertEqual(require_env("TMDB_API_KEY", {"TMDB_API_KEY": " abc "}), "abc")

    def test_require_env_names_the_missing_variable(self):
        with self.assertRaises(MissingEnvError) as ctx:
            require_env("TMDB_API_KEY", {})
        self.assertIn("TMDB_API_KEY", str(ctx.exception))

    def test_blank_counts_as_missing(self):
        with self.assertRaises(MissingEnvError):
            require_env("TMDB_API_KEY", {"TMDB_API_KEY": "  "})


if __name__ == "__main__":
    unittest.main()
```

`tests/catalog/test_cli.py`:
```python
import contextlib
import io
import unittest

from catalog.cli import main


class TestCli(unittest.TestCase):
    def test_help_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("catalog", out.getvalue())

    def test_unknown_command_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main(["nonsense"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: errors — `ModuleNotFoundError: No module named 'catalog'`.

- [ ] **Step 3: Write the implementation**

`catalog/__init__.py`:
```python
"""Little Movie Store catalogue pipeline: audit → picker push → apply → libib.

Run from the repo root: python3 -m catalog <command>. See catalog/README.md.
"""
```

`catalog/__main__.py`:
```python
import sys

from catalog.cli import main

sys.exit(main())
```

`catalog/errors.py`:
```python
"""Expected failures. The CLI prints these as one-line errors (exit 2)
instead of a traceback; anything else is a bug and keeps its traceback."""


class CatalogError(Exception):
    """Base for every expected, user-fixable failure."""


class MissingEnvError(CatalogError):
    """A required environment variable is not set."""


class NoRunError(CatalogError):
    """No usable audit run folder exists."""


class InputShapeError(CatalogError):
    """An input file is not the shape the command expects."""


class ShopifyError(CatalogError):
    """The Shopify CLI failed, is missing, or is not authenticated."""
```

`catalog/config.py`:
```python
"""Paths, the default store, and secret lookup. Secrets never live in source."""

import os
from pathlib import Path

from catalog.errors import MissingEnvError

REPO_ROOT = Path(__file__).resolve().parents[1]

# CLAUDE.md: production is the working store until the major release.
DEFAULT_STORE = "p0wkgv-wy.myshopify.com"

RUNS_DIR = REPO_ROOT / "runs"
TMDB_CACHE_FILENAME = ".tmdb-cache.json"
PICKER_DIR = REPO_ROOT / "tools" / "review-picker"
LIBIB_SYNC_DIR = REPO_ROOT / "libib-sync"

ENV_TMDB_API_KEY = "TMDB_API_KEY"
ENV_LIBIB_EMAIL = "LIBIB_EMAIL"
ENV_LIBIB_PASSWORD = "LIBIB_PASSWORD"


def require_env(name: str, environ=None) -> str:
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    if not value:
        raise MissingEnvError(f"{name} is not set. Export it first: export {name}=...")
    return value
```

`catalog/core/__init__.py`: empty file.

`catalog/core/runs.py`:
```python
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
```

`catalog/core/text.py`:
```python
"""The one HTML-to-text and whitespace normaliser for the whole package.

strip_html deletes tags without inserting spaces — the same behaviour the
Libib imports so far were built with, so comparisons against Libib stay
stable.
"""

import html
import re


def strip_html(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def norm_ws(text: str | None) -> str:
    """Collapse whitespace runs (including non-breaking spaces) to one space."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
```

`catalog/cli.py`:
```python
"""python3 -m catalog <command> — argument parsing and dispatch only.

Each command module exposes register(subparsers), which adds its parser and
sets func=<callable(args) -> int>.
"""

import argparse
import sys

from catalog.errors import CatalogError

COMMANDS: list = []  # modules with register(subparsers); stages append themselves here


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m catalog",
        description="Little Movie Store catalog pipeline: audit → picker push → apply → libib.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for module in COMMANDS:
        module.register(subparsers)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except CatalogError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Work saved so far is kept; the run is not marked complete.", file=sys.stderr)
        return 130
```

Append to `.gitignore`:
```
# Catalog pipeline run folders (local working data)
runs/
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all tests OK.

- [ ] **Step 5: Commit**

```bash
git add catalog .gitignore tests/catalog
git commit -m "feat(catalog): package skeleton — errors, config, run folders, CLI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Port core — taxonomy, columns, handles, csv_io

**Files:**
- Create (copied): `catalog/core/taxonomy.py`, `catalog/core/columns.py`, `catalog/core/handles.py`, `catalog/core/csv_io.py`
- Modify: `catalog/core/columns.py` (append `SNAPSHOT_COLUMNS`)
- Test (ported): `tests/catalog/test_taxonomy.py`, `tests/catalog/test_columns.py`, `tests/catalog/test_handles.py`, `tests/catalog/test_csv_io.py`

**Interfaces:**
- Produces (unchanged APIs from the originals): `catalog.core.taxonomy` (`GENRES`, `FORMATS`, `TYPES`, `canonical_genre`, `canonical_format`, `canonical_type`, `genre_handle`, `normalize_key`); `catalog.core.columns` (`GENRE_METAFIELD`, `REASON_COLUMN`, `FORMATTED_TAG`, `TEMPLATE_COLUMNS`, `EXPORT_COLUMNS`, `FIXED_VALUES`, `ISSUE_TAG_*`, **new** `SNAPSHOT_COLUMNS: list[str]`); `catalog.core.handles` (`slugify`, `derive_handle`, `HandleAllocator`); `catalog.core.csv_io` (`load_export(path) -> (fieldnames, rows)`, `write_csv(path, fieldnames, rows)`, `group_rows_by_handle(rows) -> list[(handle, rows)]`).

- [ ] **Step 1: Copy the modules** (none import other project modules, so no edits are needed)

```bash
cp formatting-scripts/taxonomy.py catalog/core/taxonomy.py
cp formatting-scripts/columns.py catalog/core/columns.py
cp formatting-scripts/handles.py catalog/core/handles.py
cp formatting-scripts/catalog_common.py catalog/core/csv_io.py
```

- [ ] **Step 2: Port their tests** (drop the `sys.path` line, rewrite the import)

```bash
port() {  # port <old test> <new test> <old module> <new dotted module>
  sed -e '/sys.path.insert(0, str(.*formatting-scripts/d' \
      -e "s/^from $3 import/from $4 import/" \
      "tests/formatting_scripts/$1" > "tests/catalog/$2"
}
port test_taxonomy.py test_taxonomy.py taxonomy catalog.core.taxonomy
port test_columns.py test_columns.py columns catalog.core.columns
port test_handles.py test_handles.py handles catalog.core.handles
port test_catalog_common.py test_csv_io.py catalog_common catalog.core.csv_io
grep -n "formatting-scripts\|^from [a-z_]* import" tests/catalog/test_taxonomy.py tests/catalog/test_columns.py tests/catalog/test_handles.py tests/catalog/test_csv_io.py
```
Expected from the grep: no `formatting-scripts` lines except `REPO_ROOT = ...` in `test_columns.py` (harmless), and every `from … import` starts with `catalog.`.

- [ ] **Step 3: Add the failing snapshot-columns test**

Append to `tests/catalog/test_columns.py`, just above the final `if __name__ == "__main__":` block:
```python
from catalog.core.columns import SNAPSHOT_COLUMNS


class TestSnapshotColumns(unittest.TestCase):
    def test_carries_every_field_the_audit_reads(self):
        for column in ("Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status",
                       "Template Suffix", "Image Src", "Image Alt Text", "Option1 Name",
                       "Option1 Value", "Variant Price", "Variant Barcode",
                       "Variant Inventory Tracker", "Variant Count", GENRE_METAFIELD):
            self.assertIn(column, SNAPSHOT_COLUMNS)

    def test_has_no_duplicates(self):
        self.assertEqual(len(SNAPSHOT_COLUMNS), len(set(SNAPSHOT_COLUMNS)))
```

Run: `python3 -m unittest tests.catalog.test_columns 2>&1 | tail -3` — expected: `ImportError: cannot import name 'SNAPSHOT_COLUMNS'`.

(If `python3 -m unittest tests.catalog.test_columns` fails because `tests` is not a package, run `python3 -m unittest discover -s tests/catalog -p "test_columns.py"` instead — same for every single-file run in this plan.)

- [ ] **Step 4: Append `SNAPSHOT_COLUMNS` to `catalog/core/columns.py`**

```python

# One row per product in runs/<id>/snapshot.json. Keys are Shopify export
# column names, so the API reader and --from-export produce identical rows
# and every resolver reads them unchanged. "Variant Count" and
# "Template Suffix" are snapshot-only (not import columns).
SNAPSHOT_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Tags",
    "Status",
    "Template Suffix",
    "Image Src",
    "Image Alt Text",
    "Option1 Name",
    "Option1 Value",
    "Variant Price",
    "Variant Barcode",
    "Variant Inventory Tracker",
    "Variant Count",
    GENRE_METAFIELD,
]
```

- [ ] **Step 5: Run the catalog suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK.

- [ ] **Step 6: Commit**

```bash
git add catalog/core tests/catalog
git commit -m "feat(catalog): port taxonomy, columns, handles and CSV I/O into catalog.core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Logging

**Files:**
- Create: `catalog/core/log.py`
- Test: `tests/catalog/test_log.py`

**Interfaces:**
- Produces: `catalog.core.log`: `SUMMARY = 25`, `setup_logging(log_path=None, verbosity: int = 0, stream=None) -> Logger`, `get_logger()`, `header(msg)`, `summary(msg)`, `progress(index, total, label, message)`, `detail(msg)`, `add_verbosity_args(parser)`, `verbosity(args) -> int` (`-1` quiet, `0` normal, `1` verbose).

- [ ] **Step 1: Write the failing test**

`tests/catalog/test_log.py`:
```python
import argparse
import io
import tempfile
import unittest
from pathlib import Path

from catalog.core import log


def lines(stream: io.StringIO) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line]


class TestLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "run" / "audit.log"

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())  # release the file handler
        self.tmp.cleanup()

    def emit_all(self):
        log.header("audit")
        log.progress(1, 2, "Rushmore", "filled image")
        log.detail("rule genre-alias fired")
        log.summary("3 findings")

    def test_normal_shows_progress_not_detail(self):
        out = io.StringIO()
        log.setup_logging(None, 0, out)
        self.emit_all()
        self.assertEqual(lines(out), ["== audit ==", "[1/2] Rushmore: filled image", "3 findings"])

    def test_quiet_shows_headers_and_summary_only(self):
        out = io.StringIO()
        log.setup_logging(None, -1, out)
        self.emit_all()
        self.assertEqual(lines(out), ["== audit ==", "3 findings"])

    def test_verbose_shows_detail(self):
        out = io.StringIO()
        log.setup_logging(None, 1, out)
        self.emit_all()
        self.assertIn("rule genre-alias fired", lines(out))

    def test_file_gets_everything_even_when_quiet(self):
        log.setup_logging(self.log_path, -1, io.StringIO())
        self.emit_all()
        text = self.log_path.read_text(encoding="utf-8")
        for fragment in ("== audit ==", "[1/2] Rushmore", "rule genre-alias fired", "3 findings"):
            self.assertIn(fragment, text)

    def test_setup_twice_does_not_duplicate_lines(self):
        out = io.StringIO()
        log.setup_logging(None, 0, io.StringIO())
        log.setup_logging(None, 0, out)
        log.summary("once")
        self.assertEqual(lines(out), ["once"])

    def test_verbosity_flags(self):
        parser = argparse.ArgumentParser()
        log.add_verbosity_args(parser)
        self.assertEqual(log.verbosity(parser.parse_args([])), 0)
        self.assertEqual(log.verbosity(parser.parse_args(["-q"])), -1)
        self.assertEqual(log.verbosity(parser.parse_args(["--verbose"])), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s tests/catalog -p "test_log.py"`
Expected: `ImportError: cannot import name 'log'`.

- [ ] **Step 3: Implement `catalog/core/log.py`**

```python
"""One logger for every stage: console plus runs/<id>/<stage>.log.

Levels: SUMMARY (25) = stage headers and closing counts, always shown;
INFO = per-item progress, hidden by --quiet; DEBUG = per-rule detail,
shown only with --verbose. The log file always records everything.
"""

import logging
import sys
from pathlib import Path

LOGGER_NAME = "catalog"
SUMMARY = 25
logging.addLevelName(SUMMARY, "SUMMARY")

_CONSOLE_LEVELS = {-1: SUMMARY, 0: logging.INFO, 1: logging.DEBUG}


def setup_logging(log_path=None, verbosity: int = 0, stream=None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler(stream if stream is not None else sys.stdout)
    console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def header(message: str) -> None:
    get_logger().log(SUMMARY, f"== {message} ==")


def summary(message: str) -> None:
    get_logger().log(SUMMARY, message)


def progress(index, total, label: str, message: str) -> None:
    get_logger().info(f"[{index}/{total}] {label}: {message}")


def detail(message: str) -> None:
    get_logger().debug(message)


def add_verbosity_args(parser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", action="store_true", help="show per-rule detail")
    group.add_argument("-q", "--quiet", action="store_true", help="show headers and summary only")


def verbosity(args) -> int:
    if getattr(args, "quiet", False):
        return -1
    if getattr(args, "verbose", False):
        return 1
    return 0
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add catalog/core/log.py tests/catalog/test_log.py
git commit -m "feat(catalog): shared logging with progress, summary and per-run log file

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Snapshot model and export reader

**Files:**
- Create: `catalog/shopify/__init__.py` (empty), `catalog/shopify/snapshot.py`, `catalog/shopify/export_reader.py`
- Test: `tests/catalog/test_snapshot.py`, `tests/catalog/test_export_reader.py`

**Interfaces:**
- Consumes: `SNAPSHOT_COLUMNS`, `GENRE_METAFIELD` (Task 2); `load_export`, `group_rows_by_handle` (Task 2); `InputShapeError` (Task 1).
- Produces:
  - `catalog.shopify.snapshot`: `blank_row() -> dict`, `exclusion_reason(row) -> str | None`, `filter_catalogue(rows) -> tuple[list[dict], dict[str, int]]`, `write_snapshot(path, rows)`, `load_snapshot(path) -> list[dict]`
  - `catalog.shopify.export_reader`: `read_export(path) -> list[dict]` (snapshot rows)

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_snapshot.py`:
```python
import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import SNAPSHOT_COLUMNS
from catalog.shopify.snapshot import (
    blank_row, exclusion_reason, filter_catalogue, load_snapshot, write_snapshot,
)


def row(**overrides):
    base = blank_row()
    base.update({"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Status": "active",
                 "Vendor": "VHS", "Tags": "Rental, VHS, Comedy"})
    base.update(overrides)
    return base


class TestSnapshot(unittest.TestCase):
    def test_blank_row_has_every_column(self):
        self.assertEqual(list(blank_row()), SNAPSHOT_COLUMNS)

    def test_movie_is_kept(self):
        self.assertIsNone(exclusion_reason(row()))

    def test_retail_template_excluded(self):
        self.assertEqual(exclusion_reason(row(**{"Template Suffix": "retail"})), "retail template")

    def test_archived_excluded(self):
        self.assertEqual(exclusion_reason(row(Status="archived")), "archived")

    def test_draft_kept(self):
        self.assertIsNone(exclusion_reason(row(Status="draft")))

    def test_membership_vendor_excluded(self):
        self.assertEqual(exclusion_reason(row(Vendor="Supercycle")), "membership plan")

    def test_online_store_tag_excluded_case_insensitively(self):
        self.assertEqual(exclusion_reason(row(Tags="Apparel, Online-Store")), "online-store item")

    def test_filter_counts_reasons(self):
        kept, excluded = filter_catalogue([row(), row(Status="archived"), row(Status="archived")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, {"archived": 2})

    def test_round_trip_keeps_leading_zero_barcode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            write_snapshot(path, [row(**{"Variant Barcode": "01577790", "Title": "Amélie"})])
            loaded = load_snapshot(path)
        self.assertEqual(loaded[0]["Variant Barcode"], "01577790")
        self.assertEqual(loaded[0]["Title"], "Amélie")


if __name__ == "__main__":
    unittest.main()
```

`tests/catalog/test_export_reader.py`:
```python
import csv
import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import InputShapeError
from catalog.shopify.export_reader import read_export

HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Option1 Name",
          "Option1 Value", "Variant Price", "Variant Barcode", "Variant Inventory Tracker",
          "Image Src", "Image Alt Text", GENRE_METAFIELD]


def write(path: Path, rows, header=HEADER):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in header})


def product(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>x</p>",
            "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
            "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0",
            "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
            "Image Src": "https://cdn/x.jpg", "Image Alt Text": "", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


class TestReadExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "export.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_row_per_product_with_extra_image_rows_folded(self):
        write(self.path, [product(), {"Handle": "rushmore-vhs-rental", "Image Src": "https://cdn/2.jpg"}])
        rows = read_export(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Image Src"], "https://cdn/x.jpg")
        self.assertEqual(rows[0]["Variant Count"], "1")

    def test_counts_real_variant_rows(self):
        write(self.path, [product(), {"Handle": "rushmore-vhs-rental", "Option1 Value": "Drama",
                                       "Variant Price": "0", "Variant Barcode": "01577791"}])
        self.assertEqual(read_export(self.path)[0]["Variant Count"], "2")

    def test_plural_barcode_header_is_accepted(self):
        header = [("Variant Barcodes" if c == "Variant Barcode" else c) for c in HEADER]
        r = product()
        r["Variant Barcodes"] = r.pop("Variant Barcode")
        write(self.path, [r], header)
        self.assertEqual(read_export(self.path)[0]["Variant Barcode"], "01577790")

    def test_status_lowercased_and_missing_columns_blank(self):
        write(self.path, [product(Status="Active")])
        r = read_export(self.path)[0]
        self.assertEqual(r["Status"], "active")
        self.assertEqual(r["Template Suffix"], "")

    def test_not_an_export_raises(self):
        write(self.path, [{"Title": "x"}], ["Title", "Format"])
        with self.assertRaises(InputShapeError):
            read_export(self.path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: `ModuleNotFoundError: No module named 'catalog.shopify'`.

- [ ] **Step 3: Implement**

`catalog/shopify/__init__.py`: empty file.

`catalog/shopify/snapshot.py`:
```python
"""The snapshot: one normalized row per catalogue movie (SNAPSHOT_COLUMNS).

Both readers (API and export CSV) produce these rows; filter_catalogue then
drops everything that is not a live movie.
"""

import json
from pathlib import Path

from catalog.core.columns import SNAPSHOT_COLUMNS


def blank_row() -> dict:
    return {column: "" for column in SNAPSHOT_COLUMNS}


def exclusion_reason(row: dict) -> str | None:
    """Why this product is not audited, or None for a catalogue movie."""
    if (row.get("Template Suffix") or "").strip().lower() == "retail":
        return "retail template"
    if (row.get("Status") or "").strip().lower() == "archived":
        return "archived"
    # Export-path fallbacks: an export CSV carries no template suffix.
    if (row.get("Vendor") or "").strip() == "Supercycle":
        return "membership plan"
    tags = [t.strip().lower() for t in (row.get("Tags") or "").split(",")]
    if "online-store" in tags:
        return "online-store item"
    return None


def filter_catalogue(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    kept: list[dict] = []
    excluded: dict[str, int] = {}
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            kept.append(row)
    return kept, excluded


def write_snapshot(path, rows: list[dict]) -> None:
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")


def load_snapshot(path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

`catalog/shopify/export_reader.py`:
```python
"""A Shopify product-export CSV -> snapshot rows (the audit's --from-export path)."""

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import group_rows_by_handle, load_export
from catalog.errors import InputShapeError
from catalog.shopify.snapshot import blank_row

REQUIRED_COLUMNS = ("Handle", "Title")
COPIED_COLUMNS = (
    "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Template Suffix", "Image Src",
    "Image Alt Text", "Option1 Name", "Option1 Value", "Variant Price", "Variant Barcode",
    "Variant Inventory Tracker", GENRE_METAFIELD,
)


def _is_variant_row(row: dict) -> bool:
    """A real variant row carries option, price or barcode data; image rows don't."""
    return any((row.get(c) or "").strip() for c in ("Option1 Value", "Variant Price", "Variant Barcode"))


def read_export(path) -> list[dict]:
    fieldnames, rows = load_export(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise InputShapeError(f"{path} is not a Shopify product export (missing {', '.join(missing)})")

    products = []
    for handle, group in group_rows_by_handle(rows):
        if not (handle or "").strip():
            continue
        primary = group[0]
        out = blank_row()
        out["Handle"] = handle.strip()
        for column in COPIED_COLUMNS:
            value = primary.get(column) or ""
            out[column] = value if column == "Body (HTML)" else value.strip()
        out["Status"] = out["Status"].lower()
        out["Variant Count"] = str(max(sum(1 for r in group if _is_variant_row(r)), 1))
        products.append(out)
    return products
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add catalog/shopify tests/catalog/test_snapshot.py tests/catalog/test_export_reader.py
git commit -m "feat(catalog): snapshot rows, catalogue filter and export-CSV reader

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Shopify API reader

**Files:**
- Create: `catalog/shopify/queries/products.graphql`, `catalog/shopify/reader.py`
- Test: `tests/catalog/test_reader.py`

**Interfaces:**
- Consumes: `blank_row` (Task 4), `ShopifyError` (Task 1), `log` (Task 3), `GENRE_METAFIELD`.
- Produces: `catalog.shopify.reader`: `QUERY_PATH: Path`, `run_cli_query(store, query_path, variables) -> dict`, `node_to_row(node) -> dict`, `read_products(store, execute=run_cli_query) -> list[dict]`.

Verified 2026-09-25 against the dev store: `shopify store execute -s <store> --json -q <query>` returns the GraphQL `data` object **unwrapped** (top-level key `products`), with status lines (`Loading stored store auth ...`) outside the JSON. The code below accepts both wrapped (`{"data": …}`) and unwrapped payloads and tolerates non-JSON noise around the object.

- [ ] **Step 1: Write the failing test**

`tests/catalog/test_reader.py`:
```python
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import ShopifyError
from catalog.shopify import reader
from catalog.shopify.reader import _parse_json_output, node_to_row, read_products


def node(**overrides):
    base = {
        "handle": "rushmore-vhs-rental", "title": "Rushmore", "descriptionHtml": "<p>x</p>",
        "vendor": "VHS", "tags": ["Rental", "VHS", "Comedy"], "status": "ACTIVE",
        "templateSuffix": None, "variantsCount": {"count": 1},
        "variants": {"nodes": [{"price": "0.00", "barcode": "01577790",
                                "selectedOptions": [{"name": "Genre", "value": "Comedy"}],
                                "inventoryItem": {"tracked": True}}]},
        "media": {"nodes": [{"image": {"url": "https://cdn.shopify.com/r.jpg", "altText": "Rushmore poster"}}]},
        "genre": {"references": {"nodes": [{"handle": "comedy"}, {"handle": "drama"}]}},
    }
    base.update(overrides)
    return base


def page(nodes, has_next, cursor=None):
    return {"products": {"pageInfo": {"hasNextPage": has_next, "endCursor": cursor}, "nodes": nodes}}


class TestNodeToRow(unittest.TestCase):
    def test_full_node(self):
        r = node_to_row(node())
        self.assertEqual(r["Handle"], "rushmore-vhs-rental")
        self.assertEqual(r["Tags"], "Rental, VHS, Comedy")
        self.assertEqual(r["Status"], "active")
        self.assertEqual(r["Template Suffix"], "")
        self.assertEqual(r["Option1 Name"], "Genre")
        self.assertEqual(r["Option1 Value"], "Comedy")
        self.assertEqual(r["Variant Price"], "0.00")
        self.assertEqual(r["Variant Barcode"], "01577790")
        self.assertEqual(r["Variant Inventory Tracker"], "shopify")
        self.assertEqual(r["Variant Count"], "1")
        self.assertEqual(r["Image Src"], "https://cdn.shopify.com/r.jpg")
        self.assertEqual(r["Image Alt Text"], "Rushmore poster")
        self.assertEqual(r[GENRE_METAFIELD], "comedy; drama")

    def test_node_with_nothing_optional(self):
        r = node_to_row(node(descriptionHtml=None, vendor=None, tags=[], templateSuffix="retail",
                             variantsCount={"count": 0}, variants={"nodes": []},
                             media={"nodes": [{}]},  # first media is a video: fragment yields {}
                             genre=None))
        self.assertEqual(r["Body (HTML)"], "")
        self.assertEqual(r["Template Suffix"], "retail")
        self.assertEqual(r["Variant Barcode"], "")
        self.assertEqual(r["Variant Inventory Tracker"], "")
        self.assertEqual(r["Image Src"], "")
        self.assertEqual(r[GENRE_METAFIELD], "")
        self.assertEqual(r["Variant Count"], "0")

    def test_untracked_and_null_barcode(self):
        n = node()
        n["variants"]["nodes"][0].update({"barcode": None, "inventoryItem": {"tracked": False}})
        r = node_to_row(n)
        self.assertEqual(r["Variant Barcode"], "")
        self.assertEqual(r["Variant Inventory Tracker"], "")


class TestReadProducts(unittest.TestCase):
    def test_paginates_until_done(self):
        calls = []

        def execute(store, query_path, variables):
            calls.append(variables["cursor"])
            if variables["cursor"] is None:
                return page([node(handle="a")], True, "c1")
            return {"data": page([node(handle="b")], False)}  # wrapped form also accepted

        rows = read_products("example.myshopify.com", execute=execute)
        self.assertEqual([r["Handle"] for r in rows], ["a", "b"])
        self.assertEqual(calls, [None, "c1"])

    def test_graphql_errors_raise(self):
        with self.assertRaises(ShopifyError):
            read_products("s", execute=lambda *a: {"errors": [{"message": "Throttled"}]})


class TestRunCliQuery(unittest.TestCase):
    def fake_run(self, returncode, stdout="", stderr=""):
        return mock.patch.object(reader.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr))

    def test_auth_failure_names_the_auth_command(self):
        with self.fake_run(1, stderr="Error: You are not logged in to this store"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("p0wkgv-wy.myshopify.com", reader.QUERY_PATH, {"cursor": None})
        self.assertIn("shopify store auth --store p0wkgv-wy.myshopify.com --scopes read_products", str(ctx.exception))

    def test_other_failure_raises_with_stderr(self):
        with self.fake_run(1, stderr="boom"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})
        self.assertIn("boom", str(ctx.exception))

    def test_missing_cli(self):
        with mock.patch.object(reader.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(ShopifyError):
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})

    def test_parses_stdout_with_status_noise(self):
        noisy = 'Loading stored store auth ...\nExecuting GraphQL operation ...\n{"products": {"nodes": []}}\n✨ New version available'
        self.assertEqual(_parse_json_output(noisy), {"products": {"nodes": []}})

    def test_query_file_exists_and_names_every_field(self):
        text = Path(reader.QUERY_PATH).read_text(encoding="utf-8")
        for field in ("handle", "descriptionHtml", "templateSuffix", "variantsCount", "barcode",
                      "tracked", "altText", 'namespace: "shopify", key: "genre"', "endCursor"):
            self.assertIn(field, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_reader.py"`
Expected: `ImportError` for `catalog.shopify.reader`.

- [ ] **Step 3: Write the query**

`catalog/shopify/queries/products.graphql` (page size 50 keeps query cost well under Shopify's per-query limit with 5 metaobject references per product):
```graphql
query CatalogProducts($cursor: String) {
  products(first: 50, after: $cursor, sortKey: ID) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      handle
      title
      descriptionHtml
      vendor
      tags
      status
      templateSuffix
      variantsCount {
        count
      }
      variants(first: 1) {
        nodes {
          price
          barcode
          selectedOptions {
            name
            value
          }
          inventoryItem {
            tracked
          }
        }
      }
      media(first: 1) {
        nodes {
          ... on MediaImage {
            image {
              url
              altText
            }
          }
        }
      }
      genre: metafield(namespace: "shopify", key: "genre") {
        references(first: 5) {
          nodes {
            ... on Metaobject {
              handle
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 4: Implement `catalog/shopify/reader.py`**

```python
"""Read every product through `shopify store execute` (read-only).

Only query operations are ever sent — never --allow-mutations — so the
pipeline cannot write to Shopify from here.
"""

import json
import subprocess
from pathlib import Path

from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import ShopifyError
from catalog.shopify.snapshot import blank_row

QUERY_PATH = Path(__file__).parent / "queries" / "products.graphql"
_AUTH_HINTS = ("auth", "log in", "logged in", "login", "unauthorized", "401", "403")


def _parse_json_output(text: str) -> dict:
    """The CLI prints status lines around the JSON; keep the outermost object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ShopifyError(f"no JSON in shopify CLI output: {text.strip()[:300]}")
    return json.loads(text[start:end + 1])


def run_cli_query(store: str, query_path: Path, variables: dict) -> dict:
    cmd = ["shopify", "store", "execute", "--store", store, "--json",
           "--query-file", str(query_path), "--variables", json.dumps(variables)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise ShopifyError("the `shopify` CLI is not installed or not on PATH") from None
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        if any(hint in message.lower() for hint in _AUTH_HINTS):
            raise ShopifyError(
                f"Shopify CLI is not authenticated for {store}. Run:\n"
                f"  shopify store auth --store {store} --scopes read_products\n({message})"
            )
        raise ShopifyError(f"shopify store execute failed for {store}: {message}")
    return _parse_json_output(proc.stdout)


def node_to_row(node: dict) -> dict:
    variants = (node.get("variants") or {}).get("nodes") or []
    variant = variants[0] if variants else {}
    options = variant.get("selectedOptions") or []
    option = options[0] if options else {}
    media = (node.get("media") or {}).get("nodes") or []
    image = (media[0].get("image") if media and media[0] else None) or {}
    references = (((node.get("genre") or {}).get("references")) or {}).get("nodes") or []

    row = blank_row()
    row.update({
        "Handle": node.get("handle") or "",
        "Title": node.get("title") or "",
        "Body (HTML)": node.get("descriptionHtml") or "",
        "Vendor": node.get("vendor") or "",
        "Tags": ", ".join(node.get("tags") or []),
        "Status": (node.get("status") or "").lower(),
        "Template Suffix": node.get("templateSuffix") or "",
        "Image Src": image.get("url") or "",
        "Image Alt Text": image.get("altText") or "",
        "Option1 Name": option.get("name") or "",
        "Option1 Value": option.get("value") or "",
        "Variant Price": variant.get("price") or "",
        "Variant Barcode": variant.get("barcode") or "",
        "Variant Inventory Tracker": "shopify" if (variant.get("inventoryItem") or {}).get("tracked") else "",
        "Variant Count": str(((node.get("variantsCount") or {}).get("count")) or 0),
        GENRE_METAFIELD: "; ".join(r["handle"] for r in references if r and r.get("handle")),
    })
    return row


def read_products(store: str, execute=run_cli_query) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    page_number = 0
    while True:
        page_number += 1
        payload = execute(store, QUERY_PATH, {"cursor": cursor})
        if payload.get("errors"):
            raise ShopifyError(f"GraphQL errors from {store}: {payload['errors']}")
        products = payload.get("data", payload)["products"]
        rows.extend(node_to_row(n) for n in products["nodes"])
        log.get_logger().info(f"[page {page_number}] {len(rows)} products read from {store}")
        if not products["pageInfo"]["hasNextPage"]:
            return rows
        cursor = products["pageInfo"]["endCursor"]
```

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK.

- [ ] **Step 6: Live smoke check against the DEV store (read-only)**

```bash
python3 -c "
from catalog.core import log
from catalog.shopify.reader import read_products
log.setup_logging()
rows = read_products('lms-sandbox-lutsfahz.myshopify.com')
print(len(rows)); print(rows[0])
"
```
Expected: page progress lines, a product count in the thousands, and a first row with every snapshot key. If the CLI reports an auth error, stop and ask the user to run `shopify store auth --store lms-sandbox-lutsfahz.myshopify.com --scopes read_products`. Note: the Shopify CLI may self-upgrade on first run (observed 2026-09-25); that is the CLI's behaviour, not this code's.

- [ ] **Step 7: Commit**

```bash
git add catalog/shopify tests/catalog/test_reader.py
git commit -m "feat(catalog): read-only Shopify product reader via shopify store execute

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: TMDB — matcher, client, cache

**Files:**
- Create: `catalog/tmdb/__init__.py` (empty), `catalog/tmdb/match.py` (from `formatting-scripts/tmdb_fill.py` lines 18–369 + new code), `catalog/tmdb/client.py`, `catalog/tmdb/cache.py`
- Test: `tests/catalog/test_match.py` (ported lines 15–196 of `tests/formatting_scripts/test_tmdb_fill.py` + new), `tests/catalog/test_cache.py` (ported + new), `tests/catalog/test_client.py`

**Interfaces:**
- Consumes: `GENRE_METAFIELD` (Task 2), `strip_html` (Task 1).
- Produces:
  - `catalog.tmdb.match`: everything the old module had above `strip_html` (`POSTER_BASE_URL`, `REQUEST_DELAY_SECONDS`, `VHS_YEAR_CUTOFF`, `GLOBAL_YEAR_CUTOFF`, `clean_title_and_year`, `title_similarity`, `genre_matches`, `search_tmdb`, `is_vhs`, `filter_by_year_cutoff`, `classify_match`, …) plus `MatchResult(kind, best, reason)`, `match_product(row, fetch_fn) -> MatchResult`, `poster_url(best) -> str`, `alt_text_for(title, best) -> str`
  - `catalog.tmdb.client`: `TMDB_SEARCH_URL`, `make_fetcher(api_key, sleep_fn=time.sleep, urlopen=urllib.request.urlopen) -> fetch(query, year) -> dict`
  - `catalog.tmdb.cache`: `TmdbCache(path, save_every=50)` with `.wrap(fetch_fn)`, `.save()`, `.hits`, `.misses`

- [ ] **Step 1: Port the matcher tests and add the new ones (failing)**

```bash
mkdir -p catalog/tmdb && touch catalog/tmdb/__init__.py
{ cat <<'EOF'
import unittest

from catalog.tmdb.match import (
    POSTER_BASE_URL,
    MatchResult,
    alt_text_for,
    classify_match,
    clean_title_and_year,
    match_product,
    poster_url,
)
EOF
sed -n '15,196p' tests/formatting_scripts/test_tmdb_fill.py
} > tests/catalog/test_match.py
```
Lines 15–196 are the helper functions (`result`, `row`, `fetcher`), `TestPosterBase` and `TestClassifyMatch`; `TestBuildOutput` (197+) is intentionally dropped — `build_output` no longer exists; `match_product` replaces its per-product logic and is covered below.

Append to `tests/catalog/test_match.py`:
```python


class TestMatchProduct(unittest.TestCase):
    def test_confident_single_match(self):
        m = match_product(row(), fetcher([result("Rushmore", "1998", genre_ids=[35])]))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(poster_url(m.best), f"{POSTER_BASE_URL}/p.jpg")

    def test_no_results_is_none(self):
        m = match_product(row(), fetcher([]))
        self.assertEqual((m.kind, m.reason), ("none", "no TMDB match"))

    def test_tie_is_ambiguous_and_names_best(self):
        tied = [result("Mandela", "1996", popularity=5), result("Mandela", "1987", popularity=5)]
        m = match_product(row(Title="Mandela", **{"Genre (product.metafields.shopify.genre)": ""}), fetcher(tied))
        self.assertEqual(m.kind, "ambiguous")
        self.assertIn("Mandela", m.reason)

    def test_request_failure_is_error_not_none(self):
        def boom(query, year):
            raise OSError("network down")
        m = match_product(row(), boom)
        self.assertEqual(m.kind, "error")
        self.assertIn("network down", m.reason)

    def test_vhs_year_cutoff_breaks_a_remake_tie(self):
        # A same-titled 2014 remake ties the 1987 original on title; VHS rows drop post-2008 candidates.
        tied = [result("RoboCop", "1987", popularity=5), result("RoboCop", "2014", popularity=5)]
        m = match_product(row(Title="RoboCop", Vendor="VHS", **{"Genre (product.metafields.shopify.genre)": ""}),
                          fetcher(tied))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(m.best["release_date"][:4], "1987")

    def test_description_breaks_a_tie(self):
        tied = [result("Rear Window", "1954", overview="A photographer in a wheelchair spies on his neighbors and suspects murder.", popularity=5),
                result("Rear Window", "1998", overview="A paralysed architect remake set in a modern apartment.", popularity=5)]
        body = "<p>Laid up with a broken leg, a photographer spies on his neighbors and becomes convinced of a murder.</p>"
        m = match_product(row(Title="Rear Window", **{"Body (HTML)": body, "Genre (product.metafields.shopify.genre)": ""}),
                          fetcher(tied))
        self.assertEqual(m.kind, "confident")
        self.assertEqual(m.best["release_date"][:4], "1954")

    def test_alt_text_uses_match_year(self):
        self.assertEqual(alt_text_for("Rushmore (Special Edition)", {"release_date": "1998-12-11"}), "Rushmore (1998) poster")
        self.assertEqual(alt_text_for("Rushmore", {"release_date": ""}), "Rushmore poster")

    def test_poster_url_blank_without_path(self):
        self.assertEqual(poster_url({"poster_path": ""}), "")
        self.assertEqual(poster_url(None), "")


if __name__ == "__main__":
    unittest.main()
```

Port the cache tests and add new ones:
```bash
sed -e '/sys.path.insert(0, str(.*formatting-scripts/d' \
    -e 's/^from tmdb_cache import TmdbCache/from catalog.tmdb.cache import TmdbCache/' \
    tests/formatting_scripts/test_tmdb_cache.py > tests/catalog/test_cache.py
```
Then insert this class into `tests/catalog/test_cache.py` just above its `if __name__ == "__main__":` block:
```python
class TestPeriodicSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "runs" / ".tmdb-cache.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_saves_every_n_misses(self):
        cache = TmdbCache(self.path, save_every=2)
        fetch = cache.wrap(lambda q, y: {"results": [q]})
        fetch("a", None)
        self.assertFalse(self.path.exists())
        fetch("b", None)  # second miss -> saved, so an interrupt now keeps a and b
        self.assertEqual(set(json.loads(self.path.read_text(encoding="utf-8"))), {"a|", "b|"})

    def test_hits_do_not_trigger_saves(self):
        cache = TmdbCache(self.path, save_every=1)
        fetch = cache.wrap(lambda q, y: {"results": []})
        fetch("a", None)
        self.path.unlink()
        fetch("a", None)
        self.assertFalse(self.path.exists())

    def test_save_leaves_no_temp_file(self):
        cache = TmdbCache(self.path)
        cache.wrap(lambda q, y: {"results": []})("a", 1999)
        cache.save()
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [".tmdb-cache.json"])
```

`tests/catalog/test_client.py`:
```python
import io
import json
import unittest
from urllib.parse import parse_qs, urlparse

from catalog.tmdb.client import make_fetcher


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestClient(unittest.TestCase):
    def test_builds_query_and_sleeps_after_each_request(self):
        seen, sleeps = [], []

        def urlopen(url, timeout):
            seen.append(url)
            return FakeResponse(json.dumps({"results": [1]}).encode())

        fetch = make_fetcher("KEY", sleep_fn=sleeps.append, urlopen=urlopen)
        self.assertEqual(fetch("Rushmore", 1998), {"results": [1]})
        params = parse_qs(urlparse(seen[0]).query)
        self.assertEqual(params["query"], ["Rushmore"])
        self.assertEqual(params["primary_release_year"], ["1998"])
        self.assertEqual(params["api_key"], ["KEY"])
        self.assertEqual(len(sleeps), 1)

    def test_no_year_param_when_year_is_none(self):
        seen = []
        fetch = make_fetcher("KEY", sleep_fn=lambda s: None,
                             urlopen=lambda url, timeout: seen.append(url) or FakeResponse(b'{"results": []}'))
        fetch("Rushmore", None)
        self.assertNotIn("primary_release_year", seen[0])

    def test_sleeps_even_when_request_fails(self):
        sleeps = []

        def urlopen(url, timeout):
            raise OSError("down")

        fetch = make_fetcher("KEY", sleep_fn=sleeps.append, urlopen=urlopen)
        with self.assertRaises(OSError):
            fetch("Rushmore", None)
        self.assertEqual(len(sleeps), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: import errors for `catalog.tmdb.match`, `catalog.tmdb.cache`, `catalog.tmdb.client`.

- [ ] **Step 3: Build `catalog/tmdb/match.py`**

Lines 18–369 of `formatting-scripts/tmdb_fill.py` are the constants and pure matching functions (from `POSTER_BASE_URL` through the end of `classify_match`); lines 1–17 are its docstring, imports and `TMDB_SEARCH_URL` (which moves to `client.py`); lines 370+ are `strip_html`, `needs_*`, `build_output`, the fetcher and `print_progress`, all replaced.

```bash
{ cat <<'EOF'
"""TMDB matching: clean a title, search, and decide confident / ambiguous / none.

Moved from formatting-scripts/tmdb_fill.py. The matching rules are
unchanged; match_product replaces build_output's per-product logic.
"""

import difflib
import re
from dataclasses import dataclass

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.text import strip_html

EOF
sed -n '18,369p' formatting-scripts/tmdb_fill.py
cat <<'EOF'

@dataclass(frozen=True)
class MatchResult:
    kind: str  # "confident" | "ambiguous" | "none" | "error"
    best: dict | None
    reason: str


def match_product(row: dict, fetch_fn) -> MatchResult:
    """Search TMDB for one snapshot row and classify the result: classify_match,
    then the format-aware year-cutoff retry when the title carried no year.
    The product's own description is the overview tiebreak hint."""
    title = (row.get("Title") or "").strip() or row.get("Handle", "")
    clean_title, year = clean_title_and_year(title)
    genre = row.get(GENRE_METAFIELD, "") or ""
    overview_hint = strip_html(row.get("Body (HTML)", ""))

    try:
        results = search_tmdb(fetch_fn, clean_title, year)
    except Exception as exc:  # network, HTTP or JSON failure: never cached, retried next audit
        return MatchResult("error", None, f"TMDB request failed: {exc}")

    best, kind = classify_match(clean_title, year, results, genre, overview_hint)
    if year is None and kind == "ambiguous":
        cutoff = VHS_YEAR_CUTOFF if is_vhs(row.get("Vendor", "")) else GLOBAL_YEAR_CUTOFF
        filtered = filter_by_year_cutoff(results, cutoff)
        if filtered and filtered != results:
            filtered_best, filtered_kind = classify_match(clean_title, year, filtered, genre, overview_hint)
            if filtered_kind == "confident":
                best, kind = filtered_best, filtered_kind

    if kind == "none":
        return MatchResult("none", None, "no TMDB match")
    if kind == "ambiguous":
        best_year = (best.get("release_date") or "")[:4] or "?"
        return MatchResult("ambiguous", best,
                           f"ambiguous match (best candidate: '{best.get('title', '?')}' ({best_year}))")
    return MatchResult("confident", best, "confident TMDB match")


def poster_url(best: dict | None) -> str:
    path = ((best or {}).get("poster_path") or "").strip()
    return f"{POSTER_BASE_URL}{path}" if path else ""


def alt_text_for(title: str, best: dict | None) -> str:
    clean_title, _ = clean_title_and_year(title)
    year = ((best or {}).get("release_date") or "")[:4]
    return f"{clean_title} ({year}) poster" if year else f"{clean_title} poster"
EOF
} > catalog/tmdb/match.py
sed -n '14,20p' catalog/tmdb/match.py   # should show POSTER_BASE_URL right after the imports
grep -n "import time\|import json\|urllib\|group_rows_by_handle" catalog/tmdb/match.py  # expect no output
```

- [ ] **Step 4: Write `catalog/tmdb/client.py`**

```python
"""The real, network-hitting TMDB search fetcher. Sleeps after every request
(hit the API politely); cache hits never reach it, so they never sleep."""

import json
import time
import urllib.parse
import urllib.request

from catalog.tmdb.match import REQUEST_DELAY_SECONDS

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"


def make_fetcher(api_key: str, sleep_fn=time.sleep, urlopen=urllib.request.urlopen):
    def fetch(query: str, year: int | None) -> dict:
        params = {"api_key": api_key, "query": query}
        if year is not None:
            params["primary_release_year"] = year
        url = f"{TMDB_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        finally:
            sleep_fn(REQUEST_DELAY_SECONDS)

    return fetch
```

- [ ] **Step 5: Write `catalog/tmdb/cache.py`**

```python
"""On-disk cache of TMDB search responses, keyed by query + year, shared by
every run (runs/.tmdb-cache.json).

Saved every `save_every` new fetches and atomically (temp file + rename), so
an interrupted audit keeps its work and a crash mid-write never corrupts the
file. Failed requests are never cached — a network blip must not become a
permanent "no match".
"""

import json
from pathlib import Path


class TmdbCache:
    def __init__(self, path, save_every: int = 50):
        self.path = Path(path)
        self.save_every = save_every
        self.hits = 0
        self.misses = 0
        self._entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._entries = loaded
            except (json.JSONDecodeError, OSError):
                self._entries = {}

    @staticmethod
    def _key(query: str, year: int | None) -> str:
        return f"{(query or '').strip().lower()}|{year if year is not None else ''}"

    def wrap(self, fetch_fn):
        def cached_fetch(query: str, year: int | None) -> dict:
            key = self._key(query, year)
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            data = fetch_fn(query, year)
            self._entries[key] = data
            self.misses += 1
            if self.save_every and self.misses % self.save_every == 0:
                self.save()
            return data

        return cached_fetch

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._entries), encoding="utf-8")
        tmp.replace(self.path)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK. If `test_vhs_year_cutoff_breaks_a_remake_tie` or `test_description_breaks_a_tie` fails, print `classify_match(...)` for that input before changing anything — these pin the ported behaviour plus the overview-hint change (decision 6); do not tune thresholds to make them pass.

- [ ] **Step 7: Commit**

```bash
git add catalog/tmdb tests/catalog/test_match.py tests/catalog/test_cache.py tests/catalog/test_client.py
git commit -m "feat(catalog): TMDB matcher, fetcher and shared cache with periodic atomic saves

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Registry in core, with applied / skipped / promotion

**Files:**
- Create: `catalog/core/registry.py`
- Test: `tests/catalog/test_registry.py` (ported `tests/formatting_scripts/test_review_registry.py` + new)

**Interfaces:**
- Consumes: `norm_ws`, `strip_html` (Task 1).
- Produces: `catalog.core.registry`: `REGISTRY_FILENAME`, `registry_path(picker_dir) -> Path`, `load_registry(picker_dir) -> dict`, `save_registry(picker_dir, registry)`, `is_known(registry, handle) -> bool`, `filter_unknown(rows, registry) -> list[dict]`, `mark_queued(registry, handles, batch_id)`, `mark_applied(registry, handle, run_id, values: dict)`, `mark_skipped(registry, handle)`, `mark_resolved(registry, handles)`, `fix_visible(row, field, value) -> bool`, `promote_applied(registry, rows_by_handle) -> tuple[list[str], list[str]]` (resolved, still_missing — only handles present in `rows_by_handle`).

- [ ] **Step 1: Port tests and add new ones (failing)**

```bash
sed -e '/sys.path.insert(0, str(.*formatting-scripts/d' \
    -e 's/^from review_registry import (/from catalog.core.registry import (/' \
    tests/formatting_scripts/test_review_registry.py > tests/catalog/test_registry.py
```
Insert above the final `if __name__ == "__main__":` block of `tests/catalog/test_registry.py`:
```python
from catalog.core.registry import fix_visible, mark_applied, mark_skipped, promote_applied


class TestLifecycle(unittest.TestCase):
    def test_applied_records_run_and_values(self):
        registry = {"a": {"batch": "ambiguous-queue", "status": "queued"}}
        mark_applied(registry, "a", "2026-09-25", {"Image Src": "https://img/x.jpg"})
        self.assertEqual(registry["a"]["status"], "applied")
        self.assertEqual(registry["a"]["run"], "2026-09-25")
        self.assertEqual(registry["a"]["values"], {"Image Src": "https://img/x.jpg"})
        self.assertEqual(registry["a"]["batch"], "ambiguous-queue")

    def test_skipped(self):
        registry = {"a": {"batch": "q", "status": "queued"}}
        mark_skipped(registry, "a")
        self.assertEqual(registry["a"]["status"], "skipped")

    def test_image_src_counts_as_visible_when_rehosted(self):
        self.assertTrue(fix_visible({"Image Src": "https://cdn.shopify.com/files/x.jpg"},
                                    "Image Src", "https://image.tmdb.org/t/p/w1280/x.jpg"))
        self.assertFalse(fix_visible({"Image Src": ""}, "Image Src", "https://image.tmdb.org/x.jpg"))

    def test_description_compared_as_text(self):
        self.assertTrue(fix_visible({"Body (HTML)": "<p>A  film.</p>\n"}, "Body (HTML)", "<p>A film.</p>"))
        self.assertFalse(fix_visible({"Body (HTML)": ""}, "Body (HTML)", "<p>A film.</p>"))

    def test_other_fields_compared_exactly(self):
        self.assertTrue(fix_visible({"Vendor": "VHS"}, "Vendor", "VHS"))
        self.assertFalse(fix_visible({"Vendor": "vhs"}, "Vendor", "VHS"))

    def test_promote_applied(self):
        registry = {
            "done": {"status": "applied", "run": "r", "values": {"Image Src": "u"}},
            "pending": {"status": "applied", "run": "r", "values": {"Body (HTML)": "<p>x</p>"}},
            "gone": {"status": "applied", "run": "r", "values": {"Image Src": "u"}},
            "queued": {"status": "queued", "batch": "q"},
        }
        rows = {"done": {"Image Src": "https://cdn/1.jpg"}, "pending": {"Body (HTML)": ""},
                "queued": {"Image Src": ""}}
        resolved, missing = promote_applied(registry, rows)
        self.assertEqual(resolved, ["done"])
        self.assertEqual(missing, ["pending"])  # "gone" is not in the snapshot: left alone
        self.assertEqual(registry["done"]["status"], "resolved")
        self.assertEqual(registry["gone"]["status"], "applied")
        self.assertEqual(registry["queued"]["status"], "queued")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_registry.py"`
Expected: `ModuleNotFoundError: No module named 'catalog.core.registry'`.

- [ ] **Step 3: Implement `catalog/core/registry.py`**

```python
"""Which handles the review picker already knows about.

One JSON file, <picker_dir>/data/_handle-index.json:

    {"<handle>": {"batch": "ambiguous-queue", "status": "queued"}, ...}

status: queued   — a card is in a picker queue, no decision applied yet
        applied  — apply wrote an import CSV; `run` and `values` record what
        resolved — a later audit saw those values in Shopify
        skipped  — the client chose "none of these match"
Every status blocks re-queuing. Files written by the old pipeline hold only
queued/resolved and load unchanged. Lives in core/ because audit, picker
push and apply all read it.
"""

import json
from pathlib import Path

from catalog.core.text import norm_ws, strip_html

REGISTRY_FILENAME = "_handle-index.json"


def registry_path(picker_dir) -> Path:
    return Path(picker_dir) / "data" / REGISTRY_FILENAME


def load_registry(picker_dir) -> dict:
    path = registry_path(picker_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(picker_dir, registry: dict) -> None:
    path = registry_path(picker_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def is_known(registry: dict, handle: str) -> bool:
    return handle in registry


def filter_unknown(rows: list[dict], registry: dict) -> list[dict]:
    return [row for row in rows if not is_known(registry, row["Handle"])]


def mark_queued(registry: dict, handles, batch_id: str) -> None:
    for handle in handles:
        registry[handle] = {"batch": batch_id, "status": "queued"}


def mark_applied(registry: dict, handle: str, run_id: str, values: dict) -> None:
    entry = registry.setdefault(handle, {})
    entry.update({"status": "applied", "run": run_id, "values": dict(values)})


def mark_skipped(registry: dict, handle: str) -> None:
    registry.setdefault(handle, {})["status"] = "skipped"


def mark_resolved(registry: dict, handles) -> None:
    for handle in handles:
        registry.setdefault(handle, {})["status"] = "resolved"


def fix_visible(row: dict, field: str, value: str) -> bool:
    """Does the snapshot row show a value we applied?"""
    current = row.get(field) or ""
    if field == "Image Src":
        # Shopify re-hosts an imported image on its own CDN, so the URL changes.
        return bool(current.strip())
    if field == "Body (HTML)":
        return norm_ws(strip_html(current)) == norm_ws(strip_html(value))
    return current.strip() == (value or "").strip()


def promote_applied(registry: dict, rows_by_handle: dict) -> tuple[list[str], list[str]]:
    """applied -> resolved where every recorded value is visible. Handles not
    in the snapshot (deleted/archived products) are left untouched."""
    resolved, missing = [], []
    for handle, entry in registry.items():
        if entry.get("status") != "applied" or handle not in rows_by_handle:
            continue
        row = rows_by_handle[handle]
        if all(fix_visible(row, f, v) for f, v in (entry.get("values") or {}).items()):
            entry["status"] = "resolved"
            resolved.append(handle)
        else:
            missing.append(handle)
    return resolved, missing
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK (ported tests unchanged in behaviour).

- [ ] **Step 5: Commit**

```bash
git add catalog/core/registry.py tests/catalog/test_registry.py
git commit -m "feat(catalog): review registry in core with applied/skipped/resolved lifecycle

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Resolvers and per-product rules

**Files:**
- Create: `catalog/audit/__init__.py` (empty), `catalog/audit/resolvers.py` (copied from `formatting-scripts/resolve.py`), `catalog/audit/findings.py`, `catalog/audit/rules.py`
- Test: `tests/catalog/test_resolvers.py` (ported), `tests/catalog/test_rules.py`

**Interfaces:**
- Consumes: taxonomy, columns (Task 2), `strip_html` (Task 1).
- Produces:
  - `catalog.audit.resolvers`: `split_list`, `dedupe`, `resolve_type`, `resolve_genres`, `resolve_format`, `resolve_price`, `extra_tags` (same signatures as the originals; `_dedupe` renamed `dedupe`)
  - `catalog.audit.findings`: `AUTO_FIX = "auto-fix"`, `PICKER = "picker"`, `MANUAL = "manual"`, `FINDING_COLUMNS`, `Finding` (frozen dataclass: `handle, title, type, rule, field, current_value, proposed_value, bucket, detail=""`, method `as_row() -> dict`)
  - `catalog.audit.rules`: `RENTAL_BARCODE` (regex), `Resolved` dataclass (`tags, type, type_reason, format, genres`), `resolve_row(row) -> Resolved`, `canonical_tags(r) -> str`, `needs_poster(row) -> bool`, `needs_description(row) -> bool`, `is_multi_variant(row) -> bool`, `check_row(row) -> list[Finding]`, `check_catalogue(rows) -> list[Finding]`

- [ ] **Step 1: Copy the resolvers and port their test**

```bash
mkdir -p catalog/audit && touch catalog/audit/__init__.py
sed -e 's/^from columns import FORMATTED_TAG/from catalog.core.columns import FORMATTED_TAG/' \
    -e 's/^from taxonomy import/from catalog.core.taxonomy import/' \
    -e 's/_dedupe/dedupe/g' \
    formatting-scripts/resolve.py > catalog/audit/resolvers.py
sed -e '/sys.path.insert(0, str(.*formatting-scripts/d' \
    -e 's/^from resolve import (/from catalog.audit.resolvers import (/' \
    tests/formatting_scripts/test_resolve.py > tests/catalog/test_resolvers.py
python3 -m unittest discover -s tests/catalog -p "test_resolvers.py" 2>&1 | tail -2
```
Expected: `OK`.

- [ ] **Step 2: Write the failing rules test**

`tests/catalog/test_rules.py`:
```python
import unittest

from catalog.audit.findings import AUTO_FIX, MANUAL
from catalog.audit.rules import canonical_tags, check_catalogue, check_row, resolve_row
from catalog.core.columns import GENRE_METAFIELD
from catalog.shopify.snapshot import blank_row


def movie(**overrides):
    base = blank_row()
    base.update({
        "Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
        "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
        "Image Src": "https://cdn/r.jpg", "Image Alt Text": "Rushmore poster",
        "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0.00",
        "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
        "Variant Count": "1", GENRE_METAFIELD: "comedy",
    })
    base.update(overrides)
    return base


def floor_sale(**overrides):
    base = {"Handle": "heat-dvd-floor-sale", "Title": "Heat", "Vendor": "DVD",
            "Tags": "Floor Sale, DVD, Action", "Option1 Value": "Action", "Variant Price": "9.99",
            "Variant Barcode": "", GENRE_METAFIELD: "action"}
    base.update(overrides)
    return movie(**base)


def by_rule(findings):
    return {(f.rule, f.field): f for f in findings}


class TestCleanProduct(unittest.TestCase):
    def test_clean_rental_has_no_findings(self):
        self.assertEqual(check_row(movie()), [])

    def test_clean_floor_sale_has_no_findings(self):
        self.assertEqual(check_row(floor_sale()), [])


class TestAutoFixRules(unittest.TestCase):
    def test_misspelt_genre_everywhere(self):
        f = by_rule(check_row(movie(Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor", GENRE_METAFIELD: ""})))
        self.assertEqual(f[("genre-alias", "Tags")].proposed_value, "Rental, VHS, Horror")
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Horror")
        self.assertEqual(f[("genre-metafield-sync", GENRE_METAFIELD)].proposed_value, "horror")
        self.assertTrue(all(x.bucket == AUTO_FIX for x in f.values()))

    def test_misspelt_type_tag(self):
        f = by_rule(check_row(floor_sale(Tags="floorsale, DVD, Action")))
        self.assertEqual(f[("type-alias", "Tags")].proposed_value, "Floor Sale, DVD, Action")

    def test_vendor_alias(self):
        f = by_rule(check_row(movie(Vendor="bluray", Tags="Rental, Blu-Ray, Comedy")))
        self.assertEqual(f[("format-alias", "Vendor")].proposed_value, "Blu-Ray")

    def test_format_tag_alias_keeps_formatted_last_and_curation_tags(self):
        f = by_rule(check_row(movie(Tags="Rental, vhs, Comedy, Formatted, Staff Picks")))
        self.assertEqual(f[("format-alias", "Tags")].proposed_value,
                         "Rental, VHS, Comedy, Staff Picks, Formatted")

    def test_formatted_is_never_added(self):
        self.assertNotIn("Formatted", canonical_tags(resolve_row(movie(Tags="Rental, vhs, Comedy"))))

    def test_metafield_order_does_not_matter(self):
        self.assertEqual(check_row(movie(Tags="Rental, VHS, Comedy, Drama", **{GENRE_METAFIELD: "drama; comedy"})), [])

    def test_default_title_option_gets_genre(self):
        f = by_rule(check_row(movie(**{"Option1 Name": "Title", "Option1 Value": "Default Title"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Comedy")
        self.assertEqual(f[("option1-genre", "Option1 Name")].proposed_value, "Genre")

    def test_compound_option1(self):
        f = by_rule(check_row(movie(Vendor="4K", Tags="Rental, 4K, Action",
                                    **{"Option1 Value": "4K, Action", GENRE_METAFIELD: "action"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Action")

    def test_alt_text_missing(self):
        f = by_rule(check_row(movie(**{"Image Alt Text": ""})))
        self.assertEqual(f[("alt-text-missing", "Image Alt Text")].proposed_value, "Rushmore poster")

    def test_no_alt_text_rule_without_image(self):
        self.assertNotIn(("alt-text-missing", "Image Alt Text"),
                         by_rule(check_row(movie(**{"Image Src": "", "Image Alt Text": ""}))))

    def test_rental_blank_price(self):
        f = by_rule(check_row(movie(**{"Variant Price": ""})))
        self.assertEqual(f[("rental-price-blank", "Variant Price")].proposed_value, "0")
        self.assertEqual(f[("rental-price-blank", "Variant Price")].bucket, AUTO_FIX)


class TestManualRules(unittest.TestCase):
    def test_type_missing_skips_price_and_barcode_rules(self):
        rules = {f.rule for f in check_row(movie(Tags="VHS, Comedy", **{"Variant Price": "4.99", "Variant Barcode": ""}))}
        self.assertIn("type-missing", rules)
        self.assertFalse(rules & {"rental-price-nonzero", "rental-barcode-missing"})

    def test_type_conflict(self):
        self.assertIn("type-conflict", {f.rule for f in check_row(movie(Tags="Rental, Floor Sale, VHS, Comedy"))})

    def test_format_missing(self):
        self.assertIn("format-missing", {f.rule for f in check_row(movie(Vendor="", Tags="Rental, Comedy"))})

    def test_genre_missing_has_no_genre_autofixes(self):
        rules = {f.rule for f in check_row(movie(Tags="Rental, VHS", **{"Option1 Value": "Default Title", GENRE_METAFIELD: ""}))}
        self.assertIn("genre-missing", rules)
        self.assertFalse(rules & {"option1-genre", "genre-metafield-sync"})

    def test_floor_sale_prices(self):
        for price in ("", "0", "0.00", "-3"):
            with self.subTest(price=price):
                self.assertIn("floor-sale-price", {f.rule for f in check_row(floor_sale(**{"Variant Price": price}))})

    def test_price_unreadable(self):
        self.assertIn("price-unreadable", {f.rule for f in check_row(floor_sale(**{"Variant Price": "abc"}))})

    def test_rental_price_nonzero(self):
        self.assertIn("rental-price-nonzero", {f.rule for f in check_row(movie(**{"Variant Price": "4.99"}))})

    def test_inventory_untracked(self):
        f = by_rule(check_row(movie(**{"Variant Inventory Tracker": ""})))
        self.assertEqual(f[("inventory-untracked", "Variant Inventory Tracker")].bucket, MANUAL)

    def test_rental_barcode_missing(self):
        self.assertIn("rental-barcode-missing", {f.rule for f in check_row(movie(**{"Variant Barcode": ""}))})

    def test_rental_barcode_seven_digits(self):
        self.assertIn("rental-barcode-format", {f.rule for f in check_row(movie(**{"Variant Barcode": "1577790"}))})

    def test_rental_barcode_with_letter(self):
        self.assertIn("rental-barcode-format", {f.rule for f in check_row(movie(**{"Variant Barcode": "0157779A"}))})

    def test_rental_barcode_whitespace_is_tolerated(self):
        self.assertEqual(check_row(movie(**{"Variant Barcode": " 01577790 "})), [])

    def test_floor_sale_barcode_has_no_rules(self):
        self.assertEqual(check_row(floor_sale(**{"Variant Barcode": "abc"})), [])

    def test_multi_variant_gets_no_autofix(self):
        findings = check_row(movie(Tags="Rental, VHS, Horor", **{"Variant Count": "2", "Image Alt Text": ""}))
        self.assertIn("multiple-variants", {f.rule for f in findings})
        self.assertFalse([f for f in findings if f.bucket == AUTO_FIX])


class TestCatalogueRules(unittest.TestCase):
    def test_rental_sharing_with_floor_sale_is_flagged_on_the_rental_only(self):
        findings = check_catalogue([movie(), floor_sale(**{"Variant Barcode": "01577790"})])
        self.assertEqual([(f.handle, f.rule) for f in findings], [("rushmore-vhs-rental", "rental-barcode-duplicate")])
        self.assertIn("heat-dvd-floor-sale", findings[0].detail)

    def test_two_rentals_flag_each_other(self):
        findings = check_catalogue([movie(), movie(Handle="rushmore-vhs-rental-2")])
        self.assertEqual(sorted(f.handle for f in findings), ["rushmore-vhs-rental", "rushmore-vhs-rental-2"])

    def test_floor_sales_may_share(self):
        self.assertEqual(check_catalogue([floor_sale(**{"Variant Barcode": "1"}),
                                          floor_sale(Handle="b", **{"Variant Barcode": "1"})]), [])

    def test_duplicate_ignores_surrounding_whitespace(self):
        findings = check_catalogue([movie(), floor_sale(**{"Variant Barcode": " 01577790"})])
        self.assertEqual(len(findings), 1)

    def test_blank_barcodes_are_not_duplicates(self):
        self.assertEqual(check_catalogue([movie(**{"Variant Barcode": ""}),
                                          movie(Handle="x", **{"Variant Barcode": ""})]), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rules.py"`
Expected: `ModuleNotFoundError: No module named 'catalog.audit.findings'`.

- [ ] **Step 4: Write `catalog/audit/findings.py`**

```python
"""One audit finding = one problem with one field of one product."""

from dataclasses import asdict, dataclass

AUTO_FIX = "auto-fix"
PICKER = "picker"
MANUAL = "manual"

FINDING_COLUMNS = ["handle", "title", "type", "rule", "field", "current_value",
                   "proposed_value", "bucket", "detail"]


@dataclass(frozen=True)
class Finding:
    handle: str
    title: str
    type: str
    rule: str
    field: str
    current_value: str
    proposed_value: str
    bucket: str
    detail: str = ""

    def as_row(self) -> dict:
        return asdict(self)
```

- [ ] **Step 5: Write `catalog/audit/rules.py`**

```python
"""Audit rules. Pure: snapshot rows in, Findings out.

check_row covers one product; check_catalogue covers rules that need the
whole catalogue (rental barcode uniqueness). Content (poster/description)
and registry rules live in audit/run.py because they need TMDB and state.
"""

import re
from dataclasses import dataclass

from catalog.audit.findings import AUTO_FIX, MANUAL, Finding
from catalog.audit.resolvers import (
    dedupe, extra_tags, resolve_format, resolve_genres, resolve_price, resolve_type, split_list,
)
from catalog.core.columns import FORMATTED_TAG, GENRE_METAFIELD
from catalog.core.taxonomy import canonical_format, canonical_genre, canonical_type, genre_handle
from catalog.core.text import strip_html

RENTAL_BARCODE = re.compile(r"^[0-9]{8}$")
_TAG_ALIAS_RULES = (("type-alias", canonical_type), ("format-alias", canonical_format),
                    ("genre-alias", canonical_genre))


@dataclass
class Resolved:
    tags: list[str]
    type: str | None
    type_reason: str | None
    format: str | None
    genres: list[str]


def resolve_row(row: dict) -> Resolved:
    tags = split_list(row.get("Tags", ""))
    option1 = (row.get("Option1 Value") or "").strip()
    product_type, type_reason = resolve_type(tags)
    media_format, _ = resolve_format(row.get("Vendor", ""), option1, tags, "")
    genres, _ = resolve_genres(option1, tags, [])
    return Resolved(tags, product_type, type_reason, media_format, genres)


def canonical_tags(r: Resolved) -> str:
    """Type, format, genres, then curation tags, spelled canonically. Keeps
    Formatted (last) if present; never adds it."""
    parts = ([r.type] if r.type else []) + ([r.format] if r.format else []) + r.genres + extra_tags(r.tags)
    if FORMATTED_TAG in r.tags:
        parts.append(FORMATTED_TAG)
    return ", ".join(dedupe(parts))


def needs_poster(row: dict) -> bool:
    return not (row.get("Image Src") or "").strip()


def needs_description(row: dict) -> bool:
    return not strip_html(row.get("Body (HTML)", ""))


def is_multi_variant(row: dict) -> bool:
    try:
        return int(row.get("Variant Count") or 1) > 1
    except ValueError:
        return False


def _finder(row: dict, r: Resolved):
    handle = row.get("Handle", "")
    title = (row.get("Title") or "").strip()

    def make(rule, field, current, proposed, bucket, detail=""):
        return Finding(handle, title, r.type or "", rule, field, current or "", proposed or "", bucket, detail)

    return make


def _price_findings(row, r, make) -> list[Finding]:
    if r.type is None:
        return []  # price can't be validated against an unknown type
    raw = (row.get("Variant Price") or "").strip()
    if r.type == "Rental" and not raw:
        return [make("rental-price-blank", "Variant Price", "", "0", AUTO_FIX, "rentals are always 0")]
    _, reason = resolve_price(r.type, raw)
    if reason is None:
        return []
    if reason.startswith("unreadable"):
        rule = "price-unreadable"
    elif reason.startswith("Rental"):
        rule = "rental-price-nonzero"
    else:
        rule = "floor-sale-price"
    return [make(rule, "Variant Price", raw, "", MANUAL, reason)]


def _rental_barcode_findings(row, r, make) -> list[Finding]:
    if r.type != "Rental":
        return []
    barcode = (row.get("Variant Barcode") or "").strip()
    if not barcode:
        return [make("rental-barcode-missing", "Variant Barcode", "", "", MANUAL,
                     "rentals need a unique 8-digit barcode")]
    if not RENTAL_BARCODE.match(barcode):
        return [make("rental-barcode-format", "Variant Barcode", barcode, "", MANUAL,
                     "rental barcodes must be exactly 8 digits")]
    return []


def _autofix_findings(row, r, make) -> list[Finding]:
    out: list[Finding] = []
    current_tags = row.get("Tags", "")
    proposed_tags = canonical_tags(r)
    for tag in r.tags:
        for rule, resolver in _TAG_ALIAS_RULES:
            canonical = resolver(tag)
            if canonical and canonical != tag:
                out.append(make(rule, "Tags", current_tags, proposed_tags, AUTO_FIX, f"{tag!r} -> {canonical!r}"))

    vendor = (row.get("Vendor") or "").strip()
    if r.format and vendor != r.format:
        out.append(make("format-alias", "Vendor", vendor, r.format, AUTO_FIX, "Vendor carries the media format"))

    if r.genres:
        option1 = (row.get("Option1 Value") or "").strip()
        if option1 != r.genres[0]:
            out.append(make("option1-genre", "Option1 Value", option1, r.genres[0], AUTO_FIX,
                            "Option1 holds the primary genre (barcode label slot)"))
            option1_name = (row.get("Option1 Name") or "").strip()
            if option1_name != "Genre":
                out.append(make("option1-genre", "Option1 Name", option1_name, "Genre", AUTO_FIX,
                                "Option1 is the Genre option"))
        expected = [genre_handle(g) for g in r.genres]
        current = [h.strip() for h in (row.get(GENRE_METAFIELD) or "").split(";") if h.strip()]
        if set(current) != set(expected):
            out.append(make("genre-metafield-sync", GENRE_METAFIELD, "; ".join(current), "; ".join(expected),
                            AUTO_FIX, "the genre filter and PDP chip read this field"))

    if (row.get("Image Src") or "").strip() and not (row.get("Image Alt Text") or "").strip():
        out.append(make("alt-text-missing", "Image Alt Text", "", f"{(row.get('Title') or '').strip()} poster",
                        AUTO_FIX))
    return out


def check_row(row: dict) -> list[Finding]:
    r = resolve_row(row)
    make = _finder(row, r)
    findings: list[Finding] = []

    if r.type_reason:
        rule = "type-conflict" if r.type_reason.startswith("tagged as both") else "type-missing"
        findings.append(make(rule, "Tags", row.get("Tags", ""), "", MANUAL, r.type_reason))
    if r.format is None:
        findings.append(make("format-missing", "Vendor", row.get("Vendor", ""), "", MANUAL,
                             "no VHS/DVD/Blu-Ray/4K/Laserdisc/Betamax in Vendor, Option1 or tags"))
    if not r.genres:
        findings.append(make("genre-missing", GENRE_METAFIELD, row.get(GENRE_METAFIELD, ""), "", MANUAL,
                             "no recognisable genre in Option1 Value or tags"))
    findings += _price_findings(row, r, make)
    if (row.get("Variant Inventory Tracker") or "").strip() != "shopify":
        findings.append(make("inventory-untracked", "Variant Inventory Tracker",
                             row.get("Variant Inventory Tracker", ""), "shopify", MANUAL,
                             "an untracked product never shows as unavailable"))
    findings += _rental_barcode_findings(row, r, make)
    findings += _autofix_findings(row, r, make)

    if is_multi_variant(row):
        # A CSV fix on a multi-variant product can merge or clobber variants:
        # report only, never auto-fix.
        findings = [f for f in findings if f.bucket != AUTO_FIX]
        findings.insert(0, make("multiple-variants", "Variant Count", row.get("Variant Count", ""), "", MANUAL,
                                "one product per physical copy"))
    return findings


def check_catalogue(rows: list[dict]) -> list[Finding]:
    """rental-barcode-duplicate: a Rental's barcode on any other movie."""
    by_barcode: dict[str, list[str]] = {}
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if barcode:
            by_barcode.setdefault(barcode, []).append(row.get("Handle", ""))

    findings: list[Finding] = []
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if not barcode:
            continue
        others = [h for h in by_barcode.get(barcode, []) if h != row.get("Handle", "")]
        if not others:
            continue
        r = resolve_row(row)
        if r.type != "Rental":
            continue
        findings.append(_finder(row, r)("rental-barcode-duplicate", "Variant Barcode", barcode, "", MANUAL,
                                        "also on " + ", ".join(others)))
    return findings
```

- [ ] **Step 6: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK. If a rules test fails, fix the rule, not the test — each test encodes a spec §4 rule or a Review Focus item.

- [ ] **Step 7: Commit**

```bash
git add catalog/audit tests/catalog/test_resolvers.py tests/catalog/test_rules.py
git commit -m "feat(catalog): audit rules — auto-fix, manual and rental-barcode checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Audit orchestration — TMDB step, registry findings, auto-fix collection, outputs

**Files:**
- Create: `catalog/audit/run.py`
- Test: `tests/catalog/test_audit_run.py`

**Interfaces:**
- Consumes: `check_row`, `check_catalogue`, `resolve_row`, `needs_poster`, `needs_description`, `is_multi_variant` (Task 8); `Finding`, buckets, `FINDING_COLUMNS` (Task 8); `promote_applied` (Task 7); `match_product`, `poster_url`, `alt_text_for` (Task 6); `write_csv` (Task 2); `write_snapshot` (Task 4); `COMPLETE_MARKER` (Task 1); `log` (Task 3).
- Produces: `catalog.audit.run`: `AMBIGUOUS_QUEUE = "ambiguous-queue"`, `UNMATCHED_QUEUE = "unmatched-queue"`, `AuditResult(findings, autofix, review, promoted)`, `run_audit(rows, registry, fetch_fn=None) -> AuditResult`, `collect_autofix(findings) -> dict`, `build_report(result, *, source, audited, excluded, tmdb_status) -> str`, `write_outputs(run_dir, rows, result, report)`.
  - `autofix.json` shape: `{handle: {"changes": {field: value}, "rules": [rule, ...]}}` — Plan 2's `apply` reads this.
  - `review.json` shape: list of `{"Handle", "Title", "Vendor", "Genre", "Tags", "Kind": "ambiguous"|"unmatched", "Reason"}` — the exact keys the existing picker candidate collector reads; Plan 2's `picker push` reads this.

- [ ] **Step 1: Write the failing test**

`tests/catalog/test_audit_run.py`:
```python
import csv
import json
import tempfile
import unittest
from pathlib import Path

from catalog.audit.findings import AUTO_FIX, MANUAL, PICKER
from catalog.audit.run import build_report, collect_autofix, run_audit, write_outputs
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.runs import COMPLETE_MARKER
from catalog.shopify.snapshot import blank_row
from catalog.tmdb.match import POSTER_BASE_URL


def movie(**overrides):
    base = blank_row()
    base.update({
        "Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
        "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
        "Image Src": "https://cdn/r.jpg", "Image Alt Text": "Rushmore poster",
        "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0.00",
        "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
        "Variant Count": "1", GENRE_METAFIELD: "comedy",
    })
    base.update(overrides)
    return base


def tmdb(title, year, poster="/p.jpg", overview="An overview.", popularity=5):
    return {"title": title, "release_date": f"{year}-01-01", "poster_path": poster,
            "overview": overview, "genre_ids": [], "popularity": popularity}


def fetcher(by_title, calls=None):
    def fetch(query, year):
        if calls is not None:
            calls.append(query)
        return {"results": by_title.get(query, [])}
    return fetch


def rules_for(result, handle):
    return {(f.rule, f.field, f.bucket) for f in result.findings if f.handle == handle}


class TestContentStep(unittest.TestCase):
    def test_confident_match_autofills_poster_and_alt(self):
        row = movie(**{"Image Src": "", "Image Alt Text": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998)]}))
        changes = result.autofix["rushmore-vhs-rental"]["changes"]
        self.assertEqual(changes["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(changes["Image Alt Text"], "Rushmore (1998) poster")
        self.assertEqual(result.review, [])

    def test_confident_match_autofills_description(self):
        row = movie(**{"Body (HTML)": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998, overview="A precocious teen.")]}))
        self.assertEqual(result.autofix["rushmore-vhs-rental"]["changes"]["Body (HTML)"], "<p>A precocious teen.</p>")

    def test_confident_match_without_poster_goes_to_unmatched(self):
        row = movie(**{"Image Src": "", "Image Alt Text": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998, poster="")]}))
        self.assertEqual(result.review[0]["Kind"], "unmatched")
        self.assertIn(("poster-missing", "Image Src", PICKER), rules_for(result, "rushmore-vhs-rental"))

    def test_ambiguous_goes_to_ambiguous_queue(self):
        row = movie(Title="Mandela", **{"Image Src": "", "Image Alt Text": "", GENRE_METAFIELD: ""},
                    Tags="Rental, VHS, Drama", **{"Option1 Value": "Drama"})
        result = run_audit([row], {}, fetcher({"Mandela": [tmdb("Mandela", 1996), tmdb("Mandela", 1987)]}))
        self.assertEqual(len(result.review), 1)
        entry = result.review[0]
        self.assertEqual(entry["Kind"], "ambiguous")
        self.assertEqual(set(entry), {"Handle", "Title", "Vendor", "Genre", "Tags", "Kind", "Reason"})

    def test_no_match_goes_to_unmatched_queue(self):
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, fetcher({}))
        self.assertEqual(result.review[0]["Kind"], "unmatched")

    def test_request_failure_is_manual_and_not_queued(self):
        def boom(query, year):
            raise OSError("down")
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, boom)
        self.assertIn(("tmdb-request-failed", "Image Src", MANUAL), rules_for(result, "rushmore-vhs-rental"))
        self.assertEqual(result.review, [])

    def test_queued_handle_is_not_searched_again(self):
        calls = []
        registry = {"rushmore-vhs-rental": {"batch": "ambiguous-queue", "status": "queued"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}, calls))
        self.assertEqual(calls, [])
        self.assertEqual(result.review, [])
        finding = [f for f in result.findings if f.rule == "poster-missing"][0]
        self.assertEqual((finding.bucket, finding.detail), (PICKER, "already queued in ambiguous-queue"))

    def test_skipped_handle_is_client_skipped(self):
        registry = {"rushmore-vhs-rental": {"batch": "q", "status": "skipped"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}))
        self.assertIn(("client-skipped", "Image Src", MANUAL), rules_for(result, "rushmore-vhs-rental"))

    def test_legacy_resolved_but_still_missing(self):
        registry = {"rushmore-vhs-rental": {"batch": "q", "status": "resolved"}}
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], registry, fetcher({}))
        finding = [f for f in result.findings if f.rule == "applied-but-missing"][0]
        self.assertIn("old pipeline", finding.detail)

    def test_multi_variant_skips_tmdb(self):
        calls = []
        run_audit([movie(**{"Image Src": "", "Variant Count": "2"})], {}, fetcher({}, calls))
        self.assertEqual(calls, [])

    def test_skip_tmdb_lists_picker_findings_without_review_entries(self):
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": ""})], {}, None)
        finding = [f for f in result.findings if f.rule == "poster-missing"][0]
        self.assertEqual((finding.bucket, finding.detail), (PICKER, "not matched (--skip-tmdb)"))
        self.assertEqual(result.review, [])


class TestRegistryStep(unittest.TestCase):
    def test_visible_fix_is_promoted(self):
        registry = {"rushmore-vhs-rental": {"status": "applied", "run": "r1", "values": {"Image Src": "u"}}}
        result = run_audit([movie()], registry, None)
        self.assertEqual(result.promoted, ["rushmore-vhs-rental"])
        self.assertEqual(registry["rushmore-vhs-rental"]["status"], "resolved")

    def test_invisible_fix_is_applied_but_missing(self):
        registry = {"rushmore-vhs-rental": {"status": "applied", "run": "r1", "values": {"Body (HTML)": "<p>New.</p>"}}}
        result = run_audit([movie()], registry, None)
        finding = [f for f in result.findings if f.rule == "applied-but-missing"][0]
        self.assertIn("r1", finding.detail)


class TestCollectAutofix(unittest.TestCase):
    def test_merges_fields_and_rules(self):
        result = run_audit([movie(Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor", GENRE_METAFIELD: ""})], {}, None)
        entry = result.autofix["rushmore-vhs-rental"]
        self.assertEqual(entry["changes"]["Tags"], "Rental, VHS, Horror")
        self.assertEqual(entry["changes"][GENRE_METAFIELD], "horror")
        self.assertEqual(set(entry["rules"]), {"genre-alias", "option1-genre", "genre-metafield-sync"})

    def test_conflicting_values_raise(self):
        from catalog.audit.findings import Finding
        a = Finding("h", "t", "Rental", "r1", "Vendor", "", "VHS", AUTO_FIX)
        b = Finding("h", "t", "Rental", "r2", "Vendor", "", "DVD", AUTO_FIX)
        with self.assertRaises(ValueError):
            collect_autofix([a, b])


class TestOutputs(unittest.TestCase):
    def test_writes_every_file_and_marks_complete_last(self):
        rows = [movie(), movie(Handle="bad", Tags="VHS, Comedy", **{"Variant Barcode": "1"})]
        result = run_audit(rows, {}, None)
        report = build_report(result, source="export test.csv", audited=2,
                              excluded={"archived": 3}, tmdb_status="skipped (--skip-tmdb)")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_outputs(run_dir, rows, result, report)
            names = sorted(p.name for p in run_dir.iterdir())
            self.assertEqual(names, ["autofix.json", "findings.csv", "review.json", COMPLETE_MARKER, "snapshot.json"])
            with open(run_dir / "findings.csv", newline="", encoding="utf-8") as f:
                found = list(csv.DictReader(f))
            self.assertTrue(all(r["handle"] == "bad" for r in found))
            self.assertEqual(json.loads((run_dir / "review.json").read_text(encoding="utf-8")), [])
        self.assertIn("type-missing", report)
        self.assertIn("archived: 3", report)
        self.assertIn("skipped (--skip-tmdb)", report)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_audit_run.py"`
Expected: `ModuleNotFoundError: No module named 'catalog.audit.run'`.

- [ ] **Step 3: Implement `catalog/audit/run.py`**

```python
"""Stage 1 orchestration: snapshot rows -> findings, auto-fixes and picker entries.

run_audit is pure apart from progress logging and mutating `registry` in
place (applied -> resolved promotion); the caller saves the registry and
writes outputs.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from catalog.audit.findings import AUTO_FIX, FINDING_COLUMNS, MANUAL, PICKER, Finding
from catalog.audit.rules import (
    check_catalogue, check_row, is_multi_variant, needs_description, needs_poster, resolve_row,
)
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import write_csv
from catalog.core.registry import promote_applied
from catalog.core.runs import COMPLETE_MARKER
from catalog.shopify.snapshot import write_snapshot
from catalog.tmdb.match import alt_text_for, match_product, poster_url

AMBIGUOUS_QUEUE = "ambiguous-queue"
UNMATCHED_QUEUE = "unmatched-queue"
_CONTENT_RULE = {"Image Src": "poster-missing", "Body (HTML)": "description-missing"}


@dataclass
class AuditResult:
    findings: list[Finding]
    autofix: dict       # {handle: {"changes": {field: value}, "rules": [rule, ...]}}
    review: list[dict]  # review.json entries for picker push
    promoted: list[str]


def _review_entry(row: dict, kind: str, reason: str) -> dict:
    return {"Handle": row["Handle"], "Title": row.get("Title", ""), "Vendor": row.get("Vendor", ""),
            "Genre": row.get(GENRE_METAFIELD, ""), "Tags": row.get("Tags", ""),
            "Kind": kind, "Reason": reason}


def _content(row: dict, registry: dict, fetch_fn) -> tuple[list[Finding], dict | None, str]:
    """Findings for a missing poster/description, plus a review entry if the
    product needs the picker, plus a one-line progress message."""
    missing = [f for f, needed in (("Image Src", needs_poster(row)), ("Body (HTML)", needs_description(row))) if needed]
    ptype = resolve_row(row).type or ""
    title = (row.get("Title") or "").strip()

    def make(field, bucket, detail, proposed="", rule=None):
        return Finding(row["Handle"], title, ptype, rule or _CONTENT_RULE[field], field, "", proposed, bucket, detail)

    entry = registry.get(row["Handle"])
    if entry:
        status = entry.get("status")
        if status == "queued":
            detail = f"already queued in {entry.get('batch', '?')}"
            return [make(f, PICKER, detail) for f in missing], None, detail
        if status == "skipped":
            return ([make(f, MANUAL, "client skipped this in the picker", rule="client-skipped") for f in missing],
                    None, "client skipped")
        if status == "resolved":
            return ([make(f, MANUAL, "marked resolved by the old pipeline but still missing in Shopify",
                          rule="applied-but-missing") for f in missing], None, "resolved but still missing")
        return [], None, "applied, awaiting import"  # reported by the registry step

    if fetch_fn is None:
        return [make(f, PICKER, "not matched (--skip-tmdb)") for f in missing], None, "TMDB skipped"

    result = match_product(row, fetch_fn)
    if result.kind == "error":
        return ([make(f, MANUAL, result.reason, rule="tmdb-request-failed") for f in missing],
                None, result.reason)
    if result.kind in ("ambiguous", "none"):
        kind = "ambiguous" if result.kind == "ambiguous" else "unmatched"
        queue = AMBIGUOUS_QUEUE if kind == "ambiguous" else UNMATCHED_QUEUE
        return ([make(f, PICKER, result.reason) for f in missing],
                _review_entry(row, kind, result.reason), f"-> {queue}")

    findings: list[Finding] = []
    unfilled: list[tuple[str, str]] = []
    if "Image Src" in missing:
        url = poster_url(result.best)
        if url:
            findings.append(make("Image Src", AUTO_FIX, result.reason, url))
            if not (row.get("Image Alt Text") or "").strip():
                findings.append(make("Image Alt Text", AUTO_FIX, result.reason, alt_text_for(title, result.best),
                                     rule="poster-missing"))
        else:
            unfilled.append(("Image Src", "matched but TMDB has no poster"))
    if "Body (HTML)" in missing:
        overview = ((result.best or {}).get("overview") or "").strip()
        if overview:
            findings.append(make("Body (HTML)", AUTO_FIX, result.reason, f"<p>{overview}</p>"))
        else:
            unfilled.append(("Body (HTML)", "matched but TMDB has no overview"))

    review = None
    if unfilled:
        findings += [make(f, PICKER, why) for f, why in unfilled]
        review = _review_entry(row, "unmatched", "; ".join(why for _, why in unfilled))
    filled = [_CONTENT_RULE[f.field].split("-")[0] for f in findings if f.bucket == AUTO_FIX and f.field in _CONTENT_RULE]
    message = ("auto-fill " + ", ".join(filled)) if filled else ""
    if review:
        message = (message + "; " if message else "") + f"-> {UNMATCHED_QUEUE}"
    return findings, review, message


def _applied_missing(registry: dict, rows_by_handle: dict, handles: list[str]) -> list[Finding]:
    out = []
    for handle in handles:
        entry, row = registry[handle], rows_by_handle[handle]
        fields = ", ".join((entry.get("values") or {}).keys())
        out.append(Finding(handle, (row.get("Title") or "").strip(), resolve_row(row).type or "",
                           "applied-but-missing", fields, "", "", MANUAL,
                           f"applied in run {entry.get('run', '?')} but not visible in Shopify — was that import CSV imported?"))
    return out


def collect_autofix(findings: list[Finding]) -> dict:
    out: dict = {}
    for f in findings:
        if f.bucket != AUTO_FIX:
            continue
        entry = out.setdefault(f.handle, {"changes": {}, "rules": []})
        existing = entry["changes"].get(f.field)
        if existing is not None and existing != f.proposed_value:
            raise ValueError(f"conflicting auto-fixes for {f.handle} {f.field}: {existing!r} vs {f.proposed_value!r}")
        entry["changes"][f.field] = f.proposed_value
        if f.rule not in entry["rules"]:
            entry["rules"].append(f.rule)
    return out


def run_audit(rows: list[dict], registry: dict, fetch_fn=None) -> AuditResult:
    rows_by_handle = {row["Handle"]: row for row in rows}
    promoted, still_missing = promote_applied(registry, rows_by_handle)

    findings: list[Finding] = []
    for row in rows:
        findings.extend(check_row(row))
    findings.extend(check_catalogue(rows))
    findings.extend(_applied_missing(registry, rows_by_handle, still_missing))
    log.summary(f"rules: {len(findings)} findings before content checks")

    content_rows = [r for r in rows if (needs_poster(r) or needs_description(r)) and not is_multi_variant(r)]
    review: list[dict] = []
    for index, row in enumerate(content_rows, start=1):
        found, entry, message = _content(row, registry, fetch_fn)
        findings.extend(found)
        if entry:
            review.append(entry)
        log.progress(index, len(content_rows), (row.get("Title") or row["Handle"]).strip(), message)

    for f in findings:
        log.detail(f"{f.handle}: {f.rule} [{f.bucket}] {f.field} {f.current_value!r} -> {f.proposed_value!r} {f.detail}")
    return AuditResult(findings, collect_autofix(findings), review, promoted)


def build_report(result: AuditResult, *, source: str, audited: int, excluded: dict, tmdb_status: str) -> str:
    by_rule: dict[str, set] = {}
    by_bucket: dict[str, set] = {}
    for f in result.findings:
        by_rule.setdefault(f.rule, set()).add(f.handle)
        by_bucket.setdefault(f.bucket, set()).add(f.handle)
    excluded_text = ", ".join(f"{k}: {v}" for k, v in sorted(excluded.items())) or "none"
    lines = [
        f"source:    {source}",
        f"audited:   {audited} movies (excluded — {excluded_text})",
        f"findings:  {len(result.findings)} across {len({f.handle for f in result.findings})} products",
        "by bucket (products):",
        *[f"  {b:<10} {len(by_bucket.get(b, ()))}" for b in (AUTO_FIX, PICKER, MANUAL)],
        "by rule (products):",
        *[f"  {rule:<26} {len(handles)}" for rule, handles in sorted(by_rule.items())],
        f"auto-fix:  {len(result.autofix)} products in autofix.json",
        f"picker:    {len(result.review)} new products in review.json",
        f"registry:  {len(result.promoted)} applied -> resolved",
        f"tmdb:      {tmdb_status}",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(run_dir, rows: list[dict], result: AuditResult, report: str) -> None:
    """Write every output; the completion marker (run-report.txt) goes last."""
    run_dir = Path(run_dir)
    write_snapshot(run_dir / "snapshot.json", rows)
    ordered = sorted(result.findings, key=lambda f: (f.handle, f.rule, f.field))
    write_csv(run_dir / "findings.csv", FINDING_COLUMNS, [f.as_row() for f in ordered])
    (run_dir / "autofix.json").write_text(json.dumps(result.autofix, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "review.json").write_text(json.dumps(result.review, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / COMPLETE_MARKER).write_text(report, encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add catalog/audit/run.py tests/catalog/test_audit_run.py
git commit -m "feat(catalog): audit orchestration — TMDB content step, registry findings, run outputs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `audit` command wiring

**Files:**
- Create: `catalog/audit/command.py`
- Modify: `catalog/cli.py` (register the audit command)
- Test: `tests/catalog/test_audit_command.py`

**Interfaces:**
- Consumes: everything above; `read_products` (Task 5), `read_export` (Task 4), `filter_catalogue` (Task 4), `load_registry`/`save_registry` (Task 7), `make_fetcher` (Task 6), `TmdbCache` (Task 6), `new_run`/`resolve_run` (Task 1), `require_env` (Task 1).
- Produces: `catalog.audit.command`: `register(subparsers)`, `run_command(args, fetch_fn=None, read_api=read_products, today=None) -> int`. CLI: `python3 -m catalog audit [--store S] [--from-export CSV] [--skip-tmdb] [--no-cache] [-v|-q]` (hidden `--runs-dir`, `--picker-dir` for tests).

- [ ] **Step 1: Write the failing test**

`tests/catalog/test_audit_command.py`:
```python
import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from catalog.audit import command
from catalog.cli import build_parser, main
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.runs import COMPLETE_MARKER, list_runs, resolve_run

HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status", "Option1 Name", "Option1 Value",
          "Variant Price", "Variant Barcode", "Variant Inventory Tracker", "Image Src", "Image Alt Text",
          GENRE_METAFIELD]


def product(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
            "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active", "Option1 Name": "Genre",
            "Option1 Value": "Comedy", "Variant Price": "0", "Variant Barcode": "01577790",
            "Variant Inventory Tracker": "shopify", "Image Src": "https://cdn/r.jpg",
            "Image Alt Text": "Rushmore poster", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


CATALOGUE = [
    product(),
    product(Handle="heat-vhs-rental", Title="Heat", Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor",
            GENRE_METAFIELD: "", "Variant Barcode": "02000000"}),
    product(Handle="jaws-dvd-rental", Title="Jaws", **{"Image Src": "", "Image Alt Text": "", "Variant Barcode": "03000000"}),
    product(Handle="dup-dvd-floor-sale", Title="Dup", Tags="Floor Sale, DVD, Drama", Vendor="DVD",
            **{"Option1 Value": "Drama", GENRE_METAFIELD: "drama", "Variant Price": "5", "Variant Barcode": "01577790"}),
    product(Handle="old-vhs-rental", Title="Old", Status="archived", **{"Variant Barcode": "04000000"}),
]


class TestAuditCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.picker = root / "runs", root / "picker"
        self.export = root / "export.csv"
        with open(self.export, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(CATALOGUE)

    def tearDown(self):
        from catalog.core import log
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["audit", "--from-export", str(self.export), "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "-q", *extra])

    def fetch(self, query, year):
        if query == "Jaws":
            return {"results": [{"title": "Jaws", "release_date": "1975-06-20", "poster_path": "/jaws.jpg",
                                 "overview": "A shark.", "genre_ids": [], "popularity": 50}]}
        return {"results": []}

    def test_end_to_end_from_export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.args(), fetch_fn=self.fetch, today=date(2026, 9, 25))
        self.assertEqual(code, 0)
        run_dir = resolve_run(self.runs)
        self.assertEqual(run_dir.name, "2026-09-25")
        snapshot = json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot), 4)  # archived product excluded
        with open(run_dir / "findings.csv", newline="", encoding="utf-8") as f:
            rules = {(r["handle"], r["rule"]) for r in csv.DictReader(f)}
        self.assertIn(("heat-vhs-rental", "genre-alias"), rules)
        self.assertIn(("rushmore-vhs-rental", "rental-barcode-duplicate"), rules)
        self.assertNotIn(("dup-dvd-floor-sale", "rental-barcode-duplicate"), rules)
        autofix = json.loads((run_dir / "autofix.json").read_text(encoding="utf-8"))
        self.assertTrue(autofix["jaws-dvd-rental"]["changes"]["Image Src"].endswith("/jaws.jpg"))
        report = (run_dir / COMPLETE_MARKER).read_text(encoding="utf-8")
        self.assertIn("archived: 1", report)
        self.assertIn("1 fetches", report)
        self.assertTrue((run_dir / "audit.log").exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_skip_tmdb_needs_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = command.run_command(self.args("--skip-tmdb"), today=date(2026, 9, 25))
        self.assertEqual(code, 0)

    def test_missing_key_fails_before_reading_anything(self):
        err = io.StringIO()
        argv = ["audit", "--from-export", str(self.export), "--runs-dir", str(self.runs),
                "--picker-dir", str(self.picker)]
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("TMDB_API_KEY", err.getvalue())
        self.assertEqual(list_runs(self.runs), [])  # no run folder left behind

    def test_interrupt_saves_cache_and_leaves_run_incomplete(self):
        calls = []

        def fetch(query, year):
            calls.append(query)
            raise KeyboardInterrupt

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            command.run_command(self.args(), fetch_fn=fetch, today=date(2026, 9, 25))
        run_dir = list_runs(self.runs)[0]
        self.assertFalse((run_dir / COMPLETE_MARKER).exists())
        self.assertTrue((self.runs / ".tmdb-cache.json").exists())

    def test_registry_saved_only_when_promoted(self):
        self.picker.joinpath("data").mkdir(parents=True)
        registry_file = self.picker / "data" / "_handle-index.json"
        registry_file.write_text(json.dumps({"rushmore-vhs-rental": {
            "status": "applied", "run": "r0", "values": {"Image Src": "https://x"}}}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(self.args("--skip-tmdb"), today=date(2026, 9, 25))
        saved = json.loads(registry_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["rushmore-vhs-rental"]["status"], "resolved")

    def test_api_path_uses_injected_reader(self):
        from catalog.shopify.export_reader import read_export
        rows = read_export(self.export)
        args = build_parser().parse_args(["audit", "--store", "dev.myshopify.com", "--runs-dir", str(self.runs),
                                          "--picker-dir", str(self.picker), "--skip-tmdb", "-q"])
        seen = []
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_command(args, read_api=lambda store: seen.append(store) or rows, today=date(2026, 9, 25))
        self.assertEqual(seen, ["dev.myshopify.com"])
        self.assertIn("api dev.myshopify.com", (resolve_run(self.runs) / COMPLETE_MARKER).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests/catalog -p "test_audit_command.py"`
Expected: `ImportError` for `catalog.audit.command`.

- [ ] **Step 3: Implement `catalog/audit/command.py`**

```python
"""`python3 -m catalog audit` — read Shopify, run every rule, write a run folder.

Read-only toward Shopify. Writes only its own run folder, the shared TMDB
cache, and registry promotion (applied -> resolved), so it asks for no approval.
"""

import argparse
from datetime import date
from pathlib import Path

from catalog import config
from catalog.audit.run import build_report, run_audit, write_outputs
from catalog.core import log
from catalog.core.registry import load_registry, save_registry
from catalog.core.runs import new_run
from catalog.shopify.export_reader import read_export
from catalog.shopify.reader import read_products
from catalog.shopify.snapshot import filter_catalogue
from catalog.tmdb.cache import TmdbCache
from catalog.tmdb.client import make_fetcher


def register(subparsers) -> None:
    p = subparsers.add_parser("audit", help="audit the Shopify movie catalogue (read-only)")
    p.add_argument("--store", default=config.DEFAULT_STORE, help=f"store domain (default {config.DEFAULT_STORE})")
    p.add_argument("--from-export", metavar="CSV", help="read a Shopify product export instead of the API")
    p.add_argument("--skip-tmdb", action="store_true", help="no TMDB lookups; missing content is listed only")
    p.add_argument("--no-cache", action="store_true", help="bypass the TMDB cache (re-fetch everything)")
    p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--picker-dir", default=str(config.PICKER_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)
    p.set_defaults(func=run_command)


def run_command(args, fetch_fn=None, read_api=read_products, today: date | None = None) -> int:
    runs_dir = Path(args.runs_dir)
    # Fail fast on a missing key: before creating a run folder or reading Shopify.
    raw_fetch = None
    if not args.skip_tmdb:
        raw_fetch = fetch_fn or make_fetcher(config.require_env(config.ENV_TMDB_API_KEY))

    run_dir = new_run(runs_dir, today or date.today())
    log.setup_logging(run_dir / "audit.log", log.verbosity(args))
    log.header(f"audit — run {run_dir.name}")

    if args.from_export:
        source = f"export {args.from_export}"
        log.summary(f"reading {args.from_export}")
        raw_rows = read_export(args.from_export)
    else:
        source = f"api {args.store}"
        log.summary(f"reading products from {args.store} (read-only)")
        raw_rows = read_api(args.store)
    rows, excluded = filter_catalogue(raw_rows)
    log.summary(f"{len(rows)} movies to audit; excluded {sum(excluded.values())} ({excluded or 'none'})")

    registry = load_registry(args.picker_dir)
    cache = None
    if raw_fetch is None:
        fetch, tmdb_status = None, "skipped (--skip-tmdb)"
    elif args.no_cache:
        fetch, tmdb_status = raw_fetch, "cache bypassed (--no-cache)"
    else:
        cache = TmdbCache(runs_dir / config.TMDB_CACHE_FILENAME)
        fetch = cache.wrap(raw_fetch)

    try:
        result = run_audit(rows, registry, fetch)
    finally:
        if cache is not None:
            cache.save()
    if cache is not None:
        tmdb_status = f"{cache.hits} cache hits, {cache.misses} fetches"

    if result.promoted:
        save_registry(args.picker_dir, registry)

    report = build_report(result, source=source, audited=len(rows), excluded=excluded, tmdb_status=tmdb_status)
    write_outputs(run_dir, rows, result, report)
    log.summary(report.rstrip())
    log.summary(f"-> {run_dir}")
    return 0
```

Note: `KeyboardInterrupt` propagates out of `run_command` (the `finally` saves the cache first); `cli.main` turns it into exit 130. `write_outputs` never runs, so the run has no `run-report.txt` and is never "latest".

- [ ] **Step 4: Register the command in `catalog/cli.py`**

Replace the line `COMMANDS: list = []  # modules with register(subparsers); stages append themselves here` with:
```python
from catalog.audit import command as audit_command

COMMANDS: list = [audit_command]  # modules with register(subparsers), in help order
```

- [ ] **Step 5: Run the whole catalog suite and the old suite**

```bash
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -3
python3 -m catalog audit --help
```
Expected: catalog suite OK; old suite `Ran 348 tests` OK; help lists `--store`, `--from-export`, `--skip-tmdb`, `--no-cache`, `-v`, `-q`.

- [ ] **Step 6: Commit**

```bash
git add catalog/audit/command.py catalog/cli.py tests/catalog/test_audit_command.py
git commit -m "feat(catalog): python3 -m catalog audit command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: README and production acceptance run

**Files:**
- Create: `catalog/README.md`
- Create: `claudedocs/2026-09-25-catalog-audit-acceptance.md` (results)

**Interfaces:** none new.

- [ ] **Step 1: Write `catalog/README.md`**

```markdown
# catalog — Little Movie Store catalogue pipeline

Design: `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md`.
Run everything from the repo root. Standard library only (Libib `fix` will need Playwright).

## Stage 1 — audit (read-only)

    export TMDB_API_KEY=...            # not needed with --skip-tmdb
    python3 -m catalog audit           # production, via the Shopify CLI
    python3 -m catalog audit --from-export products_export.csv
    python3 -m catalog audit --store lms-sandbox-lutsfahz.myshopify.com

If the CLI is not authenticated: `shopify store auth --store <domain> --scopes read_products`.

Writes `runs/<date>/` (a second run the same day gets `-2`, `-3`, …):

| file | contents |
|---|---|
| `snapshot.json` | every audited movie, normalised (archived, retail-template and non-catalogue products excluded) |
| `findings.csv` | one row per problem: `handle, title, type, rule, field, current_value, proposed_value, bucket, detail` |
| `autofix.json` | safe fixes, `{handle: {"changes": {field: value}, "rules": [...]}}` — applied by stage 3 |
| `review.json` | products that need the client in the picker — pushed by stage 2 |
| `run-report.txt` | counts per bucket and rule; written last, so its presence means the run completed |
| `audit.log` | everything printed, plus per-rule detail |

Buckets: **auto-fix** (safe, goes to autofix.json), **picker** (needs the client), **manual** (fix in Shopify admin).
Rental barcodes must be 8 digits and unique across every movie.

Flags: `--skip-tmdb` (no lookups), `--no-cache` (bypass `runs/.tmdb-cache.json`), `-v` / `-q`.

The audit changes nothing outside its run folder except the shared TMDB cache and
promoting picker registry entries from `applied` to `resolved` once Shopify shows the fix.

## Tests

    python3 -m unittest discover -s tests/catalog -p "test_*.py"
```

- [ ] **Step 2: Dev-store dry run (read-only, no TMDB)**

```bash
python3 -m catalog audit --store lms-sandbox-lutsfahz.myshopify.com --skip-tmdb
```
Expected: page progress, a summary with bucket/rule counts, `-> runs/<date>`. Open `findings.csv` and spot-check five rows of different rules against the dev store admin.

- [ ] **Step 3: Production acceptance run — ask the user first**

This reads production and spends TMDB calls on every product missing a poster or description. Ask the user to confirm, and to export `TMDB_API_KEY` in the shell (or run it themselves with `! python3 -m catalog audit`). If auth fails, the user runs `shopify store auth --store p0wkgv-wy.myshopify.com --scopes read_products`.

```bash
python3 -m catalog audit
```

- [ ] **Step 4: Compare against the known counts, each on its own scope**

```bash
RUN=$(ls -d runs/20* | tail -1)
python3 - "$RUN" <<'EOF'
import json, re, sys, collections
run = sys.argv[1]
rows = json.load(open(f"{run}/snapshot.json", encoding="utf-8"))
rentals = [r for r in rows if "Rental" in [t.strip() for t in r["Tags"].split(",")]]
print("rentals:", len(rentals))
print("rentals missing poster:", sum(1 for r in rentals if not r["Image Src"].strip()))
print("rentals missing description:", sum(1 for r in rentals if not re.sub(r"<[^>]+>", "", r["Body (HTML)"]).strip()))
by = collections.defaultdict(list)
for r in rows:
    if r["Variant Barcode"].strip():
        by[r["Variant Barcode"].strip()].append(r["Handle"])
print("barcodes shared by >1 movie (all movies):", sum(1 for v in by.values() if len(v) > 1))
EOF
```
Known reference points: 133 rentals missing a poster and 118 missing a description (rental catalogue, 2026-09-16, `LIBIB_MIGRATION_PROGRESS.md`); 13 duplicate-barcode pairs (2026-09-19, not rental-scoped). The catalogue has changed since, so expect differences — explain each gap (new uploads, fixes made since, archived exclusion) rather than forcing a match.

- [ ] **Step 5: Record the results**

Write `claudedocs/2026-09-25-catalog-audit-acceptance.md` with: run id, source, the `run-report.txt` contents, the Step 4 numbers beside the reference numbers, the explanation for each gap, and any rule that looked wrong on spot-check (with example handles). Any rule that looked wrong becomes a fix-up task before Plan 2 starts.

- [ ] **Step 6: Commit**

```bash
git add catalog/README.md claudedocs/2026-09-25-catalog-audit-acceptance.md
git commit -m "docs(catalog): audit README and production acceptance results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## What Plans 2–4 will build on

- `runs/<id>/autofix.json` and `review.json` shapes (Task 9) — consumed by apply and picker push.
- `catalog.core.registry` lifecycle (Task 7) — picker push marks `queued`, apply marks `applied`/`skipped`.
- `catalog.core.runs.resolve_run` — every later stage defaults to the latest complete run.
- `catalog.cli.COMMANDS` — each later stage adds its module here.
- Plan 2 adds `core/plan.py` (approval prompt, `--dry-run`, `--yes`, non-TTY refusal) and the dev-store verification of `Option1` and image re-import behaviour before any `genre.csv` / `alt-text` import.
