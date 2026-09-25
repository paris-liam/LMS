# Catalog Pipeline — Plan 3: Libib — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship stage 4: `python3 -m catalog libib diff | prepare | mark-imported | fix | status` — compare Libib's exports with the latest audit snapshot's rentals, prepare import batches for missing items, report drift, and (only when explicitly run) fix Libib items in the browser.

**Architecture:** A new `catalog/libib/` stage package: pure `fields`/`columns`/`exports`/`diff` modules (fully tested), `state` for `libib-sync/_state.json`, `prepare` for batch building, `browser` (Playwright page operations, moved verbatim) and `fix` (the runner + a pure report-to-state function), plus `command.py`. A shared `core/barcodes.py` holds the rental-barcode rule the audit and the diff both need. Replaces `formatting-scripts/libib_*.py` (deleted in Plan 4).

**Tech Stack:** Python 3.10+ standard library; Playwright only inside `libib fix` (installed in `.venv-libib/`); `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md` — §7 (Libib), §8 (logging), §9 (approval). Plans 1–2 are merged (`core/plan.py`, `core/runs.py`, the audit snapshot).

## Global Constraints

- Standard library everywhere except `catalog/libib/browser.py` and the runner inside `catalog/libib/fix.py`, which import Playwright **lazily** (inside functions). Nothing else may import `browser`.
- `libib fix` runs under the Playwright venv: `.venv-libib/bin/python -m catalog libib fix …`.
- Libib credentials only from `LIBIB_EMAIL` / `LIBIB_PASSWORD`. No credentials in source (`libib_sync_fix.py` hardcoded them).
- Run from the repo root. Tests: `python3 -m unittest discover -s tests/catalog -p "test_*.py"` (baseline at plan start = the count Plan 2 ended with; record it in Task 0) and the old suite (348) stay green. Do not modify `formatting-scripts/` or `tests/formatting_scripts/`.
- Join key: Shopify `Variant Barcode` == Libib `call_number`. Rentals whose barcode fails the rental rules (8 digits, unique across all movies) are `blocked` and never diffed.
- `diff` writes only its run folder (`runs/<id>/libib/`) and `libib-sync/_state.json` (promotions + one-time `poster_src` migration), saving a copy of the previous state into the run folder first. It asks no approval.
- `prepare`, `mark-imported`, `fix` show a Plan and ask (`--dry-run`, `--yes`, refuse without a terminal) — `core/plan.py`.
- Orphans are never deleted automatically.
- Tests never touch Libib, the network, or the real `libib-sync/`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS
  ```

## Decisions made while planning (confirm at review)

1. **Items with no `call_number` are matched on their copy `barcode`.** Libib's 9.20 export has items imported before call numbers existed (barcode only). Without this fallback those rentals would look missing and `prepare` would import duplicates. Such a match reports a `call_number` drift row, which the fixer cannot fix (it searches by call number) — it is listed for a manual fix.
2. **`diff` only reads the `Rental Library` collection** (`--collection` overrides). Libib exports carry a `collection` column.
3. **`diff` promotes `queued`, `imported` and `needs-review` handles that are now in sync to `done`** (the spec named only `imported`): an item fixed by hand, or imported but never marked, is just as done.
4. **A rental whose state says `done` but which is missing from Libib becomes eligible again** (the item was deleted in Libib). Only `queued` / `imported` (in flight) are held back.
5. **`fix` maps call numbers to handles through the snapshot** (every unblocked rental barcode is unique), so batch fixes and drift fixes share one code path, and records `poster_src` from the snapshot's `Image Src` when a poster upload succeeds.
6. **`diff` backs up `_state.json` into `runs/<id>/libib/state-before.json` before saving**, so a bad diff can be rolled back without git archaeology.
7. **The rental-barcode rule moves to `core/barcodes.py`**; the audit's `rules.py` imports it (no behaviour change).

## Review Focus

1. **A Libib item with no call number whose barcode is a live rental's** → matched, `call_number` drift, never `eligible`. → Task 5 test `test_item_without_call_number_matches_on_barcode`.
2. **Two Libib items with one call number** → both listed as duplicates in orphans, the rental not diffed, not eligible. → Task 5 test `test_duplicate_call_number_lists_both_items`.
3. **A rental already queued/imported but not yet in the export** → not offered again by `prepare`. → Task 5 test `test_in_flight_rental_is_not_eligible`, Task 9 test `test_prepare_skips_handles_queued_since_the_diff`.
4. **Playwright missing from the Python running `fix`** → clear error naming `.venv-libib`, nothing edited. → Task 7 test `test_run_fixer_without_playwright_names_the_venv`.
5. **Export files with a BOM, a missing column, or a wrong path** → a one-line error naming the file, not a traceback. → Task 3 tests `test_bom_header_is_read`, `test_missing_column_names_the_file`, `test_missing_file_is_an_input_error`.

---

### Task 0: Branch setup

- [ ] **Step 1**

```bash
git status --short                      # must be empty
git checkout fix/redirect-all-collection
git checkout -b refactor/catalog-pipeline-3
python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -3
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -3
ls .venv-libib/bin/python && .venv-libib/bin/python -c "import playwright; print('playwright ok')"
```
Expected: both suites `OK` (record the catalog count in the ledger as this plan's baseline); `playwright ok`.

---

### Task 1: Shared rental-barcode rule — `core/barcodes.py`

**Files:**
- Create: `catalog/core/barcodes.py`
- Modify: `catalog/audit/rules.py` (use it)
- Test: `tests/catalog/test_barcodes.py`

**Interfaces:**
- Produces: `catalog.core.barcodes`: `RENTAL_BARCODE` (compiled `^[0-9]{8}$`), `is_rental_barcode(value) -> bool` (strips first), `barcode_owners(rows) -> dict[str, list[str]]` (stripped barcode → handles, blanks skipped).

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_barcodes.py`:

```python
import unittest

from catalog.core.barcodes import barcode_owners, is_rental_barcode


class TestBarcodes(unittest.TestCase):
    def test_rental_barcode(self):
        self.assertTrue(is_rental_barcode("01577790"))
        self.assertTrue(is_rental_barcode(" 01577790 "))
        for bad in ("", "1577790", "0157779A", "015777901", None):
            self.assertFalse(is_rental_barcode(bad))

    def test_owners(self):
        rows = [{"Handle": "a", "Variant Barcode": "1"}, {"Handle": "b", "Variant Barcode": " 1 "},
                {"Handle": "c", "Variant Barcode": ""}]
        self.assertEqual(barcode_owners(rows), {"1": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError: No module named 'catalog.core.barcodes'`.

- [ ] **Step 2: Implement `catalog/core/barcodes.py`**

```python
"""The rental barcode rule, shared by the audit and the Libib diff. A rental's
barcode is its Libib call number, so it must be exactly 8 digits and appear on
no other movie (Rental or Floor Sale)."""

import re

RENTAL_BARCODE = re.compile(r"^[0-9]{8}$")


def is_rental_barcode(value) -> bool:
    return bool(RENTAL_BARCODE.match((value or "").strip()))


def barcode_owners(rows: list[dict]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if barcode:
            owners.setdefault(barcode, []).append(row.get("Handle", ""))
    return owners
```

- [ ] **Step 3: Use it in `catalog/audit/rules.py`**

Delete the line `import re` and the line `RENTAL_BARCODE = re.compile(r"^[0-9]{8}$")`, and add to the imports:
```python
from catalog.core.barcodes import RENTAL_BARCODE, barcode_owners
```
In `check_catalogue`, replace:
```python
    by_barcode: dict[str, list[str]] = {}
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if barcode:
            by_barcode.setdefault(barcode, []).append(row.get("Handle", ""))
```
with:
```python
    by_barcode = barcode_owners(rows)
```

- [ ] **Step 4: Run the suite** — `python3 -m unittest discover -s tests/catalog -p "test_*.py" 2>&1 | tail -2` → `OK` (every audit rules test unchanged and passing).

- [ ] **Step 5: Commit**

```bash
git add catalog/core/barcodes.py catalog/audit/rules.py tests/catalog/test_barcodes.py
git commit -m "refactor(catalog): rental barcode rule shared in core.barcodes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 2: Libib fields and import columns

**Files:**
- Create: `catalog/libib/__init__.py` (empty), `catalog/libib/fields.py`, `catalog/libib/columns.py`
- Test: `tests/catalog/test_libib_fields.py`

**Interfaces:**
- Produces:
  - `catalog.libib.fields`: `REQUIRED_FIELDS: dict[str, str]`, `is_rental(row) -> bool` (exactly one canonical type and it is Rental), `is_complete(row)`, `missing_fields(row) -> list[str]`, `expected_title(row)`, `expected_description(row)`, `expected_tags_string(row)`, `normalized_tag_set(tags) -> set[str]`.
  - `catalog.libib.columns`: `LIBIB_MOVIE_COLUMNS` (26 names), `READY_COLUMNS = ["call_number", "title", "description", "tags", "image_path"]`, `import_row(row) -> dict`, `ready_row(row, image_path: str) -> dict`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_fields.py`:

```python
import unittest

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS, import_row, ready_row
from catalog.libib.fields import (
    expected_description, expected_tags_string, expected_title, is_complete, is_rental, missing_fields,
    normalized_tag_set,
)


def rental(**overrides):
    base = {"Handle": "jaws-vhs-rental", "Title": "  Jaws ", "Body (HTML)": "<p>A  shark.</p>\n",
            "Image Src": "https://cdn/j.jpg", "Variant Barcode": "01577790", "Variant Price": "0.00",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", GENRE_METAFIELD: "horror; thriller"}
    base.update(overrides)
    return base


class TestFields(unittest.TestCase):
    def test_is_rental(self):
        self.assertTrue(is_rental(rental()))
        self.assertTrue(is_rental(rental(Tags="rental, VHS")))  # alias spelling still a rental
        self.assertFalse(is_rental(rental(Tags="Floor Sale, VHS")))
        self.assertFalse(is_rental(rental(Tags="Rental, Floor Sale")))  # type conflict: not in scope
        self.assertFalse(is_rental(rental(Tags="VHS")))

    def test_complete_and_missing(self):
        self.assertTrue(is_complete(rental()))
        self.assertEqual(missing_fields(rental(**{"Image Src": "", GENRE_METAFIELD: ""})), ["poster", "genre"])

    def test_expected_values(self):
        self.assertEqual(expected_title(rental()), "Jaws")
        self.assertEqual(expected_description(rental()), "A shark.")
        self.assertEqual(expected_tags_string(rental()), "VHS, horror; thriller")

    def test_normalized_tag_set_matches_libib_reformatting(self):
        self.assertEqual(normalized_tag_set("VHS, Horror"), normalized_tag_set("horror,vhs"))
        self.assertEqual(normalized_tag_set(""), set())


class TestColumns(unittest.TestCase):
    def test_import_row(self):
        out = import_row(rental())
        self.assertEqual(list(out), LIBIB_MOVIE_COLUMNS)
        self.assertEqual((out["title"], out["description"], out["tags"], out["price"], out["copies"], out["call_number"]),
                         ("Jaws", "A shark.", "VHS, horror; thriller", "0.00", "1", "01577790"))
        self.assertEqual(out["upc_isbn10"], "")

    def test_ready_row(self):
        out = ready_row(rental(), "libib-sync/batch-0001/01577790.jpg")
        self.assertEqual(list(out), READY_COLUMNS)
        self.assertEqual(out["image_path"], "libib-sync/batch-0001/01577790.jpg")


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError: No module named 'catalog.libib'`.

- [ ] **Step 2: Implement `catalog/libib/fields.py`**

```python
"""What "1:1 with Shopify" means for a Libib item (moved from
formatting-scripts/libib_fields.py). Shopify is authoritative: a rental is
eligible for Libib once every REQUIRED_FIELDS column is filled, and the same
expected_* values define drift."""

import re

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.taxonomy import canonical_type
from catalog.core.text import norm_ws, strip_html

# Libib concept -> snapshot column
REQUIRED_FIELDS = {
    "title": "Title",
    "poster": "Image Src",
    "barcode": "Variant Barcode",
    "description": "Body (HTML)",
    "genre": GENRE_METAFIELD,
    "tags": "Tags",
    "format": "Vendor",
}


def is_rental(row: dict) -> bool:
    types = {canonical_type(t) for t in (row.get("Tags") or "").split(",")} - {None}
    return types == {"Rental"}


def is_complete(row: dict) -> bool:
    return all((row.get(col) or "").strip() for col in REQUIRED_FIELDS.values())


def missing_fields(row: dict) -> list[str]:
    return [name for name, col in REQUIRED_FIELDS.items() if not (row.get(col) or "").strip()]


def expected_title(row: dict) -> str:
    return norm_ws(row.get("Title", ""))


def expected_description(row: dict) -> str:
    return norm_ws(strip_html(row.get("Body (HTML)", "")))


def expected_tags_string(row: dict) -> str:
    """What goes in Libib's `tags`: the format (Vendor) and the genre handles."""
    vendor = (row.get("Vendor") or "").strip()
    genre = (row.get(GENRE_METAFIELD) or "").strip()
    return ", ".join(p for p in (vendor, genre) if p)


def normalized_tag_set(tags: str) -> set[str]:
    """Libib lowercases and reorders tags on save ("VHS, Comedy" -> "comedy,vhs"),
    so tags compare as a normalised set."""
    return {t.strip().lower() for t in re.split(r"[,\n]", tags or "") if t.strip()}
```

- [ ] **Step 3: Implement `catalog/libib/columns.py`**

```python
"""Libib's Movie CSV import template and the ready.csv the fixer reads."""

from catalog.libib.fields import expected_description, expected_tags_string, expected_title

LIBIB_MOVIE_COLUMNS = [
    "title", "creators", "description", "upc_isbn10", "ean_isbn13", "number_of_discs", "ensemble",
    "aspect_ratio", "tags", "notes", "group", "price", "added", "publisher", "publish_date", "length_of",
    "copies", "call_number", "ddc", "lcc", "rating", "review", "review_created", "status", "began_date",
    "completed_date",
]
READY_COLUMNS = ["call_number", "title", "description", "tags", "image_path"]


def import_row(row: dict) -> dict:
    """One Libib import row per physical copy. The UPC/EAN fields stay blank —
    Force Import Mode needs only a title; the barcode goes in call_number."""
    out = {column: "" for column in LIBIB_MOVIE_COLUMNS}
    out.update({
        "title": expected_title(row),
        "description": expected_description(row),
        "tags": expected_tags_string(row),
        "price": (row.get("Variant Price") or "").strip(),
        "copies": "1",
        "call_number": (row.get("Variant Barcode") or "").strip(),
    })
    return out


def ready_row(row: dict, image_path: str) -> dict:
    return {
        "call_number": (row.get("Variant Barcode") or "").strip(),
        "title": expected_title(row),
        "description": expected_description(row),
        "tags": expected_tags_string(row),
        "image_path": image_path,
    }
```

- [ ] **Step 4: Run the suite** → `OK`.

- [ ] **Step 5: Commit**

```bash
git add catalog/libib tests/catalog/test_libib_fields.py
git commit -m "feat(catalog): Libib field rules and import/ready columns

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 3: Libib export loader — `libib/exports.py`

**Files:**
- Create: `catalog/libib/exports.py`
- Test: `tests/catalog/test_libib_exports.py`

**Interfaces:**
- Consumes: `InputShapeError`.
- Produces: `catalog.libib.exports`: `DEFAULT_COLLECTION = "Rental Library"`, `load_libib(barcode_export, collection_export, collection=DEFAULT_COLLECTION) -> list[dict]` — each item `{"id", "title", "barcode", "call_number", "tags", "description", "collection"}` (barcode and call_number stripped; description joined from the collection export by `id`). `collection=None` keeps every collection.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_exports.py`:

```python
import tempfile
import unittest
from pathlib import Path

from catalog.errors import InputShapeError
from catalog.libib.exports import load_libib

BARCODE_HEADER = "id,item_type,barcode,title,collection,tags,call_number"
COLLECTION_HEADER = "id,item_type,title,collection,description,call_number"


class TestLoadLibib(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.barcodes = self.dir / "barcodes.csv"
        self.collection = self.dir / "collection.csv"
        self.barcodes.write_text("\n".join([
            BARCODE_HEADER,
            'a1,movie, 01577790 ,Jaws,Rental Library,"vhs, horror",01577790',
            "a2,movie,2010000000007,Old Item,Rental Library,,",
            "a3,movie,09999999,Elsewhere,Untracked,,09999999",
        ]) + "\n", encoding="utf-8")
        self.collection.write_text("\n".join([
            COLLECTION_HEADER,
            'a1,movie,Jaws,Rental Library,"A shark,\nat sea.",01577790',
            "a2,movie,Old Item,Rental Library,,",
        ]) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_joins_description_and_filters_the_collection(self):
        items = load_libib(self.barcodes, self.collection)
        self.assertEqual([i["id"] for i in items], ["a1", "a2"])
        self.assertEqual(items[0]["barcode"], "01577790")
        self.assertEqual(items[0]["description"], "A shark,\nat sea.")
        self.assertEqual(items[1]["call_number"], "")
        self.assertEqual(items[1]["description"], "")

    def test_all_collections(self):
        self.assertEqual(len(load_libib(self.barcodes, self.collection, collection=None)), 3)

    def test_bom_header_is_read(self):
        self.barcodes.write_text("﻿" + self.barcodes.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(len(load_libib(self.barcodes, self.collection)), 2)

    def test_missing_column_names_the_file(self):
        self.barcodes.write_text("id,title\na1,Jaws\n", encoding="utf-8")
        with self.assertRaises(InputShapeError) as ctx:
            load_libib(self.barcodes, self.collection)
        self.assertIn("barcodes.csv", str(ctx.exception))
        self.assertIn("call_number", str(ctx.exception))

    def test_missing_file_is_an_input_error(self):
        with self.assertRaises(InputShapeError):
            load_libib(self.dir / "nope.csv", self.collection)


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError: No module named 'catalog.libib.exports'`.

- [ ] **Step 2: Implement `catalog/libib/exports.py`**

```python
"""Read Libib's two exports and join them. The item/barcode export has the copy
`barcode` but no `description`; the collection export has `description` but
no copy barcode — both are needed (see the 2026-09-18 notes)."""

import csv
from pathlib import Path

from catalog.errors import InputShapeError

DEFAULT_COLLECTION = "Rental Library"
BARCODE_REQUIRED = ("id", "title", "barcode", "call_number", "tags", "collection")
COLLECTION_REQUIRED = ("id", "description")


def _read(path, required: tuple[str, ...]) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise InputShapeError(f"Libib export not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise InputShapeError(f"{path.name} is missing column(s) {', '.join(missing)} — is it the right Libib export?")
        return list(reader)


def load_libib(barcode_export, collection_export, collection: str | None = DEFAULT_COLLECTION) -> list[dict]:
    items_rows = _read(barcode_export, BARCODE_REQUIRED)
    descriptions = {r["id"]: r.get("description") or "" for r in _read(collection_export, COLLECTION_REQUIRED)}
    items = []
    for r in items_rows:
        item_collection = (r.get("collection") or "").strip()
        if collection and item_collection != collection:
            continue
        items.append({
            "id": r["id"],
            "title": r.get("title") or "",
            "barcode": (r.get("barcode") or "").strip(),
            "call_number": (r.get("call_number") or "").strip(),
            "tags": r.get("tags") or "",
            "description": descriptions.get(r["id"], ""),
            "collection": item_collection,
        })
    return items
```

- [ ] **Step 3: Run the suite** → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/exports.py tests/catalog/test_libib_exports.py
git commit -m "feat(catalog): Libib export loader (barcode + collection join, collection filter)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 4: Sync state — `libib/state.py`

**Files:**
- Create: `catalog/libib/state.py`
- Test: `tests/catalog/test_libib_state.py`

**Interfaces:**
- Produces: `catalog.libib.state`: `STATE_FILENAME = "_state.json"`, `IN_FLIGHT = ("queued", "imported")`, `state_path(sync_dir)`, `load_state(sync_dir) -> dict` (missing → `{}`; bad JSON → `InputShapeError`), `save_state(sync_dir, state)`, `set_status(state, handle, status, **fields)`, `counts_by_status(state) -> dict`, `migrate_poster_src(state, rows_by_handle) -> int`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_state.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from catalog.errors import InputShapeError
from catalog.libib.state import counts_by_status, load_state, migrate_poster_src, save_state, set_status


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_and_missing_file(self):
        self.assertEqual(load_state(self.dir), {})
        state = {}
        set_status(state, "a", "queued", batch="batch-0001", call_number="01577790")
        save_state(self.dir, state)
        self.assertEqual(load_state(self.dir), {"a": {"status": "queued", "batch": "batch-0001",
                                                      "call_number": "01577790"}})

    def test_bad_json_is_an_input_error(self):
        (self.dir / "_state.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(InputShapeError):
            load_state(self.dir)

    def test_counts(self):
        self.assertEqual(counts_by_status({"a": {"status": "done"}, "b": {"status": "done"}, "c": {"status": "queued"}}),
                         {"done": 2, "queued": 1})

    def test_migrate_poster_src_from_old_poster_confirmed(self):
        state = {"a": {"status": "done", "poster_confirmed": True},
                 "b": {"status": "done", "poster_confirmed": False},
                 "c": {"status": "done", "poster_confirmed": True, "poster_src": "https://kept"},
                 "d": {"status": "done", "poster_confirmed": True}}
        rows = {"a": {"Image Src": "https://cdn/a.jpg"}, "b": {"Image Src": "https://cdn/b.jpg"},
                "c": {"Image Src": "https://cdn/c.jpg"}}
        self.assertEqual(migrate_poster_src(state, rows), 1)
        self.assertEqual(state["a"]["poster_src"], "https://cdn/a.jpg")
        self.assertNotIn("poster_src", state["b"])
        self.assertEqual(state["c"]["poster_src"], "https://kept")
        self.assertNotIn("poster_src", state["d"])  # not in the snapshot


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError`.

- [ ] **Step 2: Implement `catalog/libib/state.py`**

```python
"""What only we know about each rental's Libib sync — libib-sync/_state.json:

    {"<handle>": {"status": "queued" | "imported" | "done" | "needs-review",
                  "batch": "batch-0007", "call_number": "...",
                  "poster_src": "<Shopify Image Src last uploaded as the poster>",
                  "note": "..."}}

Libib's exports carry no image data, so poster_src is the only way to see
poster drift. Entries written by the old pipeline carry `poster_confirmed`
instead; migrate_poster_src converts them once, from the snapshot.
"""

import json
from pathlib import Path

from catalog.errors import InputShapeError

STATE_FILENAME = "_state.json"
IN_FLIGHT = ("queued", "imported")


def state_path(sync_dir) -> Path:
    return Path(sync_dir) / STATE_FILENAME


def load_state(sync_dir) -> dict:
    path = state_path(sync_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputShapeError(f"{path} is not valid JSON ({exc})") from None


def save_state(sync_dir, state: dict) -> None:
    path = state_path(sync_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def set_status(state: dict, handle: str, status: str, **fields) -> None:
    entry = state.setdefault(handle, {})
    entry["status"] = status
    entry.update(fields)


def counts_by_status(state: dict) -> dict:
    counts: dict = {}
    for entry in state.values():
        counts[entry.get("status", "?")] = counts.get(entry.get("status", "?"), 0) + 1
    return counts


def migrate_poster_src(state: dict, rows_by_handle: dict) -> int:
    migrated = 0
    for handle, entry in state.items():
        if entry.get("poster_confirmed") and not entry.get("poster_src"):
            src = ((rows_by_handle.get(handle) or {}).get("Image Src") or "").strip()
            if src:
                entry["poster_src"] = src
                migrated += 1
    return migrated
```

- [ ] **Step 3: Run the suite** → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/state.py tests/catalog/test_libib_state.py
git commit -m "feat(catalog): Libib sync state with poster_src migration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 5: The diff — `libib/diff.py`

**Files:**
- Create: `catalog/libib/diff.py`
- Test: `tests/catalog/test_libib_diff.py`

**Interfaces:**
- Consumes: `barcode_owners`, `is_rental_barcode` (Task 1); fields (Task 2); `IN_FLIGHT` (Task 4); `norm_ws`.
- Produces: `catalog.libib.diff`: `DRIFT_COLUMNS = ["handle", "call_number", "field", "shopify", "libib"]`, `ORPHAN_COLUMNS = ["id", "title", "call_number", "barcode", "reason"]`, `BLOCKED_COLUMNS = ["handle", "barcode", "reason"]`, `ELIGIBLE_COLUMNS = ["handle", "call_number", "title"]`, `FIXABLE_FIELDS = ("title", "description", "tags", "barcode", "poster")`, `DiffResult(in_sync, drift, eligible, incomplete, blocked, orphans, promoted)`, `diff(rows, items, state) -> DiffResult` (mutates `state` only to promote in-sync handles to `done`).

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_diff.py`:

```python
import unittest

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.diff import diff


def rental(handle="jaws", barcode="01577790", **overrides):
    base = {"Handle": handle, "Title": "Jaws", "Body (HTML)": "<p>A shark.</p>", "Image Src": "https://cdn/j.jpg",
            "Variant Barcode": barcode, "Variant Price": "0", "Tags": "Rental, VHS, Horror", "Vendor": "VHS",
            GENRE_METAFIELD: "horror"}
    base.update(overrides)
    return base


def item(item_id="i1", call="01577790", **overrides):
    base = {"id": item_id, "title": "Jaws", "barcode": call, "call_number": call, "tags": "horror,vhs",
            "description": "A shark.", "collection": "Rental Library"}
    base.update(overrides)
    return base


def fields(result, handle="jaws"):
    return {d["field"] for d in result.drift if d["handle"] == handle}


class TestDiff(unittest.TestCase):
    def test_in_sync(self):
        result = diff([rental()], [item()], {})
        self.assertEqual(result.in_sync, ["jaws"])
        self.assertEqual((result.drift, result.eligible, result.orphans), ([], [], []))

    def test_field_drift(self):
        result = diff([rental()], [item(title="JAWS", description="Old.", tags="vhs", barcode="99999999")], {})
        self.assertEqual(fields(result), {"title", "description", "tags", "barcode"})

    def test_whitespace_and_tag_order_are_not_drift(self):
        result = diff([rental()], [item(title=" Jaws ", description="A  shark.", tags="VHS, Horror")], {})
        self.assertEqual(result.in_sync, ["jaws"])

    def test_poster_drift_only_when_a_poster_src_is_recorded(self):
        self.assertEqual(fields(diff([rental()], [item()], {"jaws": {"status": "done", "poster_src": "https://cdn/old.jpg"}})),
                         {"poster"})
        self.assertEqual(diff([rental()], [item()], {"jaws": {"status": "done"}}).in_sync, ["jaws"])

    def test_missing_and_complete_is_eligible(self):
        result = diff([rental()], [], {})
        self.assertEqual(result.eligible, [{"handle": "jaws", "call_number": "01577790", "title": "Jaws"}])

    def test_missing_and_incomplete_is_counted_not_eligible(self):
        result = diff([rental(**{"Image Src": ""})], [], {})
        self.assertEqual((result.eligible, result.incomplete), ([], ["jaws"]))

    def test_in_flight_rental_is_not_eligible(self):
        for status in ("queued", "imported"):
            with self.subTest(status=status):
                self.assertEqual(diff([rental()], [], {"jaws": {"status": status}}).eligible, [])

    def test_done_but_missing_becomes_eligible_again(self):
        self.assertEqual(len(diff([rental()], [], {"jaws": {"status": "done"}}).eligible), 1)

    def test_blocked_barcodes(self):
        rows = [rental("a", ""), rental("b", "1234567"), rental("c", "01577790"),
                {**rental("d", "01577790"), "Tags": "Floor Sale, DVD, Drama"}]
        result = diff(rows, [], {})
        reasons = {b["handle"]: b["reason"] for b in result.blocked}
        self.assertEqual(reasons["a"], "barcode missing")
        self.assertEqual(reasons["b"], "barcode is not 8 digits")
        self.assertIn("also on d", reasons["c"])
        self.assertNotIn("d", reasons)  # floor sale: not in Libib scope
        self.assertEqual(result.eligible, [])

    def test_floor_sale_is_ignored(self):
        result = diff([rental(Tags="Floor Sale, VHS, Horror")], [], {})
        self.assertEqual((result.eligible, result.blocked, result.in_sync), ([], [], []))

    def test_item_without_call_number_matches_on_barcode(self):
        result = diff([rental()], [item(call_number="")], {})
        self.assertEqual(result.eligible, [])
        self.assertEqual(fields(result), {"call_number"})
        self.assertEqual(result.orphans, [])

    def test_duplicate_call_number_lists_both_items(self):
        result = diff([rental()], [item("i1"), item("i2")], {})
        self.assertEqual(sorted(o["id"] for o in result.orphans), ["i1", "i2"])
        self.assertTrue(all("duplicate" in o["reason"] for o in result.orphans))
        self.assertEqual((result.eligible, result.in_sync, result.drift), ([], [], []))

    def test_orphans(self):
        result = diff([], [item("i1", "05555555"), item("i2", "", barcode="2010000000007")], {})
        reasons = {o["id"]: o["reason"] for o in result.orphans}
        self.assertIn("05555555", reasons["i1"])
        self.assertEqual(reasons["i2"], "no call number")

    def test_in_sync_in_flight_or_needs_review_is_promoted(self):
        for status in ("queued", "imported", "needs-review"):
            with self.subTest(status=status):
                state = {"jaws": {"status": status, "batch": "batch-0001"}}
                result = diff([rental()], [item()], state)
                self.assertEqual(result.promoted, ["jaws"])
                self.assertEqual(state["jaws"], {"status": "done", "batch": "batch-0001"})

    def test_drifting_item_is_not_promoted(self):
        state = {"jaws": {"status": "imported"}}
        diff([rental()], [item(title="Wrong")], state)
        self.assertEqual(state["jaws"]["status"], "imported")


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError`.

- [ ] **Step 2: Implement `catalog/libib/diff.py`**

```python
"""Compare the snapshot's rentals with Libib's exports. Pure, except that
in-sync handles still marked queued/imported/needs-review are promoted to
done in `state` (the caller saves it).

Join key: Shopify Variant Barcode == Libib call_number. An item with no
call_number is matched on its copy barcode instead, so an item imported
before call numbers existed is never mistaken for missing and re-imported.
"""

from dataclasses import dataclass, field

from catalog.core.barcodes import barcode_owners, is_rental_barcode
from catalog.core.text import norm_ws
from catalog.libib.fields import (
    expected_description, expected_tags_string, expected_title, is_complete, is_rental, normalized_tag_set,
)
from catalog.libib.state import IN_FLIGHT

DRIFT_COLUMNS = ["handle", "call_number", "field", "shopify", "libib"]
ORPHAN_COLUMNS = ["id", "title", "call_number", "barcode", "reason"]
BLOCKED_COLUMNS = ["handle", "barcode", "reason"]
ELIGIBLE_COLUMNS = ["handle", "call_number", "title"]
FIXABLE_FIELDS = ("title", "description", "tags", "barcode", "poster")
_PROMOTABLE = ("queued", "imported", "needs-review")


@dataclass
class DiffResult:
    in_sync: list = field(default_factory=list)
    drift: list = field(default_factory=list)
    eligible: list = field(default_factory=list)
    incomplete: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    orphans: list = field(default_factory=list)
    promoted: list = field(default_factory=list)


def _orphan(item: dict, reason: str) -> dict:
    return {"id": item["id"], "title": item["title"], "call_number": item["call_number"],
            "barcode": item["barcode"], "reason": reason}


def _drift(row: dict, item: dict, entry: dict | None, matched_on_barcode: bool) -> list[dict]:
    call = row["Variant Barcode"].strip()
    out: list[dict] = []

    def add(name, shopify, libib):
        out.append({"handle": row["Handle"], "call_number": call, "field": name, "shopify": shopify, "libib": libib})

    if matched_on_barcode:
        add("call_number", call, "")
    if norm_ws(item["title"]) != expected_title(row):
        add("title", expected_title(row), norm_ws(item["title"]))
    if norm_ws(item["description"]) != expected_description(row):
        add("description", expected_description(row), norm_ws(item["description"]))
    if normalized_tag_set(item["tags"]) != normalized_tag_set(expected_tags_string(row)):
        add("tags", expected_tags_string(row), item["tags"])
    if item["barcode"] != call:
        add("barcode", call, item["barcode"])
    poster_src = (entry or {}).get("poster_src")
    image = (row.get("Image Src") or "").strip()
    if poster_src and poster_src != image:
        add("poster", image, poster_src)
    return out


def diff(rows: list[dict], items: list[dict], state: dict) -> DiffResult:
    result = DiffResult()
    owners = barcode_owners(rows)
    by_call: dict[str, list[dict]] = {}
    by_barcode: dict[str, list[dict]] = {}
    for item in items:
        if item["call_number"]:
            by_call.setdefault(item["call_number"], []).append(item)
        elif item["barcode"]:
            by_barcode.setdefault(item["barcode"], []).append(item)
    matched: set[str] = set()

    for row in rows:
        if not is_rental(row):
            continue
        handle = row["Handle"]
        call = (row.get("Variant Barcode") or "").strip()
        if not is_rental_barcode(call):
            reason = "barcode missing" if not call else "barcode is not 8 digits"
            result.blocked.append({"handle": handle, "barcode": call, "reason": reason})
            continue
        others = [h for h in owners.get(call, []) if h != handle]
        if others:
            result.blocked.append({"handle": handle, "barcode": call, "reason": "barcode also on " + ", ".join(others)})
            continue

        found = by_call.get(call) or []
        on_barcode = False
        if not found:
            found = by_barcode.get(call) or []
            on_barcode = bool(found)
        if len(found) > 1:
            for dup in found:
                matched.add(dup["id"])
                result.orphans.append(_orphan(dup, f"duplicate: {len(found)} Libib items share {call}"))
            continue

        entry = state.get(handle)
        if not found:
            if (entry or {}).get("status") in IN_FLIGHT:
                continue
            if is_complete(row):
                result.eligible.append({"handle": handle, "call_number": call, "title": expected_title(row)})
            else:
                result.incomplete.append(handle)
            continue

        libib_item = found[0]
        matched.add(libib_item["id"])
        drift = _drift(row, libib_item, entry, on_barcode)
        if drift:
            result.drift.extend(drift)
            continue
        result.in_sync.append(handle)
        if entry and entry.get("status") in _PROMOTABLE:
            entry["status"] = "done"
            result.promoted.append(handle)

    for libib_item in items:
        if libib_item["id"] not in matched:
            reason = (f"no Shopify rental with call number {libib_item['call_number']}"
                      if libib_item["call_number"] else "no call number")
            result.orphans.append(_orphan(libib_item, reason))
    return result
```

- [ ] **Step 3: Run the suite** → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/diff.py tests/catalog/test_libib_diff.py
git commit -m "feat(catalog): Libib diff — drift, eligible, orphans, blocked, promotion

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 6: Batch builder — `libib/prepare.py`

**Files:**
- Create: `catalog/libib/prepare.py`
- Test: `tests/catalog/test_libib_prepare.py`

**Interfaces:**
- Consumes: `import_row`, `ready_row`, `LIBIB_MOVIE_COLUMNS`, `READY_COLUMNS` (Task 2); `write_csv`; `log`.
- Produces: `catalog.libib.prepare`: `next_batch_id(sync_dir) -> str` (`batch-NNNN`), `image_ext(url) -> str`, `download_posters(rows, dest_dir, download=urllib.request.urlretrieve) -> tuple[dict[str, str], list[str]]` (call number → local path; failed call numbers), `write_batch(batch_dir, rows, poster_paths) -> None` (writes `import.csv` and `ready.csv`).

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_prepare.py`:

```python
import csv
import tempfile
import unittest
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS
from catalog.libib.prepare import download_posters, image_ext, next_batch_id, write_batch


def rental(handle, barcode, image="https://cdn/x.jpg?v=1"):
    return {"Handle": handle, "Title": handle.title(), "Body (HTML)": "<p>D.</p>", "Image Src": image,
            "Variant Barcode": barcode, "Variant Price": "0", "Tags": "Rental, VHS", "Vendor": "VHS",
            GENRE_METAFIELD: "horror"}


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_batch_id(self):
        self.assertEqual(next_batch_id(self.dir), "batch-0001")
        (self.dir / "batch-0009").mkdir()
        (self.dir / "batch-0010").mkdir()
        (self.dir / "drift-2026-09-25").mkdir()
        (self.dir / "batch-notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(next_batch_id(self.dir), "batch-0011")

    def test_image_ext(self):
        self.assertEqual(image_ext("https://cdn/a.PNG?v=3"), "png")
        self.assertEqual(image_ext("https://cdn/a"), "jpg")
        self.assertEqual(image_ext("https://cdn/a.jpeg"), "jpeg")

    def test_download_posters_reports_failures(self):
        def download(url, path):
            if "bad" in url:
                raise OSError("404")
            Path(path).write_bytes(b"img")

        rows = [rental("a", "01111111"), rental("b", "02222222", image="https://cdn/bad.jpg")]
        paths, failed = download_posters(rows, self.dir, download)
        self.assertEqual(paths, {"01111111": str(self.dir / "01111111.jpg")})
        self.assertEqual(failed, ["02222222"])

    def test_write_batch(self):
        rows = [rental("a", "01111111"), rental("b", "02222222")]
        write_batch(self.dir, rows, {"01111111": "libib-sync/batch-0001/01111111.jpg"})
        with open(self.dir / "import.csv", newline="", encoding="utf-8") as f:
            imported = list(csv.DictReader(f))
        with open(self.dir / "ready.csv", newline="", encoding="utf-8") as f:
            ready = list(csv.DictReader(f))
        self.assertEqual(list(imported[0]), LIBIB_MOVIE_COLUMNS)
        self.assertEqual([r["call_number"] for r in imported], ["01111111", "02222222"])
        self.assertEqual(list(ready[0]), READY_COLUMNS)
        self.assertEqual([r["image_path"] for r in ready], ["libib-sync/batch-0001/01111111.jpg", ""])


if __name__ == "__main__":
    unittest.main()
```
Run → `ModuleNotFoundError`.

- [ ] **Step 2: Implement `catalog/libib/prepare.py`**

```python
"""Build a Libib import batch: import.csv (for Add Items -> CSV with Force
Import Mode on), each rental's poster, and ready.csv (the fixer's input)."""

import re
import urllib.request
from pathlib import Path

from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS, import_row, ready_row

IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif")
_BATCH_NAME = re.compile(r"^batch-(\d+)$")


def next_batch_id(sync_dir) -> str:
    sync_dir = Path(sync_dir)
    numbers = [int(m.group(1)) for p in (sync_dir.iterdir() if sync_dir.is_dir() else [])
               if p.is_dir() and (m := _BATCH_NAME.match(p.name))]
    return f"batch-{(max(numbers) + 1) if numbers else 1:04d}"


def image_ext(url: str) -> str:
    name = (url or "").split("?")[0].rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in IMAGE_EXTS else "jpg"


def download_posters(rows: list[dict], dest_dir, download=urllib.request.urlretrieve) -> tuple[dict[str, str], list[str]]:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    failed: list[str] = []
    for index, row in enumerate(rows, start=1):
        call = (row.get("Variant Barcode") or "").strip()
        url = (row.get("Image Src") or "").strip()
        target = dest_dir / f"{call}.{image_ext(url)}"
        try:
            download(url, target)
            paths[call] = str(target)
            log.progress(index, len(rows), f"{call} {row.get('Title', '').strip()}", "poster ok")
        except Exception as exc:  # a bad URL must not abort the batch
            failed.append(call)
            log.progress(index, len(rows), f"{call} {row.get('Title', '').strip()}", f"poster FAILED: {exc}")
    return paths, failed


def write_batch(batch_dir, rows: list[dict], poster_paths: dict[str, str]) -> None:
    batch_dir = Path(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    write_csv(batch_dir / "import.csv", LIBIB_MOVIE_COLUMNS, [import_row(r) for r in rows])
    write_csv(batch_dir / "ready.csv", READY_COLUMNS,
              [ready_row(r, poster_paths.get((r.get("Variant Barcode") or "").strip(), "")) for r in rows])
```

- [ ] **Step 3: Run the suite** → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/prepare.py tests/catalog/test_libib_prepare.py
git commit -m "feat(catalog): Libib batch builder — import.csv, posters, ready.csv

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 7: Browser operations and the fixer — `libib/browser.py`, `libib/fix.py`

**Files:**
- Create: `catalog/libib/browser.py` (from `formatting-scripts/libib_sync_fix.py` lines 40 and 50–270), `catalog/libib/fix.py`
- Test: `tests/catalog/test_libib_fix.py`

**Interfaces:**
- Consumes: `ready_row`, `READY_COLUMNS` (Task 2), `FIXABLE_FIELDS` (Task 5), `CatalogError`, `log`.
- Produces:
  - `catalog.libib.browser` (Playwright; imported only by `run_fixer`): `login(page, email, password)`, `sync_item(page, row) -> (barcode_status, content_status, message)` plus the helpers moved with them.
  - `catalog.libib.fix`: `REPORT_COLUMNS = ["call_number", "barcode_status", "content_status", "message"]`, `read_ready(path) -> list[dict]`, `drift_targets(drift_rows) -> tuple[dict[str, set], list[str]]` (handle → fixable fields; handles needing a manual fix), `drift_ready_rows(fields_by_handle, rows_by_handle, poster_paths) -> list[dict]`, `apply_report(state, results, handle_by_call, rows_by_handle) -> dict`, `run_fixer(rows, report_path, email, password, headless) -> list[dict]`.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_fix.py`:

```python
import ast
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import CatalogError
from catalog.libib import fix
from catalog.libib.fix import apply_report, drift_ready_rows, drift_targets, read_ready

BROWSER = Path(__file__).resolve().parents[2] / "catalog" / "libib" / "browser.py"


def rental(handle, barcode):
    return {"Handle": handle, "Title": handle.title(), "Body (HTML)": "<p>D.</p>", "Image Src": f"https://cdn/{handle}.jpg",
            "Variant Barcode": barcode, "Tags": "Rental, VHS", "Vendor": "VHS", GENRE_METAFIELD: "horror"}


def result(call, barcode="updated", content="updated", message="barcode: ok | content: changed: title"):
    return {"call_number": call, "barcode_status": barcode, "content_status": content, "message": message}


class TestBrowserModule(unittest.TestCase):
    def test_parses_holds_no_credentials_and_imports_nothing_old(self):
        source = BROWSER.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("LIBIB_PASSWORD", source)
        self.assertNotIn("@littlemoviestore.com", source)
        self.assertNotIn("from libib_fields", source)
        self.assertIn("from catalog.libib.fields import normalized_tag_set", source)
        for name in ("def login(", "def sync_item(", "def ensure_rental_library_scope("):
            self.assertIn(name, source)


class TestDrift(unittest.TestCase):
    def test_targets_split_fixable_from_manual(self):
        rows = [{"handle": "a", "field": "title"}, {"handle": "a", "field": "poster"},
                {"handle": "b", "field": "call_number"}, {"handle": "b", "field": "title"}]
        fields, manual = drift_targets(rows)
        self.assertEqual(fields, {"a": {"title", "poster"}})
        self.assertEqual(manual, ["b"])

    def test_ready_rows_only_upload_a_poster_for_poster_drift(self):
        rows_by_handle = {"a": rental("a", "01111111"), "b": rental("b", "02222222")}
        ready = drift_ready_rows({"a": {"poster"}, "b": {"title"}}, rows_by_handle, {"01111111": "/tmp/a.jpg"})
        self.assertEqual({r["call_number"]: r["image_path"] for r in ready}, {"01111111": "/tmp/a.jpg", "02222222": ""})


class TestApplyReport(unittest.TestCase):
    def test_outcomes(self):
        rows = {h: rental(h, c) for h, c in (("a", "01111111"), ("b", "02222222"), ("c", "03333333"))}
        state = {"a": {"status": "queued", "batch": "batch-0001"}, "b": {"status": "done"},
                 "c": {"status": "imported", "note": "old"}}
        results = [result("01111111", message="barcode: ok | content: changed: poster"),
                   result("02222222"),
                   result("03333333", barcode="error", message="Barcode already exists"),
                   result("09999999")]
        counts = apply_report(state, results, {"01111111": "a", "02222222": "b", "03333333": "c"}, rows)
        self.assertEqual(state["a"]["status"], "imported")
        self.assertEqual(state["a"]["poster_src"], "https://cdn/a.jpg")
        self.assertEqual(state["b"]["status"], "done")  # a drift fix never downgrades done
        self.assertEqual(state["c"]["status"], "needs-review")
        self.assertIn("Barcode already exists", state["c"]["note"])
        self.assertEqual(counts, {"ok": 2, "needs_review": 1, "posters": 1, "untracked": 1})


class TestReadReady(unittest.TestCase):
    def test_skips_rows_without_a_call_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ready.csv"
            path.write_text("call_number,title,description,tags,image_path\n01111111,A,,,\n,B,,,\n", encoding="utf-8")
            self.assertEqual([r["title"] for r in read_ready(path)], ["A"])


class TestRunFixer(unittest.TestCase):
    def test_run_fixer_without_playwright_names_the_venv(self):
        real_import = builtins.__import__

        def no_playwright(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=no_playwright):
            with self.assertRaises(CatalogError) as ctx:
                fix.run_fixer([{"call_number": "01111111"}], Path("/tmp/r.csv"), "e", "p", True)
        self.assertIn(".venv-libib", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```
Run → `ImportError` (no `catalog.libib.fix`).

- [ ] **Step 2: Build `catalog/libib/browser.py`**

```bash
sed -n '40p;50p;270p' formatting-scripts/libib_sync_fix.py
# expect: LIBIB_LOGIN_URL = "https://www.libib.com/login" / def login(… / return barcode_status, content_status, message
{ cat <<'EOF'
"""Libib page operations (Playwright). Moved verbatim from
formatting-scripts/libib_sync_fix.py minus its hardcoded credentials and CLI.
For each item: search `call:<call_number>` (exactly one hit), fix the copy
barcode, then title/description/tags/poster in the Edit form, and reload to
verify what persisted. Imported only by catalog.libib.fix.run_fixer.
"""

from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

EOF
sed -n '40p' formatting-scripts/libib_sync_fix.py
echo
echo
sed -n '50,270p' formatting-scripts/libib_sync_fix.py | sed 's/^    from libib_fields import normalized_tag_set$/    from catalog.libib.fields import normalized_tag_set/'
} > catalog/libib/browser.py
grep -n "normalized_tag_set\|PASSWORD\|EMAIL" catalog/libib/browser.py
python3 -c "import ast; ast.parse(open('catalog/libib/browser.py').read()); print('parses')"
```
Expected grep: only the two `from catalog.libib.fields import normalized_tag_set` lines and their uses — no `PASSWORD`/`EMAIL`. Then `parses`.

- [ ] **Step 3: Write `catalog/libib/fix.py`**

```python
"""`libib fix` core: build the fixer's input, run the browser fixer, and turn
its report into state changes.

Playwright is imported inside run_fixer only, so every other catalog command
runs on plain Python. Run this command with .venv-libib/bin/python.
"""

import csv
from pathlib import Path

from catalog.core import log
from catalog.errors import CatalogError
from catalog.libib.columns import ready_row
from catalog.libib.diff import FIXABLE_FIELDS

REPORT_COLUMNS = ["call_number", "barcode_status", "content_status", "message"]


def read_ready(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if (row.get("call_number") or "").strip()]


def drift_targets(drift_rows: list[dict]) -> tuple[dict[str, set], list[str]]:
    """Handles whose drift the fixer can repair, and handles that need a
    person (a call_number drift: the fixer finds items by call number)."""
    fields: dict[str, set] = {}
    for d in drift_rows:
        fields.setdefault(d["handle"], set()).add(d["field"])
    manual = sorted(h for h, f in fields.items() if not f <= set(FIXABLE_FIELDS))
    return {h: f for h, f in fields.items() if h not in manual}, manual


def drift_ready_rows(fields_by_handle: dict, rows_by_handle: dict, poster_paths: dict[str, str]) -> list[dict]:
    ready = []
    for handle in sorted(fields_by_handle):
        row = rows_by_handle[handle]
        call = (row.get("Variant Barcode") or "").strip()
        image = poster_paths.get(call, "") if "poster" in fields_by_handle[handle] else ""
        ready.append(ready_row(row, image))
    return ready


def apply_report(state: dict, results: list[dict], handle_by_call: dict, rows_by_handle: dict) -> dict:
    counts = {"ok": 0, "needs_review": 0, "posters": 0, "untracked": 0}
    for r in results:
        handle = handle_by_call.get(r["call_number"])
        if handle is None:
            counts["untracked"] += 1
            continue
        entry = state.setdefault(handle, {"call_number": r["call_number"]})
        if r["barcode_status"] == "error" or r["content_status"] == "error":
            entry.update(status="needs-review", note=r["message"][:300])
            counts["needs_review"] += 1
            continue
        if entry.get("status") != "done":
            entry["status"] = "imported"  # the next diff confirms and promotes it
        entry.pop("note", None)
        counts["ok"] += 1
        if r["content_status"] == "updated" and "poster" in r["message"]:
            src = ((rows_by_handle.get(handle) or {}).get("Image Src") or "").strip()
            if src:
                entry["poster_src"] = src
                counts["posters"] += 1
    return counts


def run_fixer(rows: list[dict], report_path, email: str, password: str, headless: bool) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CatalogError("Playwright is not installed for this Python. Run the fixer with the Libib venv:\n"
                           "  .venv-libib/bin/python -m catalog libib fix …") from None
    from catalog.libib import browser

    report_path = Path(report_path)
    results: list[dict] = []
    with sync_playwright() as p, report_path.open("w", newline="", encoding="utf-8") as report_f:
        writer = csv.DictWriter(report_f, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        report_f.flush()
        chromium = p.chromium.launch(headless=headless)
        page = chromium.new_page()
        browser.login(page, email, password)
        for index, row in enumerate(rows, start=1):
            call = row["call_number"].strip()
            try:
                barcode_status, content_status, message = browser.sync_item(page, row)
            except Exception as exc:  # keep going across a whole batch
                barcode_status, content_status, message = "error", "error", f"{type(exc).__name__}: {exc}"
            outcome = {"call_number": call, "barcode_status": barcode_status,
                       "content_status": content_status, "message": message}
            results.append(outcome)
            writer.writerow(outcome)
            report_f.flush()
            log.progress(index, len(rows), call, f"{barcode_status}/{content_status} — {message}")
        chromium.close()
    return results
```

- [ ] **Step 4: Run the suite** → `OK`. (`test_libib_fix` never imports `browser`; it parses it.)

- [ ] **Step 5: Commit**

```bash
git add catalog/libib/browser.py catalog/libib/fix.py tests/catalog/test_libib_fix.py
git commit -m "feat(catalog): Libib browser fixer (credentials from env) and report-to-state

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 8: `libib diff` and `libib status`

**Files:**
- Create: `catalog/libib/command.py`
- Modify: `catalog/cli.py` (register)
- Test: `tests/catalog/test_libib_command.py`

**Interfaces:**
- Consumes: Tasks 2–5, `resolve_run`, `load_snapshot`, `write_csv`, `config.LIBIB_SYNC_DIR`, `log`.
- Produces: `catalog.libib.command`: `register(subparsers)`, `run_diff_command(args) -> int`, `run_status_command(args) -> int` (Task 9/10 add the other runners to this module). Diff writes `runs/<id>/libib/{drift,eligible,orphans,blocked}.csv`, `libib-report.txt`, `diff.log`, and `state-before.json` when it changes state.

- [ ] **Step 1: Write the failing test** — `tests/catalog/test_libib_command.py`:

```python
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from catalog.cli import build_parser
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.libib import command


def rental(handle, barcode, **overrides):
    base = {"Handle": handle, "Title": handle.title(), "Body (HTML)": f"<p>{handle}.</p>",
            "Image Src": f"https://cdn/{handle}.jpg", "Variant Barcode": barcode, "Variant Price": "0",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", GENRE_METAFIELD: "horror", "Status": "active"}
    base.update(overrides)
    return base


class LibibCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs, self.sync = root / "runs", root / "libib-sync"
        self.run = self.runs / "2026-09-25"
        self.run.mkdir(parents=True)
        self.sync.mkdir()
        rows = [rental("jaws", "01111111"), rental("heat", "02222222"), rental("alien", "03333333"),
                rental("blank", "")]
        (self.run / "snapshot.json").write_text(json.dumps(rows), encoding="utf-8")
        (self.run / "run-report.txt").write_text("done\n", encoding="utf-8")
        self.barcodes, self.collection = root / "b.csv", root / "c.csv"
        self.barcodes.write_text(
            "id,item_type,barcode,title,collection,tags,call_number\n"
            'i1,movie,01111111,Jaws,Rental Library,"vhs, horror",01111111\n'
            'i2,movie,02222222,Heat (old),Rental Library,"vhs, horror",02222222\n'
            "i3,movie,07777777,Orphan,Rental Library,,07777777\n", encoding="utf-8")
        self.collection.write_text(
            "id,item_type,title,collection,description,call_number\n"
            "i1,movie,Jaws,Rental Library,jaws.,01111111\n"
            "i2,movie,Heat,Rental Library,heat.,02222222\n"
            "i3,movie,Orphan,Rental Library,,07777777\n", encoding="utf-8")
        (self.sync / "_state.json").write_text(json.dumps({
            "jaws": {"status": "imported", "batch": "batch-0001", "call_number": "01111111", "poster_confirmed": True}}),
            encoding="utf-8")

    def tearDown(self):
        log.setup_logging(None, 0, io.StringIO())
        self.tmp.cleanup()

    def parse(self, *argv):
        return build_parser().parse_args(["libib", *argv, "--runs-dir", str(self.runs), "--sync-dir", str(self.sync), "-q"])

    def diff(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return command.run_diff_command(self.parse("diff", "--barcode-export", str(self.barcodes),
                                                       "--collection-export", str(self.collection)))

    def read(self, name):
        with open(self.run / "libib" / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def state(self):
        return json.loads((self.sync / "_state.json").read_text(encoding="utf-8"))


class TestDiffCommand(LibibCase):
    def test_writes_every_output_and_updates_state(self):
        self.assertEqual(self.diff(), 0)
        self.assertEqual({(d["handle"], d["field"]) for d in self.read("drift.csv")}, {("heat", "title")})
        self.assertEqual([e["handle"] for e in self.read("eligible.csv")], ["alien"])
        self.assertEqual([o["id"] for o in self.read("orphans.csv")], ["i3"])
        self.assertEqual([b["handle"] for b in self.read("blocked.csv")], ["blank"])
        state = self.state()
        self.assertEqual(state["jaws"]["status"], "done")                      # promoted
        self.assertEqual(state["jaws"]["poster_src"], "https://cdn/jaws.jpg")  # migrated
        before = json.loads((self.run / "libib" / "state-before.json").read_text(encoding="utf-8"))
        self.assertEqual(before["jaws"]["status"], "imported")
        report = (self.run / "libib" / "libib-report.txt").read_text(encoding="utf-8")
        for fragment in ("in sync:", "drift:", "eligible:", "orphans:", "blocked:", "promoted"):
            self.assertIn(fragment, report)


class TestStatusCommand(LibibCase):
    def test_status_counts(self):
        out = io.StringIO()
        log.setup_logging(None, 0, out)
        args = build_parser().parse_args(["libib", "status", "--sync-dir", str(self.sync)])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(command.run_status_command(args), 0)
        self.assertIn("imported: 1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
```
Run → `ImportError`.

- [ ] **Step 2: Write `catalog/libib/command.py`** (diff + status now; Tasks 9–10 add to it)

```python
"""`python3 -m catalog libib <diff|prepare|mark-imported|fix|status>` — keep
Libib 1:1 with the Shopify snapshot's rentals.

diff writes its run folder and libib-sync/_state.json (promotions, one-time
poster_src migration; a pre-change copy is kept in the run folder) and asks
nothing. prepare / mark-imported / fix show a plan and ask first.
"""

import argparse
import csv
import shutil
from pathlib import Path

from catalog import config
from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.core.runs import resolve_run
from catalog.errors import NoRunError
from catalog.libib.diff import BLOCKED_COLUMNS, DRIFT_COLUMNS, ELIGIBLE_COLUMNS, ORPHAN_COLUMNS, diff
from catalog.libib.exports import DEFAULT_COLLECTION, load_libib
from catalog.libib.state import counts_by_status, load_state, migrate_poster_src, save_state, state_path
from catalog.shopify.snapshot import load_snapshot


def _common(p, needs_run: bool = True) -> None:
    if needs_run:
        p.add_argument("--run", help="audit run id (default: the latest complete run)")
        p.add_argument("--runs-dir", default=str(config.RUNS_DIR), help=argparse.SUPPRESS)
    p.add_argument("--sync-dir", default=str(config.LIBIB_SYNC_DIR), help=argparse.SUPPRESS)
    log.add_verbosity_args(p)


def register(subparsers) -> None:
    libib = subparsers.add_parser("libib", help="compare and sync Libib with the Shopify snapshot")
    sub = libib.add_subparsers(dest="libib_command", required=True, metavar="<libib command>")

    p = sub.add_parser("diff", help="compare Libib's exports with the latest audit snapshot")
    p.add_argument("--barcode-export", required=True, help="Libib item/barcode export CSV")
    p.add_argument("--collection-export", required=True, help="Libib collection export CSV")
    p.add_argument("--collection", default=DEFAULT_COLLECTION, help=f"Libib collection (default {DEFAULT_COLLECTION!r})")
    _common(p)
    p.set_defaults(func=run_diff_command)

    p = sub.add_parser("status", help="count tracked handles per state")
    _common(p, needs_run=False)
    p.set_defaults(func=run_status_command)


def _libib_dir(args) -> tuple[Path, Path]:
    run_dir = resolve_run(args.runs_dir, args.run)
    out = run_dir / "libib"
    out.mkdir(exist_ok=True)
    return run_dir, out


def run_diff_command(args) -> int:
    run_dir, out = _libib_dir(args)
    log.setup_logging(out / "diff.log", log.verbosity(args))
    log.header(f"libib diff — audit run {run_dir.name}")
    rows = load_snapshot(run_dir / "snapshot.json")
    items = load_libib(args.barcode_export, args.collection_export, args.collection)
    log.summary(f"{len(items)} Libib items in {args.collection or 'all collections'}")

    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    migrated = migrate_poster_src(state, {r["Handle"]: r for r in rows})
    result = diff(rows, items, state)

    write_csv(out / "drift.csv", DRIFT_COLUMNS, result.drift)
    write_csv(out / "eligible.csv", ELIGIBLE_COLUMNS, result.eligible)
    write_csv(out / "orphans.csv", ORPHAN_COLUMNS, result.orphans)
    write_csv(out / "blocked.csv", BLOCKED_COLUMNS, result.blocked)

    if migrated or result.promoted:
        if state_path(sync_dir).exists():
            shutil.copyfile(state_path(sync_dir), out / "state-before.json")
        save_state(sync_dir, state)

    drift_handles = {d["handle"] for d in result.drift}
    lines = [
        f"libib items:  {len(items)} ({args.collection or 'all collections'})",
        f"in sync:      {len(result.in_sync)} rentals",
        f"drift:        {len(drift_handles)} rentals, {len(result.drift)} fields -> drift.csv",
        f"eligible:     {len(result.eligible)} rentals missing from Libib -> eligible.csv",
        f"incomplete:   {len(result.incomplete)} rentals missing from Libib but not complete in Shopify",
        f"orphans:      {len(result.orphans)} Libib items (no rental / duplicates) -> orphans.csv",
        f"blocked:      {len(result.blocked)} rentals with a bad or shared barcode -> blocked.csv",
        f"state:        {len(result.promoted)} promoted to done, {migrated} poster_src migrated",
    ]
    (out / "libib-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        log.summary(line)
    log.summary(f"-> {out}")
    return 0


def run_status_command(args) -> int:
    log.setup_logging(None, log.verbosity(args))
    state = load_state(args.sync_dir)
    if not state:
        log.summary("No handles tracked yet.")
        return 0
    for status, count in sorted(counts_by_status(state).items()):
        log.summary(f"{status}: {count}")
    return 0
```

Register in `catalog/cli.py`: add `from catalog.libib import command as libib_command` to the imports and append `libib_command` to `COMMANDS` (after `apply_command`).

- [ ] **Step 3: Run the suite** → `OK`. `python3 -m catalog libib --help` lists `diff`, `status`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/command.py catalog/cli.py tests/catalog/test_libib_command.py
git commit -m "feat(catalog): python3 -m catalog libib diff / status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 9: `libib prepare` and `libib mark-imported`

**Files:**
- Modify: `catalog/libib/command.py`
- Test: `tests/catalog/test_libib_command.py` (add classes)

**Interfaces:**
- Consumes: `next_batch_id`, `download_posters`, `write_batch` (Task 6), `IN_FLIGHT`, `set_status` (Task 4), `Plan`, `confirm`, `add_approval_args` (Plan 2).
- Produces: `run_prepare_command(args, download=None, stdin=None) -> int`, `run_mark_imported_command(args, stdin=None) -> int`. CLI: `libib prepare [--size 200] [--run ID] [--dry-run] [--yes]`, `libib mark-imported <batch> [--dry-run] [--yes]`.

- [ ] **Step 1: Write the failing tests** — add above the final `if __name__ == "__main__":` block of `tests/catalog/test_libib_command.py`:

```python
class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def fake_download(url, path):
    Path(path).write_bytes(b"img")


class TestPrepareCommand(LibibCase):
    def test_needs_a_diff_first(self):
        from catalog.errors import NoRunError
        with self.assertRaises(NoRunError):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)

    def test_dry_run_writes_nothing(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--dry-run"), download=fake_download)
        self.assertFalse((self.sync / "batch-0001").exists())

    def test_yes_builds_the_batch_and_queues(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
        batch = self.sync / "batch-0001"
        self.assertEqual(sorted(p.name for p in batch.iterdir()), ["03333333.jpg", "import.csv", "ready.csv"])
        self.assertEqual(self.state()["alien"],
                         {"status": "queued", "batch": "batch-0001", "call_number": "03333333"})

    def test_prepare_skips_handles_queued_since_the_diff(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
        self.assertFalse((self.sync / "batch-0002").exists())

    def test_refuses_without_a_terminal(self):
        from catalog.core.plan import ApprovalRefused
        self.diff()
        with self.assertRaises(ApprovalRefused):
            command.run_prepare_command(self.parse("prepare"), download=fake_download, stdin=FakeStdin(tty=False))
        self.assertFalse((self.sync / "batch-0001").exists())


class TestMarkImportedCommand(LibibCase):
    def test_marks_only_that_batchs_queued_handles(self):
        (self.sync / "_state.json").write_text(json.dumps({
            "a": {"status": "queued", "batch": "batch-0002"}, "b": {"status": "queued", "batch": "batch-0003"},
            "c": {"status": "done", "batch": "batch-0002"}}), encoding="utf-8")
        args = build_parser().parse_args(["libib", "mark-imported", "batch-0002", "--sync-dir", str(self.sync),
                                          "-q", "--yes"])
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_mark_imported_command(args)
        state = self.state()
        self.assertEqual((state["a"]["status"], state["b"]["status"], state["c"]["status"]),
                         ("imported", "queued", "done"))
```
Run → `AttributeError` (no `run_prepare_command`).

- [ ] **Step 2: Add to `catalog/libib/command.py`**

Add imports:
```python
import urllib.request

from catalog.core.plan import Plan, add_approval_args, confirm
from catalog.libib.prepare import download_posters, next_batch_id, write_batch
from catalog.libib.state import IN_FLIGHT, set_status
```
In `register`, before the `status` parser, add:
```python
    p = sub.add_parser("prepare", help="build the next Libib import batch from the diff's eligible rentals")
    p.add_argument("--size", type=int, default=200, help="rentals per batch (default 200)")
    _common(p)
    add_approval_args(p)
    p.set_defaults(func=run_prepare_command)

    p = sub.add_parser("mark-imported", help="record that a batch's import.csv was force-imported into Libib")
    p.add_argument("batch", help="batch id, e.g. batch-0017")
    _common(p, needs_run=False)
    add_approval_args(p)
    p.set_defaults(func=run_mark_imported_command)
```
Append the runners:
```python
def _read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_prepare_command(args, download=None, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    eligible_path = run_dir / "libib" / "eligible.csv"
    if not eligible_path.exists():
        raise NoRunError(f"no libib diff for run {run_dir.name} — run `python3 -m catalog libib diff …` first")
    log.setup_logging(run_dir / "libib" / "prepare.log", log.verbosity(args))
    log.header(f"libib prepare — audit run {run_dir.name}")

    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    rows_by_handle = {r["Handle"]: r for r in load_snapshot(run_dir / "snapshot.json")}
    chosen = [e for e in _read_csv(eligible_path)
              if (state.get(e["handle"]) or {}).get("status") not in IN_FLIGHT][: args.size]
    batch_id = next_batch_id(sync_dir)
    batch_dir = sync_dir / batch_id

    plan = Plan(
        title="libib prepare",
        count=len(chosen),
        summary=[f"{batch_id}: {len(chosen)} rentals (of {len(_read_csv(eligible_path))} eligible)",
                 f"downloads {len(chosen)} posters and writes {batch_dir}/import.csv + ready.csv",
                 f"state: {len(chosen)} -> queued"],
        samples=[f"{e['call_number']} {e['title']}" for e in chosen],
    )
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0

    rows = [rows_by_handle[e["handle"]] for e in chosen]
    posters, failed = download_posters(rows, batch_dir, download or urllib.request.urlretrieve)
    write_batch(batch_dir, rows, posters)
    for e in chosen:
        set_status(state, e["handle"], "queued", batch=batch_id, call_number=e["call_number"])
    save_state(sync_dir, state)

    if failed:
        log.summary(f"{len(failed)} poster(s) failed to download (ready.csv leaves image_path blank): {', '.join(failed)}")
    log.summary(f"Next: in Libib, Add Items -> CSV -> {batch_dir / 'import.csv'} with Force Import Mode on, then")
    log.summary(f"  python3 -m catalog libib mark-imported {batch_id}")
    log.summary(f"  .venv-libib/bin/python -m catalog libib fix {batch_id}")
    return 0


def run_mark_imported_command(args, stdin=None) -> int:
    log.setup_logging(None, log.verbosity(args))
    sync_dir = Path(args.sync_dir)
    state = load_state(sync_dir)
    handles = sorted(h for h, e in state.items() if e.get("batch") == args.batch and e.get("status") == "queued")
    plan = Plan(title="libib mark-imported", count=len(handles),
                summary=[f"{args.batch}: {len(handles)} handles queued -> imported"], samples=handles)
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0
    for handle in handles:
        set_status(state, handle, "imported")
    save_state(sync_dir, state)
    log.summary(f"Next: .venv-libib/bin/python -m catalog libib fix {args.batch}")
    return 0
```

- [ ] **Step 3: Run the suite** → `OK`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/command.py tests/catalog/test_libib_command.py
git commit -m "feat(catalog): libib prepare and mark-imported

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 10: `libib fix`

**Files:**
- Modify: `catalog/libib/command.py`
- Test: `tests/catalog/test_libib_command.py` (add a class)

**Interfaces:**
- Consumes: `read_ready`, `drift_targets`, `drift_ready_rows`, `apply_report`, `run_fixer` (Task 7); `download_posters` (Task 6); `is_rental` (Task 2); `READY_COLUMNS`; `config.require_env`, `ENV_LIBIB_EMAIL`, `ENV_LIBIB_PASSWORD`.
- Produces: `run_fix_command(args, fixer=run_fixer, download=None, stdin=None) -> int`. CLI: `libib fix (<batch> | --drift) [--limit N] [--headless] [--run ID] [--dry-run] [--yes]`. Drift work goes to `libib-sync/drift-<run id>/` (`ready.csv`, posters, `ready.sync-report.csv`); batch fixes write `libib-sync/<batch>/ready.sync-report.csv`.

- [ ] **Step 1: Write the failing tests** — add above the final `if __name__ == "__main__":` block:

```python
class TestFixCommand(LibibCase):
    def fake_fixer(self, calls):
        def fixer(rows, report_path, email, password, headless):
            calls.append({"rows": rows, "report": report_path, "email": email, "headless": headless})
            return [{"call_number": r["call_number"], "barcode_status": "skipped", "content_status": "updated",
                     "message": "barcode: ok | content: changed: title"} for r in rows]
        return fixer

    def env(self):
        return mock.patch.dict("os.environ", {"LIBIB_EMAIL": "e@x", "LIBIB_PASSWORD": "pw"})

    def test_drift_fix_runs_the_fixer_on_fixable_drift(self):
        self.diff()
        calls = []
        with self.env(), contextlib.redirect_stdout(io.StringIO()):
            command.run_fix_command(self.parse("fix", "--drift", "--yes", "--headless"),
                                    fixer=self.fake_fixer(calls), download=fake_download)
        self.assertEqual([r["call_number"] for r in calls[0]["rows"]], ["02222222"])
        self.assertEqual(calls[0]["rows"][0]["image_path"], "")  # title drift: no poster upload
        self.assertEqual(calls[0]["email"], "e@x")
        self.assertTrue(calls[0]["headless"])
        self.assertTrue((self.sync / "drift-2026-09-25" / "ready.csv").exists())
        self.assertEqual(self.state()["heat"]["status"], "imported")

    def test_batch_fix_reads_the_batch_ready_csv(self):
        self.diff()
        with contextlib.redirect_stdout(io.StringIO()):
            command.run_prepare_command(self.parse("prepare", "--yes"), download=fake_download)
        calls = []
        with self.env(), contextlib.redirect_stdout(io.StringIO()):
            command.run_fix_command(self.parse("fix", "batch-0001", "--yes", "--limit", "5"),
                                    fixer=self.fake_fixer(calls))
        self.assertEqual([r["call_number"] for r in calls[0]["rows"]], ["03333333"])
        self.assertEqual(calls[0]["report"], self.sync / "batch-0001" / "ready.sync-report.csv")

    def test_dry_run_never_runs_the_fixer_or_needs_credentials(self):
        self.diff()
        calls = []
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            command.run_fix_command(self.parse("fix", "--drift", "--dry-run"), fixer=self.fake_fixer(calls))
        self.assertEqual(calls, [])

    def test_missing_credentials_fail_before_asking(self):
        from catalog.errors import MissingEnvError
        self.diff()
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(MissingEnvError):
                command.run_fix_command(self.parse("fix", "--drift", "--yes"), fixer=self.fake_fixer([]))

    def test_needs_a_batch_or_drift(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.parse("fix")
```
Also add `from unittest import mock` to the test file's imports. Run → `AttributeError` (no `run_fix_command`).

- [ ] **Step 2: Add to `catalog/libib/command.py`**

Add imports:
```python
from catalog.libib.columns import READY_COLUMNS
from catalog.libib.fields import is_rental
from catalog.libib.fix import apply_report, drift_ready_rows, drift_targets, read_ready, run_fixer
```
In `register`, before the `status` parser, add:
```python
    p = sub.add_parser("fix", help="fix Libib items in the browser (run with .venv-libib/bin/python)")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("batch", nargs="?", help="a prepared batch id, e.g. batch-0017")
    target.add_argument("--drift", action="store_true", help="fix the latest diff's drift instead of a batch")
    p.add_argument("--limit", type=int, default=None, help="only the first N items")
    p.add_argument("--headless", action="store_true", help="no visible browser window")
    _common(p)
    add_approval_args(p)
    p.set_defaults(func=run_fix_command)
```
Append the runner:
```python
def run_fix_command(args, fixer=run_fixer, download=None, stdin=None) -> int:
    run_dir = resolve_run(args.runs_dir, args.run)
    (run_dir / "libib").mkdir(exist_ok=True)
    log.setup_logging(run_dir / "libib" / "fix.log", log.verbosity(args))
    sync_dir = Path(args.sync_dir)
    rows = load_snapshot(run_dir / "snapshot.json")
    rows_by_handle = {r["Handle"]: r for r in rows}
    handle_by_call = {(r.get("Variant Barcode") or "").strip(): r["Handle"] for r in rows if is_rental(r)}

    manual: list[str] = []
    if args.drift:
        drift_path = run_dir / "libib" / "drift.csv"
        if not drift_path.exists():
            raise NoRunError(f"no libib diff for run {run_dir.name} — run `python3 -m catalog libib diff …` first")
        fields_by_handle, manual = drift_targets(_read_csv(drift_path))
        handles = sorted(fields_by_handle)[: args.limit] if args.limit else sorted(fields_by_handle)
        fields_by_handle = {h: fields_by_handle[h] for h in handles}
        work_dir = sync_dir / f"drift-{run_dir.name}"
        ready_path = work_dir / "ready.csv"
        label = f"drift from run {run_dir.name}"
        samples = [f"{rows_by_handle[h]['Variant Barcode']} {rows_by_handle[h]['Title'].strip()}: "
                   f"{', '.join(sorted(fields_by_handle[h]))}" for h in handles]
        count = len(handles)
    else:
        ready_path = sync_dir / args.batch / "ready.csv"
        if not ready_path.exists():
            raise NoRunError(f"{ready_path} does not exist — run `python3 -m catalog libib prepare` first")
        ready = read_ready(ready_path)
        ready = ready[: args.limit] if args.limit else ready
        label = args.batch
        samples = [f"{r['call_number']} {r['title']}" for r in ready]
        count = len(ready)

    log.header(f"libib fix — {label}")
    credentials = None
    if count and not args.dry_run:  # fail fast, before asking
        credentials = (config.require_env(config.ENV_LIBIB_EMAIL), config.require_env(config.ENV_LIBIB_PASSWORD))
    plan = Plan(
        title="libib fix",
        count=count,
        summary=[f"{label}: edits {count} Libib items in the browser (barcode, title, description, tags, poster)",
                 f"report: {ready_path.with_suffix('.sync-report.csv')}"]
        + ([f"manual fix needed (no call number in Libib): {len(manual)} — {', '.join(manual[:10])}"] if manual else []),
        samples=samples,
    )
    if not confirm(plan, dry_run=args.dry_run, assume_yes=args.yes, stdin=stdin):
        return 0

    if args.drift:
        poster_rows = [rows_by_handle[h] for h, f in fields_by_handle.items() if "poster" in f]
        posters, _ = download_posters(poster_rows, work_dir, download or urllib.request.urlretrieve)
        ready = drift_ready_rows(fields_by_handle, rows_by_handle, posters)
        write_csv(ready_path, READY_COLUMNS, ready)

    results = fixer(ready, ready_path.with_suffix(".sync-report.csv"), credentials[0], credentials[1], args.headless)
    state = load_state(sync_dir)
    counts = apply_report(state, results, handle_by_call, rows_by_handle)
    save_state(sync_dir, state)
    log.summary(f"{counts['ok']} fixed, {counts['needs_review']} need review, {counts['posters']} posters recorded"
                + (f", {counts['untracked']} not rentals in the snapshot" if counts["untracked"] else ""))
    log.summary("Next: fresh Libib exports, then `python3 -m catalog libib diff …` to confirm.")
    return 0
```

- [ ] **Step 3: Run the suite** → `OK`. `python3 -m catalog libib fix --help` shows `batch`, `--drift`, `--limit`, `--headless`, `--dry-run`, `--yes`.

- [ ] **Step 4: Commit**

```bash
git add catalog/libib/command.py tests/catalog/test_libib_command.py
git commit -m "feat(catalog): libib fix for a batch or the latest drift

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```

---

### Task 11: README and acceptance

**Files:**
- Modify: `catalog/README.md`
- Create: `claudedocs/2026-09-25-libib-acceptance.md`

- [ ] **Step 1: Add the Stage 4 section to `catalog/README.md`** (before `## Tests`):

```markdown
## Stage 4 — Libib

Libib has no API: its exports and CSV imports are manual; only fixing items runs in a browser.

    # 1. Export from Libib: the item/barcode export and the collection export (both needed).
    python3 -m catalog libib diff --barcode-export libib_barcodes.csv --collection-export libib_collections.csv
    # -> runs/<id>/libib/: drift.csv, eligible.csv, orphans.csv, blocked.csv, libib-report.txt

    python3 -m catalog libib prepare --size 200     # -> libib-sync/batch-NNNN/{import.csv, posters, ready.csv}
    # 2. In Libib: Add Items -> CSV -> import.csv with Force Import Mode on.
    python3 -m catalog libib mark-imported batch-NNNN
    .venv-libib/bin/python -m catalog libib fix batch-NNNN      # barcode + title/description/tags/poster
    .venv-libib/bin/python -m catalog libib fix --drift         # fix what the diff found drifted
    python3 -m catalog libib status

`fix` needs `LIBIB_EMAIL` / `LIBIB_PASSWORD` and the Playwright venv. Items are matched by
Shopify barcode = Libib call number (items without a call number fall back to their copy
barcode; that drift needs a manual fix). Rentals with a bad or shared barcode are `blocked`
until the audit's barcode findings are fixed. Orphans are listed, never deleted.
`diff` promotes in-sync handles to `done` in `libib-sync/_state.json` and keeps the previous
state as `runs/<id>/libib/state-before.json`.
```

- [ ] **Step 2: Acceptance diff — ask the user for fresh exports**

Ask the user to export both Libib files (item/barcode + collection) and put them under `exports/<date>/`. Then run the diff against the **latest production audit run**:

```bash
python3 -m catalog libib diff --barcode-export exports/<date>/<barcodes>.csv --collection-export exports/<date>/<collection>.csv
cat "$(ls -d runs/20* | tail -1)/libib/libib-report.txt"
python3 -m catalog libib prepare --dry-run
python3 -m catalog libib fix --drift --dry-run
git diff --stat libib-sync/_state.json
```
Check against `LIBIB_MIGRATION_PROGRESS.md` and the old `libib-sync/_state.json` counts (2,512 done / 465 needs-review / 3 imported before this plan): in-sync + drift should be close to the number of Libib items; eligible should be the rentals not yet in Libib; look at 5 drift rows and 5 orphans by hand and confirm each is real.

- [ ] **Step 3: One-item browser check — ask the user first (edits Libib)**

Only with the user's go-ahead (it edits a real Libib item):
```bash
export LIBIB_EMAIL=... LIBIB_PASSWORD=...     # the user sets these
.venv-libib/bin/python -m catalog libib fix --drift --limit 1
```
Expected: a visible browser logs in, fixes one item, reloads to verify, and the report CSV shows no `error`. Then `python3 -m catalog libib status`.

- [ ] **Step 4: Record and commit**

Write `claudedocs/2026-09-25-libib-acceptance.md`: the export files used, `libib-report.txt`, the dry-run plan summaries, the spot-checks (5 drift, 5 orphans), the one-item fix result (or "not run — user declined"), and any rule that looked wrong (becomes a fix-up task before Plan 4).

```bash
git add catalog/README.md claudedocs/2026-09-25-libib-acceptance.md libib-sync/_state.json
git commit -m "docs(catalog): Libib stage README and acceptance results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PXt42mXgnGwT9xq4eZqewS"
```
(`libib-sync/_state.json` is committed only if the diff changed it — check `git diff --stat` first and mention the promoted/migrated counts in the commit body.)
