# Movie Product Data Reformat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a script that reformats the ~1,849 plain resale movie products in `data-cleanup/current-movies-export.csv` into clean Shopify fields (fixed vendor, `shopify.genre` metafield, `shopify.media-format` metafield, `Media > Videos` category), producing a CSV ready for bulk re-upload plus a review report for rows that can't be cleanly reformatted.

**Architecture:** A small, dependency-free Python 3 script (stdlib `csv` + `unittest` only, no pip installs — matches this repo, which has no existing Python tooling). Logic splits into a pure mapping module (raw CSV values → canonical metaobject handles) and a pipeline module (CSV I/O, row grouping, transform). Both are unit tested with Python's built-in `unittest`, no new dependencies.

**Tech Stack:** Python 3 (stdlib only: `csv`, `unittest`, `pathlib`).

## Global Constraints

- Scope is the ~1,849 products where `Option1 Name == "Genre"` only. Serialized rental items (`Option1 Name == "Condition"`), the stray `Type == "Supercycle Plan"` product, and anything else are silently excluded from the output entirely (not touched, not flagged).
- `Vendor` becomes `"Little Movie Store"` for every in-scope product, unconditionally.
- `Product Category` becomes `"Media > Videos"` for every in-scope product (set only on each product's first CSV row, matching Shopify's per-product-fields-on-first-row convention).
- Fake variant option (`Option1 Name/Value = "Genre"/<value>`) is replaced with the standard single-variant convention: `Option1 Name = "Title"`, `Option1 Value = "Default Title"`.
- `product.metafields.shopify.media-format` and `product.metafields.shopify.genre` are `list.metaobject_reference` fields. Confirmed via the dev store's real metaobject definitions and a real populated CSV row (`data-cleanup/single-product-with-all-values.csv`): CSV values are the plain metaobject **handle** text (e.g. `vhs`, `comedy`), not a GID, not JSON. Multiple values would be semicolon-space separated (`"dvd; blu-ray"`), but this design always writes exactly one handle per field.
- Confirmed metaobject handles — format: `vhs`, `dvd`, `blu-ray`, `4-k`. Genre: `crime-mystery`, `thriller-suspense`, `comedy`, `action`, `kids-family`, `thriller`, `romantic-comedy`, `musical`, `foreign`, `drama`, `horror`, `fantasy`, `documentary`, `sci-fi`.
- Value normalization table is `/Users/liamparis/Desktop/format-mapping.md`, with one correction: `Foreign -> foreign` (not `foreignz` — matches the real metaobject handle).
- Rows with `Option1 Value == "#VALUE!"` (2 rows) or `Option1 Name == "Title"` (~27 rows, no genre ever set) go to a `needs-review.csv` report (Handle, Title, Reason) and are excluded from the main output.
- Tags are left untouched this pass.
- `data-cleanup/` is untracked in git (confirmed: not gitignored, just never `git add`ed). Only the script and its tests get committed; the CSVs (source export, reformatted output, review report) stay untracked, matching current repo state.

---

## File Structure

- `data-cleanup/genre_format_mapping.py` — pure lookup tables and resolver functions (raw `Vendor` string → format handle; raw `Option1 Value` string → genre handle + optional format override). No I/O, no CSV handling. This is the transcription of `format-mapping.md` into code.
- `data-cleanup/reformat_movies.py` — CSV pipeline: reads the export, groups rows by `Handle` (to keep each product's extra image rows attached to its primary row), classifies each product in/out of scope, transforms in-scope products, writes `movies-reformatted.csv` and `needs-review.csv`. Imports `genre_format_mapping`.
- `tests/data_cleanup/test_genre_format_mapping.py` — unit tests for the mapping tables and resolver functions.
- `tests/data_cleanup/test_reformat_movies.py` — unit tests for row classification, transform, and the full pipeline against an in-memory fixture (not the real 2,600-row file).
- `tests/data_cleanup/fixtures/sample_export.csv` — small hand-built fixture CSV covering every scenario the pipeline must handle.

---

### Task 1: Genre/format mapping tables

**Files:**
- Create: `data-cleanup/genre_format_mapping.py`
- Test: `tests/data_cleanup/test_genre_format_mapping.py`

**Interfaces:**
- Produces: `VENDOR_TO_FORMAT: dict[str, str | None]`, `GENRE_VALUE_MAP: dict[str, tuple[str | None, str | None]]` (value is `(genre_handle, format_override)`), `resolve_format(vendor: str, option1_value: str) -> str | None`, `resolve_genre(option1_value: str) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/data_cleanup/test_genre_format_mapping.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from genre_format_mapping import (
    VENDOR_TO_FORMAT,
    GENRE_VALUE_MAP,
    resolve_format,
    resolve_genre,
)


class TestVendorToFormat(unittest.TestCase):
    def test_known_formats_map_correctly(self):
        self.assertEqual(VENDOR_TO_FORMAT["VHS"], "vhs")
        self.assertEqual(VENDOR_TO_FORMAT["DVD"], "dvd")
        self.assertEqual(VENDOR_TO_FORMAT["Blu-Ray"], "blu-ray")
        self.assertEqual(VENDOR_TO_FORMAT["BLU-RAY"], "blu-ray")
        self.assertEqual(VENDOR_TO_FORMAT["4K"], "4-k")
        self.assertEqual(VENDOR_TO_FORMAT["4k"], "4-k")
        self.assertEqual(VENDOR_TO_FORMAT["Dvd"], "dvd")

    def test_junk_vendors_map_to_none(self):
        for junk in [
            "Unknown",
            "Unknown Brand",
            "Little Movie Store",
            "Walt Disney",
            "The Franchise Collection",
            "Walt Disney Pictures",
            "Blockbuster",
            "Basquiat",
            "Disney",
            "Arrow Video",
            "Alfred Hitchcock",
            "Universal Pictures",
            "Supercycle",
        ]:
            self.assertIsNone(VENDOR_TO_FORMAT[junk])

    def test_covers_all_20_known_vendor_values(self):
        self.assertEqual(len(VENDOR_TO_FORMAT), 20)


class TestGenreValueMap(unittest.TestCase):
    def test_simple_genres_map_correctly(self):
        self.assertEqual(GENRE_VALUE_MAP["Comedy"], ("comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["Action"], ("action", None))
        self.assertEqual(GENRE_VALUE_MAP["Sci-Fi"], ("sci-fi", None))
        self.assertEqual(GENRE_VALUE_MAP["Foreign"], ("foreign", None))

    def test_typos_normalize_to_canonical_handles(self):
        self.assertEqual(GENRE_VALUE_MAP["Romatic Comedy"], ("romantic-comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["Muscal"], ("musical", None))
        self.assertEqual(GENRE_VALUE_MAP["SciFi"], ("sci-fi", None))
        self.assertEqual(GENRE_VALUE_MAP["Kids"], ("kids-family", None))

    def test_compound_4k_values_override_format(self):
        self.assertEqual(GENRE_VALUE_MAP["4K, Action"], ("action", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Action, 4K"], ("action", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["4k, Fantasy"], ("fantasy", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Kids & Family, 4K"], ("kids-family", "4-k"))
        self.assertEqual(GENRE_VALUE_MAP["Horror, 4K"], ("horror", "4-k"))

    def test_curation_labels_strip_to_underlying_genre(self):
        self.assertEqual(GENRE_VALUE_MAP["Comedy, Criterion Collection"], ("comedy", None))
        self.assertEqual(GENRE_VALUE_MAP["A24, Sci-Fi"], ("sci-fi", None))

    def test_special_interest_has_no_genre(self):
        self.assertEqual(GENRE_VALUE_MAP["Special Interest"], (None, None))

    def test_value_error_is_not_in_the_map(self):
        self.assertNotIn("#VALUE!", GENRE_VALUE_MAP)

    def test_covers_all_28_known_genre_values(self):
        self.assertEqual(len(GENRE_VALUE_MAP), 28)


class TestResolveFormatAndGenre(unittest.TestCase):
    def test_plain_vendor_gives_format(self):
        self.assertEqual(resolve_format("VHS", "Comedy"), "vhs")
        self.assertEqual(resolve_format("Blu-Ray", "Action"), "blu-ray")

    def test_compound_genre_value_overrides_vendor_format(self):
        self.assertEqual(resolve_format("Blu-Ray", "4K, Action"), "4-k")

    def test_junk_vendor_gives_no_format(self):
        self.assertIsNone(resolve_format("Walt Disney", "Drama"))

    def test_resolve_genre_plain(self):
        self.assertEqual(resolve_genre("Comedy"), "comedy")

    def test_resolve_genre_compound(self):
        self.assertEqual(resolve_genre("4K, Action"), "action")

    def test_resolve_genre_special_interest_is_none(self):
        self.assertIsNone(resolve_genre("Special Interest"))

    def test_resolve_genre_unknown_value_is_none(self):
        self.assertIsNone(resolve_genre("#VALUE!"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_genre_format_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genre_format_mapping'`

- [ ] **Step 3: Write the mapping module**

Create `data-cleanup/genre_format_mapping.py`:

```python
"""Canonical Vendor/Genre value normalization for the movie catalogue reformat.

Source of truth: /Users/liamparis/Desktop/format-mapping.md, derived from
every distinct Vendor and Option1 Value seen in current-movies-export.csv,
with one correction: Foreign maps to "foreign" (the real metaobject handle
on the store), not the file's "foreignz".
"""

# Raw Vendor string -> product.metafields.shopify.media-format metaobject handle,
# or None if the vendor value carries no format information.
VENDOR_TO_FORMAT = {
    "VHS": "vhs",
    "DVD": "dvd",
    "Blu-Ray": "blu-ray",
    "BLU-RAY": "blu-ray",
    "Unknown": None,
    "Little Movie Store": None,
    "4K": "4-k",
    "4k": "4-k",
    "Unknown Brand": None,
    "Dvd": "dvd",
    "Walt Disney": None,
    "The Franchise Collection": None,
    "Walt Disney Pictures": None,
    "Blockbuster": None,
    "Basquiat": None,
    "Disney": None,
    "Arrow Video": None,
    "Alfred Hitchcock": None,
    "Universal Pictures": None,
    "Supercycle": None,
}

# Raw Option1 Value string (the fake "Genre" variant option value) ->
# (genre metaobject handle or None, format metaobject handle override or None).
# The format override is only set for compound values that mention "4K"/"4k";
# it takes precedence over VENDOR_TO_FORMAT when resolving format.
GENRE_VALUE_MAP = {
    "Comedy": ("comedy", None),
    "Action": ("action", None),
    "Drama": ("drama", None),
    "Kids & Family": ("kids-family", None),
    "Sci-Fi": ("sci-fi", None),
    "Thriller": ("thriller", None),
    "Horror": ("horror", None),
    "Romantic Comedy": ("romantic-comedy", None),
    "Musical": ("musical", None),
    "Fantasy": ("fantasy", None),
    "Documentary": ("documentary", None),
    "Foreign": ("foreign", None),
    "4K, Action": ("action", "4-k"),
    "Special Interest": (None, None),
    "4K, Kids & Family": ("kids-family", "4-k"),
    "Comedy, Criterion Collection": ("comedy", None),
    "Kids & Family, 4K": ("kids-family", "4-k"),
    "Romatic Comedy": ("romantic-comedy", None),
    "4K, Drama": ("drama", "4-k"),
    "4K, Sci-Fi": ("sci-fi", "4-k"),
    "4K, Fantasy": ("fantasy", "4-k"),
    "Muscal": ("musical", None),
    "SciFi": ("sci-fi", None),
    "4k, Fantasy": ("fantasy", "4-k"),
    "A24, Sci-Fi": ("sci-fi", None),
    "Action, 4K": ("action", "4-k"),
    "Horror, 4K": ("horror", "4-k"),
    "Kids": ("kids-family", None),
}


def resolve_format(vendor: str, option1_value: str) -> str | None:
    """Return the media-format metaobject handle for a product, or None."""
    mapping = GENRE_VALUE_MAP.get(option1_value)
    if mapping is not None:
        _, format_override = mapping
        if format_override is not None:
            return format_override
    return VENDOR_TO_FORMAT.get(vendor)


def resolve_genre(option1_value: str) -> str | None:
    """Return the genre metaobject handle for a product, or None."""
    mapping = GENRE_VALUE_MAP.get(option1_value)
    if mapping is None:
        return None
    genre_handle, _ = mapping
    return genre_handle
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_genre_format_mapping.py -v`
Expected: all tests PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/genre_format_mapping.py tests/data_cleanup/test_genre_format_mapping.py
git commit -m "Add genre/format value normalization tables for movie reformat"
```

---

### Task 2: Row classification and per-product transform

**Files:**
- Create: `data-cleanup/reformat_movies.py` (classification/transform functions only in this task; CSV I/O comes in Task 3)
- Test: `tests/data_cleanup/test_reformat_movies.py` (classification/transform tests only in this task)

**Interfaces:**
- Consumes: `resolve_format`, `resolve_genre` from `genre_format_mapping` (Task 1)
- Produces: `FIXED_VENDOR: str`, `FIXED_CATEGORY: str`, `GENRE_COLUMN: str`, `FORMAT_COLUMN: str`, `classify_row(row: dict) -> tuple[str, str | None]` (status is `"in_scope"`, `"review"`, or `"skip"`), `transform_group(rows: list[dict]) -> tuple[str, list[dict] | None, str | None]` (status, transformed rows or None, reason or None)

- [ ] **Step 1: Write the failing tests**

Create `tests/data_cleanup/test_reformat_movies.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from reformat_movies import (
    FIXED_VENDOR,
    FIXED_CATEGORY,
    GENRE_COLUMN,
    FORMAT_COLUMN,
    classify_row,
    transform_group,
)


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Vendor": "VHS",
        "Product Category": "Uncategorized",
        "Type": "",
        "Tags": "Comedy, Floor Sale",
        "Option1 Name": "Genre",
        "Option1 Value": "Comedy",
        "Variant Barcode": "12345",
        "Image Src": "https://img/1.jpg",
        "Image Position": "1",
        GENRE_COLUMN: "",
    }
    row.update(overrides)
    return row


class TestClassifyRow(unittest.TestCase):
    def test_genre_option_is_in_scope(self):
        status, reason = classify_row(make_row())
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)

    def test_value_error_genre_is_flagged_for_review(self):
        status, reason = classify_row(make_row(**{"Option1 Value": "#VALUE!"}))
        self.assertEqual(status, "review")
        self.assertIn("#VALUE!", reason)

    def test_unrecognized_genre_value_is_flagged_for_review(self):
        status, reason = classify_row(make_row(**{"Option1 Value": "Not A Real Genre"}))
        self.assertEqual(status, "review")
        self.assertIn("Not A Real Genre", reason)

    def test_title_only_variant_is_flagged_for_review(self):
        status, reason = classify_row(
            make_row(**{"Option1 Name": "Title", "Option1 Value": "Default Title"})
        )
        self.assertEqual(status, "review")
        self.assertIn("no genre set", reason)

    def test_condition_option_is_skipped(self):
        status, reason = classify_row(
            make_row(**{"Option1 Name": "Condition", "Option1 Value": "Standard"})
        )
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)

    def test_supercycle_plan_type_is_skipped(self):
        status, reason = classify_row(make_row(**{"Type": "Supercycle Plan"}))
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)

    def test_extra_image_row_is_skipped(self):
        # Extra image rows for an already-classified product have blank Option1 Name.
        status, reason = classify_row(make_row(**{"Option1 Name": ""}))
        self.assertEqual(status, "skip")
        self.assertIsNone(reason)


class TestTransformGroup(unittest.TestCase):
    def test_simple_product_gets_full_transform(self):
        rows = [make_row(Vendor="VHS", **{"Option1 Value": "Comedy"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)
        first = transformed[0]
        self.assertEqual(first["Vendor"], FIXED_VENDOR)
        self.assertEqual(first["Product Category"], FIXED_CATEGORY)
        self.assertEqual(first["Option1 Name"], "Title")
        self.assertEqual(first["Option1 Value"], "Default Title")
        self.assertEqual(first[GENRE_COLUMN], "comedy")
        self.assertEqual(first[FORMAT_COLUMN], "vhs")

    def test_compound_4k_value_sets_both_fields(self):
        rows = [make_row(Vendor="Blu-Ray", **{"Option1 Value": "4K, Action"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "in_scope")
        first = transformed[0]
        self.assertEqual(first[GENRE_COLUMN], "action")
        self.assertEqual(first[FORMAT_COLUMN], "4-k")

    def test_junk_vendor_leaves_format_blank(self):
        rows = [make_row(Vendor="Walt Disney", **{"Option1 Value": "Drama"})]
        status, transformed, reason = transform_group(rows)
        first = transformed[0]
        self.assertEqual(first[GENRE_COLUMN], "drama")
        self.assertEqual(first[FORMAT_COLUMN], "")

    def test_extra_image_rows_pass_through_unchanged(self):
        primary = make_row(Vendor="DVD", **{"Option1 Value": "Comedy", "Image Position": "1"})
        image_2 = {"Handle": "some-movie", "Image Src": "https://img/2.jpg", "Image Position": "2"}
        image_3 = {"Handle": "some-movie", "Image Src": "https://img/3.jpg", "Image Position": "3"}
        status, transformed, reason = transform_group([primary, image_2, image_3])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(transformed), 3)
        self.assertEqual(transformed[1], image_2)
        self.assertEqual(transformed[2], image_3)

    def test_review_group_returns_no_transformed_rows(self):
        rows = [make_row(**{"Option1 Value": "#VALUE!"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "review")
        self.assertIsNone(transformed)
        self.assertIn("#VALUE!", reason)

    def test_skip_group_returns_no_transformed_rows(self):
        rows = [make_row(**{"Option1 Name": "Condition"})]
        status, transformed, reason = transform_group(rows)
        self.assertEqual(status, "skip")
        self.assertIsNone(transformed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_reformat_movies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reformat_movies'`

- [ ] **Step 3: Write the classification/transform code**

Create `data-cleanup/reformat_movies.py`:

```python
"""Reformat the plain resale movie catalogue in current-movies-export.csv
into clean Shopify fields, ready for bulk re-upload.

Scope: products with Option1 Name == "Genre" only. Serialized rental items
(Option1 Name == "Condition") and the stray Supercycle Plan product are
out of scope for this pass and are left untouched.
"""

from genre_format_mapping import GENRE_VALUE_MAP, resolve_format, resolve_genre

FIXED_VENDOR = "Little Movie Store"
FIXED_CATEGORY = "Media > Videos"
GENRE_COLUMN = "Genre (product.metafields.shopify.genre)"
FORMAT_COLUMN = "Media format (product.metafields.shopify.media-format)"


def classify_row(row: dict) -> tuple[str, str | None]:
    """Classify a product's primary CSV row.

    Returns (status, reason) where status is one of:
    - "in_scope": a plain resale product to reformat
    - "review": can't be cleanly reformatted, needs manual attention
    - "skip": out of scope for this pass (rental, membership plan, or an
      extra image row that isn't a product's primary row)
    """
    option1_name = row["Option1 Name"].strip()

    if option1_name == "Condition":
        return "skip", None
    if row["Type"].strip() == "Supercycle Plan":
        return "skip", None
    if option1_name == "Title":
        return "review", "no genre set (default Title variant)"
    if option1_name != "Genre":
        return "skip", None

    option1_value = row["Option1 Value"].strip()
    if option1_value == "#VALUE!":
        return "review", "corrupted genre value (#VALUE!)"
    if option1_value not in GENRE_VALUE_MAP:
        return "review", f"unrecognized genre value: {option1_value!r}"
    return "in_scope", None


def transform_group(rows: list[dict]) -> tuple[str, list[dict] | None, str | None]:
    """Classify and, if in scope, transform all CSV rows for one product handle.

    `rows` is every CSV row sharing a Handle, in original order (the first
    row is the product's primary row; any remaining rows are extra images).
    Returns (status, transformed_rows_or_None, reason_or_None).
    """
    first = rows[0]
    status, reason = classify_row(first)
    if status != "in_scope":
        return status, None, reason

    vendor = first["Vendor"].strip()
    option1_value = first["Option1 Value"].strip()

    new_first = dict(first)
    new_first["Vendor"] = FIXED_VENDOR
    new_first["Product Category"] = FIXED_CATEGORY
    new_first["Option1 Name"] = "Title"
    new_first["Option1 Value"] = "Default Title"
    new_first[GENRE_COLUMN] = resolve_genre(option1_value) or ""
    new_first[FORMAT_COLUMN] = resolve_format(vendor, option1_value) or ""

    transformed = [new_first] + [dict(r) for r in rows[1:]]
    return "in_scope", transformed, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_reformat_movies.py -v`
Expected: all tests PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/reformat_movies.py tests/data_cleanup/test_reformat_movies.py
git commit -m "Add row classification and per-product transform for movie reformat"
```

---

### Task 3: CSV pipeline (grouping, file I/O, review report)

**Files:**
- Modify: `data-cleanup/reformat_movies.py` (add grouping + `build_output` + `main`)
- Modify: `tests/data_cleanup/test_reformat_movies.py` (add pipeline tests)
- Create: `tests/data_cleanup/fixtures/sample_export.csv`

**Interfaces:**
- Consumes: `classify_row`, `transform_group` (Task 2)
- Produces: `group_rows_by_handle(rows: list[dict]) -> list[tuple[str, list[dict]]]`, `build_output(rows: list[dict], fieldnames: list[str]) -> tuple[list[str], list[dict], list[dict]]` (new_fieldnames, output_rows, review_rows), `main(input_path, output_path, review_path) -> tuple[int, int]` (counts of output rows, review rows)

- [ ] **Step 1: Create the fixture CSV**

Create `tests/data_cleanup/fixtures/sample_export.csv`:

```csv
Handle,Title,Vendor,Product Category,Type,Tags,Option1 Name,Option1 Value,Variant Barcode,Image Src,Image Position,Genre (product.metafields.shopify.genre)
simple-comedy-vhs,Simple Comedy,VHS,Uncategorized,,"Comedy, Floor Sale",Genre,Comedy,111,https://img/1.jpg,1,
junk-vendor-drama,Junk Vendor Drama,Walt Disney,Uncategorized,,"Drama, Floor Sale",Genre,Drama,222,https://img/2.jpg,1,
compound-4k-action,Compound 4K Action,Blu-Ray,Uncategorized,,"Action, Floor Sale",Genre,"4K, Action",333,https://img/3.jpg,1,
multi-image-product,Multi Image Product,DVD,Uncategorized,,"Comedy, Floor Sale",Genre,Comedy,444,https://img/4a.jpg,1,
multi-image-product,,,,,,,,,https://img/4b.jpg,2,
multi-image-product,,,,,,,,,https://img/4c.jpg,3,
badvalue-row,Bad Value Row,VHS,Uncategorized,,"Comedy, Floor Sale",Genre,#VALUE!,555,https://img/5.jpg,1,
title-only-row,Title Only Row,VHS,Uncategorized,,"Action, Floor Sale",Title,Default Title,666,https://img/6.jpg,1,
rental-condition-row,Rental Condition Row,DVD,Uncategorized,,Rental,Condition,Standard,777,https://img/7.jpg,1,
supercycle-plan,Supercycle Membership,,,Supercycle Plan,,,,,,,
foreign-typo-check,Foreign Movie,DVD,Uncategorized,,"Foreign, Floor Sale",Genre,Foreign,999,https://img/9.jpg,1,
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/data_cleanup/test_reformat_movies.py` (append before the `if __name__ == "__main__":` line):

```python
import csv
import tempfile
from pathlib import Path as _Path

from reformat_movies import group_rows_by_handle, build_output, main

FIXTURE_PATH = _Path(__file__).resolve().parent / "fixtures" / "sample_export.csv"


def load_fixture():
    with open(FIXTURE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


class TestGroupRowsByHandle(unittest.TestCase):
    def test_groups_preserve_order_and_multi_row_products(self):
        fieldnames, rows = load_fixture()
        groups = group_rows_by_handle(rows)
        handles = [handle for handle, _ in groups]
        self.assertEqual(handles[0], "simple-comedy-vhs")
        multi = dict(groups)["multi-image-product"]
        self.assertEqual(len(multi), 3)
        self.assertEqual(multi[0]["Image Position"], "1")
        self.assertEqual(multi[1]["Image Position"], "2")
        self.assertEqual(multi[2]["Image Position"], "3")


class TestBuildOutput(unittest.TestCase):
    def setUp(self):
        self.fieldnames, self.rows = load_fixture()
        self.new_fieldnames, self.output_rows, self.review_rows = build_output(
            self.rows, self.fieldnames
        )

    def test_adds_media_format_column(self):
        self.assertIn(FORMAT_COLUMN, self.new_fieldnames)

    def test_in_scope_products_are_in_output(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        self.assertIn("simple-comedy-vhs", output_handles)
        self.assertIn("junk-vendor-drama", output_handles)
        self.assertIn("compound-4k-action", output_handles)
        self.assertIn("foreign-typo-check", output_handles)

    def test_multi_image_product_keeps_all_three_rows(self):
        rows = [r for r in self.output_rows if r["Handle"] == "multi-image-product"]
        self.assertEqual(len(rows), 3)

    def test_foreign_typo_is_corrected(self):
        row = next(r for r in self.output_rows if r["Handle"] == "foreign-typo-check")
        self.assertEqual(row[GENRE_COLUMN], "foreign")

    def test_out_of_scope_rows_excluded_entirely(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        self.assertNotIn("rental-condition-row", output_handles)
        self.assertNotIn("rental-condition-row", review_handles)
        self.assertNotIn("supercycle-plan", output_handles)
        self.assertNotIn("supercycle-plan", review_handles)

    def test_bad_rows_go_to_review_not_output(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        self.assertNotIn("badvalue-row", output_handles)
        self.assertIn("badvalue-row", review_handles)
        self.assertNotIn("title-only-row", output_handles)
        self.assertIn("title-only-row", review_handles)


class TestMain(unittest.TestCase):
    def test_writes_output_and_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "movies-reformatted.csv"
            review_path = Path(tmp) / "needs-review.csv"
            n_out, n_review = main(FIXTURE_PATH, output_path, review_path)

            self.assertTrue(output_path.exists())
            self.assertTrue(review_path.exists())
            self.assertEqual(n_review, 2)

            with open(output_path, newline="", encoding="utf-8") as f:
                out_rows = list(csv.DictReader(f))
            self.assertEqual(len(out_rows), n_out)
            self.assertIn(FORMAT_COLUMN, out_rows[0].keys())

            with open(review_path, newline="", encoding="utf-8") as f:
                review_rows = list(csv.DictReader(f))
            reasons = {row["Handle"]: row["Reason"] for row in review_rows}
            self.assertIn("#VALUE!", reasons["badvalue-row"])
            self.assertIn("no genre set", reasons["title-only-row"])
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_reformat_movies.py -v`
Expected: FAIL with `ImportError: cannot import name 'group_rows_by_handle'`

- [ ] **Step 4: Add the pipeline code**

Append to `data-cleanup/reformat_movies.py`:

```python
import csv
from pathlib import Path


def group_rows_by_handle(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group CSV rows by Handle, preserving first-seen order."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        handle = row["Handle"]
        if handle not in groups:
            groups[handle] = []
            order.append(handle)
        groups[handle].append(row)
    return [(handle, groups[handle]) for handle in order]


def build_output(
    rows: list[dict], fieldnames: list[str]
) -> tuple[list[str], list[dict], list[dict]]:
    """Run the full reformat over every row, split into output vs. review rows.

    Returns (new_fieldnames, output_rows, review_rows). new_fieldnames is
    fieldnames with FORMAT_COLUMN inserted if it wasn't already present.
    """
    new_fieldnames = list(fieldnames)
    if FORMAT_COLUMN not in new_fieldnames:
        genre_index = new_fieldnames.index(GENRE_COLUMN)
        new_fieldnames.insert(genre_index + 1, FORMAT_COLUMN)

    output_rows: list[dict] = []
    review_rows: list[dict] = []
    for handle, group in group_rows_by_handle(rows):
        status, transformed, reason = transform_group(group)
        if status == "in_scope":
            output_rows.extend(transformed)
        elif status == "review":
            review_rows.append(
                {"Handle": handle, "Title": group[0]["Title"], "Reason": reason}
            )
        # status == "skip": out of scope for this pass, omitted entirely

    return new_fieldnames, output_rows, review_rows


def main(input_path, output_path, review_path) -> tuple[int, int]:
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    new_fieldnames, output_rows, review_rows = build_output(rows, fieldnames)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with open(review_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Handle", "Title", "Reason"])
        writer.writeheader()
        writer.writerows(review_rows)

    return len(output_rows), len(review_rows)


if __name__ == "__main__":
    base = Path(__file__).parent
    n_out, n_review = main(
        base / "current-movies-export.csv",
        base / "movies-reformatted.csv",
        base / "needs-review.csv",
    )
    print(f"Wrote {n_out} rows to movies-reformatted.csv")
    print(f"Wrote {n_review} rows to needs-review.csv")
```

Move the `from genre_format_mapping import ...` and `FIXED_VENDOR`/`FIXED_CATEGORY`/`GENRE_COLUMN`/`FORMAT_COLUMN` constants (already at the top of the file from Task 2) so they stay above these additions — no changes needed to them, just confirm the file now has: module docstring, imports (`csv`, `Path`, then `genre_format_mapping`), constants, `classify_row`, `transform_group`, `group_rows_by_handle`, `build_output`, `main`, and the `if __name__ == "__main__":` block, in that order.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_reformat_movies.py -v`
Expected: all tests PASS (21 tests)

- [ ] **Step 6: Commit**

```bash
git add data-cleanup/reformat_movies.py tests/data_cleanup/test_reformat_movies.py tests/data_cleanup/fixtures/sample_export.csv
git commit -m "Add CSV pipeline for movie product reformat with review report"
```

---

### Task 4: Run against the real export and verify

**Files:**
- None created/modified — this task runs the script from Task 3 against the real data and manually verifies the result.

**Interfaces:**
- Consumes: `main` from `data-cleanup/reformat_movies.py`

- [ ] **Step 1: Run the script against the real export**

Run: `python3 data-cleanup/reformat_movies.py`
Expected output (verified during design against the real file): `Wrote 1846 rows to movies-reformatted.csv` and `Wrote 29 rows to needs-review.csv`. One of the 29 review rows is not a `#VALUE!` or `Title`-only case: `muppets-treasure-island` already has `Option1 Value = "kids-family"` (someone previously hand-edited this one product's metafield directly in the admin, leaving the fake variant option out of sync) — it's correctly caught by the "unrecognized genre value" fallback rather than silently mishandled.

- [ ] **Step 2: Verify handle-level counts add up**

Run:

```bash
python3 -c "
import csv
from pathlib import Path
import sys
sys.path.insert(0, 'data-cleanup')
from reformat_movies import group_rows_by_handle, build_output

with open('data-cleanup/current-movies-export.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    rows = list(reader)

total_handles = len(group_rows_by_handle(rows))
_, output_rows, review_rows = build_output(rows, fieldnames)
output_handles = {r['Handle'] for r in output_rows}
review_handles = {r['Handle'] for r in review_rows}
skipped = total_handles - len(output_handles) - len(review_handles)

print('total product handles:', total_handles)
print('in-scope (output) handles:', len(output_handles))
print('review handles:', len(review_handles))
print('skipped (out of scope) handles:', skipped)
"
```

Expected (verified against the real file during design): `total product handles: 2547`, `in-scope (output) handles: 1846`, `review handles: 29`, `skipped (out of scope) handles: 672` (671 serialized rental + 1 Supercycle Plan). If these numbers don't match exactly, inspect which handles differ with a quick `python3 -c` printing their `Option1 Name`/`Type`/`Option1 Value` before proceeding — every skipped handle should be explainable as rental or the membership plan, and every review handle as a corrupted, missing, or unrecognized genre value.

- [ ] **Step 3: Spot-check the output CSV by hand**

Run: `head -5 data-cleanup/movies-reformatted.csv` and confirm: `Vendor` column reads `Little Movie Store` for every row, `Product Category` reads `Media > Videos` on first rows, `Option1 Name`/`Option1 Value` read `Title`/`Default Title`, and the `Media format`/`Genre` metafield columns are populated with lowercase-hyphenated handles (e.g. `vhs`, `comedy`).

Run: `grep -c "Little Movie Store" data-cleanup/movies-reformatted.csv` and confirm the count is greater than 0 and consistent with the number of in-scope product rows (product rows only — extra image rows won't contain it).

- [ ] **Step 4: Spot-check the review report**

Run: `cat data-cleanup/needs-review.csv` and manually confirm all 29 rows are genuinely the 2 `#VALUE!` rows and 27 `Title`-only rows identified during design (cross-check a couple of handles against `grep <handle> data-cleanup/current-movies-export.csv` in the original file).

- [ ] **Step 5: No commit this step**

`movies-reformatted.csv` and `needs-review.csv` live in `data-cleanup/`, which is untracked in git (verified: not gitignored, just never added). Leave them untracked, matching the existing `current-movies-export.csv`. Nothing to commit for this task.

---

### Task 5: Manual trial import on the dev store (verification, not code)

This task has no code changes. It exists to de-risk the actual Shopify import before the user commits to re-uploading all ~1,820 products, since changing an existing product's variant option scheme via CSV import is not something this plan can verify without hitting a real store.

- [ ] **Step 1: Build a tiny trial CSV**

Copy the header row plus 3-5 representative product row-groups (include at least one multi-image product) from `data-cleanup/movies-reformatted.csv` into `data-cleanup/trial-import.csv`.

- [ ] **Step 2: Import the trial CSV to the dev store**

In the Shopify admin for `lms-sandbox-lutsfahz.myshopify.com` (per `CLAUDE.md`, the default dev store — never the production store for this): Products → Import → upload `data-cleanup/trial-import.csv` → "Overwrite existing products that have the same handle".

- [ ] **Step 3: Confirm the update took effect correctly**

Open one of the trial products in the admin. Confirm: Vendor shows `Little Movie Store`, Category shows `Media > Videos`, the product has a single "Default Title" variant (no more genre-named fake variant), and the Genre/Media format metafields show the correct values with no data loss (price, images, barcode, inventory unchanged from before the import).

- [ ] **Step 4: Decide on the full import**

If the trial looks correct, the user can import the full `data-cleanup/movies-reformatted.csv` the same way. If anything looks wrong, report back with specifics (which field, which product) so the script can be fixed before a full run — do not proceed to the full import until the trial is confirmed clean.
