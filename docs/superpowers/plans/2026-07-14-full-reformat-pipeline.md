# Full Reformat Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single, store-agnostic orchestrator script that runs the existing resale (`reformat_movies.py`) and CircaOS (`circaos_reformat.py`) reformats against one export, merges their review reports, and produces a single combined upload file with review-flagged products tagged and passed through unchanged — so the whole process can be re-run against a different store's export (e.g. production) without manual work.

**Architecture:** A new script, `data-cleanup/run_full_reformat.py`, that imports and calls the two existing modules' already-tested `build_output(rows, fieldnames)` functions unchanged — neither existing module needs any modification. New logic is purely orchestration: merging two review-row lists with a `Batch` column, and building passthrough rows (every field preserved at its real current value, only `Tags` changed) for review-flagged products so they can safely ride along in the same combined CSV without Shopify's per-column blank-clears-the-field behavior wiping any of their data. Tested with Python's stdlib `unittest`, no new dependencies. CLI via stdlib `argparse`.

**Tech Stack:** Python 3 (stdlib only: `argparse`, `csv`, `unittest`, `pathlib`).

## Global Constraints

- CLI: `python3 data-cleanup/run_full_reformat.py <input_csv> [--outdir DIR]`. `--outdir` defaults to the input file's own directory.
- Neither `reformat_movies.py` nor `circaos_reformat.py` is modified by this plan — both already accept `(rows, fieldnames)` as parameters, so the orchestrator calls `reformat_movies.build_output(...)` and `circaos_reformat.build_output(...)` directly on the same input.
- Both `build_output()` calls independently insert the `Media format` column into `fieldnames` using the same rule against the same starting `fieldnames`, so their returned fieldnames lists are identical — use either as the shared output header (verify with an `assert` in `run()`).
- Review report (`needs-review.csv`) columns: `Handle, Title, Batch, Reason`, where `Batch` is `"resale"` or `"circaos"` depending on which script flagged the row.
- Combined upload (`combined-upload.csv`) = all resale output rows + all CircaOS output rows + a **passthrough** row-set for every review-flagged handle from both batches. Passthrough rows preserve every original field at its real current value (never blank a column that's present elsewhere in the file — Shopify's CSV import clears any column present in the file when a row's cell for that column is blank) and only change `Tags`: resale-review handles get `Needs Review` appended; CircaOS-review handles get `CircaOS Import` + `Needs Review` appended (neither duplicated if already present). Multi-row handles (a review-flagged product with bonus image rows, e.g. `conan-the-barbarian`) bring all their rows along; only the first row's `Tags` changes.
- Four output files written to `--outdir`: `reformatted-resale.csv`, `reformatted-circaos.csv`, `needs-review.csv`, `combined-upload.csv`.
- `data-cleanup/` is untracked in git (confirmed unchanged). Only the script and its tests get committed; generated CSVs stay untracked.

---

## File Structure

- `data-cleanup/run_full_reformat.py` — the new script. Imports `reformat_movies` and `circaos_reformat` as modules (both define a function literally named `build_output`, so they're called as `reformat_movies.build_output(...)` / `circaos_reformat.build_output(...)`, not imported by name), plus `FORMAT_COLUMN` and `group_rows_by_handle` from `reformat_movies`. Contains: CSV loading, tag-merging, review-row merging, passthrough-row building, combined-upload building, the four-file write step, and the `argparse`-based CLI entry point.
- `tests/data_cleanup/test_run_full_reformat.py` — unit tests for every function, plus one integration test of `run()`.
- `tests/data_cleanup/fixtures/full_export_sample.csv` — fixture with one row from each scenario: resale in-scope, resale review, CircaOS in-scope, CircaOS review with a bonus image row, and the Supercycle Plan skip case.

---

### Task 1: Tag merging and passthrough-row building

**Files:**
- Create: `data-cleanup/run_full_reformat.py` (module docstring, imports, constants, and the functions listed below only — `load_export`, `write_csv`, `run`, `main`, and the fixture/integration test come in Task 2)
- Test: `tests/data_cleanup/test_run_full_reformat.py` (test classes for these functions only)

**Interfaces:**
- Consumes: `FORMAT_COLUMN` from `data-cleanup/reformat_movies.py` (already exists, unchanged)
- Produces: `NEEDS_REVIEW_TAG: str`, `CIRCAOS_IMPORT_TAG: str`, `add_tags(existing_tags_str: str, tags_to_add: list[str]) -> str`, `merge_review_rows(resale_review_rows: list[dict], circaos_review_rows: list[dict]) -> list[dict]`, `build_passthrough_rows(handle: str, groups: dict[str, list[dict]], tags_to_add: list[str]) -> list[dict]`, `build_combined_upload(resale_output_rows: list[dict], circaos_output_rows: list[dict], resale_review_rows: list[dict], circaos_review_rows: list[dict], groups: dict[str, list[dict]]) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `tests/data_cleanup/test_run_full_reformat.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from run_full_reformat import (
    NEEDS_REVIEW_TAG,
    CIRCAOS_IMPORT_TAG,
    add_tags,
    merge_review_rows,
    build_passthrough_rows,
    build_combined_upload,
)
from reformat_movies import FORMAT_COLUMN


class TestAddTags(unittest.TestCase):
    def test_appends_multiple_tags(self):
        self.assertEqual(
            add_tags("Rental", [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG]),
            "Rental, CircaOS Import, Needs Review",
        )

    def test_does_not_duplicate_existing_tags(self):
        self.assertEqual(
            add_tags(f"Rental, {NEEDS_REVIEW_TAG}", [NEEDS_REVIEW_TAG]),
            f"Rental, {NEEDS_REVIEW_TAG}",
        )


class TestMergeReviewRows(unittest.TestCase):
    def test_adds_batch_column(self):
        resale = [{"Handle": "a", "Title": "A", "Reason": "no genre set"}]
        circaos = [{"Handle": "b", "Title": "B", "Reason": "no genre-like tag found in Tags"}]
        merged = merge_review_rows(resale, circaos)
        self.assertEqual(merged[0]["Batch"], "resale")
        self.assertEqual(merged[1]["Batch"], "circaos")
        self.assertEqual(merged[0]["Handle"], "a")
        self.assertEqual(merged[1]["Reason"], "no genre-like tag found in Tags")


class TestBuildPassthroughRows(unittest.TestCase):
    def test_single_row_handle_preserves_fields_and_appends_tag(self):
        groups = {
            "some-movie": [
                {"Handle": "some-movie", "Vendor": "VHS", "Tags": "Comedy, Floor Sale"}
            ]
        }
        rows = build_passthrough_rows("some-movie", groups, [NEEDS_REVIEW_TAG])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Vendor"], "VHS")
        self.assertEqual(rows[0]["Tags"], "Comedy, Floor Sale, Needs Review")

    def test_multi_row_handle_only_tags_first_row(self):
        groups = {
            "multi": [
                {"Handle": "multi", "Vendor": "VHS", "Tags": "Rental"},
                {"Handle": "multi", "Vendor": "", "Tags": ""},
            ]
        }
        rows = build_passthrough_rows("multi", groups, [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Tags"], "Rental, CircaOS Import, Needs Review")
        self.assertEqual(rows[1]["Tags"], "")
        self.assertEqual(rows[1]["Vendor"], "")

    def test_adds_blank_format_column_if_absent(self):
        groups = {"some-movie": [{"Handle": "some-movie", "Vendor": "VHS", "Tags": ""}]}
        rows = build_passthrough_rows("some-movie", groups, [NEEDS_REVIEW_TAG])
        self.assertEqual(rows[0][FORMAT_COLUMN], "")


class TestBuildCombinedUpload(unittest.TestCase):
    def test_combines_output_and_passthrough_review_rows(self):
        resale_output = [{"Handle": "resale-in-scope", "Tags": "Comedy"}]
        circaos_output = [{"Handle": "circaos-in-scope", "Tags": "Thriller, CircaOS Import"}]
        resale_review = [{"Handle": "resale-review", "Title": "R", "Reason": "no genre"}]
        circaos_review = [{"Handle": "circaos-review", "Title": "C", "Reason": "no tag"}]
        groups = {
            "resale-review": [{"Handle": "resale-review", "Vendor": "VHS", "Tags": "Action"}],
            "circaos-review": [{"Handle": "circaos-review", "Vendor": "DVD", "Tags": "Rental"}],
        }
        combined = build_combined_upload(
            resale_output, circaos_output, resale_review, circaos_review, groups
        )
        by_handle = {r["Handle"]: r for r in combined}
        self.assertEqual(len(combined), 4)
        self.assertEqual(by_handle["resale-in-scope"]["Tags"], "Comedy")
        self.assertEqual(by_handle["circaos-in-scope"]["Tags"], "Thriller, CircaOS Import")
        self.assertEqual(by_handle["resale-review"]["Tags"], "Action, Needs Review")
        self.assertEqual(by_handle["circaos-review"]["Tags"], "Rental, CircaOS Import, Needs Review")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_run_full_reformat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_full_reformat'`

- [ ] **Step 3: Write the module (this task's functions only)**

Create `data-cleanup/run_full_reformat.py`:

```python
"""Orchestrate the full movie-catalogue reformat pipeline: run both the
resale and CircaOS reformats against one export, merge their review reports,
and build a single combined upload file with review-flagged products tagged
and passed through unchanged.

See docs/superpowers/specs/2026-07-14-full-reformat-pipeline-design.md.
"""

from reformat_movies import FORMAT_COLUMN

NEEDS_REVIEW_TAG = "Needs Review"
CIRCAOS_IMPORT_TAG = "CircaOS Import"


def add_tags(existing_tags_str: str, tags_to_add: list[str]) -> str:
    existing = [t.strip() for t in existing_tags_str.split(",") if t.strip()]
    for t in tags_to_add:
        if t not in existing:
            existing.append(t)
    return ", ".join(existing)


def merge_review_rows(resale_review_rows: list[dict], circaos_review_rows: list[dict]) -> list[dict]:
    merged = []
    for r in resale_review_rows:
        merged.append({**r, "Batch": "resale"})
    for r in circaos_review_rows:
        merged.append({**r, "Batch": "circaos"})
    return merged


def build_passthrough_rows(handle: str, groups: dict, tags_to_add: list[str]) -> list[dict]:
    """Return this handle's original CSV rows, unchanged except Tags on the first row.

    Every other field is preserved at its real current value, since Shopify's
    CSV import clears any column present in the file when a row's cell for
    that column is blank — passthrough rows must never leave a column blank
    just because they don't need to change it.
    """
    group = groups[handle]
    out = []
    for i, r in enumerate(group):
        new_row = dict(r)
        if FORMAT_COLUMN not in new_row:
            new_row[FORMAT_COLUMN] = ""
        if i == 0:
            new_row["Tags"] = add_tags(r["Tags"], tags_to_add)
        out.append(new_row)
    return out


def build_combined_upload(
    resale_output_rows: list[dict],
    circaos_output_rows: list[dict],
    resale_review_rows: list[dict],
    circaos_review_rows: list[dict],
    groups: dict,
) -> list[dict]:
    combined = list(resale_output_rows) + list(circaos_output_rows)
    for r in resale_review_rows:
        combined.extend(build_passthrough_rows(r["Handle"], groups, [NEEDS_REVIEW_TAG]))
    for r in circaos_review_rows:
        combined.extend(
            build_passthrough_rows(r["Handle"], groups, [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG])
        )
    return combined
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_run_full_reformat.py -v`
Expected: all tests PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/run_full_reformat.py tests/data_cleanup/test_run_full_reformat.py
git commit -m "Add tag-merging and passthrough-row building for full reformat pipeline"
```

---

### Task 2: CSV loading, orchestration, and CLI

**Files:**
- Modify: `data-cleanup/run_full_reformat.py` (add `load_export`, `write_csv`, `run`, `main`, plus imports)
- Modify: `tests/data_cleanup/test_run_full_reformat.py` (add the integration test)
- Create: `tests/data_cleanup/fixtures/full_export_sample.csv`

**Interfaces:**
- Consumes: `merge_review_rows`, `build_combined_upload` (Task 1); `reformat_movies.build_output`, `circaos_reformat.build_output`, `group_rows_by_handle` from `reformat_movies.py`
- Produces: `load_export(path) -> tuple[list[str], list[dict]]`, `write_csv(path, fieldnames: list[str], rows: list[dict]) -> None`, `run(input_path, outdir) -> dict[str, int]` (keys: `resale_output`, `circaos_output`, `review`, `combined`), `main() -> None` (CLI entry point)

- [ ] **Step 1: Create the fixture CSV**

Create `tests/data_cleanup/fixtures/full_export_sample.csv`:

```csv
Handle,Title,Vendor,Product Category,Type,Tags,Option1 Name,Option1 Value,Option2 Name,Option2 Value,Variant SKU,Variant Barcode,Image Src,Image Position,Genre (product.metafields.shopify.genre)
simple-comedy-resale,Simple Comedy,VHS,Uncategorized,,"Comedy, Floor Sale",Genre,Comedy,,,,,https://img/1.jpg,1,
resale-review-row,Resale Review,VHS,Uncategorized,,"Action, Floor Sale",Title,Default Title,,,,,https://img/2.jpg,1,
simple-thriller-circaos,Simple Thriller,VHS,Uncategorized,,"Rental, Thriller",Condition,Standard,Serial Number,001A,191-VHSSIM-001A,191-VHSSIM-001A,https://img/3.jpg,1,
circaos-review-multi,Circaos Review Multi,VHS,Uncategorized,,Rental,Condition,Standard,Serial Number,001A,191-VHSCRM-001A,191-VHSCRM-001A,https://img/4a.jpg,1,
circaos-review-multi,,,,,,,,,,,,https://img/4b.jpg,2,
supercycle-membership,Supercycle Membership,,,Supercycle Plan,,,,,,,,,,
```

- [ ] **Step 2: Write the failing test**

Add to `tests/data_cleanup/test_run_full_reformat.py` (add imports and the new test class before `if __name__ == "__main__":`):

```python
import csv
import tempfile

from run_full_reformat import run

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "full_export_sample.csv"


class TestRun(unittest.TestCase):
    def test_writes_four_files_with_expected_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts = run(FIXTURE_PATH, tmp)
            outdir = Path(tmp)

            self.assertEqual(counts["resale_output"], 1)
            self.assertEqual(counts["circaos_output"], 1)
            self.assertEqual(counts["review"], 2)
            self.assertEqual(counts["combined"], 1 + 1 + 1 + 2)  # +2 for the multi-row review handle

            with open(outdir / "reformatted-resale.csv", newline="", encoding="utf-8") as f:
                resale_rows = list(csv.DictReader(f))
            self.assertEqual(resale_rows[0]["Handle"], "simple-comedy-resale")

            with open(outdir / "reformatted-circaos.csv", newline="", encoding="utf-8") as f:
                circaos_rows = list(csv.DictReader(f))
            self.assertEqual(circaos_rows[0]["Handle"], "simple-thriller-circaos")

            with open(outdir / "needs-review.csv", newline="", encoding="utf-8") as f:
                review_rows = list(csv.DictReader(f))
            batches = {r["Handle"]: r["Batch"] for r in review_rows}
            self.assertEqual(batches["resale-review-row"], "resale")
            self.assertEqual(batches["circaos-review-multi"], "circaos")

            with open(outdir / "combined-upload.csv", newline="", encoding="utf-8") as f:
                combined_rows = list(csv.DictReader(f))
            combined_handles = [r["Handle"] for r in combined_rows]
            self.assertIn("simple-comedy-resale", combined_handles)
            self.assertIn("simple-thriller-circaos", combined_handles)
            self.assertEqual(combined_handles.count("circaos-review-multi"), 2)
            self.assertNotIn("supercycle-membership", combined_handles)

            multi_rows = [r for r in combined_rows if r["Handle"] == "circaos-review-multi"]
            self.assertIn(NEEDS_REVIEW_TAG, multi_rows[0]["Tags"])
            self.assertIn(CIRCAOS_IMPORT_TAG, multi_rows[0]["Tags"])
            self.assertEqual(multi_rows[1]["Tags"], "")
```

Note: `Path` is already imported at the top of the test file from Task 1 — reuse it, don't re-import.

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_run_full_reformat.py -v`
Expected: FAIL with `ImportError: cannot import name 'run'`

- [ ] **Step 4: Add the orchestration and CLI code**

Add these imports at the very top of `data-cleanup/run_full_reformat.py`, above the existing `from reformat_movies import FORMAT_COLUMN` line:

```python
import argparse
import csv
from pathlib import Path

import reformat_movies
import circaos_reformat
from reformat_movies import group_rows_by_handle
```

(The file will then have two import lines referencing `reformat_movies`: the new `import reformat_movies` and `from reformat_movies import group_rows_by_handle` alongside the existing `from reformat_movies import FORMAT_COLUMN` — combine `group_rows_by_handle` into that existing line rather than adding a separate one, i.e. the final line reads `from reformat_movies import FORMAT_COLUMN, group_rows_by_handle`.)

Append to the end of `data-cleanup/run_full_reformat.py`:

```python
def load_export(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(input_path, outdir):
    fieldnames, rows = load_export(input_path)

    resale_fieldnames, resale_output_rows, resale_review_rows = reformat_movies.build_output(
        rows, fieldnames
    )
    circaos_fieldnames, circaos_output_rows, circaos_review_rows = circaos_reformat.build_output(
        rows, fieldnames
    )
    assert resale_fieldnames == circaos_fieldnames
    shared_fieldnames = resale_fieldnames

    groups = dict(group_rows_by_handle(rows))

    review_rows = merge_review_rows(resale_review_rows, circaos_review_rows)
    combined_rows = build_combined_upload(
        resale_output_rows, circaos_output_rows, resale_review_rows, circaos_review_rows, groups
    )

    outdir = Path(outdir)
    write_csv(outdir / "reformatted-resale.csv", shared_fieldnames, resale_output_rows)
    write_csv(outdir / "reformatted-circaos.csv", shared_fieldnames, circaos_output_rows)
    write_csv(outdir / "needs-review.csv", ["Handle", "Title", "Batch", "Reason"], review_rows)
    write_csv(outdir / "combined-upload.csv", shared_fieldnames, combined_rows)

    return {
        "resale_output": len(resale_output_rows),
        "circaos_output": len(circaos_output_rows),
        "review": len(review_rows),
        "combined": len(combined_rows),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run the full movie-catalogue reformat pipeline."
    )
    parser.add_argument("input_csv", help="Path to the full product export CSV")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write output files (default: input file's directory)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    outdir = Path(args.outdir) if args.outdir else input_path.parent

    counts = run(input_path, outdir)
    print(f"Reformatted resale: {counts['resale_output']} rows -> {outdir / 'reformatted-resale.csv'}")
    print(f"Reformatted circaos: {counts['circaos_output']} rows -> {outdir / 'reformatted-circaos.csv'}")
    print(f"Needs review: {counts['review']} rows -> {outdir / 'needs-review.csv'}")
    print(f"Combined upload: {counts['combined']} rows -> {outdir / 'combined-upload.csv'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_run_full_reformat.py -v`
Expected: all tests PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add data-cleanup/run_full_reformat.py tests/data_cleanup/test_run_full_reformat.py tests/data_cleanup/fixtures/full_export_sample.csv
git commit -m "Add CSV orchestration and CLI for full reformat pipeline"
```

---

### Task 3: Run against the real export and verify

**Files:**
- None created/modified — this task runs the script from Task 2 against the real data and manually verifies the result.

**Interfaces:**
- Consumes: `main`/`run` from `data-cleanup/run_full_reformat.py`

- [ ] **Step 1: Run the script against the real export**

Run: `python3 data-cleanup/run_full_reformat.py data-cleanup/current-movies-export.csv`

Expected output (verified during planning against the real file):
```
Reformatted resale: 1846 rows -> data-cleanup/reformatted-resale.csv
Reformatted circaos: 696 rows -> data-cleanup/reformatted-circaos.csv
Needs review: 50 rows -> data-cleanup/needs-review.csv
Combined upload: 2593 rows -> data-cleanup/combined-upload.csv
```

- [ ] **Step 2: Verify the review report's batch split**

Run:

```bash
python3 -c "
import csv
from collections import Counter
with open('data-cleanup/needs-review.csv', newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
print('total review rows:', len(rows))
print('by batch:', Counter(r['Batch'] for r in rows))
"
```

Expected: `total review rows: 50`, `by batch: Counter({'resale': 29, 'circaos': 21})`.

- [ ] **Step 3: Spot-check the combined upload's tagging for both review batches and one in-scope product each**

Run:

```bash
python3 -c "
import csv
with open('data-cleanup/combined-upload.csv', newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
by_handle = {}
for r in rows:
    by_handle.setdefault(r['Handle'], []).append(r)
for h in ['tornado', 'confessions-of-a-police-captain', 'escape-clause']:
    for r in by_handle[h]:
        print(h, '| Vendor:', r['Vendor'], '| Opt1:', r['Option1 Name'], '/', r['Option1 Value'], '| Tags:', r['Tags'])
"
```

Expected: `tornado` (resale review) shows its original `Vendor`/`Option1` untouched with `Tags` ending in `Needs Review`; `confessions-of-a-police-captain` (CircaOS review) shows its original fields untouched with `Tags` ending in `CircaOS Import, Needs Review`; `escape-clause` (CircaOS in-scope) shows the full reformat (`Vendor: Little Movie Store`, `Option1: Title / Default Title`) with `Tags` ending in `CircaOS Import`.

- [ ] **Step 4: No commit this step**

The four generated CSVs live in `data-cleanup/`, which is untracked in git. Leave them untracked, matching the existing pattern. Nothing to commit for this task.
