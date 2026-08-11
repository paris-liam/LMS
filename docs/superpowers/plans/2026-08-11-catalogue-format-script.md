# Catalogue Format Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `formatting-scripts/run.py`, one command that takes any movie CSV — a batch from the upload template or a Shopify catalogue export — and produces an importable `upload.csv` plus separate, re-runnable files for rows it could not resolve.

**Architecture:** Two stages. Stage 1 (`normalize.py`, pure functions, no I/O) classifies every product and either normalizes it to the current data model or diverts it to `issues.csv` with a reason. Stage 2 (`tmdb_fill.py`) fills empty descriptions and posters from TMDB, sending ambiguous matches to an HTML poster picker and dead ends to `tmdb-unmatched.csv`. Every output file is a valid input file, so the correction loop is the same command re-run.

**Tech Stack:** Python 3.13 standard library only — `csv`, `json`, `re`, `difflib`, `urllib`, `unittest`. No third-party packages, no venv, matching `data-cleanup/`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md`. Read it before Task 1.
- **New code lives in `formatting-scripts/` at the repo root.** `data-cleanup/` is never modified. Files reused from it are *copied* with `cp`, then edited, so `git log --follow` still reaches the original.
- **Standard library only.** No `pip install`, no `requirements.txt`.
- **Handles on export-shaped rows are never rewritten.** A handle is a live product's identity.
- **Never write review state into product tags.** Issues live in files. Tags on an output row must contain only `Type, Format, Genre…, extras`.
- **`Variant Inventory Tracker` is always `shopify`.** Blank stops Shopify tracking stock, which pins `product.available` to true and makes the theme's out-of-stock state unreachable.
- **Genre is never inferred from a title; type is never inferred from price.** Both are flagged instead.
- **Never overwrite a non-empty `Body (HTML)` or `Image Src`.**
- **Poster base URL is `https://image.tmdb.org/t/p/w1280`** (the `data-cleanup` original uses `w500` — this is a deliberate change).
- **Genre metaobject handles** are joined with `"; "` — semicolon then space.
- **Tags** are joined with `", "` — comma then space.
- Tests are `unittest`, in `tests/formatting_scripts/`, run with `python3 -m unittest discover -s tests/formatting_scripts -p "<file>.py" -v` from the repo root. Each test file inserts `formatting-scripts/` on `sys.path`, matching `tests/data_cleanup/`.
- Work on the current branch `feature/client-upload-template`. Commit after every task.

---

### Task 1: Scaffold + taxonomy

The vocabulary every other module resolves against: 13 genre labels and their metaobject handles, 4 formats, 2 types, and the typo table drawn from the real values in `products_export_1.csv`.

**Files:**
- Create: `formatting-scripts/taxonomy.py`
- Test: `tests/formatting_scripts/test_taxonomy.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GENRES: dict[str, str]` (label → metaobject handle), `FORMATS: list[str]`, `TYPES: list[str]`, `canonical_genre(value: str) -> str | None`, `canonical_format(value: str) -> str | None`, `canonical_type(value: str) -> str | None`, `genre_handle(label: str) -> str | None`, `normalize_key(value: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_taxonomy.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from taxonomy import (
    GENRES,
    FORMATS,
    TYPES,
    canonical_format,
    canonical_genre,
    canonical_type,
    genre_handle,
    normalize_key,
)


class TestNormalizeKey(unittest.TestCase):
    def test_lowercases_and_collapses_punctuation(self):
        self.assertEqual(normalize_key("Blu-Ray"), "blu ray")
        self.assertEqual(normalize_key("  Kids & Family "), "kids family")
        self.assertEqual(normalize_key("Sci-Fi"), "sci fi")


class TestCanonicalGenre(unittest.TestCase):
    def test_exact_labels_round_trip(self):
        for label in GENRES:
            self.assertEqual(canonical_genre(label), label)

    def test_thirteen_genres(self):
        self.assertEqual(len(GENRES), 13)

    def test_case_and_punctuation_insensitive(self):
        self.assertEqual(canonical_genre("sci-fi"), "Sci-Fi")
        self.assertEqual(canonical_genre("KIDS & FAMILY"), "Kids & Family")

    def test_known_typos_from_the_real_export(self):
        self.assertEqual(canonical_genre("Horor"), "Horror")
        self.assertEqual(canonical_genre("Sc-Fi"), "Sci-Fi")
        self.assertEqual(canonical_genre("SciFi"), "Sci-Fi")
        self.assertEqual(canonical_genre("Kids & Famiy"), "Kids & Family")
        self.assertEqual(canonical_genre("Romatic Comedy"), "Romantic Comedy")
        self.assertEqual(canonical_genre("Muscal"), "Musical")
        self.assertEqual(canonical_genre("Kids"), "Kids & Family")

    def test_unknown_values_return_none(self):
        for value in ("Special Interest", "Chicago", "#REF!", "#VALUE!", "", "   "):
            self.assertIsNone(canonical_genre(value), value)


class TestGenreHandle(unittest.TestCase):
    def test_maps_labels_to_metaobject_handles(self):
        self.assertEqual(genre_handle("Kids & Family"), "kids-family")
        self.assertEqual(genre_handle("Romantic Comedy"), "romantic-comedy")
        self.assertEqual(genre_handle("Foreign"), "foreign")

    def test_unknown_label_returns_none(self):
        self.assertIsNone(genre_handle("Special Interest"))


class TestCanonicalFormat(unittest.TestCase):
    def test_four_formats(self):
        self.assertEqual(FORMATS, ["VHS", "DVD", "Blu-Ray", "4K"])

    def test_fixes_case_from_the_real_export(self):
        self.assertEqual(canonical_format("BLU-RAY"), "Blu-Ray")
        self.assertEqual(canonical_format("Dvd"), "DVD")
        self.assertEqual(canonical_format("4k"), "4K")
        self.assertEqual(canonical_format("vhs"), "VHS")

    def test_non_format_vendors_return_none(self):
        for value in ("Unknown", "Unknown Brand", "Little Movie Store",
                      "Walt Disney", "Arrow Video", "Supercycle", ""):
            self.assertIsNone(canonical_format(value), value)


class TestCanonicalType(unittest.TestCase):
    def test_two_types(self):
        self.assertEqual(TYPES, ["Rental", "Floor Sale"])

    def test_fixes_typos_from_the_real_export(self):
        self.assertEqual(canonical_type("Floorsale"), "Floor Sale")
        self.assertEqual(canonical_type("Foor Sale"), "Floor Sale")
        self.assertEqual(canonical_type("Floor sale"), "Floor Sale")
        self.assertEqual(canonical_type("rental"), "Rental")

    def test_other_tags_return_none(self):
        for value in ("Comedy", "Criterion Collection", "A24", ""):
            self.assertIsNone(canonical_type(value), value)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_taxonomy.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'taxonomy'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/taxonomy.py`:

```python
"""Canonical vocabulary for the movie catalogue: genres, formats and types.

Genre labels are the 13 shelf genres; their values are the metaobject
handles behind product.metafields.shopify.genre. Formats are the four
values allowed in product.vendor (media format lives in Vendor, not in
shopify.media-format — see claudedocs/2026-08-07-product-data-model-audit.md).

The alias tables hold every misspelling actually observed in
products_export_1.csv. Anything outside them resolves to None and is
flagged rather than guessed.
"""

import re

GENRES = {
    "Comedy": "comedy",
    "Action": "action",
    "Drama": "drama",
    "Kids & Family": "kids-family",
    "Sci-Fi": "sci-fi",
    "Thriller": "thriller",
    "Horror": "horror",
    "Romantic Comedy": "romantic-comedy",
    "Musical": "musical",
    "Fantasy": "fantasy",
    "Documentary": "documentary",
    "Foreign": "foreign",
    "Holiday": "holiday",
}

FORMATS = ["VHS", "DVD", "Blu-Ray", "4K"]

TYPES = ["Rental", "Floor Sale"]

# Observed misspellings -> canonical label, keyed by normalize_key().
GENRE_ALIASES = {
    "horor": "Horror",
    "sc fi": "Sci-Fi",
    "scifi": "Sci-Fi",
    "kids famiy": "Kids & Family",
    "kids": "Kids & Family",
    "romatic comedy": "Romantic Comedy",
    "muscal": "Musical",
}

FORMAT_ALIASES = {
    "bluray": "Blu-Ray",
}

TYPE_ALIASES = {
    "floorsale": "Floor Sale",
    "foor sale": "Floor Sale",
}


def normalize_key(value: str) -> str:
    """Lowercase and collapse every run of non-alphanumerics to one space."""
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _resolve(value: str, canonical: list[str], aliases: dict[str, str]) -> str | None:
    key = normalize_key(value)
    if not key:
        return None
    for label in canonical:
        if normalize_key(label) == key:
            return label
    return aliases.get(key)


def canonical_genre(value: str) -> str | None:
    """Return the canonical genre label for a raw value, or None."""
    return _resolve(value, list(GENRES), GENRE_ALIASES)


def canonical_format(value: str) -> str | None:
    """Return the canonical format for a raw Vendor or tag value, or None."""
    return _resolve(value, FORMATS, FORMAT_ALIASES)


def canonical_type(value: str) -> str | None:
    """Return "Rental" or "Floor Sale" for a raw tag value, or None."""
    return _resolve(value, TYPES, TYPE_ALIASES)


def genre_handle(label: str) -> str | None:
    """Return the shopify.genre metaobject handle for a canonical label."""
    return GENRES.get(label)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_taxonomy.py" -v`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/taxonomy.py tests/formatting_scripts/test_taxonomy.py
git commit -m "feat(formatting): canonical genre/format/type taxonomy"
```

---

### Task 2: Output column contracts

Two output shapes. The template shape must stay byte-identical to the header the client's sheets already produce — this test is the seam where the script and the sheets would otherwise drift apart unnoticed.

**Files:**
- Create: `formatting-scripts/columns.py`
- Test: `tests/formatting_scripts/test_columns.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TEMPLATE_COLUMNS: list[str]` (17), `EXPORT_COLUMNS: list[str]` (18), `FIXED_VALUES: dict[str, str]`, `GENRE_METAFIELD: str`, `REASON_COLUMN: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_columns.py`:

```python
import csv
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

from columns import (
    EXPORT_COLUMNS,
    FIXED_VALUES,
    GENRE_METAFIELD,
    REASON_COLUMN,
    TEMPLATE_COLUMNS,
)

TEMPLATE_CSV = REPO_ROOT / "data-cleanup/client-template/client-upload-template-rental.csv"


class TestTemplateContract(unittest.TestCase):
    def test_matches_the_client_template_header_exactly(self):
        """The seam: if the sheet changes and this doesn't, imports drift."""
        with open(TEMPLATE_CSV, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        # The sheet carries helper columns R-W after the 17 Shopify columns.
        self.assertEqual(TEMPLATE_COLUMNS, header[:17])

    def test_has_seventeen_columns(self):
        self.assertEqual(len(TEMPLATE_COLUMNS), 17)


class TestExportContract(unittest.TestCase):
    def test_sets_only_intended_columns(self):
        self.assertEqual(EXPORT_COLUMNS, [
            "Handle", "Title", "Body (HTML)", "Vendor", "Product Category",
            "Tags", "Option1 Name", "Option1 Value",
            "Variant Inventory Tracker", "Variant Inventory Qty",
            "Variant Inventory Policy", "Variant Fulfillment Service",
            "Variant Price", "Variant Barcode",
            "Image Src", "Image Position", "Image Alt Text",
            GENRE_METAFIELD,
        ])

    def test_omits_columns_shopify_must_leave_untouched(self):
        for column in ("Status", "Published", "SEO Title", "SEO Description",
                       "Variant SKU", "Variant Grams", "Type"):
            self.assertNotIn(column, EXPORT_COLUMNS)

    def test_carries_barcode_so_printed_labels_survive_a_variant_rebuild(self):
        self.assertIn("Variant Barcode", EXPORT_COLUMNS)


class TestFixedValues(unittest.TestCase):
    def test_inventory_tracker_is_always_shopify(self):
        self.assertEqual(FIXED_VALUES["Variant Inventory Tracker"], "shopify")

    def test_the_rest_of_the_fixed_set(self):
        self.assertEqual(FIXED_VALUES["Product Category"], "Media > Videos")
        self.assertEqual(FIXED_VALUES["Option1 Name"], "Genre")
        self.assertEqual(FIXED_VALUES["Variant Inventory Qty"], "1")
        self.assertEqual(FIXED_VALUES["Variant Inventory Policy"], "deny")
        self.assertEqual(FIXED_VALUES["Variant Fulfillment Service"], "manual")

    def test_reason_column_name(self):
        self.assertEqual(REASON_COLUMN, "Reason")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_columns.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'columns'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/columns.py`:

```python
"""The two output column contracts and the values fixed on every row.

Template output creates new products and matches the client sheets'
17-column header exactly. Export output updates products that already
exist and deliberately omits every column it does not intend to set —
Shopify leaves absent columns untouched, so anything omitted here cannot
be clobbered by the import.
"""

GENRE_METAFIELD = "Genre (product.metafields.shopify.genre)"
REASON_COLUMN = "Reason"

TEMPLATE_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Tags",
    "Status",
    "Option1 Name",
    "Option1 Value",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Image Src",
    "Image Alt Text",
    GENRE_METAFIELD,
]

EXPORT_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Tags",
    "Option1 Name",
    "Option1 Value",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    GENRE_METAFIELD,
]

FIXED_VALUES = {
    "Product Category": "Media > Videos",
    "Option1 Name": "Genre",
    "Variant Inventory Tracker": "shopify",
    "Variant Inventory Qty": "1",
    "Variant Inventory Policy": "deny",
    "Variant Fulfillment Service": "manual",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_columns.py" -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/columns.py tests/formatting_scripts/test_columns.py
git commit -m "feat(formatting): output column contracts for template and export shapes"
```

---

### Task 3: Input-shape detection

Three inputs must be told apart from the header alone, and a prior output carrying a `Reason` column must round-trip back to the shape it came from.

**Files:**
- Create: `formatting-scripts/detect.py`
- Test: `tests/formatting_scripts/test_detect.py`

**Interfaces:**
- Consumes: `columns.REASON_COLUMN`.
- Produces: `detect_shape(fieldnames: list[str]) -> str` returning `"template"` or `"export"` and raising `UnknownShapeError` otherwise; `strip_reason(fieldnames: list[str], rows: list[dict]) -> tuple[list[str], list[dict]]`; `class UnknownShapeError(ValueError)`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_detect.py`:

```python
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

from columns import EXPORT_COLUMNS, TEMPLATE_COLUMNS
from detect import UnknownShapeError, detect_shape, strip_reason

RAW_TEMPLATE = TEMPLATE_COLUMNS + ["Format", "Genre 1", "Genre 2", "Genre 3", "Year", "Extra tags"]
RAW_EXPORT = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
              "Tags", "Published", "Option1 Name", "Option1 Value", "Variant SKU",
              "Variant Inventory Tracker", "Variant Price", "Variant Barcode",
              "Image Src", "Image Position", "Image Alt Text"]


class TestDetectShape(unittest.TestCase):
    def test_raw_client_template_with_helper_columns(self):
        self.assertEqual(detect_shape(RAW_TEMPLATE), "template")

    def test_raw_shopify_export(self):
        self.assertEqual(detect_shape(RAW_EXPORT), "export")

    def test_our_own_template_output(self):
        self.assertEqual(detect_shape(TEMPLATE_COLUMNS), "template")

    def test_our_own_export_output(self):
        self.assertEqual(detect_shape(EXPORT_COLUMNS), "export")

    def test_unknown_header_is_a_hard_error_naming_what_was_missing(self):
        with self.assertRaises(UnknownShapeError) as caught:
            detect_shape(["Name", "Price", "Qty"])
        message = str(caught.exception)
        self.assertIn("Genre 1", message)
        self.assertIn("Variant Barcode", message)
        self.assertIn("Status", message)


class TestStripReason(unittest.TestCase):
    def test_removes_the_reason_column_and_its_values(self):
        fieldnames = ["Reason"] + TEMPLATE_COLUMNS
        rows = [{"Reason": "no usable genre", "Handle": "a", "Title": "A"}]
        new_fieldnames, new_rows = strip_reason(fieldnames, rows)
        self.assertEqual(new_fieldnames, TEMPLATE_COLUMNS)
        self.assertNotIn("Reason", new_rows[0])
        self.assertEqual(new_rows[0]["Handle"], "a")

    def test_leaves_a_reasonless_file_alone(self):
        rows = [{"Handle": "a"}]
        new_fieldnames, new_rows = strip_reason(TEMPLATE_COLUMNS, rows)
        self.assertEqual(new_fieldnames, TEMPLATE_COLUMNS)
        self.assertEqual(new_rows, rows)

    def test_a_prior_issues_file_round_trips_to_its_origin_shape(self):
        fieldnames, _ = strip_reason(["Reason"] + RAW_EXPORT, [])
        self.assertEqual(detect_shape(fieldnames), "export")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_detect.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'detect'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/detect.py`:

```python
"""Work out which of the three input shapes a CSV is, from its header.

A prior output of this script carries a leading Reason column plus the
columns of whatever it came from, so stripping Reason first lets the same
rules classify it.
"""

from columns import REASON_COLUMN


class UnknownShapeError(ValueError):
    """The header matches neither the upload template nor a Shopify export."""


# Checked in order. "Variant Barcode" appears in a raw Shopify export and in
# this script's export output, but never in the 17-column template contract.
TEMPLATE_MARKERS = ("Format", "Genre 1")
EXPORT_MARKER = "Variant Barcode"
TEMPLATE_OUTPUT_MARKER = "Status"


def strip_reason(fieldnames: list[str], rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Drop the Reason column added to issues/unmatched files, if present."""
    if REASON_COLUMN not in fieldnames:
        return fieldnames, rows
    kept = [name for name in fieldnames if name != REASON_COLUMN]
    stripped = [{k: v for k, v in row.items() if k != REASON_COLUMN} for row in rows]
    return kept, stripped


def detect_shape(fieldnames: list[str]) -> str:
    """Return "template" or "export"; raise UnknownShapeError if neither."""
    columns = set(fieldnames)
    if all(marker in columns for marker in TEMPLATE_MARKERS):
        return "template"
    if EXPORT_MARKER in columns:
        return "export"
    if TEMPLATE_OUTPUT_MARKER in columns:
        return "template"
    raise UnknownShapeError(
        "Unrecognised CSV header. Expected either the upload template "
        f"(columns {', '.join(TEMPLATE_MARKERS)}), this script's template output "
        f"(column {TEMPLATE_OUTPUT_MARKER}), or a Shopify product export "
        f"(column {EXPORT_MARKER}). Got: {', '.join(fieldnames) or '(empty header)'}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_detect.py" -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/detect.py tests/formatting_scripts/test_detect.py
git commit -m "feat(formatting): input-shape detection with Reason round-trip"
```

---

### Task 4: Handle derivation

Only template rows get a derived handle. This must reproduce the sheet formula exactly, including the `-n` copy suffix, or the script and the sheet will disagree about what a second copy is called.

**Files:**
- Create: `formatting-scripts/handles.py`
- Test: `tests/formatting_scripts/test_handles.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `slugify(text: str) -> str`, `derive_handle(title: str, media_format: str, product_type: str) -> str`, `class HandleAllocator` with `.allocate(base: str) -> str` and `.reserve(handle: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_handles.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from handles import HandleAllocator, derive_handle, slugify


class TestSlugify(unittest.TestCase):
    def test_drops_apostrophes_rather_than_hyphenating_them(self):
        self.assertEqual(slugify("The Monkey's Uncle"), "the-monkeys-uncle")
        self.assertEqual(slugify("Trick ’r Treat"), "trick-r-treat")

    def test_commas_and_spaces_become_single_hyphens(self):
        self.assertEqual(slugify("Paris, Texas"), "paris-texas")

    def test_trims_leading_and_trailing_hyphens(self):
        self.assertEqual(slugify("  Rushmore!  "), "rushmore")

    def test_accents_are_dropped_like_the_sheet_formula(self):
        self.assertEqual(slugify("Amélie"), "am-lie")
        self.assertEqual(slugify("8½"), "8")


class TestDeriveHandle(unittest.TestCase):
    def test_the_worked_examples_from_the_client_guide(self):
        self.assertEqual(derive_handle("Rushmore", "VHS", "Rental"), "rushmore-vhs-rental")
        self.assertEqual(derive_handle("Rushmore", "DVD", "Rental"), "rushmore-dvd-rental")
        self.assertEqual(derive_handle("Paris, Texas", "DVD", "Rental"), "paris-texas-dvd-rental")
        self.assertEqual(
            derive_handle("The Monkey's Uncle", "VHS", "Floor Sale"),
            "the-monkeys-uncle-vhs-floor-sale",
        )
        self.assertEqual(derive_handle("The Thing", "4K", "Floor Sale"), "the-thing-4k-floor-sale")

    def test_blu_ray_keeps_its_internal_hyphen(self):
        self.assertEqual(derive_handle("Alien", "Blu-Ray", "Rental"), "alien-blu-ray-rental")


class TestHandleAllocator(unittest.TestCase):
    def test_first_use_is_unsuffixed(self):
        allocator = HandleAllocator()
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental")

    def test_repeat_copies_count_up(self):
        allocator = HandleAllocator()
        allocator.allocate("rushmore-vhs-rental")
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental-2")
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental-3")

    def test_different_format_is_a_different_handle(self):
        allocator = HandleAllocator()
        allocator.allocate("rushmore-vhs-rental")
        self.assertEqual(allocator.allocate("rushmore-dvd-rental"), "rushmore-dvd-rental")

    def test_reserved_handles_are_avoided(self):
        """A client's hand-typed handle override must not be re-issued."""
        allocator = HandleAllocator()
        allocator.reserve("amelie-dvd-rental")
        self.assertEqual(allocator.allocate("amelie-dvd-rental"), "amelie-dvd-rental-2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_handles.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'handles'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/handles.py`:

```python
"""Handle derivation for new products, mirroring the sheet's LET formula.

Apostrophes are deleted rather than turned into hyphens ("the-monkeys-uncle",
not "the-monkey-s-uncle"). Every other non-alphanumeric run collapses to a
single hyphen, which is why accents drop out ("Amelie" -> "am-lie") exactly
as they do in the sheet. Rare titles like that are corrected by hand.

Only rows that describe a product Shopify does not have yet get a derived
handle. Export rows keep theirs verbatim.
"""

import re

APOSTROPHES = re.compile(r"['’]")


def slugify(text: str) -> str:
    """Lowercase, delete apostrophes, collapse everything else to hyphens."""
    lowered = APOSTROPHES.sub("", (text or "").strip().lower())
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    return hyphenated.strip("-")


def derive_handle(title: str, media_format: str, product_type: str) -> str:
    """title + format + type -> the unsuffixed base handle."""
    return f"{slugify(title)}-{slugify(media_format)}-{slugify(product_type)}"


class HandleAllocator:
    """Hands out unique handles within a single run, suffixing repeats -2, -3."""

    def __init__(self):
        self._used: set[str] = set()

    def reserve(self, handle: str) -> None:
        """Mark a handle as taken without allocating it (hand-typed overrides)."""
        if handle:
            self._used.add(handle)

    def allocate(self, base: str) -> str:
        """Return base, or base-2 / base-3 / ... if base is already taken."""
        if base not in self._used:
            self._used.add(base)
            return base
        index = 2
        while f"{base}-{index}" in self._used:
            index += 1
        handle = f"{base}-{index}"
        self._used.add(handle)
        return handle
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_handles.py" -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/handles.py tests/formatting_scripts/test_handles.py
git commit -m "feat(formatting): handle derivation matching the sheet formula"
```

---

### Task 5: Field resolution

The judgement layer: given one product's raw fields, work out its format, type and genres, or return the reason it can't be worked out. Pure, no I/O, so the whole flag table is testable directly.

**Files:**
- Create: `formatting-scripts/resolve.py`
- Test: `tests/formatting_scripts/test_resolve.py`

**Interfaces:**
- Consumes: `taxonomy.canonical_format`, `taxonomy.canonical_genre`, `taxonomy.canonical_type`.
- Produces: `split_list(value: str) -> list[str]`, `resolve_type(tags: list[str]) -> tuple[str | None, str | None]`, `resolve_genres(option1_value: str, tags: list[str], helper_genres: list[str]) -> tuple[list[str], str | None]`, `resolve_format(vendor: str, option1_value: str, tags: list[str], helper_format: str) -> tuple[str | None, str | None]`, `resolve_price(product_type: str, raw_price: str) -> tuple[str | None, str | None]`, `extra_tags(tags: list[str]) -> list[str]`. Every resolver returns `(value, reason)` where exactly one side is non-None.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_resolve.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from resolve import (
    extra_tags,
    resolve_format,
    resolve_genres,
    resolve_price,
    resolve_type,
    split_list,
)


class TestSplitList(unittest.TestCase):
    def test_splits_on_commas_and_trims(self):
        self.assertEqual(split_list("Rental, VHS,  Comedy "), ["Rental", "VHS", "Comedy"])

    def test_drops_empties(self):
        self.assertEqual(split_list("Rental,,VHS"), ["Rental", "VHS"])
        self.assertEqual(split_list(""), [])


class TestResolveType(unittest.TestCase):
    def test_finds_the_type_tag(self):
        self.assertEqual(resolve_type(["Rental", "VHS", "Comedy"]), ("Rental", None))
        self.assertEqual(resolve_type(["Floorsale", "DVD"]), ("Floor Sale", None))

    def test_no_type_tag_is_flagged_never_guessed_from_price(self):
        value, reason = resolve_type(["VHS", "Comedy"])
        self.assertIsNone(value)
        self.assertIn("no Rental or Floor Sale tag", reason)

    def test_both_types_is_flagged(self):
        value, reason = resolve_type(["Rental", "Floor Sale", "VHS"])
        self.assertIsNone(value)
        self.assertIn("both", reason)


class TestResolveGenres(unittest.TestCase):
    def test_prefers_option1_value(self):
        self.assertEqual(resolve_genres("Comedy", ["Rental", "Drama"], []), (["Comedy"], None))

    def test_compound_option1_keeps_only_the_genre_part(self):
        self.assertEqual(resolve_genres("4K, Action", [], []), (["Action"], None))
        self.assertEqual(resolve_genres("Comedy, Criterion Collection", [], []), (["Comedy"], None))

    def test_falls_back_to_tags_when_option1_is_unusable(self):
        self.assertEqual(resolve_genres("Standard", ["Rental", "Horror"], []), (["Horror"], None))
        self.assertEqual(resolve_genres("#VALUE!", ["Comedy"], []), (["Comedy"], None))

    def test_helper_columns_win_when_present(self):
        genres, reason = resolve_genres("", ["Rental"], ["Sci-Fi", "Thriller", ""])
        self.assertEqual(genres, ["Sci-Fi", "Thriller"])
        self.assertIsNone(reason)

    def test_multiple_tag_genres_keep_tag_order(self):
        self.assertEqual(resolve_genres("", ["Comedy", "Rental", "Musical"], [])[0],
                         ["Comedy", "Musical"])

    def test_deduplicates(self):
        self.assertEqual(resolve_genres("Comedy", ["Comedy", "comedy"], [])[0], ["Comedy"])

    def test_no_usable_genre_is_flagged(self):
        for option1, tags in (("Special Interest", ["Rental"]), ("#REF!", []),
                              ("Chicago", []), ("", ["Rental", "VHS"])):
            genres, reason = resolve_genres(option1, tags, [])
            self.assertEqual(genres, [])
            self.assertIn("no usable genre", reason)


class TestResolveFormat(unittest.TestCase):
    def test_reads_vendor_and_fixes_case(self):
        self.assertEqual(resolve_format("BLU-RAY", "", [], ""), ("Blu-Ray", None))
        self.assertEqual(resolve_format("Dvd", "", [], ""), ("DVD", None))

    def test_helper_column_wins(self):
        self.assertEqual(resolve_format("VHS", "", [], "4K"), ("4K", None))

    def test_compound_option1_overrides_vendor(self):
        """A DVD-vendored row whose genre cell says "4K, Action" is a 4K disc."""
        self.assertEqual(resolve_format("DVD", "4K, Action", [], ""), ("4K", None))

    def test_falls_back_to_a_format_tag(self):
        self.assertEqual(resolve_format("Unknown", "", ["Rental", "4K"], ""), ("4K", None))

    def test_unusable_vendor_with_no_other_signal_is_flagged(self):
        for vendor in ("Unknown", "Little Movie Store", "Walt Disney", ""):
            value, reason = resolve_format(vendor, "Comedy", ["Rental"], "")
            self.assertIsNone(value, vendor)
            self.assertIn("no media format", reason)


class TestResolvePrice(unittest.TestCase):
    def test_rental_is_forced_to_zero(self):
        self.assertEqual(resolve_price("Rental", ""), ("0", None))
        self.assertEqual(resolve_price("Rental", "0.00"), ("0", None))

    def test_rental_with_a_real_price_is_flagged(self):
        value, reason = resolve_price("Rental", "12.99")
        self.assertIsNone(value)
        self.assertIn("Rental with a nonzero price", reason)

    def test_floor_sale_keeps_its_price(self):
        self.assertEqual(resolve_price("Floor Sale", "24.99"), ("24.99", None))

    def test_floor_sale_at_zero_or_blank_is_flagged(self):
        for raw in ("0", "0.00", ""):
            value, reason = resolve_price("Floor Sale", raw)
            self.assertIsNone(value, raw)
            self.assertIn("Floor Sale with no price", reason)

    def test_unparseable_price_is_flagged(self):
        value, reason = resolve_price("Floor Sale", "#REF!")
        self.assertIsNone(value)
        self.assertIn("unreadable price", reason)


class TestExtraTags(unittest.TestCase):
    def test_keeps_only_tags_that_are_not_type_format_or_genre(self):
        tags = ["Rental", "VHS", "Comedy", "Criterion Collection", "A24"]
        self.assertEqual(extra_tags(tags), ["Criterion Collection", "A24"])

    def test_preserves_order_and_deduplicates(self):
        self.assertEqual(extra_tags(["A24", "Rental", "A24"]), ["A24"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_resolve.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'resolve'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/resolve.py`:

```python
"""Resolve one product's format, type, genres and price from raw fields.

Every resolver returns (value, reason): a value with reason None, or None
with a human-readable reason that lands in issues.csv. Nothing is guessed —
a genre is never inferred from a title and a type is never inferred from a
price, because both would silently mislabel physical shelf stock.
"""

from taxonomy import canonical_format, canonical_genre, canonical_type

ZERO_PRICES = {"", "0", "0.0", "0.00"}


def split_list(value: str) -> list[str]:
    """Split a comma-separated cell into trimmed, non-empty parts."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def resolve_type(tags: list[str]) -> tuple[str | None, str | None]:
    """Find the Rental / Floor Sale tag."""
    found = _dedupe([t for t in (canonical_type(tag) for tag in tags) if t])
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, "no Rental or Floor Sale tag — cannot tell which this is"
    return None, f"tagged as both {' and '.join(found)}"


def resolve_genres(
    option1_value: str, tags: list[str], helper_genres: list[str]
) -> tuple[list[str], str | None]:
    """Resolve the genre list, primary first.

    Helper columns win when the sheet supplied them; otherwise Option1
    Value (the barcode-label slot) is authoritative, and tags are the
    fallback for CircaOS-era rows whose Option1 holds a condition.
    """
    from_helpers = _dedupe([g for g in (canonical_genre(v) for v in helper_genres) if g])
    if from_helpers:
        return from_helpers, None

    from_option1 = _dedupe([g for g in (canonical_genre(v) for v in split_list(option1_value)) if g])
    if from_option1:
        return from_option1, None

    from_tags = _dedupe([g for g in (canonical_genre(tag) for tag in tags) if g])
    if from_tags:
        return from_tags, None

    return [], (
        f"no usable genre (Option1 Value {option1_value!r}, "
        f"tags {', '.join(tags) or '(none)'})"
    )


def resolve_format(
    vendor: str, option1_value: str, tags: list[str], helper_format: str
) -> tuple[str | None, str | None]:
    """Resolve the media format for product.vendor.

    Precedence: helper column, then a format named inside a compound
    Option1 Value ("4K, Action" is a 4K disc whatever Vendor says), then
    Vendor itself, then a format tag.
    """
    from_helper = canonical_format(helper_format)
    if from_helper:
        return from_helper, None

    for part in split_list(option1_value):
        from_option1 = canonical_format(part)
        if from_option1:
            return from_option1, None

    from_vendor = canonical_format(vendor)
    if from_vendor:
        return from_vendor, None

    for tag in tags:
        from_tag = canonical_format(tag)
        if from_tag:
            return from_tag, None

    return None, f"no media format (Vendor {vendor!r} is not VHS/DVD/Blu-Ray/4K)"


def resolve_price(product_type: str, raw_price: str) -> tuple[str | None, str | None]:
    """Rentals are always 0; floor-sale items must carry a real price."""
    value = (raw_price or "").strip()

    if product_type == "Rental":
        if value in ZERO_PRICES:
            return "0", None
        return None, f"Rental with a nonzero price ({value})"

    if value in ZERO_PRICES:
        return None, "Floor Sale with no price"
    try:
        float(value)
    except ValueError:
        return None, f"unreadable price ({value})"
    return value, None


def extra_tags(tags: list[str]) -> list[str]:
    """Tags that are not a type, a format or a genre — curation labels."""
    kept = [
        tag for tag in tags
        if not (canonical_type(tag) or canonical_format(tag) or canonical_genre(tag))
    ]
    return _dedupe(kept)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_resolve.py" -v`
Expected: PASS, 21 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/resolve.py tests/formatting_scripts/test_resolve.py
git commit -m "feat(formatting): field resolvers for format, type, genre and price"
```

---

### Task 6: Normalization

Assembles the resolvers into whole output rows, handles the group-level cases (extra image rows, multi-variant products, duplicate output handles), and produces the two output shapes.

**Files:**
- Create: `formatting-scripts/normalize.py`
- Create: `formatting-scripts/catalog_common.py` (copied)
- Test: `tests/formatting_scripts/test_normalize.py`

**Interfaces:**
- Consumes: `columns.*`, `handles.HandleAllocator`, `handles.derive_handle`, `resolve.*`, `taxonomy.genre_handle`.
- Produces: `normalize_rows(rows: list[dict], shape: str) -> tuple[list[dict], list[dict]]` returning `(clean_rows, issue_rows)`, where `clean_rows` use `TEMPLATE_COLUMNS` or `EXPORT_COLUMNS` and `issue_rows` are the original input rows with a `Reason` key added. Also `output_columns(shape: str) -> list[str]`.
- `catalog_common.py` provides `load_export`, `write_csv`, `split_tags`, `has_tag`, `add_tags`, `remove_tag`, `group_rows_by_handle` — copied unchanged.

- [ ] **Step 1: Copy catalog_common and commit it separately**

```bash
mkdir -p formatting-scripts tests/formatting_scripts
cp data-cleanup/catalog_common.py formatting-scripts/catalog_common.py
```

Then edit only its docstring's final line to read:

```python
"""Shared helpers for the catalogue formatting scripts: CSV I/O, tag
manipulation, and handle grouping.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""
```

```bash
git add formatting-scripts/catalog_common.py
git commit -m "chore(formatting): copy catalog_common from data-cleanup"
```

- [ ] **Step 2: Write the failing test**

Create `tests/formatting_scripts/test_normalize.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from columns import EXPORT_COLUMNS, GENRE_METAFIELD, TEMPLATE_COLUMNS
from normalize import normalize_rows, output_columns


def export_row(**overrides):
    row = {
        "Handle": "legend-of-zorro",
        "Title": "Legend of Zorro",
        "Body (HTML)": "<p>A masked hero rides again.</p>",
        "Vendor": "DVD",
        "Product Category": "",
        "Type": "",
        "Tags": "Floor Sale, Action",
        "Published": "TRUE",
        "Option1 Name": "Condition",
        "Option1 Value": "Standard",
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": "1",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": "9.99",
        "Variant Barcode": "88302842",
        "Image Src": "https://cdn.shopify.com/x.jpg",
        "Image Position": "1",
        "Image Alt Text": "",
    }
    row.update(overrides)
    return row


def template_row(**overrides):
    row = {
        "Handle": "",
        "Title": "Rushmore",
        "Body (HTML)": "",
        "Vendor": "",
        "Product Category": "",
        "Tags": "Rental, VHS, Comedy",
        "Status": "",
        "Option1 Name": "",
        "Option1 Value": "",
        "Variant Inventory Tracker": "",
        "Variant Inventory Qty": "",
        "Variant Inventory Policy": "",
        "Variant Fulfillment Service": "",
        "Variant Price": "",
        "Image Src": "",
        "Image Alt Text": "",
        GENRE_METAFIELD: "",
        "Format": "VHS",
        "Genre 1": "Comedy",
        "Genre 2": "",
        "Genre 3": "",
        "Year": "1998",
        "Extra tags": "",
    }
    row.update(overrides)
    return row


class TestOutputColumns(unittest.TestCase):
    def test_picks_the_contract_by_shape(self):
        self.assertEqual(output_columns("template"), TEMPLATE_COLUMNS)
        self.assertEqual(output_columns("export"), EXPORT_COLUMNS)


class TestExportNormalization(unittest.TestCase):
    def test_produces_exactly_the_export_columns(self):
        clean, issues = normalize_rows([export_row()], "export")
        self.assertEqual(issues, [])
        self.assertEqual(list(clean[0]), EXPORT_COLUMNS)

    def test_preserves_the_existing_handle_verbatim(self):
        clean, _ = normalize_rows([export_row(Handle="lEgEnd-of-zorro-99")], "export")
        self.assertEqual(clean[0]["Handle"], "lEgEnd-of-zorro-99")

    def test_carries_the_barcode_through(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Variant Barcode"], "88302842")

    def test_rewrites_option1_from_condition_to_the_primary_genre(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Option1 Name"], "Genre")
        self.assertEqual(clean[0]["Option1 Value"], "Action")

    def test_fills_the_genre_metafield_with_semicolon_joined_handles(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Floor Sale, Action, Sci-Fi")], "export"
        )
        self.assertEqual(clean[0][GENRE_METAFIELD], "action; sci-fi")

    def test_rebuilds_tags_as_type_format_genres_extras(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Floor Sale, Action, Criterion Collection")], "export"
        )
        self.assertEqual(clean[0]["Tags"], "Floor Sale, DVD, Action, Criterion Collection")

    def test_normalizes_vendor_case(self):
        clean, _ = normalize_rows([export_row(Vendor="BLU-RAY")], "export")
        self.assertEqual(clean[0]["Vendor"], "Blu-Ray")

    def test_applies_the_fixed_values(self):
        clean, _ = normalize_rows([export_row(**{"Product Category": ""})], "export")
        self.assertEqual(clean[0]["Product Category"], "Media > Videos")
        self.assertEqual(clean[0]["Variant Inventory Tracker"], "shopify")
        self.assertEqual(clean[0]["Variant Inventory Qty"], "1")
        self.assertEqual(clean[0]["Variant Inventory Policy"], "deny")
        self.assertEqual(clean[0]["Variant Fulfillment Service"], "manual")

    def test_forces_rental_price_to_zero(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Rental, Action", **{"Variant Price": "0.00"})], "export"
        )
        self.assertEqual(clean[0]["Variant Price"], "0")

    def test_writes_alt_text_when_an_image_has_none(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Image Alt Text"], "Legend of Zorro poster")

    def test_leaves_existing_alt_text_alone(self):
        clean, _ = normalize_rows(
            [export_row(**{"Image Alt Text": "Legend of Zorro (2005) poster"})], "export"
        )
        self.assertEqual(clean[0]["Image Alt Text"], "Legend of Zorro (2005) poster")

    def test_extra_image_rows_pass_through_with_image_fields_only(self):
        rows = [
            export_row(),
            {"Handle": "legend-of-zorro", "Title": "", "Vendor": "", "Tags": "",
             "Option1 Name": "", "Option1 Value": "", "Variant Price": "",
             "Variant Barcode": "", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2", "Image Alt Text": ""},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), 2)
        self.assertEqual(clean[1]["Image Src"], "https://cdn.shopify.com/y.jpg")
        self.assertEqual(clean[1]["Image Position"], "2")
        self.assertEqual(clean[1]["Title"], "")
        self.assertEqual(clean[1]["Vendor"], "")


class TestExportIssues(unittest.TestCase):
    def test_flags_a_row_with_no_usable_genre(self):
        clean, issues = normalize_rows(
            [export_row(**{"Option1 Value": "Special Interest", "Tags": "Floor Sale"})],
            "export",
        )
        self.assertEqual(clean, [])
        self.assertIn("no usable genre", issues[0]["Reason"])

    def test_flags_a_row_with_no_format(self):
        clean, issues = normalize_rows([export_row(Vendor="Unknown")], "export")
        self.assertEqual(clean, [])
        self.assertIn("no media format", issues[0]["Reason"])

    def test_flags_a_row_with_no_type_tag(self):
        clean, issues = normalize_rows([export_row(Tags="Action")], "export")
        self.assertEqual(clean, [])
        self.assertIn("no Rental or Floor Sale tag", issues[0]["Reason"])

    def test_flags_a_rental_priced_above_zero(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Rental, Action", **{"Variant Price": "12.99"})], "export"
        )
        self.assertEqual(clean, [])
        self.assertIn("Rental with a nonzero price", issues[0]["Reason"])

    def test_flags_a_multi_variant_product(self):
        rows = [
            export_row(**{"Option1 Value": "Standard"}),
            export_row(**{"Option1 Value": "50%", "Variant Barcode": "88302843"}),
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(clean, [])
        self.assertIn("2 variants", issues[0]["Reason"])

    def test_issue_rows_carry_the_original_columns_verbatim_for_editing(self):
        original = export_row(Vendor="Unknown")
        _, issues = normalize_rows([original], "export")
        for key, value in original.items():
            self.assertEqual(issues[0][key], value, key)
        self.assertIn("Reason", issues[0])

    def test_every_row_of_a_flagged_product_goes_to_issues(self):
        rows = [
            export_row(Vendor="Unknown"),
            {"Handle": "legend-of-zorro", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2"},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(clean, [])
        self.assertEqual(len(issues), 2)


class TestTemplateNormalization(unittest.TestCase):
    def test_produces_exactly_the_template_columns(self):
        clean, issues = normalize_rows([template_row()], "template")
        self.assertEqual(issues, [])
        self.assertEqual(list(clean[0]), TEMPLATE_COLUMNS)

    def test_derives_the_handle_and_sets_status_active(self):
        clean, _ = normalize_rows([template_row()], "template")
        self.assertEqual(clean[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(clean[0]["Status"], "Active")

    def test_second_copy_gets_a_numeric_suffix(self):
        clean, _ = normalize_rows([template_row(), template_row()], "template")
        self.assertEqual(clean[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(clean[1]["Handle"], "rushmore-vhs-rental-2")

    def test_a_hand_typed_handle_override_is_kept(self):
        clean, _ = normalize_rows(
            [template_row(Handle="amelie-dvd-rental", Title="Amélie", Format="DVD")],
            "template",
        )
        self.assertEqual(clean[0]["Handle"], "amelie-dvd-rental")

    def test_vendor_comes_from_the_format_helper(self):
        clean, _ = normalize_rows([template_row(Format="Blu-Ray")], "template")
        self.assertEqual(clean[0]["Vendor"], "Blu-Ray")

    def test_helper_genres_drive_option1_metafield_and_tags(self):
        clean, _ = normalize_rows(
            [template_row(**{"Genre 1": "Sci-Fi", "Genre 2": "Thriller",
                             "Extra tags": "A24"})],
            "template",
        )
        self.assertEqual(clean[0]["Option1 Value"], "Sci-Fi")
        self.assertEqual(clean[0][GENRE_METAFIELD], "sci-fi; thriller")
        self.assertEqual(clean[0]["Tags"], "Rental, VHS, Sci-Fi, Thriller, A24")

    def test_floor_sale_without_a_price_is_flagged(self):
        clean, issues = normalize_rows(
            [template_row(Tags="Floor Sale, VHS, Comedy")], "template"
        )
        self.assertEqual(clean, [])
        self.assertIn("Floor Sale with no price", issues[0]["Reason"])


class TestGrouping(unittest.TestCase):
    def test_template_rows_are_one_product_each_despite_blank_handles(self):
        """Blank Handle cells must not collapse a batch into one product."""
        clean, issues = normalize_rows(
            [template_row(Title="Rushmore"), template_row(Title="Bottle Rocket")],
            "template",
        )
        self.assertEqual(issues, [])
        self.assertEqual([r["Handle"] for r in clean],
                         ["rushmore-vhs-rental", "bottle-rocket-vhs-rental"])

    def test_export_rows_sharing_a_handle_are_one_product(self):
        rows = [
            export_row(),
            {"Handle": "legend-of-zorro", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2"},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), 2)


class TestDuplicateHandles(unittest.TestCase):
    def test_two_template_rows_typing_the_same_handle_are_both_flagged(self):
        rows = [
            template_row(Handle="amelie-dvd-rental", Title="Amélie", Format="DVD"),
            template_row(Handle="amelie-dvd-rental", Title="Amelie", Format="DVD"),
        ]
        clean, issues = normalize_rows(rows, "template")
        self.assertEqual(clean, [])
        self.assertEqual(len(issues), 2)
        self.assertIn("duplicate handle", issues[0]["Reason"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_normalize.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'normalize'`

- [ ] **Step 4: Write the implementation**

Create `formatting-scripts/normalize.py`:

```python
"""Turn raw input rows into rows that are safe to import, or into issues.

Pure: dicts in, dicts out, no filesystem and no network, so the whole
classification table is testable without a CSV or an API key.

A product is one Handle group. Its first row is the primary row; any
further rows are extra images, which pass through carrying image fields
only. When a product is flagged, every one of its rows goes to issues.csv
so the operator can fix and re-run the file as a whole.
"""

from catalog_common import group_rows_by_handle
from columns import (
    EXPORT_COLUMNS,
    FIXED_VALUES,
    GENRE_METAFIELD,
    REASON_COLUMN,
    TEMPLATE_COLUMNS,
)
from handles import HandleAllocator, derive_handle
from resolve import extra_tags, resolve_format, resolve_genres, resolve_price, resolve_type, split_list
from taxonomy import genre_handle


def output_columns(shape: str) -> list[str]:
    return TEMPLATE_COLUMNS if shape == "template" else EXPORT_COLUMNS


def _is_variant_row(row: dict) -> bool:
    """A real variant row carries option or price data; image rows don't."""
    return bool(
        (row.get("Option1 Value") or "").strip()
        or (row.get("Variant Price") or "").strip()
        or (row.get("Variant Barcode") or "").strip()
    )


def _blank_row(shape: str) -> dict:
    return {column: "" for column in output_columns(shape)}


def _image_row(row: dict, shape: str) -> dict:
    out = _blank_row(shape)
    out["Handle"] = row.get("Handle", "")
    out["Image Src"] = (row.get("Image Src") or "").strip()
    out["Image Alt Text"] = (row.get("Image Alt Text") or "").strip()
    if "Image Position" in out:
        out["Image Position"] = (row.get("Image Position") or "").strip()
    return out


def _resolve_product(primary: dict, shape: str) -> tuple[dict | None, str | None]:
    """Resolve one primary row into output values, or return a reason."""
    tags = split_list(primary.get("Tags", ""))
    option1_value = (primary.get("Option1 Value") or "").strip()

    helper_format = (primary.get("Format") or "").strip() if shape == "template" else ""
    helper_genres = (
        [(primary.get(f"Genre {n}") or "").strip() for n in (1, 2, 3)]
        if shape == "template" else []
    )

    product_type, reason = resolve_type(tags)
    if reason:
        return None, reason

    media_format, reason = resolve_format(
        primary.get("Vendor", ""), option1_value, tags, helper_format
    )
    if reason:
        return None, reason

    genres, reason = resolve_genres(option1_value, tags, helper_genres)
    if reason:
        return None, reason

    price, reason = resolve_price(product_type, primary.get("Variant Price", ""))
    if reason:
        return None, reason

    extras = extra_tags(tags)
    if shape == "template":
        extras = extras + [
            tag for tag in split_list(primary.get("Extra tags", "")) if tag not in extras
        ]

    return {
        "type": product_type,
        "format": media_format,
        "genres": genres,
        "price": price,
        "extras": extras,
    }, None


def _build_row(primary: dict, resolved: dict, handle: str, shape: str) -> dict:
    out = _blank_row(shape)
    out.update(FIXED_VALUES)

    title = (primary.get("Title") or "").strip()
    image_src = (primary.get("Image Src") or "").strip()
    alt_text = (primary.get("Image Alt Text") or "").strip()

    out["Handle"] = handle
    out["Title"] = title
    out["Body (HTML)"] = primary.get("Body (HTML)", "") or ""
    out["Vendor"] = resolved["format"]
    out["Tags"] = ", ".join(
        [resolved["type"], resolved["format"]] + resolved["genres"] + resolved["extras"]
    )
    out["Option1 Value"] = resolved["genres"][0]
    out["Variant Price"] = resolved["price"]
    out["Image Src"] = image_src
    out["Image Alt Text"] = alt_text or (f"{title} poster" if image_src else "")
    out[GENRE_METAFIELD] = "; ".join(
        h for h in (genre_handle(g) for g in resolved["genres"]) if h
    )

    if shape == "template":
        out["Status"] = "Active"
    else:
        out["Variant Barcode"] = (primary.get("Variant Barcode") or "").strip()
        out["Image Position"] = (primary.get("Image Position") or "").strip() or (
            "1" if image_src else ""
        )

    return out


def _flag(group: list[dict], reason: str) -> list[dict]:
    """Every row of a flagged product, with Reason prepended."""
    return [{REASON_COLUMN: reason, **row} for row in group]


def _group_products(rows: list[dict], shape: str) -> list[tuple[str, list[dict]]]:
    """Split rows into one group per product.

    An export groups by Handle, because a product's extra images are extra
    rows sharing its handle. A template batch cannot: its Handle cells are
    blank until this script derives them, so grouping by handle would
    collapse the whole batch into one product. One template row is one
    product — one physical copy.
    """
    if shape == "template":
        return [((row.get("Handle") or "").strip(), [row]) for row in rows]
    return group_rows_by_handle(rows)


def normalize_rows(rows: list[dict], shape: str) -> tuple[list[dict], list[dict]]:
    """Normalize every product. Returns (clean_rows, issue_rows)."""
    allocator = HandleAllocator()
    if shape == "template":
        for row in rows:
            allocator.reserve((row.get("Handle") or "").strip())

    clean_rows: list[dict] = []
    issue_rows: list[dict] = []
    produced: dict[str, list[dict]] = {}

    for handle, group in _group_products(rows, shape):
        primary = group[0]

        variant_rows = [row for row in group if _is_variant_row(row)]
        if len(variant_rows) > 1:
            issue_rows.extend(_flag(group, f"product has {len(variant_rows)} variants"))
            continue

        resolved, reason = _resolve_product(primary, shape)
        if reason:
            issue_rows.extend(_flag(group, reason))
            continue

        if shape == "template":
            typed = (primary.get("Handle") or "").strip()
            out_handle = typed or allocator.allocate(
                derive_handle(primary.get("Title", ""), resolved["format"], resolved["type"])
            )
        else:
            out_handle = handle

        product_rows = [_build_row(primary, resolved, out_handle, shape)]
        product_rows += [_image_row(row, shape) for row in group[1:]]

        produced.setdefault(out_handle, []).append({"group": group, "rows": product_rows})

    # Two input products landing on one output handle would merge on import.
    for out_handle, entries in produced.items():
        if len(entries) > 1:
            reason = f"duplicate handle {out_handle} — produced by {len(entries)} input products"
            for entry in entries:
                issue_rows.extend(_flag(entry["group"], reason))
        else:
            clean_rows.extend(entries[0]["rows"])

    return clean_rows, issue_rows
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_normalize.py" -v`
Expected: PASS, 30 tests

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/normalize.py tests/formatting_scripts/test_normalize.py
git commit -m "feat(formatting): normalization to the current data model"
```

---

### Task 7: TMDB query cache

Without this the fix-and-re-run loop re-queries 2,500 rows every pass and is unusable.

**Files:**
- Create: `formatting-scripts/tmdb_cache.py`
- Test: `tests/formatting_scripts/test_tmdb_cache.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class TmdbCache(path)` with `.wrap(fetch_fn) -> callable`, `.save() -> None`, `.hits: int`, `.misses: int`. The wrapped function has the same signature as the raw fetcher: `fetch(query: str, year: int | None) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_tmdb_cache.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from tmdb_cache import TmdbCache


class TestTmdbCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".tmdb-cache.json"
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fetcher(self, query, year):
        self.calls.append((query, year))
        return {"results": [{"title": query}]}

    def test_first_call_hits_the_fetcher(self):
        cache = TmdbCache(self.path)
        fetch = cache.wrap(self.fetcher)
        self.assertEqual(fetch("Rushmore", 1998)["results"][0]["title"], "Rushmore")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(cache.misses, 1)

    def test_repeat_call_costs_no_fetch(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("Rushmore", 1998)
        fetch("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_case_and_whitespace_insensitive_key(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("Rushmore", 1998)
        fetch("  rushmore ", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_different_year_is_a_different_query(self):
        fetch = TmdbCache(self.path).wrap(self.fetcher)
        fetch("The Thing", 1982)
        fetch("The Thing", 2011)
        fetch("The Thing", None)
        self.assertEqual(len(self.calls), 3)

    def test_survives_a_save_and_reload(self):
        cache = TmdbCache(self.path)
        cache.wrap(self.fetcher)("Rushmore", 1998)
        cache.save()

        reloaded = TmdbCache(self.path)
        reloaded.wrap(self.fetcher)("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(reloaded.hits, 1)

    def test_a_corrupt_cache_file_starts_empty_instead_of_crashing(self):
        self.path.write_text("{not json", encoding="utf-8")
        cache = TmdbCache(self.path)
        cache.wrap(self.fetcher)("Rushmore", 1998)
        self.assertEqual(len(self.calls), 1)

    def test_a_failing_fetch_is_not_cached(self):
        def boom(query, year):
            raise RuntimeError("network down")

        cache = TmdbCache(self.path)
        fetch = cache.wrap(boom)
        with self.assertRaises(RuntimeError):
            fetch("Rushmore", 1998)
        cache.save()
        self.assertEqual(json.loads(self.path.read_text()), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_tmdb_cache.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tmdb_cache'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/tmdb_cache.py`:

```python
"""On-disk cache of TMDB search responses, keyed by query + year.

The first pass over the full catalogue is thousands of requests. Every
correction pass afterwards re-reads the same rows, so without a cache the
fix-and-re-run loop pays the full rate-limited cost each time.

Failed requests are never cached — a network blip must not become a
permanent "no match".
"""

import json
from pathlib import Path


class TmdbCache:
    def __init__(self, path):
        self.path = Path(path)
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
        """Return a fetch_fn(query, year) -> dict that consults the cache first."""

        def cached_fetch(query: str, year: int | None) -> dict:
            key = self._key(query, year)
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            data = fetch_fn(query, year)
            self._entries[key] = data
            self.misses += 1
            return data

        return cached_fetch

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_tmdb_cache.py" -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add formatting-scripts/tmdb_cache.py tests/formatting_scripts/test_tmdb_cache.py
git commit -m "feat(formatting): on-disk TMDB query cache"
```

---

### Task 8: TMDB fill

Copy `data-cleanup/tmdb_fill.py` and rework it: no tag machinery, stricter confidence, `w1280` posters, year-bearing alt text, and review entries split into `ambiguous` (→ picker) and `unmatched` (→ CSV).

**Files:**
- Create: `formatting-scripts/tmdb_fill.py` (copied, then edited)
- Test: `tests/formatting_scripts/test_tmdb_fill.py`

**Interfaces:**
- Consumes: `catalog_common.group_rows_by_handle`.
- Produces: `POSTER_BASE_URL: str`, `MATCH_THRESHOLD: float`, `MATCH_MARGIN: float`, `clean_title_and_year(title) -> tuple[str, int | None]`, `normalize_title`, `title_similarity`, `search_tmdb(fetch_fn, title, year) -> list[dict]`, `classify_match(clean_title, year, results) -> tuple[dict | None, str]` where the string is `"confident"`, `"ambiguous"` or `"none"`, `needs_image(group)`, `needs_description(group)`, `make_tmdb_fetcher(api_key)`, `print_progress`, `build_output(rows, fetch_fn, sleep_fn, progress_fn) -> tuple[list[dict], list[dict]]` where review rows are `{"Handle", "Title", "Kind", "Reason"}`.

- [ ] **Step 1: Copy the file and commit the unmodified copy**

```bash
cp data-cleanup/tmdb_fill.py formatting-scripts/tmdb_fill.py
git add formatting-scripts/tmdb_fill.py
git commit -m "chore(formatting): copy tmdb_fill from data-cleanup"
```

- [ ] **Step 2: Write the failing test**

Create `tests/formatting_scripts/test_tmdb_fill.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

import tmdb_fill
from tmdb_fill import (
    POSTER_BASE_URL,
    build_output,
    classify_match,
    clean_title_and_year,
)


def result(title, year="1998", poster="/p.jpg", overview="An overview long enough to count."):
    return {"title": title, "release_date": f"{year}-01-01",
            "poster_path": poster, "overview": overview}


def row(**overrides):
    base = {"Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "",
            "Image Src": "", "Image Alt Text": "", "Tags": "Rental, VHS, Comedy"}
    base.update(overrides)
    return base


def fetcher(results, calls=None):
    def fetch(query, year):
        if calls is not None:
            calls.append((query, year))
        return {"results": results}
    return fetch


class TestPosterBase(unittest.TestCase):
    def test_uses_w1280_not_w500(self):
        self.assertEqual(POSTER_BASE_URL, "https://image.tmdb.org/t/p/w1280")


class TestClassifyMatch(unittest.TestCase):
    def test_no_results_is_none(self):
        best, kind = classify_match("Rushmore", None, [])
        self.assertIsNone(best)
        self.assertEqual(kind, "none")

    def test_single_strong_match_is_confident(self):
        best, kind = classify_match("Rushmore", None, [result("Rushmore")])
        self.assertEqual(kind, "confident")
        self.assertEqual(best["title"], "Rushmore")

    def test_weak_single_match_is_ambiguous(self):
        _, kind = classify_match("Rushmore", None, [result("Rush Hour")])
        self.assertEqual(kind, "ambiguous")

    def test_two_equally_good_candidates_are_ambiguous(self):
        _, kind = classify_match("The Thing", None,
                                 [result("The Thing", "1982"), result("The Thing", "2011")])
        self.assertEqual(kind, "ambiguous")

    def test_a_known_year_breaks_the_tie(self):
        best, kind = classify_match("The Thing", 1982,
                                    [result("The Thing", "1982"), result("The Thing", "2011")])
        self.assertEqual(kind, "confident")
        self.assertEqual(best["release_date"][:4], "1982")

    def test_a_known_year_that_matches_nothing_is_ambiguous(self):
        _, kind = classify_match("The Thing", 1975, [result("The Thing", "1982")])
        self.assertEqual(kind, "ambiguous")


class TestBuildOutput(unittest.TestCase):
    def test_fills_image_description_and_alt_text(self):
        out, review = build_output([row()], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(review, [])
        self.assertEqual(out[0]["Image Src"], f"{POSTER_BASE_URL}/p.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>An overview long enough to count.</p>")
        self.assertEqual(out[0]["Image Alt Text"], "Rushmore (1998) poster")

    def test_never_overwrites_an_existing_description_or_image(self):
        existing = row(**{"Body (HTML)": "<p>The client wrote this one himself.</p>",
                          "Image Src": "https://example.com/mine.jpg"})
        out, review = build_output([existing], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(out[0]["Body (HTML)"], "<p>The client wrote this one himself.</p>")
        self.assertEqual(out[0]["Image Src"], "https://example.com/mine.jpg")
        self.assertEqual(review, [])

    def test_a_complete_row_costs_no_request(self):
        calls = []
        complete = row(**{"Body (HTML)": "<p>A description that is plenty long enough.</p>",
                          "Image Src": "https://example.com/mine.jpg"})
        build_output([complete], fetcher([], calls), sleep_fn=lambda s: None)
        self.assertEqual(calls, [])

    def test_zero_results_is_reported_as_unmatched(self):
        out, review = build_output([row()], fetcher([]), sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertEqual(out[0]["Image Src"], "")

    def test_ambiguous_results_are_reported_for_the_picker(self):
        results = [result("The Thing", "1982"), result("The Thing", "2011")]
        out, review = build_output([row(Title="The Thing")], fetcher(results), sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "ambiguous")
        self.assertEqual(out[0]["Image Src"], "")

    def test_a_match_with_no_poster_is_unmatched_but_still_fills_the_description(self):
        out, review = build_output([row()], fetcher([result("Rushmore", poster=None)]),
                                   sleep_fn=lambda s: None)
        self.assertEqual(review[0]["Kind"], "unmatched")
        self.assertIn("poster", review[0]["Reason"])
        self.assertTrue(out[0]["Body (HTML)"])

    def test_a_request_failure_is_unmatched_and_does_not_abort_the_run(self):
        def boom(query, year):
            raise RuntimeError("network down")

        out, review = build_output([row(), row(Handle="b")], boom, sleep_fn=lambda s: None)
        self.assertEqual(len(out), 2)
        self.assertEqual(review[0]["Kind"], "unmatched")

    def test_writes_no_tags(self):
        out, _ = build_output([row()], fetcher([result("Rushmore")]), sleep_fn=lambda s: None)
        self.assertEqual(out[0]["Tags"], "Rental, VHS, Comedy")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_tmdb_fill.py" -v`
Expected: FAIL — `ImportError: cannot import name 'classify_match'`

- [ ] **Step 4: Edit the copied file**

In `formatting-scripts/tmdb_fill.py` make exactly these changes:

1. Replace the module docstring's `See …` line with `See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.`
2. Change the import line to `from catalog_common import group_rows_by_handle, load_export, write_csv` (drop `add_tags`, `has_tag`).
3. Replace the constants block:

```python
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w1280"

MATCH_THRESHOLD = 0.9
MATCH_MARGIN = 0.05
SHORT_DESCRIPTION_LENGTH = 40
REQUEST_DELAY_SECONDS = 0.25
```

  and delete `CIRCAOS_IMPORT_TAG`, `TMDB_FILLED_TAG` and `NEEDS_DATA_TAG`.
4. Delete `has_circaos_tag` entirely.
5. Replace `find_best_match` with:

```python
def classify_match(clean_title: str, year: int | None, results: list[dict]) -> tuple[dict | None, str]:
    """Return (candidate_or_None, "confident" | "ambiguous" | "none").

    Confident needs all three: a strong title score, no runner-up close
    behind it, and — when the input told us a year — a candidate released
    in that year. A lone weak match is ambiguous, not an answer: across
    thousands of rows that difference is hundreds of wrong posters.
    """
    if not results:
        return None, "none"

    scored = sorted(
        ((title_similarity(clean_title, r.get("title", "")), r) for r in results),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]

    if year is not None:
        year_matches = [r for score, r in scored
                        if score >= MATCH_THRESHOLD and (r.get("release_date") or "")[:4] == str(year)]
        if len(year_matches) == 1:
            return year_matches[0], "confident"
        return best, "ambiguous"

    if best_score < MATCH_THRESHOLD:
        return best, "ambiguous"
    if len(scored) > 1 and best_score - scored[1][0] < MATCH_MARGIN:
        return best, "ambiguous"
    return best, "confident"
```

6. Replace `build_output` with:

```python
def build_output(
    rows: list[dict],
    fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, handle, message: None,
) -> tuple[list[dict], list[dict]]:
    """Fill empty Image Src / Body (HTML) / Image Alt Text via TMDB.

    Returns (output_rows, review_rows). Row order and count are preserved.
    Review rows are {"Handle", "Title", "Kind", "Reason"} where Kind is
    "ambiguous" (send to the picker) or "unmatched" (send to the CSV).
    Nothing is ever written to Tags.
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    groups = group_rows_by_handle(rows)
    total = len(groups)

    def review(handle, title, kind, reason):
        review_rows.append({"Handle": handle, "Title": title, "Kind": kind, "Reason": reason})

    for index, (handle, group) in enumerate(groups, start=1):
        need_img = needs_image(group)
        need_desc = needs_description(group)

        if not need_img and not need_desc:
            output_rows.extend(group)
            progress_fn(index, total, handle, "already complete, skipped")
            continue

        primary = dict(group[0])
        title = primary.get("Title", "").strip() or handle
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, "unmatched", f"TMDB request failed: {exc}")
            output_rows.extend(group)
            progress_fn(index, total, handle, f"unmatched: request failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)

        best, kind = classify_match(clean_title, year, results)

        if kind == "none":
            review(handle, title, "unmatched", "no TMDB match")
            output_rows.extend(group)
            progress_fn(index, total, handle, "unmatched: no TMDB match")
            continue

        if kind == "ambiguous":
            best_title = best.get("title", "?")
            best_year = (best.get("release_date") or "")[:4] or "?"
            review(handle, title, "ambiguous",
                   f"ambiguous match (best candidate: '{best_title}' ({best_year}))")
            output_rows.extend(group)
            progress_fn(index, total, handle, f"ambiguous: '{best_title}' ({best_year})")
            continue

        match_year = (best.get("release_date") or "")[:4]
        filled = []

        if need_img:
            poster_path = best.get("poster_path")
            if poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
                if not (primary.get("Image Alt Text") or "").strip():
                    suffix = f" ({match_year})" if match_year else ""
                    primary["Image Alt Text"] = f"{title}{suffix} poster"
                filled.append("image")
            else:
                review(handle, title, "unmatched", "matched but TMDB has no poster")

        if need_desc:
            overview = (best.get("overview") or "").strip()
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
                filled.append("description")
            else:
                review(handle, title, "unmatched", "matched but TMDB has no overview")

        output_rows.append(primary)
        output_rows.extend(group[1:])
        progress_fn(index, total, handle, f"filled {', '.join(filled)}" if filled else "matched")

    return output_rows, review_rows
```

7. Delete `build_changes_html`, `run` and `main`, and the now-unused imports `argparse`, `html`, `os`, `sys` and `Path`. `run.py` owns orchestration; this module is library code plus `make_tmdb_fetcher`, `print_progress`, `clean_title_and_year`, `normalize_title`, `title_similarity`, `search_tmdb`, `strip_html`, `needs_image`, `needs_description`. Keep the `if __name__` block out entirely.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_tmdb_fill.py" -v`
Expected: PASS, 15 tests

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/tmdb_fill.py tests/formatting_scripts/test_tmdb_fill.py
git commit -m "feat(formatting): rework TMDB fill — stricter matching, no tag writes, w1280"
```

---

### Task 9: Review picker page

Copy the picker and retarget it at the new review-row shape. Behaviour is unchanged except that the "needs data" option becomes a plain skip — nothing writes tags any more.

**Files:**
- Create: `formatting-scripts/review_page.py` (copied from `data-cleanup/tmdb_review_page.py`, then edited)
- Test: `tests/formatting_scripts/test_review_page.py`

**Interfaces:**
- Consumes: `tmdb_fill.clean_title_and_year`, `tmdb_fill.search_tmdb`, `tmdb_fill.REQUEST_DELAY_SECONDS`.
- Produces: `MAX_CANDIDATES: int`, `fetch_candidates(fetch_fn, title, year) -> list[dict]`, `collect_products(review_rows, fetch_fn, sleep_fn, progress_fn) -> list[dict]`, `build_picker_html(products) -> str`, `write_picker(review_rows, outdir, fetch_fn, sleep_fn, progress_fn) -> dict`.

- [ ] **Step 1: Copy the file and commit the unmodified copy**

```bash
cp data-cleanup/tmdb_review_page.py formatting-scripts/review_page.py
git add formatting-scripts/review_page.py
git commit -m "chore(formatting): copy tmdb_review_page from data-cleanup as review_page"
```

- [ ] **Step 2: Write the failing test**

Create `tests/formatting_scripts/test_review_page.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from review_page import MAX_CANDIDATES, build_picker_html, collect_products, write_picker


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


class TestCollectProducts(unittest.TestCase):
    def test_caps_candidates_at_five(self):
        many = [result(f"The Thing {n}") for n in range(9)]
        products = collect_products(
            [{"Handle": "the-thing", "Title": "The Thing", "Kind": "ambiguous", "Reason": "ambiguous match"}],
            fetcher(many), sleep_fn=lambda s: None,
        )
        self.assertEqual(MAX_CANDIDATES, 5)
        self.assertEqual(len(products[0]["candidates"]), 5)

    def test_merges_multiple_reasons_for_one_handle(self):
        rows = [
            {"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "no poster"},
            {"Handle": "x", "Title": "X", "Kind": "unmatched", "Reason": "no overview"},
        ]
        products = collect_products(rows, fetcher([result("X")]), sleep_fn=lambda s: None)
        self.assertEqual(len(products), 1)
        self.assertIn("no poster", products[0]["reason"])
        self.assertIn("no overview", products[0]["reason"])

    def test_a_failed_request_yields_a_card_with_no_candidates(self):
        def boom(query, year):
            raise RuntimeError("network down")

        products = collect_products(
            [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
            boom, sleep_fn=lambda s: None,
        )
        self.assertEqual(products[0]["candidates"], [])


class TestBuildPickerHtml(unittest.TestCase):
    def test_offers_skip_rather_than_a_needs_data_tag(self):
        html = build_picker_html([{"handle": "x", "title": "X", "reason": "r", "candidates": []}])
        self.assertIn('value="skip"', html)
        self.assertNotIn("needs_data", html)
        self.assertNotIn("needs data", html)

    def test_escapes_content_that_could_close_the_script_tag(self):
        html = build_picker_html([
            {"handle": "x", "title": "X", "reason": "r",
             "candidates": [{"id": 1, "title": "</script><b>x</b>", "year": "1999",
                             "overview": "", "poster_path": ""}]}
        ])
        self.assertNotIn("</script><b>", html)


class TestWritePicker(unittest.TestCase):
    def test_writes_the_page_and_reports_a_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts = write_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tmp, fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(counts["products"], 1)
            self.assertTrue((Path(tmp) / "review-picker.html").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_review_page.py" -v`
Expected: FAIL — `ImportError: cannot import name 'write_picker'`

- [ ] **Step 4: Edit the copied file**

In `formatting-scripts/review_page.py`:

1. Update the docstring: it now reads review rows produced by `tmdb_fill.build_output`, and picks are applied with `apply_picks.py`. Point the `See` line at the 2026-08-11 spec.
2. Change the import block to:

```python
import html
import json
import time
from pathlib import Path

from tmdb_fill import REQUEST_DELAY_SECONDS, clean_title_and_year, search_tmdb
```

  (drop `argparse`, `os`, `sys`, `load_export`, `make_tmdb_fetcher`, `print_progress`.)
3. In the page's JavaScript, rename the `needs_data` choice to `skip` — three places: the `optionHtml(..., "needs_data", current === "needs_data", ...)` call, its label text (`'<span class="info"><strong>Skip this one</strong> — leave it for a later pass</span>'`), and the export branch `if (pick === "needs_data")` → `if (pick === "skip") { out.push({handle: product.handle, choice: "skip"}); }`.
4. Change the page `<title>` and `<h1>` from "TMDB review picker" to "Movie review picker".
5. Replace `run` and `main` with:

```python
def write_picker(review_rows, outdir, fetch_fn, sleep_fn=time.sleep, progress_fn=None) -> dict:
    """Build review-picker.html for the given review rows."""
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    products = collect_products(review_rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)
    Path(outdir).joinpath("review-picker.html").write_text(
        build_picker_html(products), encoding="utf-8"
    )
    return {"products": len(products)}
```

  and delete the `if __name__ == "__main__"` block.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_review_page.py" -v`
Expected: PASS, 6 tests

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/review_page.py tests/formatting_scripts/test_review_page.py
git commit -m "feat(formatting): review picker page retargeted at the new review rows"
```

---

### Task 10: Apply picks

Copy `apply_review_picks.py` and strip the tag behaviour: a skipped product is simply left alone.

**Files:**
- Create: `formatting-scripts/apply_picks.py` (copied, then edited)
- Test: `tests/formatting_scripts/test_apply_picks.py`

**Interfaces:**
- Consumes: `catalog_common.group_rows_by_handle`, `catalog_common.load_export`, `catalog_common.write_csv`, `tmdb_fill.POSTER_BASE_URL`, `tmdb_fill.needs_description`, `tmdb_fill.needs_image`.
- Produces: `apply_picks(rows, picks) -> tuple[list[dict], dict]` with counts `{"applied", "skipped", "unknown"}`; `run(picks_path, base_path, outdir) -> dict` writing `picks-applied.csv`; a `main()` CLI.

- [ ] **Step 1: Copy the file and commit the unmodified copy**

```bash
cp data-cleanup/apply_review_picks.py formatting-scripts/apply_picks.py
git add formatting-scripts/apply_picks.py
git commit -m "chore(formatting): copy apply_review_picks from data-cleanup as apply_picks"
```

- [ ] **Step 2: Write the failing test**

Create `tests/formatting_scripts/test_apply_picks.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from apply_picks import apply_picks
from tmdb_fill import POSTER_BASE_URL


def row(**overrides):
    base = {"Handle": "the-thing-4k-floor-sale", "Title": "The Thing",
            "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Floor Sale, 4K, Horror"}
    base.update(overrides)
    return base


class TestApplyPicks(unittest.TestCase):
    def test_a_tmdb_pick_fills_image_and_description(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "A crew is hunted by a shapeshifter."}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(out[0]["Image Src"], f"{POSTER_BASE_URL}/t.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>A crew is hunted by a shapeshifter.</p>")
        self.assertEqual(counts["applied"], 1)

    def test_a_tmdb_pick_does_not_overwrite_existing_data(self):
        existing = row(**{"Image Src": "https://example.com/mine.jpg",
                          "Body (HTML)": "<p>A description already written by hand.</p>"})
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "tmdb",
                  "poster_path": "/t.jpg", "overview": "Overwrite me."}]
        out, _ = apply_picks([existing], picks)
        self.assertEqual(out[0]["Image Src"], "https://example.com/mine.jpg")
        self.assertIn("already written", out[0]["Body (HTML)"])

    def test_a_manual_pick_overrides_unconditionally(self):
        existing = row(**{"Image Src": "https://example.com/old.jpg"})
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "manual",
                  "image_src": "https://example.com/new.jpg", "overview": "Mine."}]
        out, _ = apply_picks([existing], picks)
        self.assertEqual(out[0]["Image Src"], "https://example.com/new.jpg")
        self.assertEqual(out[0]["Body (HTML)"], "<p>Mine.</p>")

    def test_a_skip_pick_changes_nothing_and_writes_no_tag(self):
        picks = [{"handle": "the-thing-4k-floor-sale", "choice": "skip"}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(out[0], row())
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["applied"], 0)

    def test_a_pick_for_an_unknown_handle_is_counted_not_crashed_on(self):
        picks = [{"handle": "not-in-this-file", "choice": "skip"}]
        out, counts = apply_picks([row()], picks)
        self.assertEqual(len(out), 1)
        self.assertEqual(counts["unknown"], 1)

    def test_rows_without_a_pick_pass_through_untouched(self):
        out, _ = apply_picks([row(), row(Handle="other")], [])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_apply_picks.py" -v`
Expected: FAIL — `ImportError: cannot import name 'NEEDS_DATA_TAG' from 'tmdb_fill'`

- [ ] **Step 4: Edit the copied file**

In `formatting-scripts/apply_picks.py`:

1. Point the docstring's `See` line at the 2026-08-11 spec and change "declined products tagged 'needs data'" to "skipped products left untouched".
2. Change the imports to:

```python
from catalog_common import group_rows_by_handle, load_export, write_csv
from tmdb_fill import POSTER_BASE_URL, needs_description, needs_image
```

3. In `apply_picks`, change the counts dict to `{"applied": 0, "skipped": 0, "unknown": ...}`, replace the `needs_data` branch with:

```python
        if pick["choice"] == "skip":
            counts["skipped"] += 1
```

  and in the `else` (tmdb) branch drop `or has_circaos_tag(group)` so the condition reads `if needs_description(group) and overview:`.
4. Update the docstring of `apply_picks` to describe `skip` instead of `needs_data`.
5. In `main`, replace the `Tagged '{NEEDS_DATA_TAG}'` line with `print(f"Skipped: {counts['skipped']}")`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_apply_picks.py" -v`
Expected: PASS, 6 tests

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/apply_picks.py tests/formatting_scripts/test_apply_picks.py
git commit -m "feat(formatting): apply picks without writing review tags"
```

---

### Task 11: The run entry point

Wires the stages together, writes the six output files, and proves the whole thing is idempotent.

**Files:**
- Create: `formatting-scripts/run.py`
- Test: `tests/formatting_scripts/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `output_dir_for(input_path) -> Path`, `_unmatched_rows(review_rows, filled_rows, columns) -> list[dict]`, `run(input_path, outdir=None, skip_tmdb=False, api_key=None, fetch_fn=None, sleep_fn=time.sleep, log_fn=..., progress_fn=None) -> dict` returning `{"shape", "clean", "issues", "ambiguous", "unmatched", "outdir"}`, and a `main()` CLI accepting `input_csv`, `--outdir`, `--skip-tmdb`.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_run.py`:

```python
import csv
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "formatting-scripts"))

import run as run_module
from columns import EXPORT_COLUMNS, TEMPLATE_COLUMNS

TEMPLATE_HEADER = TEMPLATE_COLUMNS + ["Format", "Genre 1", "Genre 2", "Genre 3", "Year", "Extra tags"]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def template_input_row(title, genre="Comedy", fmt="VHS", tags="Rental, VHS, Comedy"):
    row = {name: "" for name in TEMPLATE_HEADER}
    row.update({"Title": title, "Tags": tags, "Format": fmt, "Genre 1": genre, "Year": "1998"})
    return row


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fake_fetch(query, year):
    return {"results": [{"title": query, "release_date": "1998-01-01",
                         "poster_path": "/p.jpg",
                         "overview": "An overview that is long enough to count as a description."}]}


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_output_dir_is_derived_from_the_input_name(self):
        self.assertEqual(
            run_module.output_dir_for(Path("/x/products_export_1.csv")).name,
            "out-products_export_1",
        )

    def test_produces_upload_and_report_for_a_clean_template_batch(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        outdir = Path(result["outdir"])

        upload = read_csv(outdir / "upload.csv")
        self.assertEqual(result["shape"], "template")
        self.assertEqual(result["clean"], 1)
        self.assertEqual(list(upload[0]), TEMPLATE_COLUMNS)
        self.assertEqual(upload[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(upload[0]["Image Src"], "https://image.tmdb.org/t/p/w1280/p.jpg")
        self.assertTrue((outdir / "run-report.txt").exists())

    def test_broken_rows_land_in_issues_with_a_reason_and_the_original_columns(self):
        path = self.dir / "batch.csv"
        good = template_input_row("Rushmore")
        bad = template_input_row("Mystery", genre="Special Interest", tags="Rental, VHS")
        write_csv(path, TEMPLATE_HEADER, [good, bad])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        outdir = Path(result["outdir"])

        issues = read_csv(outdir / "issues.csv")
        self.assertEqual(result["issues"], 1)
        self.assertEqual(issues[0]["Title"], "Mystery")
        self.assertIn("no usable genre", issues[0]["Reason"])
        self.assertIn("Genre 1", issues[0])  # helper columns survive for editing
        self.assertEqual(len(read_csv(outdir / "upload.csv")), 1)

    def test_a_corrected_issues_file_is_a_valid_input(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER,
                  [template_input_row("Mystery", genre="Special Interest", tags="Rental, VHS")])
        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)

        issues_path = Path(first["outdir"]) / "issues.csv"
        rows = read_csv(issues_path)
        rows[0]["Genre 1"] = "Comedy"
        rows[0]["Tags"] = "Rental, VHS, Comedy"
        write_csv(issues_path, list(rows[0]), rows)

        second = run_module.run(issues_path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        self.assertEqual(second["issues"], 0)
        self.assertEqual(second["clean"], 1)
        upload = read_csv(Path(second["outdir"]) / "upload.csv")
        self.assertEqual(upload[0]["Handle"], "mystery-vhs-rental")

    def test_unmatched_rows_get_their_own_fixable_file(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])

        result = run_module.run(
            path, fetch_fn=lambda q, y: {"results": []}, sleep_fn=lambda s: None
        )
        outdir = Path(result["outdir"])
        unmatched = read_csv(outdir / "tmdb-unmatched.csv")
        self.assertEqual(result["unmatched"], 1)
        self.assertIn("no TMDB match", unmatched[0]["Reason"])
        self.assertEqual(unmatched[0]["Title"], "Rushmore")
        # Emitted in the output shape, so it feeds straight back into run.py.
        self.assertEqual(list(unmatched[0]), ["Reason"] + TEMPLATE_COLUMNS)

    def test_ambiguous_rows_produce_the_picker_page(self):
        def ambiguous(query, year):
            return {"results": [
                {"title": "The Thing", "release_date": "1982-01-01", "poster_path": "/a.jpg", "overview": "A."},
                {"title": "The Thing", "release_date": "2011-01-01", "poster_path": "/b.jpg", "overview": "B."},
            ]}

        path = self.dir / "batch.csv"
        row = template_input_row("The Thing", genre="Horror", tags="Rental, VHS, Horror")
        row["Year"] = ""
        write_csv(path, TEMPLATE_HEADER, [row])

        result = run_module.run(path, fetch_fn=ambiguous, sleep_fn=lambda s: None)
        self.assertEqual(result["ambiguous"], 1)
        self.assertTrue((Path(result["outdir"]) / "review-picker.html").exists())

    def test_skip_tmdb_leaves_descriptions_empty_and_makes_no_requests(self):
        calls = []

        def counting(query, year):
            calls.append(query)
            return {"results": []}

        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])
        result = run_module.run(path, skip_tmdb=True, fetch_fn=counting, sleep_fn=lambda s: None)
        self.assertEqual(calls, [])
        upload = read_csv(Path(result["outdir"]) / "upload.csv")
        self.assertEqual(upload[0]["Body (HTML)"], "")

    def test_rerunning_over_its_own_upload_changes_nothing(self):
        path = self.dir / "batch.csv"
        write_csv(path, TEMPLATE_HEADER, [template_input_row("Rushmore")])
        first = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        first_upload = Path(first["outdir"]) / "upload.csv"
        first_text = first_upload.read_text(encoding="utf-8")

        second = run_module.run(first_upload, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        second_text = (Path(second["outdir"]) / "upload.csv").read_text(encoding="utf-8")

        self.assertEqual(second["issues"], 0)
        self.assertEqual(first_text, second_text)

    def test_an_unrecognised_header_fails_loudly(self):
        path = self.dir / "junk.csv"
        write_csv(path, ["Name", "Price"], [{"Name": "x", "Price": "1"}])
        with self.assertRaises(run_module.UnknownShapeError):
            run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)

    def test_export_input_keeps_handles_and_barcodes(self):
        header = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
                  "Tags", "Published", "Option1 Name", "Option1 Value",
                  "Variant Inventory Tracker", "Variant Inventory Qty",
                  "Variant Inventory Policy", "Variant Fulfillment Service",
                  "Variant Price", "Variant Barcode", "Image Src", "Image Position",
                  "Image Alt Text"]
        row = {name: "" for name in header}
        row.update({"Handle": "legend-of-zorro", "Title": "Legend of Zorro", "Vendor": "DVD",
                    "Tags": "Floor Sale, Action", "Option1 Name": "Condition",
                    "Option1 Value": "Standard", "Variant Price": "9.99",
                    "Variant Barcode": "88302842"})
        path = self.dir / "export.csv"
        write_csv(path, header, [row])

        result = run_module.run(path, fetch_fn=fake_fetch, sleep_fn=lambda s: None)
        upload = read_csv(Path(result["outdir"]) / "upload.csv")
        self.assertEqual(result["shape"], "export")
        self.assertEqual(list(upload[0]), EXPORT_COLUMNS)
        self.assertEqual(upload[0]["Handle"], "legend-of-zorro")
        self.assertEqual(upload[0]["Variant Barcode"], "88302842")
        self.assertEqual(upload[0]["Option1 Value"], "Action")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_run.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/run.py`:

```python
"""One command: normalize a movie CSV, fill it from TMDB, and split out
everything that needs a human.

    python3 formatting-scripts/run.py <input.csv>

Writes to out-<inputname>/ beside the input, so re-running on that run's
issues.csv cannot clobber its upload.csv. Every output file is itself a
valid input file: fix the rows, run the same command on the fixed file,
import what comes out.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import tmdb_fill
from catalog_common import load_export, write_csv
from columns import REASON_COLUMN
from detect import UnknownShapeError, detect_shape, strip_reason
from normalize import normalize_rows, output_columns
from review_page import write_picker
from tmdb_cache import TmdbCache

NO_LOG = lambda message: None

CACHE_FILENAME = ".tmdb-cache.json"


def output_dir_for(input_path) -> Path:
    input_path = Path(input_path)
    return input_path.parent / f"out-{input_path.stem}"


def _unmatched_rows(review_rows, filled_rows, columns):
    """Build tmdb-unmatched.csv rows: Reason + the normalized output columns.

    These rows already passed normalization — the only thing missing is a
    description or a poster. Emitting them in the output shape (rather than
    the raw input shape) means the operator edits the same columns Shopify
    will read, and the file feeds straight back into run.py.
    """
    by_handle = {}
    for row in filled_rows:
        by_handle.setdefault(row.get("Handle", ""), row)

    out = []
    seen = set()
    for entry in review_rows:
        handle = entry["Handle"]
        if entry["Kind"] != "unmatched" or handle in seen or handle not in by_handle:
            continue
        seen.add(handle)
        source = by_handle[handle]
        out.append({REASON_COLUMN: entry["Reason"], **{c: source.get(c, "") for c in columns}})
    return out


def run(
    input_path,
    outdir=None,
    skip_tmdb=False,
    api_key=None,
    fetch_fn=None,
    sleep_fn=time.sleep,
    log_fn=NO_LOG,
    progress_fn=None,
) -> dict:
    input_path = Path(input_path)
    outdir = Path(outdir) if outdir else output_dir_for(input_path)
    outdir.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = load_export(input_path)
    fieldnames, rows = strip_reason(fieldnames, rows)
    shape = detect_shape(fieldnames)
    log_fn(f"== {input_path.name}: {len(rows)} rows, detected shape: {shape} ==")

    clean_rows, issue_rows = normalize_rows(rows, shape)
    columns = output_columns(shape)

    write_csv(outdir / "issues.csv", [REASON_COLUMN] + fieldnames, issue_rows)
    log_fn(f"Stage 1: {len(clean_rows)} rows normalized, {len(issue_rows)} rows flagged")

    result = {
        "shape": shape,
        "clean": len(clean_rows),
        "issues": len(issue_rows),
        "ambiguous": 0,
        "unmatched": 0,
        "outdir": str(outdir),
    }

    if skip_tmdb or (fetch_fn is None and not api_key):
        reason = "--skip-tmdb" if skip_tmdb else "TMDB_API_KEY not set"
        log_fn(f"Stage 2: skipped ({reason})")
        write_csv(outdir / "upload.csv", columns, clean_rows)
        _write_report(outdir, input_path, result, log_fn)
        return result

    cache = TmdbCache(outdir / CACHE_FILENAME)
    raw_fetch = fetch_fn or tmdb_fill.make_tmdb_fetcher(api_key)
    cached_fetch = cache.wrap(raw_fetch)

    filled_rows, review_rows = tmdb_fill.build_output(
        clean_rows, cached_fetch, sleep_fn=sleep_fn,
        progress_fn=progress_fn or (lambda i, t, h, m: None),
    )
    cache.save()

    write_csv(outdir / "upload.csv", columns, filled_rows)

    unmatched = _unmatched_rows(review_rows, filled_rows, columns)
    write_csv(outdir / "tmdb-unmatched.csv", [REASON_COLUMN] + columns, unmatched)

    ambiguous = [entry for entry in review_rows if entry["Kind"] == "ambiguous"]
    result["ambiguous"] = len({entry["Handle"] for entry in ambiguous})
    result["unmatched"] = len(unmatched)

    log_fn(
        f"Stage 2: {len(filled_rows)} rows written, "
        f"{result['ambiguous']} ambiguous, {result['unmatched']} unmatched "
        f"(cache: {cache.hits} hits, {cache.misses} fetches)"
    )

    if ambiguous:
        write_picker(ambiguous, outdir, cached_fetch, sleep_fn=sleep_fn,
                     progress_fn=progress_fn or (lambda i, t, h, m: None))
        cache.save()
        log_fn(f"Stage 3: picker page for {result['ambiguous']} products")

    _write_report(outdir, input_path, result, log_fn)
    return result


def _write_report(outdir: Path, input_path: Path, result: dict, log_fn) -> None:
    lines = [
        f"input:      {input_path}",
        f"shape:      {result['shape']}",
        f"upload.csv: {result['clean']} products normalized",
        f"issues.csv: {result['issues']} rows need a fix",
        f"ambiguous:  {result['ambiguous']} products in review-picker.html",
        f"unmatched:  {result['unmatched']} products in tmdb-unmatched.csv",
    ]
    (outdir / "run-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_fn(f"  -> {outdir}")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize and TMDB-fill a movie CSV for Shopify import."
    )
    parser.add_argument("input_csv", help="Upload-template batch, Shopify export, or a prior output")
    parser.add_argument("--outdir", default=None, help="Override the out-<inputname>/ directory")
    parser.add_argument("--skip-tmdb", action="store_true", help="Stop after normalization")
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not args.skip_tmdb and not api_key:
        print("Note: TMDB_API_KEY is not set — running normalization only.", file=sys.stderr)

    try:
        result = run(
            Path(args.input_csv),
            outdir=args.outdir,
            skip_tmdb=args.skip_tmdb,
            api_key=api_key,
            log_fn=lambda message: print(message, flush=True),
            progress_fn=tmdb_fill.print_progress,
        )
    except UnknownShapeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(result["outdir"])
    print()
    print(f"Import this:  {outdir / 'upload.csv'}")
    if result["issues"]:
        print(f"Fix and re-run: {outdir / 'issues.csv'} "
              f"({result['issues']} rows) — python3 formatting-scripts/run.py {outdir / 'issues.csv'}")
    if result["ambiguous"]:
        print(f"Pick posters: open {outdir / 'review-picker.html'}, export picks, then")
        print(f"  python3 formatting-scripts/apply_picks.py "
              f"{outdir / 'tmdb-picks.json'} {outdir / 'upload.csv'}")
    if result["unmatched"]:
        print(f"Fill by hand: {outdir / 'tmdb-unmatched.csv'} ({result['unmatched']} products)")
    print()
    print("After importing: run scripts/set-movie-template.sh so movies use the movie template.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_run.py" -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" -v`
Expected: PASS, all ~110 tests, 0 failures

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/run.py tests/formatting_scripts/test_run.py
git commit -m "feat(formatting): run entry point wiring normalize + TMDB + picker"
```

---

### Task 12: Real-data smoke run and operator README

Nothing so far has touched the 3,550-row export. This task runs it, records what actually comes out, and writes the runbook the operator follows.

**Files:**
- Create: `formatting-scripts/README.md`
- Modify: `CLAUDE.md` (add `formatting-scripts/` to the repo layout section)

- [ ] **Step 1: Run the normalizer over the real export**

Run:

```bash
python3 formatting-scripts/run.py products_export_1.csv --skip-tmdb
cat out-products_export_1/run-report.txt
```

Expected: a report naming ~3,550 products, roughly 100–150 flagged rows. No traceback.

- [ ] **Step 2: Check the issue reasons are the ones the spec predicted**

Run:

```bash
python3 -c "
import csv, collections
rows = list(csv.DictReader(open('out-products_export_1/issues.csv')))
kinds = collections.Counter(r['Reason'].split('(')[0].strip() for r in rows)
for reason, count in kinds.most_common():
    print(f'{count:5d}  {reason}')
"
```

Expected buckets, all recognisable from the spec's table: no usable genre, no media format, no Rental or Floor Sale tag, Rental with a nonzero price, Floor Sale with no price, product has N variants, duplicate handle.

If a bucket appears that the spec did not predict, or a count is wildly off (thousands of rows in one bucket), stop and investigate before continuing — that is a resolver bug, not a data problem.

- [ ] **Step 3: Verify the upload file is safe**

Run:

```bash
python3 -c "
import csv
from pathlib import Path
import sys
sys.path.insert(0, 'formatting-scripts')
from columns import EXPORT_COLUMNS
rows = list(csv.DictReader(open('out-products_export_1/upload.csv')))
header = list(rows[0])
assert header == EXPORT_COLUMNS, header
primaries = [r for r in rows if r['Title']]
assert all(r['Variant Inventory Tracker'] == 'shopify' for r in primaries)
assert all(r['Option1 Name'] == 'Genre' for r in primaries)
assert all(r['Vendor'] in ('VHS','DVD','Blu-Ray','4K') for r in primaries)
missing = [r['Handle'] for r in primaries if not r['Variant Barcode']]
print(f'{len(rows)} rows, {len(primaries)} products, {len(missing)} without a barcode')
print('OK')
"
```

Expected: `OK`. A nonzero count of barcode-less products is fine to report — those are products the export had no barcode for — but it must be small.

- [ ] **Step 4: Write the operator README**

Create `formatting-scripts/README.md`:

````markdown
# Catalogue formatting scripts

One command turns a movie CSV into a file Shopify can import, and puts
everything it could not resolve into files you fix and re-run.

Design: `docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md`

## Run it

```bash
export TMDB_API_KEY=...          # omit to normalize only
python3 formatting-scripts/run.py <input.csv>
```

Input can be a batch from the upload template, a Shopify product export, or
any file this script produced earlier. Output lands in `out-<inputname>/`.

| File | What to do with it |
|---|---|
| `upload.csv` | Import it: Shopify admin → Products → Import |
| `issues.csv` | Fix the rows, then `run.py out-<name>/issues.csv` |
| `review-picker.html` | Open it, pick the right poster, Export picks |
| `tmdb-picks.json` | `apply_picks.py <picks> <upload.csv>` → `picks-applied.csv` |
| `tmdb-unmatched.csv` | Paste a description/poster, or fix the title, then re-run it |
| `run-report.txt` | Counts for the run |

## The loop

1. Run the script.
2. Import `upload.csv`.
3. **Run `scripts/set-movie-template.sh`** — imported movies otherwise land
   on the default product template, which shows a $0.00 Buy Now button on
   rentals.
4. Open the picker, choose posters, export, apply, import `picks-applied.csv`.
5. Fix `issues.csv` and `tmdb-unmatched.csv`, run the script on each, import
   what comes out. Repeat until both files come back empty.

## Before the first full-catalogue import

Import ~20 reformatted products to the **dev store**, re-export them, and
diff `Variant Barcode` and inventory against the input. Reformatting changes
`Option1 Value` on the 669 ex-`Condition` products, and Shopify matches
variants by option value; the script carries barcodes through so a rebuilt
variant keeps its printed label, but this has not been verified against a
live store.

## Rules the code enforces

- Handles on export rows are never rewritten — a handle is a live product's
  identity.
- Genre is never inferred from a title; type is never inferred from price.
- Existing descriptions and posters are never overwritten.
- Nothing is ever written to product tags except `Type, Format, Genre…, extras`.
- The export output omits every column it does not set, so Shopify leaves
  those fields alone.

## Tests

```bash
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" -v
```

Standard library only. No venv, no install step.
````

- [ ] **Step 5: Add the folder to CLAUDE.md**

In `CLAUDE.md`, in the "Repo layout" code block, add a line after the `lms-supercycle-feature-plan.md` line:

```
formatting-scripts/             ← catalogue CSV normalizer + TMDB fill (see its README)
```

- [ ] **Step 6: Clean up the smoke-run output and commit**

The run directory is throwaway output, not source.

```bash
rm -rf out-products_export_1
git status --short          # confirm nothing stray is staged
git add formatting-scripts/README.md CLAUDE.md
git commit -m "docs(formatting): operator README and repo-layout entry"
```

- [ ] **Step 7: Final verification**

Run: `python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py"`
Expected: `OK`, 0 failures, 0 errors.

Run: `git log --oneline -14` and confirm every task committed.

---

## Notes for the implementer

**Why `data-cleanup/` is not reused directly.** It encodes two reversed
decisions: `Option1 Value = "Default Title"` (now the genre label, because
the barcode-label templates print Option 1) and media format in
`shopify.media-format` (now `product.vendor`). Copying rather than importing
keeps that history intact while letting the new code state the current model
plainly.

**The one thing that must not regress:** `tests/formatting_scripts/test_columns.py`
reads the client's real template CSV from disk and asserts the header
matches. If someone changes the sheet, that test fails — which is the point.
Do not weaken it to a hardcoded comparison.
