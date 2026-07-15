# CircaOS Product Reformat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a script that reformats the 671 serialized-rental ("CircaOS") movie products listed in `data-cleanup/out-of-scope.csv` into the same clean Shopify fields as the first reformat pass (`data-cleanup/reformat_movies.py`), while correctly splitting the 7 titles that have 2 real physical copies into separate single-variant products.

**Architecture:** A second script, `data-cleanup/circaos_reformat.py`, that reuses `data-cleanup/genre_format_mapping.py`'s lookup tables and `data-cleanup/reformat_movies.py`'s shared constants/`group_rows_by_handle`. New logic covers what's unique to this batch: extracting genre from `Tags` instead of a fake variant option, resolving format from the per-copy `Variant Barcode` prefix (falling back to `Vendor`), and splitting multi-copy titles into independent products. Tested with Python's stdlib `unittest`, no new dependencies.

**Tech Stack:** Python 3 (stdlib only: `csv`, `unittest`, `pathlib`).

## Global Constraints

- Scope is the 671 products where `Option1 Name == "Condition"` AND `Type != "Supercycle Plan"`. The 1 Supercycle Plan product is silently excluded (not touched, not flagged). Any row where `Option1 Name` isn't `"Condition"` (e.g. a resale-batch row that ended up in this data by mistake) is also silently skipped.
- `Vendor` becomes `"Little Movie Store"` for every in-scope product, unconditionally (reuse `FIXED_VENDOR` from `reformat_movies.py`).
- `Product Category` becomes `"Media > Videos"` for every in-scope product (reuse `FIXED_CATEGORY`).
- `Option1 Name/Value = "Condition"/<grading>` is dropped entirely, replaced with `Option1 Name = "Title"`, `Option1 Value = "Default Title"`.
- `Option2 Name/Value = "Serial Number"/<code>` is dropped entirely (set to empty string) — the identifier is preserved via `Variant Barcode`, which is left unchanged.
- `Variant SKU` is dropped (set to empty string) — it duplicates `Variant Barcode` in every case.
- Genre (`product.metafields.shopify.genre`, reuse `GENRE_COLUMN`): extracted from `Tags`, not a fake variant option. Use the first tag (in order) that is a key in `GENRE_VALUE_MAP` with no comma in it (the "simple" genre tags — Comedy, Action, Drama, Kids & Family, Sci-Fi, Thriller, Horror, Romantic Comedy, Musical, Fantasy, Documentary, Foreign, plus existing typo variants) whose resolved genre handle is not `None`. If a matching tag resolves to `None` (e.g. `Special Interest`), keep scanning remaining tags for one that resolves to a real genre.
- Format (`product.metafields.shopify.media-format`, reuse `FORMAT_COLUMN`): **primary signal is the row's own `Variant Barcode` prefix** — the first 3 characters after `191-` — mapped `VHS`→`vhs`, `DVD`→`dvd`, `BLR`→`blu-ray`, `4K`→`4-k`. Falls back to `Tags` containing a `4K`/`4k` tag (→`4-k`), then to `Vendor` via `VENDOR_TO_FORMAT`, only when the barcode doesn't match one of those 4 prefixes.
- `Tags`: preserved, with `CircaOS Import` appended (not duplicated if already present).
- `Body (HTML)`: untouched this pass.
- Multi-copy titles (7 confirmed: `royal-tenenbaums`, `a-million-to-juan`, `finding-dory`, `night-of-the-living-dead`, `speed-racer`, `get-shorty`, `outrageous-fortune`) split into one product per real variant row. If the copies resolve to different formats, each new handle gets a format suffix (`vhs`/`dvd`/`bluray`/`4k`) appended to the base handle. If the copies resolve to the same format, the first keeps the original handle and subsequent copies get `-copy-2`, `-copy-3`, etc. appended.
- Rows with no genre-like tag at all in `Tags` go to a review report (`Handle`, `Title`, `Reason`) and are excluded from the main output — verified: 21 such handles exist, none overlapping with the 7 multi-copy titles.
- `data-cleanup/` is untracked in git (confirmed unchanged from the first pass). Only the script and its tests get committed; the CSVs stay untracked.

---

## File Structure

- `data-cleanup/circaos_reformat.py` — the new script. Imports `VENDOR_TO_FORMAT`, `GENRE_VALUE_MAP` from `genre_format_mapping.py`, and `FIXED_VENDOR`, `FIXED_CATEGORY`, `GENRE_COLUMN`, `FORMAT_COLUMN`, `group_rows_by_handle` from `reformat_movies.py`. Contains: tag/barcode-based genre and format resolution, row classification, per-group transform (including the multi-copy split), and the CSV pipeline (`build_output`/`main`).
- `tests/data_cleanup/test_circaos_reformat.py` — unit tests for every function above.
- `tests/data_cleanup/fixtures/circaos_sample_export.csv` — fixture covering every scenario: simple product, no-genre-tag review case, Supercycle Plan skip, resale-batch-row skip, same-format multi-copy split, different-format multi-copy split, extra-image-row passthrough.

---

### Task 1: Tag/barcode resolution and row classification

**Files:**
- Create: `data-cleanup/circaos_reformat.py` (module docstring, imports, constants, and the functions listed below only — `build_product_handles`, `transform_circaos_group`, `build_output`, `main` come in later tasks)
- Test: `tests/data_cleanup/test_circaos_reformat.py` (test classes for these functions only)

**Interfaces:**
- Consumes: `VENDOR_TO_FORMAT`, `GENRE_VALUE_MAP` from `data-cleanup/genre_format_mapping.py` (already exist, unchanged)
- Produces: `TAG_TO_ADD: str`, `SIMPLE_GENRE_TAGS: dict[str, tuple[str | None, str | None]]`, `BARCODE_FORMAT_PREFIXES: list[tuple[str, str]]`, `has_genre_tag(tags_str: str) -> bool`, `extract_genre_from_tags(tags_str: str) -> str | None`, `format_from_barcode(barcode: str) -> str | None`, `resolve_circaos_format(vendor: str, tags_str: str, barcode: str) -> str | None`, `build_tags(tags_str: str) -> str`, `classify_circaos_row(row: dict) -> tuple[str, str | None]`

- [ ] **Step 1: Write the failing tests**

Create `tests/data_cleanup/test_circaos_reformat.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from circaos_reformat import (
    TAG_TO_ADD,
    has_genre_tag,
    extract_genre_from_tags,
    format_from_barcode,
    resolve_circaos_format,
    build_tags,
    classify_circaos_row,
)


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Vendor": "VHS",
        "Product Category": "Uncategorized",
        "Type": "",
        "Tags": "Rental, Thriller",
        "Option1 Name": "Condition",
        "Option1 Value": "Standard",
        "Option2 Name": "Serial Number",
        "Option2 Value": "001A",
        "Variant SKU": "191-VHSSOM-001A",
        "Variant Barcode": "191-VHSSOM-001A",
        "Image Src": "https://img/1.jpg",
        "Image Position": "1",
        "Genre (product.metafields.shopify.genre)": "",
    }
    row.update(overrides)
    return row


class TestHasGenreTag(unittest.TestCase):
    def test_true_when_genre_tag_present(self):
        self.assertTrue(has_genre_tag("Rental, Thriller"))

    def test_false_when_only_status_tags(self):
        self.assertFalse(has_genre_tag("Rental, Floor Sale"))

    def test_false_when_no_tags(self):
        self.assertFalse(has_genre_tag(""))


class TestExtractGenreFromTags(unittest.TestCase):
    def test_extracts_plain_genre_tag(self):
        self.assertEqual(extract_genre_from_tags("Rental, Thriller"), "thriller")

    def test_returns_none_when_no_genre_tag(self):
        self.assertIsNone(extract_genre_from_tags("Rental, Floor Sale"))

    def test_skips_null_genre_tag_for_a_later_real_one(self):
        self.assertEqual(extract_genre_from_tags("Special Interest, Comedy"), "comedy")


class TestFormatFromBarcode(unittest.TestCase):
    def test_vhs_prefix(self):
        self.assertEqual(format_from_barcode("191-VHSSCP-001A"), "vhs")

    def test_dvd_prefix(self):
        self.assertEqual(format_from_barcode("191-DVDROY-002A"), "dvd")

    def test_blu_ray_prefix(self):
        self.assertEqual(format_from_barcode("191-BLRSPE-50-001A"), "blu-ray")

    def test_4k_prefix(self):
        self.assertEqual(format_from_barcode("191-4K2MOR-50-001A"), "4-k")

    def test_no_191_prefix_returns_none(self):
        self.assertIsNone(format_from_barcode("88302842"))

    def test_unknown_code_returns_none(self):
        self.assertIsNone(format_from_barcode("191-WLTABC-001A"))


class TestResolveCircaosFormat(unittest.TestCase):
    def test_barcode_takes_priority_over_vendor(self):
        self.assertEqual(
            resolve_circaos_format("DVD", "Rental", "191-BLRSPE-50-001A"), "blu-ray"
        )

    def test_falls_back_to_tags_4k_override(self):
        self.assertEqual(
            resolve_circaos_format("Blu-Ray", "Rental, 4K", "88302842"), "4-k"
        )

    def test_falls_back_to_vendor(self):
        self.assertEqual(resolve_circaos_format("DVD", "Rental", "88302842"), "dvd")

    def test_returns_none_for_unmapped_vendor_and_no_barcode_match(self):
        self.assertIsNone(resolve_circaos_format("Walt Disney", "Rental", "88302842"))


class TestBuildTags(unittest.TestCase):
    def test_appends_tag_to_existing(self):
        self.assertEqual(build_tags("Rental, Thriller"), "Rental, Thriller, CircaOS Import")

    def test_does_not_duplicate_if_already_present(self):
        self.assertEqual(
            build_tags(f"Rental, {TAG_TO_ADD}"), f"Rental, {TAG_TO_ADD}"
        )


class TestClassifyCircaosRow(unittest.TestCase):
    def test_condition_option_with_genre_tag_is_in_scope(self):
        status, reason = classify_circaos_row(make_row())
        self.assertEqual(status, "in_scope")
        self.assertIsNone(reason)

    def test_supercycle_plan_is_skipped(self):
        status, reason = classify_circaos_row(make_row(Type="Supercycle Plan"))
        self.assertEqual(status, "skip")

    def test_non_condition_option_is_skipped(self):
        status, reason = classify_circaos_row(
            make_row(**{"Option1 Name": "Genre", "Option1 Value": "Comedy"})
        )
        self.assertEqual(status, "skip")

    def test_no_genre_tag_is_flagged_for_review(self):
        status, reason = classify_circaos_row(make_row(Tags="Rental, Floor Sale"))
        self.assertEqual(status, "review")
        self.assertIn("no genre-like tag", reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'circaos_reformat'`

- [ ] **Step 3: Write the module**

Create `data-cleanup/circaos_reformat.py`:

```python
"""Reformat the serialized-rental ("CircaOS") movie batch in
current-movies-export.csv into the same clean Shopify fields as the resale
batch (reformat_movies.py).

Scope: products with Option1 Name == "Condition" only, excluding the stray
Supercycle Plan product. See
docs/superpowers/specs/2026-07-14-circaos-product-reformat-design.md.
"""

from genre_format_mapping import VENDOR_TO_FORMAT, GENRE_VALUE_MAP

TAG_TO_ADD = "CircaOS Import"

SIMPLE_GENRE_TAGS = {k: v for k, v in GENRE_VALUE_MAP.items() if "," not in k}

BARCODE_FORMAT_PREFIXES = [
    ("VHS", "vhs"),
    ("DVD", "dvd"),
    ("BLR", "blu-ray"),
    ("4K", "4-k"),
]


def has_genre_tag(tags_str: str) -> bool:
    tags = [t.strip() for t in tags_str.split(",")]
    return any(t in SIMPLE_GENRE_TAGS for t in tags)


def extract_genre_from_tags(tags_str: str) -> str | None:
    tags = [t.strip() for t in tags_str.split(",")]
    for t in tags:
        if t in SIMPLE_GENRE_TAGS:
            genre_handle, _ = SIMPLE_GENRE_TAGS[t]
            if genre_handle is not None:
                return genre_handle
    return None


def format_from_barcode(barcode: str) -> str | None:
    body = barcode[4:] if barcode.startswith("191-") else barcode
    for prefix, handle in BARCODE_FORMAT_PREFIXES:
        if body.startswith(prefix):
            return handle
    return None


def resolve_circaos_format(vendor: str, tags_str: str, barcode: str) -> str | None:
    from_barcode = format_from_barcode(barcode)
    if from_barcode is not None:
        return from_barcode
    tags = [t.strip() for t in tags_str.split(",")]
    if "4K" in tags or "4k" in tags:
        return "4-k"
    return VENDOR_TO_FORMAT.get(vendor)


def build_tags(tags_str: str) -> str:
    existing = [t.strip() for t in tags_str.split(",") if t.strip()]
    if TAG_TO_ADD not in existing:
        existing.append(TAG_TO_ADD)
    return ", ".join(existing)


def classify_circaos_row(row: dict) -> tuple[str, str | None]:
    """Classify a product's primary CSV row.

    Returns (status, reason) where status is one of:
    - "in_scope": a serialized-rental product to reformat
    - "review": has no genre-like tag, can't be cleanly reformatted
    - "skip": out of scope for this pass (Supercycle Plan, or not part of
      this batch at all)
    """
    if row["Type"].strip() == "Supercycle Plan":
        return "skip", None
    if row["Option1 Name"].strip() != "Condition":
        return "skip", None
    if not has_genre_tag(row["Tags"]):
        return "review", "no genre-like tag found in Tags"
    return "in_scope", None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: all tests PASS (22 tests)

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/circaos_reformat.py tests/data_cleanup/test_circaos_reformat.py
git commit -m "Add tag/barcode resolution and classification for CircaOS reformat"
```

---

### Task 2: Multi-copy handle building and per-group transform

**Files:**
- Modify: `data-cleanup/circaos_reformat.py` (add `FORMAT_HANDLE_SUFFIX`, `build_product_handles`, `transform_circaos_group`)
- Modify: `tests/data_cleanup/test_circaos_reformat.py` (add test classes for these functions)

**Interfaces:**
- Consumes: `classify_circaos_row`, `extract_genre_from_tags`, `resolve_circaos_format`, `build_tags` (Task 1); `FIXED_VENDOR`, `FIXED_CATEGORY`, `GENRE_COLUMN`, `FORMAT_COLUMN` from `reformat_movies.py`
- Produces: `FORMAT_HANDLE_SUFFIX: dict[str, str]`, `build_product_handles(base_handle: str, real_rows: list[dict], vendor: str, tags_str: str) -> list[str]`, `transform_circaos_group(rows: list[dict]) -> tuple[str, list[list[dict]] | None, str | None]` (status, list of products where each product is itself a list of CSV rows, or None; reason or None)

- [ ] **Step 1: Write the failing tests**

Add to `tests/data_cleanup/test_circaos_reformat.py` (append before the `if __name__ == "__main__":` line, and add the new imports to the existing `from circaos_reformat import (...)` line at the top):

```python
from circaos_reformat import (
    TAG_TO_ADD,
    has_genre_tag,
    extract_genre_from_tags,
    format_from_barcode,
    resolve_circaos_format,
    build_tags,
    classify_circaos_row,
    build_product_handles,
    transform_circaos_group,
)
from reformat_movies import GENRE_COLUMN, FORMAT_COLUMN, FIXED_VENDOR, FIXED_CATEGORY
```

```python
class TestBuildProductHandles(unittest.TestCase):
    def test_single_real_row_keeps_original_handle(self):
        rows = [make_row()]
        handles = build_product_handles("some-movie", rows, "VHS", "Rental")
        self.assertEqual(handles, ["some-movie"])

    def test_same_format_copies_get_copy_suffix(self):
        rows = [
            make_row(**{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(**{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        handles = build_product_handles("split-same-format", rows, "DVD", "Drama, Rental")
        self.assertEqual(handles, ["split-same-format", "split-same-format-copy-2"])

    def test_different_format_copies_get_format_suffix(self):
        rows = [
            make_row(**{"Variant Barcode": "191-BLRDIF-50-001A"}),
            make_row(**{"Variant Barcode": "191-DVDDIF-001A"}),
        ]
        handles = build_product_handles("split-diff-format", rows, "BLU-RAY", "Action, Rental")
        self.assertEqual(handles, ["split-diff-format-bluray", "split-diff-format-dvd"])


class TestTransformCircaosGroup(unittest.TestCase):
    def test_simple_product_gets_full_transform(self):
        status, products, reason = transform_circaos_group([make_row()])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 1)
        row = products[0][0]
        self.assertEqual(row["Vendor"], FIXED_VENDOR)
        self.assertEqual(row["Product Category"], FIXED_CATEGORY)
        self.assertEqual(row["Option1 Name"], "Title")
        self.assertEqual(row["Option1 Value"], "Default Title")
        self.assertEqual(row["Option2 Name"], "")
        self.assertEqual(row["Option2 Value"], "")
        self.assertEqual(row["Variant SKU"], "")
        self.assertEqual(row["Variant Barcode"], "191-VHSSOM-001A")
        self.assertEqual(row[GENRE_COLUMN], "thriller")
        self.assertEqual(row[FORMAT_COLUMN], "vhs")
        self.assertEqual(row["Tags"], "Rental, Thriller, CircaOS Import")

    def test_split_same_format_produces_two_products(self):
        rows = [
            make_row(Handle="split-same", Vendor="DVD", Tags="Drama, Rental",
                     **{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(Handle="split-same", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        status, products, reason = transform_circaos_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0][0]["Handle"], "split-same")
        self.assertEqual(products[1][0]["Handle"], "split-same-copy-2")
        self.assertEqual(products[0][0][FORMAT_COLUMN], "dvd")
        self.assertEqual(products[1][0][FORMAT_COLUMN], "dvd")

    def test_split_different_format_produces_two_products(self):
        rows = [
            make_row(Handle="split-diff", Vendor="BLU-RAY", Tags="Action, Rental",
                     **{"Variant Barcode": "191-BLRDIF-50-001A"}),
            make_row(Handle="split-diff", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDDIF-001A"}),
        ]
        status, products, reason = transform_circaos_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertEqual(products[0][0]["Handle"], "split-diff-bluray")
        self.assertEqual(products[1][0]["Handle"], "split-diff-dvd")
        self.assertEqual(products[0][0][FORMAT_COLUMN], "blu-ray")
        self.assertEqual(products[1][0][FORMAT_COLUMN], "dvd")

    def test_extra_image_rows_pass_through_on_first_product_only(self):
        primary = make_row(Handle="multi-image-title", Tags="Horror, Rental")
        image_2 = {"Handle": "multi-image-title", "Option1 Value": "", "Image Src": "https://img/b.jpg", "Image Position": "2"}
        image_3 = {"Handle": "multi-image-title", "Option1 Value": "", "Image Src": "https://img/c.jpg", "Image Position": "3"}
        status, products, reason = transform_circaos_group([primary, image_2, image_3])
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 1)
        self.assertEqual(len(products[0]), 3)
        self.assertEqual(products[0][1], image_2)
        self.assertEqual(products[0][2], image_3)

    def test_review_group_returns_no_products(self):
        status, products, reason = transform_circaos_group([make_row(Tags="Rental, Floor Sale")])
        self.assertEqual(status, "review")
        self.assertIsNone(products)

    def test_skip_group_returns_no_products(self):
        status, products, reason = transform_circaos_group(
            [make_row(**{"Option1 Name": "Genre", "Option1 Value": "Comedy"})]
        )
        self.assertEqual(status, "skip")
        self.assertIsNone(products)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_product_handles'`

- [ ] **Step 3: Add the handle-building and transform code**

Append to `data-cleanup/circaos_reformat.py` after `classify_circaos_row`. The file doesn't import from `reformat_movies` yet — add this new import line right after the existing `from genre_format_mapping import ...` line:

```python
from reformat_movies import FIXED_VENDOR, FIXED_CATEGORY, GENRE_COLUMN, FORMAT_COLUMN
```

Then add the following:

```python
FORMAT_HANDLE_SUFFIX = {
    "vhs": "vhs",
    "dvd": "dvd",
    "blu-ray": "bluray",
    "4-k": "4k",
}


def build_product_handles(
    base_handle: str, real_rows: list[dict], vendor: str, tags_str: str
) -> list[str]:
    if len(real_rows) == 1:
        return [base_handle]
    formats = [
        resolve_circaos_format(vendor, tags_str, r["Variant Barcode"].strip())
        for r in real_rows
    ]
    if len(set(formats)) > 1:
        return [
            f"{base_handle}-{FORMAT_HANDLE_SUFFIX.get(fmt, 'copy')}" for fmt in formats
        ]
    return [base_handle] + [
        f"{base_handle}-copy-{i + 1}" for i in range(1, len(real_rows))
    ]


def transform_circaos_group(
    rows: list[dict],
) -> tuple[str, list[list[dict]] | None, str | None]:
    """Classify and, if in scope, transform all CSV rows for one product handle.

    `rows` is every CSV row sharing a Handle, in original order. Returns
    (status, products, reason). `products` is a list where each element is
    the list of output CSV rows for one product — usually one product per
    group, but multi-copy titles produce one product per real variant row.
    """
    first = rows[0]
    status, reason = classify_circaos_row(first)
    if status != "in_scope":
        return status, None, reason

    vendor = first["Vendor"].strip()
    tags_str = first["Tags"]
    genre = extract_genre_from_tags(tags_str)
    new_tags = build_tags(tags_str)

    real_rows = [r for r in rows if r["Option1 Value"].strip()]
    extra_image_rows = [r for r in rows if not r["Option1 Value"].strip()]
    base_handle = first["Handle"]
    new_handles = build_product_handles(base_handle, real_rows, vendor, tags_str)

    products = []
    for i, (real_row, new_handle) in enumerate(zip(real_rows, new_handles)):
        fmt = resolve_circaos_format(vendor, tags_str, real_row["Variant Barcode"].strip())
        new_row = dict(real_row)
        new_row["Handle"] = new_handle
        new_row["Vendor"] = FIXED_VENDOR
        new_row["Product Category"] = FIXED_CATEGORY
        new_row["Option1 Name"] = "Title"
        new_row["Option1 Value"] = "Default Title"
        new_row["Option2 Name"] = ""
        new_row["Option2 Value"] = ""
        new_row["Variant SKU"] = ""
        new_row[GENRE_COLUMN] = genre or ""
        new_row[FORMAT_COLUMN] = fmt or ""
        new_row["Tags"] = new_tags

        product_rows = [new_row]
        if i == 0:
            product_rows += [dict(r) for r in extra_image_rows]
        products.append(product_rows)

    return "in_scope", products, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: all tests PASS (31 tests)

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/circaos_reformat.py tests/data_cleanup/test_circaos_reformat.py
git commit -m "Add multi-copy split and per-group transform for CircaOS reformat"
```

---

### Task 3: CSV pipeline and fixture

**Files:**
- Modify: `data-cleanup/circaos_reformat.py` (add `build_output`, `main`)
- Modify: `tests/data_cleanup/test_circaos_reformat.py` (add pipeline tests)
- Create: `tests/data_cleanup/fixtures/circaos_sample_export.csv`

**Interfaces:**
- Consumes: `transform_circaos_group` (Task 2); `group_rows_by_handle` from `reformat_movies.py`
- Produces: `build_output(rows: list[dict], fieldnames: list[str]) -> tuple[list[str], list[dict], list[dict]]`, `main(input_path, output_path, review_path) -> tuple[int, int]`

- [ ] **Step 1: Create the fixture CSV**

Create `tests/data_cleanup/fixtures/circaos_sample_export.csv`:

```csv
Handle,Title,Vendor,Product Category,Type,Tags,Option1 Name,Option1 Value,Option2 Name,Option2 Value,Variant SKU,Variant Barcode,Image Src,Image Position,Genre (product.metafields.shopify.genre)
simple-thriller-vhs,Simple Thriller,VHS,Uncategorized,,"Rental, Thriller",Condition,Standard,Serial Number,001A,191-VHSSIM-001A,191-VHSSIM-001A,https://img/1.jpg,1,
no-genre-row,No Genre Row,VHS,Uncategorized,,Rental,Condition,Standard,Serial Number,001A,191-VHSNGR-001A,191-VHSNGR-001A,https://img/2.jpg,1,
supercycle-membership,Supercycle Membership,,,Supercycle Plan,,,,,,,,,,
already-resale-row,Already Resale,VHS,Uncategorized,,"Comedy, Floor Sale",Genre,Comedy,,,,,https://img/4.jpg,1,
split-same-format,Split Same,DVD,Uncategorized,,"Drama, Rental",Condition,Standard,Serial Number,001A,191-DVDSPL-001A,191-DVDSPL-001A,https://img/5a.jpg,1,
split-same-format,,,,,,Condition,Standard,Serial Number,002A,191-DVDSPL-002A,191-DVDSPL-002A,https://img/5b.jpg,1,
split-diff-format,Split Diff,BLU-RAY,Uncategorized,,"Action, Rental",Condition,50%,Serial Number,001A,191-BLRDIF-50-001A,191-BLRDIF-50-001A,https://img/6a.jpg,1,
split-diff-format,,,,,,Condition,Standard,Serial Number,001A,191-DVDDIF-001A,191-DVDDIF-001A,https://img/6b.jpg,1,
multi-image-title,Multi Image,VHS,Uncategorized,,"Horror, Rental",Condition,Standard,Serial Number,001A,191-VHSMUL-001A,191-VHSMUL-001A,https://img/7a.jpg,1,
multi-image-title,,,,,,,,,,,,https://img/7b.jpg,2,
multi-image-title,,,,,,,,,,,,https://img/7c.jpg,3,
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/data_cleanup/test_circaos_reformat.py` (add imports and new test classes before `if __name__ == "__main__":`):

```python
import csv
import tempfile
from pathlib import Path as _Path

from circaos_reformat import build_output, main

FIXTURE_PATH = _Path(__file__).resolve().parent / "fixtures" / "circaos_sample_export.csv"


def load_fixture():
    with open(FIXTURE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


class TestBuildOutput(unittest.TestCase):
    def setUp(self):
        self.fieldnames, self.rows = load_fixture()
        self.new_fieldnames, self.output_rows, self.review_rows = build_output(
            self.rows, self.fieldnames
        )

    def test_adds_media_format_column(self):
        self.assertIn(FORMAT_COLUMN, self.new_fieldnames)

    def test_simple_and_split_products_in_output(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        self.assertIn("simple-thriller-vhs", output_handles)
        self.assertIn("split-same-format", output_handles)
        self.assertIn("split-same-format-copy-2", output_handles)
        self.assertIn("split-diff-format-bluray", output_handles)
        self.assertIn("split-diff-format-dvd", output_handles)

    def test_multi_image_product_keeps_all_three_rows(self):
        rows = [r for r in self.output_rows if r["Handle"] == "multi-image-title"]
        self.assertEqual(len(rows), 3)

    def test_no_genre_row_excluded_and_flagged(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        self.assertNotIn("no-genre-row", output_handles)
        self.assertIn("no-genre-row", review_handles)

    def test_supercycle_and_resale_rows_excluded_entirely(self):
        output_handles = {row["Handle"] for row in self.output_rows}
        review_handles = {row["Handle"] for row in self.review_rows}
        for h in ("supercycle-membership", "already-resale-row"):
            self.assertNotIn(h, output_handles)
            self.assertNotIn(h, review_handles)


class TestMain(unittest.TestCase):
    def test_writes_output_and_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "circaos-reformatted.csv"
            review_path = Path(tmp) / "circaos-needs-review.csv"
            n_out, n_review = main(FIXTURE_PATH, output_path, review_path)

            self.assertTrue(output_path.exists())
            self.assertTrue(review_path.exists())
            self.assertEqual(n_review, 1)

            with open(output_path, newline="", encoding="utf-8") as f:
                out_rows = list(csv.DictReader(f))
            self.assertEqual(len(out_rows), n_out)

            with open(review_path, newline="", encoding="utf-8") as f:
                review_rows = list(csv.DictReader(f))
            self.assertEqual(review_rows[0]["Handle"], "no-genre-row")
```

Note: `Path` is already imported at the top of the test file from Task 1's `from pathlib import Path` line — reuse it, don't re-import.

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_output'`

- [ ] **Step 4: Add the pipeline code**

Append to `data-cleanup/circaos_reformat.py` (add `import csv` and `from pathlib import Path` at the top of the file, and add `group_rows_by_handle` to the existing `from reformat_movies import ...` line):

```python
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
        status, products, reason = transform_circaos_group(group)
        if status == "in_scope":
            for product_rows in products:
                output_rows.extend(product_rows)
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
        base / "circaos-reformatted.csv",
        base / "circaos-needs-review.csv",
    )
    print(f"Wrote {n_out} rows to circaos-reformatted.csv")
    print(f"Wrote {n_review} rows to circaos-needs-review.csv")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 tests/data_cleanup/test_circaos_reformat.py -v`
Expected: all tests PASS (37 tests)

- [ ] **Step 6: Commit**

```bash
git add data-cleanup/circaos_reformat.py tests/data_cleanup/test_circaos_reformat.py tests/data_cleanup/fixtures/circaos_sample_export.csv
git commit -m "Add CSV pipeline for CircaOS product reformat with review report"
```

---

### Task 4: Run against the real export and verify

**Files:**
- None created/modified — this task runs the script from Task 3 against the real data and manually verifies the result.

**Interfaces:**
- Consumes: `main` from `data-cleanup/circaos_reformat.py`

- [ ] **Step 1: Run the script against the real export**

Run: `python3 data-cleanup/circaos_reformat.py`
Expected output (verified during planning against the real file): `Wrote 696 rows to circaos-reformatted.csv` and `Wrote 21 rows to circaos-needs-review.csv`.

- [ ] **Step 2: Verify handle-level counts add up**

Run:

```bash
python3 -c "
import csv
with open('data-cleanup/circaos-reformatted.csv', newline='', encoding='utf-8') as f:
    output_rows = list(csv.DictReader(f))
with open('data-cleanup/circaos-needs-review.csv', newline='', encoding='utf-8') as f:
    review_rows = list(csv.DictReader(f))

output_handles = {r['Handle'] for r in output_rows}
print('total output rows (incl. extra image rows):', len(output_rows))
print('distinct output products:', len(output_handles))
print('review rows:', len(review_rows))
"
```

Expected (verified during planning): `total output rows: 696`, `distinct output products: 657`, `review rows: 21`. (657 = 671 in-scope-candidate handles − 21 review + 7 extra products from splitting the 7 multi-copy titles. 696 = 657 + 39 extra image rows from 6 of the 7 titles that have bonus images — `conan-the-barbarian` is both in the extra-image set and the review set, so its rows are fully excluded.)

- [ ] **Step 3: Spot-check the two split cases and a simple case**

Run:

```bash
python3 -c "
import csv
with open('data-cleanup/circaos-reformatted.csv', newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
by_handle = {}
for r in rows:
    by_handle.setdefault(r['Handle'], []).append(r)

for h in ['escape-clause', 'speed-racer-bluray', 'speed-racer-dvd', 'royal-tenenbaums', 'royal-tenenbaums-copy-2']:
    r = by_handle[h][0]
    print(h, '| Vendor:', r['Vendor'], '| Category:', r['Product Category'], '| Opt1:', r['Option1 Name'], '/', r['Option1 Value'], '| Barcode:', r['Variant Barcode'], '| Genre:', r['Genre (product.metafields.shopify.genre)'], '| Format:', r['Media format (product.metafields.shopify.media-format)'], '| Tags:', r['Tags'])
"
```

Expected: every row shows `Vendor: Little Movie Store`, `Category: Media > Videos`, `Opt1: Title / Default Title`, a `Tags` value ending in `CircaOS Import`, and: `speed-racer-bluray` → `Format: blu-ray`, `speed-racer-dvd` → `Format: dvd` (confirming the split correctly picked up each copy's own barcode-derived format even though both share the same original `Vendor: DVD`); `royal-tenenbaums`/`royal-tenenbaums-copy-2` → both `Format: dvd` (same format, `-copy-2` suffix used).

- [ ] **Step 4: Spot-check the review report**

Run: `cat data-cleanup/circaos-needs-review.csv` and confirm all 21 rows have reason `no genre-like tag found in Tags`, and manually cross-check 2-3 handles against `grep <handle> data-cleanup/current-movies-export.csv` to confirm their `Tags` field genuinely has no genre-like value (only status tags like `Rental`/`Floor Sale`, or no tags at all).

- [ ] **Step 5: No commit this step**

`circaos-reformatted.csv` and `circaos-needs-review.csv` live in `data-cleanup/`, which is untracked in git. Leave them untracked, matching the existing pattern. Nothing to commit for this task.

---

### Task 5: Manual trial import on the dev store (verification, not code)

This task has no code changes. It mirrors Task 5 of the first reformat pass — de-risking the actual Shopify import before the user commits to re-uploading all 657 products, since this batch additionally involves splitting products into new handles (not just updating existing ones in place).

- [ ] **Step 1: Build a tiny trial CSV**

Copy the header row plus a handful of representative product row-groups from `data-cleanup/circaos-reformatted.csv` into `data-cleanup/circaos-trial-import.csv` — include at least: one simple single-copy product, both halves of `speed-racer` (the different-format split), and both halves of `royal-tenenbaums` (the same-format split).

- [ ] **Step 2: Import the trial CSV to the dev store**

In the Shopify admin for `lms-sandbox-lutsfahz.myshopify.com` (per `CLAUDE.md`, the default dev store — never production for this): Products → Import → upload `data-cleanup/circaos-trial-import.csv`.

Note: unlike the first pass's trial (which only updated existing products by handle), `speed-racer-bluray`/`speed-racer-dvd`/`royal-tenenbaums-copy-2` are **new handles** that don't exist yet in Shopify — this import will create new products for those, and will need "Overwrite existing products that have the same handle" for the ones that do match existing handles (`royal-tenenbaums`, and whatever simple product you pick).

- [ ] **Step 3: Confirm the update took effect correctly**

Open the trial products in the admin. Confirm: the simple product updated in place correctly (same checks as the first pass — Vendor, Category, single Default Title variant, metafields, tags including `CircaOS Import`, nothing else changed). Confirm the two `speed-racer-*` products were created as two separate, independent products with the correct format each. Confirm `royal-tenenbaums` (original handle) still has its own barcode/data and `royal-tenenbaums-copy-2` exists as a fully separate product with the second copy's barcode.

- [ ] **Step 4: Decide on the full import**

If the trial looks correct, the user can import the full `data-cleanup/circaos-reformatted.csv` the same way. If anything looks wrong — especially around the split products, since that's the new behavior this pass introduces — report back with specifics (which field, which product) so the script can be fixed before a full run.
