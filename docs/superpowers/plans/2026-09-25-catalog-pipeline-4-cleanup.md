# Catalog Pipeline — Plan 4: Client Sheet, Cleanup, Docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the rebuild: move the client upload-sheet tooling into `catalog/client_sheet/` (with `python3 -m catalog check-upload`), fix the deferred minors from Plan 1's review, delete `formatting-scripts/`, `tests/formatting_scripts/` and `tests/data_cleanup/`, and update every doc that points at the old folder.

**Architecture:** `catalog/client_sheet/` is client-side tooling that shares `core/` but is not a pipeline stage. After this plan the only catalogue code is `catalog/` and the only Python tests are `tests/catalog/`.

**Tech Stack:** Python 3.10+ standard library, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md` — §2 (layout: `client_sheet/`), §10 (file mapping, deletions, references to update). Plans 1–3 are merged.

## Global Constraints

- Standard library only; run from the repo root.
- Tests: `python3 -m unittest discover -s tests/catalog -p "test_*.py"` (baseline = the count Plan 3 ended with; record it in Task 0). The old suite (348) must stay green **until Task 3 deletes it**.
- Deleting is done with `git rm` only after the replacement exists and its tests pass; nothing outside `formatting-scripts/`, `tests/formatting_scripts/`, `tests/data_cleanup/` and the Plan 2 seam test is deleted.
- Historical docs (`docs/superpowers/specs|plans/*` older than 2026-09-25, `claudedocs/*`, `libib-sync/*` logs) are left as written; only live instructions are updated.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS
  ```

## Decisions made while planning (confirm at review)

1. **Task 2 (Plan 1's deferred minors) is optional.** Drop it at review if you'd rather not; nothing else depends on it. It fixes: a video as first media hiding the poster; multi-variant products missing content not being reported; a bad `--from-export` path/BOM crashing; an invalid TMDB key not stopping the audit; a malformed registry file giving a traceback; an over-broad "auth" error hint; the "resolved by the old pipeline" wording; unescaped TMDB overview HTML; stale docstrings. It **does not** raise `references(first: 5)` (production's max is 2 genres per product).
2. **`TestAgreesWithPipeline` (in `test_sheet_transform.py`) is not ported.** It compared the sheet transform with the old template-shape normalizer, which Plan 1 dropped (decision A in brainstorming).
3. **`generate_expected.py` becomes a module**: `python3 -m catalog.client_sheet.generate_expected`.
4. **The Plan 2 seam test (`tests/catalog/test_picker_page_seam.py`) is deleted with `formatting-scripts/`** — it compared the templates with the old generator, which no longer exists; the templates are now the source of truth.

## Review Focus

1. **`check-upload` exit codes** (0 clean / 1 problems / 2 unreadable) must survive the move, because the client workflow gates on them. → Task 1 test `test_cli_exit_codes`.
2. **A Google-Sheets CSV with a BOM** for `check-upload` and for `audit --from-export`. → Task 1 (ported BOM fixture tests) and Task 2 test `test_from_export_reads_a_bom_file`.
3. **Nothing left importing `formatting-scripts`** after the delete. → Task 3 Step 2 grep gate.
4. **An invalid TMDB key** must stop the audit with one clear error, not 162 slow per-product failures. → Task 2 test `test_invalid_key_stops_the_audit`.
5. **Docs that tell someone to run a deleted script.** → Task 4 Step 5 grep gate.

---

### Task 0: Branch setup

- [ ] **Step 1**

```bash
git status --short                      # must be empty
git checkout fix/redirect-all-collection
git checkout -b refactor/catalog-pipeline-4
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -3
```
Expected: both `OK`; record the catalog count as this plan's baseline.

---

### Task 1: Client sheet → `catalog/client_sheet/` and `check-upload`

**Files:**
- Create: `catalog/client_sheet/__init__.py` (empty), `catalog/client_sheet/transform.py` (from `sheet_transform.py`), `catalog/client_sheet/check.py` (from `check_upload.py`), `catalog/client_sheet/generate_expected.py`, `catalog/client_sheet/command.py`, `catalog/client_sheet/template/` (copy of `formatting-scripts/client-template/` minus `generate_expected.py`)
- Modify: `catalog/cli.py` (register), `catalog/client_sheet/template/import-tab-formula.txt` (two path references)
- Test: `tests/catalog/test_sheet_transform.py`, `tests/catalog/test_client_template_files.py`, `tests/catalog/test_check_upload.py` (ported)

**Interfaces:**
- Produces: `catalog.client_sheet.transform` (`FILL_COLUMNS`, `fill_row_to_import_row`, `fill_rows_to_import_rows`), `catalog.client_sheet.check` (`Problem`, `detect_shape`, `check_row`, `check(path) -> (shape, rows, problems)`, **`report(path) -> int`** replacing `main()`), `catalog.client_sheet.command` (`register`; CLI `python3 -m catalog check-upload <csv>` → exit 0/1/2).

- [ ] **Step 1: Port the tests (failing)**

```bash
mkdir -p catalog/client_sheet && touch catalog/client_sheet/__init__.py

{ cat <<'EOF'
import unittest

from catalog.client_sheet.transform import FILL_COLUMNS, fill_rows_to_import_rows
from catalog.core.columns import GENRE_METAFIELD, TEMPLATE_COLUMNS
EOF
sed -n '10,95p' tests/formatting_scripts/test_sheet_transform.py
cat <<'EOF'


if __name__ == "__main__":
    unittest.main()
EOF
} > tests/catalog/test_sheet_transform.py

{ cat <<'EOF'
import csv
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

from catalog.client_sheet.transform import FILL_COLUMNS, fill_rows_to_import_rows  # noqa: E402
from catalog.core.columns import TEMPLATE_COLUMNS  # noqa: E402

TEMPLATE_DIR = os.path.join(ROOT, "catalog", "client_sheet", "template")
EOF
sed -n '14,$p' tests/formatting_scripts/test_client_template_files.py \
  | sed 's|\[sys.executable, os.path.join(TEMPLATE_DIR, "generate_expected.py")\]|[sys.executable, "-m", "catalog.client_sheet.generate_expected"]|'
} > tests/catalog/test_client_template_files.py

{ cat <<'EOF'
import contextlib
import csv
import io
import os
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

from catalog.cli import main  # noqa: E402
from catalog.client_sheet.check import check, detect_shape  # noqa: E402
from catalog.client_sheet.transform import FILL_COLUMNS  # noqa: E402
from catalog.core.columns import GENRE_METAFIELD, TEMPLATE_COLUMNS  # noqa: E402

TEMPLATE_DIR = os.path.join(ROOT, "catalog", "client_sheet", "template")
EOF
sed -n '15,$p' tests/formatting_scripts/test_check_upload.py | sed '/^if __name__ == "__main__":$/,$d'
cat <<'EOF'
class TestCli(unittest.TestCase):
    def run_cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["check-upload", *argv])

    def test_cli_exit_codes(self):
        self.assertEqual(self.run_cli(GOOD_IMPORT), 0)
        bad = _read(GOOD_IMPORT)
        bad[0]["Variant Price"] = "abc"
        self.assertEqual(self.run_cli(_write(bad, TEMPLATE_COLUMNS)), 1)
        self.assertEqual(self.run_cli(os.path.join(TEMPLATE_DIR, "no-such-file.csv")), 2)


if __name__ == "__main__":
    unittest.main()
EOF
} > tests/catalog/test_check_upload.py

grep -n "formatting-scripts\|FORMATTED_TAG\|normalize" tests/catalog/test_sheet_transform.py tests/catalog/test_client_template_files.py tests/catalog/test_check_upload.py
```
Expected grep: no output. (Check `sed -n '14p' tests/formatting_scripts/test_client_template_files.py` is the `FILL_CSV = …` line and `sed -n '15p' tests/formatting_scripts/test_check_upload.py` is `GOOD_IMPORT = …` before relying on the ranges; adjust by one line if the file moved.)

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | grep -m3 "Error"` → `ModuleNotFoundError: No module named 'catalog.client_sheet.transform'`.

- [ ] **Step 2: Move the code and the template**

```bash
cp -R formatting-scripts/client-template catalog/client_sheet/template
rm catalog/client_sheet/template/generate_expected.py
sed -i '' -e 's|formatting-scripts/columns.py:TEMPLATE_COLUMNS|catalog/core/columns.py:TEMPLATE_COLUMNS|' \
          -e 's|formatting-scripts/handles.py:slugify|catalog/core/handles.py:slugify|' \
          catalog/client_sheet/template/import-tab-formula.txt
grep -rn "formatting-scripts" catalog/client_sheet/template || echo "template clean"

sed -e 's/^from columns import/from catalog.core.columns import/' \
    -e 's/^from handles import/from catalog.core.handles import/' \
    -e 's/^from taxonomy import/from catalog.core.taxonomy import/' \
    -e 's/run.py does not import it\./The pipeline does not import it./' \
    formatting-scripts/sheet_transform.py > catalog/client_sheet/transform.py

sed -e '/^sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))$/d' \
    -e 's/^from columns import/from catalog.core.columns import/' \
    -e 's/^from sheet_transform import/from catalog.client_sheet.transform import/' \
    -e 's/^from taxonomy import/from catalog.core.taxonomy import/' \
    -e 's|    python3 formatting-scripts/check_upload.py <csv>|    python3 -m catalog check-upload <csv>|' \
    formatting-scripts/check_upload.py > catalog/client_sheet/check.py
```

In `catalog/client_sheet/check.py`, replace the CLI wrapper:
```python
def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().split("\n\n")[-2].strip(), file=sys.stderr)
        print(f"\nusage: {os.path.basename(sys.argv[0])} <csv>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    try:
```
with:
```python
def report(path) -> int:
    """Print the check for one file. 0 = clean, 1 = problems, 2 = unreadable."""
    try:
```
and delete the trailing block:
```python


if __name__ == "__main__":
    sys.exit(main())
```
Also delete the now-unused `#!/usr/bin/env python3` first line.

`catalog/client_sheet/generate_expected.py`:
```python
"""Regenerate template/client-upload-template.expected.csv from the scaffold.

    python3 -m catalog.client_sheet.generate_expected

Run after any taxonomy change, then re-run the tests. The expected file is the
answer key the manual sheet-build pass checks the spreadsheet's tab 2 against.
"""

import csv
from pathlib import Path

from catalog.client_sheet.transform import fill_rows_to_import_rows
from catalog.core.columns import TEMPLATE_COLUMNS

TEMPLATE_DIR = Path(__file__).parent / "template"
FILL_CSV = TEMPLATE_DIR / "client-upload-template.csv"
EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.expected.csv"


def main() -> None:
    with open(FILL_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    produced = fill_rows_to_import_rows(rows)
    with open(EXPECTED_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        writer.writerows(produced)
    print(f"wrote {EXPECTED_CSV} ({len(produced)} rows)")


if __name__ == "__main__":
    main()
```

`catalog/client_sheet/command.py`:
```python
"""`python3 -m catalog check-upload <csv>` — check a filled client upload sheet
(either tab) before it is imported. Exit 0 clean, 1 problems, 2 unreadable."""

from catalog.client_sheet.check import report


def register(subparsers) -> None:
    p = subparsers.add_parser("check-upload", help="check a client upload-sheet CSV before importing it")
    p.add_argument("csv", help="the fill tab or the Shopify import tab, downloaded as CSV")
    p.set_defaults(func=lambda args: report(args.csv))
```
Register in `catalog/cli.py`: add `from catalog.client_sheet import command as client_sheet_command` and append `client_sheet_command` to `COMMANDS`.

Note: `cli.main` returns `args.func(args) or 0`, so a `report()` result of `0` stays `0` and `1`/`2` pass through.

- [ ] **Step 3: Run the suite** → `OK`; `python3 -m catalog check-upload catalog/client_sheet/template/sheet-export.csv; echo "exit $?"` → `✓ nothing wrong…` and `exit 0`. `git status --short catalog/client_sheet/template` shows no modification to `client-upload-template.expected.csv` after the generator test ran.

- [ ] **Step 4: Commit**

```bash
git add catalog/client_sheet catalog/cli.py tests/catalog/test_sheet_transform.py \
        tests/catalog/test_client_template_files.py tests/catalog/test_check_upload.py
git commit -m "feat(catalog): client upload sheet tooling in catalog.client_sheet + check-upload command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 2 (optional — confirm at review): Plan 1's deferred minors

Each sub-step is its own RED → GREEN; commit once at the end.

**Files:**
- Modify: `catalog/shopify/queries/products.graphql`, `catalog/shopify/reader.py`, `catalog/audit/run.py`, `catalog/audit/command.py`, `catalog/core/csv_io.py`, `catalog/core/registry.py`, `catalog/tmdb/client.py`, `catalog/tmdb/match.py`, `catalog/apply/merge.py`, `catalog/audit/resolvers.py` (docstring)
- Test: `tests/catalog/test_reader.py`, `tests/catalog/test_audit_run.py`, `tests/catalog/test_audit_command.py`, `tests/catalog/test_registry.py`, `tests/catalog/test_client.py`, `tests/catalog/test_match.py`, `tests/catalog/test_apply_merge.py`

- [ ] **Step 1: First image, not first media**

Test (add to `TestNodeToRow` in `tests/catalog/test_reader.py`):
```python
    def test_first_image_is_used_when_a_video_comes_first(self):
        r = node_to_row(node(media={"nodes": [{}, {"image": {"url": "https://cdn/2.jpg", "altText": "B"}}]}))
        self.assertEqual((r["Image Src"], r["Image Alt Text"]), ("https://cdn/2.jpg", "B"))
```
RED, then in `products.graphql` change `media(first: 1)` to `media(first: 5)`, and in `reader.py` replace
```python
    image = (media[0].get("image") if media and media[0] else None) or {}
```
with
```python
    image = next((m["image"] for m in media if m and m.get("image")), None) or {}
```
GREEN.

- [ ] **Step 2: Multi-variant products missing content are reported**

Test (add to `TestContentStep` in `tests/catalog/test_audit_run.py`):
```python
    def test_multi_variant_missing_content_is_a_manual_finding(self):
        result = run_audit([movie(**{"Image Src": "", "Image Alt Text": "", "Variant Count": "2"})], {}, None)
        self.assertIn(("poster-missing", "Image Src", MANUAL), rules_for(result, "rushmore-vhs-rental"))
```
RED, then in `run_audit` add after the `content_rows` loop:
```python
    for row in rows:
        if is_multi_variant(row):
            for field_name, needed in (("Image Src", needs_poster(row)), ("Body (HTML)", needs_description(row))):
                if needed:
                    findings.append(Finding(row["Handle"], (row.get("Title") or "").strip(), resolve_row(row).type or "",
                                            _CONTENT_RULE[field_name], field_name, "", "", MANUAL,
                                            "multi-variant product — fill by hand"))
```
GREEN.

- [ ] **Step 3: `--from-export` path check and BOM**

Tests (add to `TestAuditCommand` in `tests/catalog/test_audit_command.py`):
```python
    def test_missing_export_fails_before_creating_a_run(self):
        err = io.StringIO()
        argv = ["audit", "--from-export", str(self.export) + ".nope", "--runs-dir", str(self.runs),
                "--picker-dir", str(self.picker), "--skip-tmdb"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(argv), 2)
        self.assertEqual(list_runs(self.runs), [])

    def test_from_export_reads_a_bom_file(self):
        self.export.write_text("﻿" + self.export.read_text(encoding="utf-8"), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(command.run_command(self.args("--skip-tmdb"), today=date(2026, 9, 25)), 0)
```
RED, then: in `catalog/core/csv_io.py` `load_export`, open with `encoding="utf-8-sig"`; in `catalog/audit/command.py` `run_command`, before `new_run(...)` add:
```python
    if args.from_export and not Path(args.from_export).is_file():
        raise InputShapeError(f"export file not found: {args.from_export}")
```
(import `InputShapeError` from `catalog.errors`). GREEN.

- [ ] **Step 4: An invalid TMDB key stops the audit**

Tests — `tests/catalog/test_client.py`:
```python
    def test_401_raises_an_auth_error(self):
        import urllib.error
        from catalog.errors import CatalogError

        def urlopen(url, timeout):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

        fetch = make_fetcher("BAD", sleep_fn=lambda s: None, urlopen=urlopen)
        with self.assertRaises(CatalogError) as ctx:
            fetch("Rushmore", None)
        self.assertIn("TMDB_API_KEY", str(ctx.exception))
```
`tests/catalog/test_match.py` (add to `TestMatchProduct`):
```python
    def test_invalid_key_stops_the_audit(self):
        from catalog.errors import CatalogError

        def bad_key(query, year):
            raise CatalogError("TMDB rejected TMDB_API_KEY (401)")
        with self.assertRaises(CatalogError):
            match_product(row(), bad_key)
```
RED, then in `catalog/tmdb/client.py`:
```python
import urllib.error

from catalog.errors import CatalogError
```
and wrap the request:
```python
        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise CatalogError("TMDB rejected TMDB_API_KEY (HTTP 401) — check the key") from None
            raise
        finally:
            sleep_fn(REQUEST_DELAY_SECONDS)
```
and in `catalog/tmdb/match.py` `match_product`, add above `except Exception as exc:`:
```python
    except CatalogError:
        raise  # a bad key or similar: stop the whole run, don't mark every product failed
```
(import `CatalogError` from `catalog.errors`). GREEN.

- [ ] **Step 5: Malformed registry is a one-line error**

Test (`tests/catalog/test_registry.py`):
```python
class TestMalformedRegistry(unittest.TestCase):
    def test_bad_json_is_an_input_error(self):
        from catalog.errors import InputShapeError
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "_handle-index.json").write_text("{oops", encoding="utf-8")
            with self.assertRaises(InputShapeError):
                load_registry(tmp)
```
RED, then in `load_registry`:
```python
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputShapeError(f"{path} is not valid JSON ({exc})") from None
```
(import `InputShapeError`). GREEN.

- [ ] **Step 6: Narrower auth hint, clearer "resolved" wording, escaped overviews**

Tests:
- `tests/catalog/test_reader.py` (`TestRunCliQuery`):
```python
    def test_a_non_auth_failure_mentioning_author_is_not_called_auth(self):
        with self.fake_run(1, stderr="Field 'author' doesn't exist on type 'Product'"):
            with self.assertRaises(ShopifyError) as ctx:
                reader.run_cli_query("s", reader.QUERY_PATH, {"cursor": None})
        self.assertNotIn("not authenticated", str(ctx.exception))
```
- `tests/catalog/test_audit_run.py`: in `test_legacy_resolved_but_still_missing` change `self.assertIn("old pipeline", finding.detail)` to `self.assertIn("marked resolved", finding.detail)`, and add to `TestContentStep`:
```python
    def test_overview_html_is_escaped(self):
        row = movie(**{"Body (HTML)": ""})
        result = run_audit([row], {}, fetcher({"Rushmore": [tmdb("Rushmore", 1998, overview="Tom & Jerry <3")]}))
        self.assertEqual(result.autofix["rushmore-vhs-rental"]["changes"]["Body (HTML)"], "<p>Tom &amp; Jerry &lt;3</p>")
```
- `tests/catalog/test_apply_merge.py` (`TestPicks`):
```python
    def test_pick_overview_is_escaped(self):
        c = changes_of(merge([row()], {}, [Pick("q", "the-thing", "tmdb", "", "A & B")], QUEUED))
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>A &amp; B</p>")
```
RED, then:
- `reader.py`: `_AUTH_HINTS = ("not logged in", "log in", "login", "authenticat", "unauthorized", "401", "403")`.
- `audit/run.py`: the `resolved` branch detail becomes `"marked resolved in the registry but still missing in Shopify"`; import `html` and build descriptions as `f"<p>{html.escape(overview, quote=False)}</p>"`.
- `apply/merge.py`: import `html`; `values["Body (HTML)"] = f"<p>{html.escape(body, quote=False)}</p>"`.
GREEN.

- [ ] **Step 7: Docstrings**

`catalog/core/csv_io.py` docstring → `"""CSV I/O shared by every stage: read a Shopify export (either barcode header spelling), write CSVs, group rows by handle."""`. `catalog/audit/resolvers.py` line 4 `with a human-readable reason that lands in issues.csv` → `with a human-readable reason that becomes an audit finding`.

- [ ] **Step 8: Run the suite and commit**

`python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK`.
```bash
git add catalog tests/catalog
git commit -m "fix(catalog): Plan 1 review minors — first image, multi-variant gaps, export/BOM, TMDB 401, registry JSON, auth hint, escaping

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 3: Delete the old code

**Files:**
- Delete: `formatting-scripts/`, `tests/formatting_scripts/`, `tests/data_cleanup/`, `tests/catalog/test_picker_page_seam.py`

- [ ] **Step 1: Delete**

```bash
git rm -r -q formatting-scripts tests/formatting_scripts tests/data_cleanup tests/catalog/test_picker_page_seam.py
rm -rf formatting-scripts tests/formatting_scripts tests/data_cleanup   # untracked leftovers (__pycache__, .DS_Store)
```

- [ ] **Step 2: Nothing may still depend on it**

```bash
git grep -n "formatting-scripts\|formatting_scripts" -- catalog tests scripts tools '*.py' '*.js' '*.sh' || echo "code clean"
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
```
Expected: `code clean` except the historical note in `catalog/tmdb/match.py`'s and `catalog/tmdb/candidates.py`'s / `catalog/picker/*.py` docstrings ("Moved from formatting-scripts/…"), `scripts/set-product-templates.sh` and `tools/review-picker/api/_github.js` (fixed in Task 4); suite `OK` with the baseline count minus the three seam tests.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove formatting-scripts/ and its tests — replaced by catalog/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 4: Docs and pointers

**Files:**
- Modify: `CLAUDE.md`, `tools/review-picker/README.md`, `tools/review-picker/api/_github.js`, `scripts/set-product-templates.sh`, `LIBIB_AUTOMATION_ROADMAP.md`, `LIBIB_MIGRATION_PROGRESS.md`, `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md` (§10 test command), `catalog/README.md` (client sheet section)

- [ ] **Step 1: `CLAUDE.md`**

```bash
python3 - <<'EOF'
from pathlib import Path
p = Path("CLAUDE.md"); s = p.read_text(encoding="utf-8")
edits = [
    ("The `formatting-scripts/` pipeline is the tooling.",
     "The `catalog/` pipeline is the tooling (`python3 -m catalog audit` → `picker push` → `apply`; see `catalog/README.md`)."),
    ("`formatting-scripts/client-template/` holds the sheet", "`catalog/client_sheet/template/` holds the sheet"),
    ("(`formatting-scripts/columns.py:TEMPLATE_COLUMNS`)", "(`catalog/core/columns.py:TEMPLATE_COLUMNS`; check a filled sheet with `python3 -m catalog check-upload <csv>`)"),
    ("formatting-scripts/             ← catalogue CSV normalizer + TMDB fill (see its README)",
     "catalog/                        ← catalogue pipeline: audit → picker push → apply → libib (see catalog/README.md)"),
    ("- Movie catalogue data pipeline (`formatting-scripts/`): resale + CircaOS CSV reformatting into a combined Shopify import, with a review-flagging pass for ambiguous rows",
     "- Movie catalogue pipeline (`catalog/`, rebuilt 2026-09-25): read-only Shopify audit, TMDB auto-fill, hosted review picker, narrow import CSVs, and Libib diff/prepare/fix"),
]
for old, new in edits:
    assert s.count(old) == 1, old[:60]
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("CLAUDE.md updated")
EOF
```

- [ ] **Step 2: `tools/review-picker/README.md`** — replace everything from `## Generating a new batch` to the end of the file with:

```markdown
## Adding products to the picker

The audit decides which products need the client; `picker push` publishes them:

```bash
python3 -m catalog audit                 # writes runs/<date>/review.json
python3 -m catalog picker push           # appends to ambiguous-queue / unmatched-queue, commits + pushes (on main)
```

New cards land in the two evergreen queues; `data/_handle-index.json` records every
handle ever queued so nothing is asked twice.

## Applying the client's picks

```bash
python3 -m catalog apply --dry-run       # reads picks from origin/main, shows the plan
python3 -m catalog apply                 # writes runs/<date>/import/*.csv to import in Shopify admin
```

See `catalog/README.md`.
```

- [ ] **Step 3: Code comments**

- `tools/review-picker/api/_github.js` line 1: `formatting-scripts/hosted_review_page.py` → `catalog/picker/queues.py`.
- `scripts/set-product-templates.sh` line 17: `formatting-scripts/normalize.py:is_non_catalogue_product` → `catalog/shopify/snapshot.py:exclusion_reason (its export-path fallback)`.

```bash
sed -i '' 's|formatting-scripts/hosted_review_page.py|catalog/picker/queues.py|' tools/review-picker/api/_github.js
sed -i '' 's|formatting-scripts/normalize.py:is_non_catalogue_product|catalog/shopify/snapshot.py:exclusion_reason (its export-path fallback)|' scripts/set-product-templates.sh
node -e "require('./tools/review-picker/api/_github.js')" && echo "js ok"
```

- [ ] **Step 4: Historical Libib docs, spec, catalog README**

Insert after the first heading line of `LIBIB_AUTOMATION_ROADMAP.md` and of `LIBIB_MIGRATION_PROGRESS.md`:
```markdown

> **2026-09-25:** the Libib scripts this doc names now live in `catalog/libib/` (`python3 -m catalog libib diff | prepare | mark-imported | fix | status`); `formatting-scripts/` was removed. The history below is unchanged.
```
In the spec §10 Testing, replace `python3 -m unittest discover -s tests/catalog -t .` with `python3 -m unittest discover -s tests/catalog -p "test_*.py"`.

Add to `catalog/README.md` before `## Tests`:
```markdown
## Client upload sheet (not a pipeline stage)

`catalog/client_sheet/template/` holds the client's Google Sheet scaffold, the tab-2
formula, `genre-mappings.csv` and the client guide.

    python3 -m catalog check-upload <sheet.csv>     # exit 0 clean, 1 problems, 2 unreadable
    python3 -m catalog.client_sheet.generate_expected   # after a taxonomy change
```

- [ ] **Step 5: No live doc tells anyone to run a deleted script**

```bash
git grep -n "formatting-scripts" -- CLAUDE.md README* catalog tools scripts LIBIB_*.md MEMBERSHIP-REMAINING-TASKS.md new-membership-approach.md
```
Expected: only the two dated notes added in Step 4 and the "Moved from formatting-scripts/…" docstrings.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md tools/review-picker/README.md tools/review-picker/api/_github.js scripts/set-product-templates.sh \
        LIBIB_AUTOMATION_ROADMAP.md LIBIB_MIGRATION_PROGRESS.md docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md \
        catalog/README.md
git commit -m "docs: point every live instruction at catalog/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 5: Final verification

- [ ] **Step 1: Everything runs**

```bash
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
(cd tools/review-picker && ls ../../tests/review_picker)   # JS tests untouched
python3 -m catalog --help
for c in audit "picker push" apply "libib diff" "libib prepare" "libib mark-imported" "libib fix" "libib status" check-upload; do
  python3 -m catalog $c --help > /dev/null && echo "ok: $c"
done
```
Expected: suite `OK`; `ok:` for all nine commands.

- [ ] **Step 2: Smoke run from an export (no network)**

```bash
EXPORT=$(ls done/9.2-products/products_export_1.csv 2>/dev/null || true)
[ -n "$EXPORT" ] && python3 -m catalog audit --from-export "$EXPORT" --skip-tmdb -q --runs-dir "$TMPDIR/catalog-smoke" \
  && cat "$(ls -d "$TMPDIR"/catalog-smoke/20* | tail -1)/run-report.txt"
```
Expected: a run report (or, if the export isn't on disk, skip and say so in the final message).

- [ ] **Step 3: Update the memory note** — edit `~/.claude/projects/-Users-liamparis-web-projects-personal-Little-Movie-Store-LMS-sandbox/memory/catalog-pipeline-rebuild.md` to say the rebuild is complete (all four plans merged), `formatting-scripts/` is gone, and keep the "run from repo root" / `.venv-libib` notes; update its `MEMORY.md` line to match.
