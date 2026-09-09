# Client Upload Template Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a two-tab Google Sheet that lets the client import canonical movie products into Shopify unaided, and remove the two dependencies that would otherwise require a developer after every upload.

**Architecture:** The client types into 10 columns on tab 1. Tab 2 holds a single array formula that emits the exact 17-column Shopify import CSV. A Python module mirrors that formula so it can be tested against the existing `formatting-scripts/` pipeline and so an expected-output fixture can be regenerated. Separately, the movie product template becomes the theme default (removing the post-import script step) and the format whitelist becomes a theme setting (removing a Liquid edit per new format).

**Tech Stack:** Google Sheets (`LET` / `LAMBDA` / `MAP` / `VSTACK`), Python 3 standard library (no venv, no install), Shopify product-CSV import, Shopify Admin GraphQL via `shopify store execute`, Liquid.

**Spec:** `docs/superpowers/specs/2026-09-09-client-upload-template-rebuild-design.md`

## Global Constraints

- **Production is the working store** (`p0wkgv-wy.myshopify.com`, live theme `166751961338`) per the TEMPORARY block in `CLAUDE.md`. "Push"/"deploy" means production. **Always `shopify theme pull` before any push** — the client edits live there.
- **The acceptance import runs on the DEV store** (`lms-sandbox-lutsfahz.myshopify.com`) because it creates throwaway products. Never import test products into production.
- **The import tab emits exactly the 17 columns of `formatting-scripts/columns.py:TEMPLATE_COLUMNS`, in that order.** Do not add, remove or reorder.
- **Genre metafield delimiter is `"; "`** (semicolon + space), values are bare metaobject handles — not GIDs, not a JSON array.
- **13 genres, 6 formats.** Genres and their handles come from `formatting-scripts/taxonomy.py:GENRES`; formats from `taxonomy.py:FORMATS` (`VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`).
- **Media format lives in `Vendor`**, never in `shopify.media-format`.
- **Rental rows carry `Variant Price` = `0`.** Floor Sale rows carry a real price.
- **One row = one physical copy = one product.** `Variant Inventory Qty` is always `1`.
- **`Variant Inventory Tracker` / `Policy` / `Fulfillment Service` always ship together.** A blank tracker means inventory is untracked, which makes `product.available` permanently true and the out-of-stock state in `sections/main-movie.liquid` unreachable.
- **Never create the `supercycle` metafield namespace** — it is app-reserved.
- **No dynamic-checkout / express-checkout path may be reachable from a movie PDP.** This is what Fix A protects.
- **Tests are standard library only**, run via `python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py"`.

---

### Task 1: The sheet transform module

Mirrors the tab-2 array formula in Python so the transform can be tested against the pipeline and the expected-output fixture regenerated. It is a specification held in executable form — `run.py` does not import it.

**Files:**
- Create: `formatting-scripts/sheet_transform.py`
- Test: `tests/formatting_scripts/test_sheet_transform.py`

**Interfaces:**
- Consumes: `columns.TEMPLATE_COLUMNS`, `columns.FIXED_VALUES`, `columns.GENRE_METAFIELD`, `handles.HandleAllocator`, `handles.derive_handle`, `taxonomy.genre_handle`.
- Produces: `FILL_COLUMNS: list[str]` (the 10 tab-1 headers, in order), `fill_row_to_import_row(row: dict, allocator: HandleAllocator) -> dict`, and `fill_rows_to_import_rows(rows: list[dict]) -> list[dict]`. Tasks 2 and 4 consume all three.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_sheet_transform.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "formatting-scripts"))

from columns import FORMATTED_TAG, GENRE_METAFIELD, TEMPLATE_COLUMNS
from normalize import normalize_rows
from sheet_transform import FILL_COLUMNS, fill_rows_to_import_rows

RENTAL = {
    "Title": "Rushmore",
    "Format": "VHS",
    "Type": "Rental",
    "Genre 1": "Comedy",
    "Genre 2": "",
    "Genre 3": "",
    "Price": "",
    "Description": "A precocious student falls for a teacher at Rushmore Academy.",
    "Image URL": "https://example.com/posters/rushmore.jpg",
    "Extra tags": "",
}

FLOOR_SALE = {
    "Title": "Little Shop of Horrors",
    "Format": "Blu-Ray",
    "Type": "Floor Sale",
    "Genre 1": "Musical",
    "Genre 2": "Comedy",
    "Genre 3": "Horror",
    "Price": "19.99",
    "Description": "A flower-shop worker discovers a blood-hungry plant.",
    "Image URL": "",
    "Extra tags": "Criterion Collection",
}


class TestFillColumns(unittest.TestCase):
    def test_ten_columns_in_order(self):
        self.assertEqual(FILL_COLUMNS, [
            "Title", "Format", "Type", "Genre 1", "Genre 2", "Genre 3",
            "Price", "Description", "Image URL", "Extra tags",
        ])


class TestTransform(unittest.TestCase):
    def test_emits_exactly_the_template_columns(self):
        out = fill_rows_to_import_rows([RENTAL])[0]
        self.assertEqual(list(out), TEMPLATE_COLUMNS)

    def test_rental_row(self):
        out = fill_rows_to_import_rows([RENTAL])[0]
        self.assertEqual(out["Handle"], "rushmore-vhs-rental")
        self.assertEqual(out["Vendor"], "VHS")
        self.assertEqual(out["Product Category"], "Media > Videos")
        self.assertEqual(out["Status"], "Active")
        self.assertEqual(out["Option1 Name"], "Genre")
        self.assertEqual(out["Option1 Value"], "Comedy")
        self.assertEqual(out["Variant Inventory Tracker"], "shopify")
        self.assertEqual(out["Variant Inventory Qty"], "1")
        self.assertEqual(out["Variant Inventory Policy"], "deny")
        self.assertEqual(out["Variant Fulfillment Service"], "manual")
        self.assertEqual(out["Variant Price"], "0")
        self.assertEqual(out["Tags"], "Rental, VHS, Comedy")
        self.assertEqual(out["Image Alt Text"], "Rushmore poster")
        self.assertEqual(out[GENRE_METAFIELD], "comedy")

    def test_floor_sale_row_multi_genre_and_extra_tag(self):
        out = fill_rows_to_import_rows([FLOOR_SALE])[0]
        self.assertEqual(out["Handle"], "little-shop-of-horrors-blu-ray-floor-sale")
        self.assertEqual(out["Variant Price"], "19.99")
        self.assertEqual(
            out["Tags"],
            "Floor Sale, Blu-Ray, Musical, Comedy, Horror, Criterion Collection",
        )
        self.assertEqual(out[GENRE_METAFIELD], "musical; comedy; horror")

    def test_blank_image_gives_blank_alt_text(self):
        out = fill_rows_to_import_rows([FLOOR_SALE])[0]
        self.assertEqual(out["Image Src"], "")
        self.assertEqual(out["Image Alt Text"], "")

    def test_repeated_title_and_format_get_suffixed_handles(self):
        rows = fill_rows_to_import_rows([RENTAL, dict(RENTAL), dict(RENTAL)])
        self.assertEqual(
            [r["Handle"] for r in rows],
            ["rushmore-vhs-rental", "rushmore-vhs-rental-2", "rushmore-vhs-rental-3"],
        )

    def test_apostrophes_are_deleted_not_hyphenated(self):
        row = dict(RENTAL, Title="The Monkey's Uncle")
        out = fill_rows_to_import_rows([row])[0]
        self.assertEqual(out["Handle"], "the-monkeys-uncle-vhs-rental")


class TestAgreesWithPipeline(unittest.TestCase):
    """The sheet's output is already canonical, so a pipeline pass over it
    must change nothing except appending the Formatted tag."""

    def test_pipeline_pass_is_a_no_op_apart_from_the_formatted_tag(self):
        sheet_rows = fill_rows_to_import_rows([RENTAL, FLOOR_SALE])
        clean, issues = normalize_rows([dict(r) for r in sheet_rows], "template")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), len(sheet_rows))
        for produced, expected in zip(clean, sheet_rows):
            self.assertEqual(
                produced["Tags"], expected["Tags"] + ", " + FORMATTED_TAG
            )
            for column in TEMPLATE_COLUMNS:
                if column == "Tags":
                    continue
                self.assertEqual(
                    produced[column], expected[column], f"column {column!r} differs"
                )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 -m unittest tests.formatting_scripts.test_sheet_transform -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'sheet_transform'`.

- [ ] **Step 3: Write the implementation**

Create `formatting-scripts/sheet_transform.py`:

```python
"""Python mirror of the client sheet's tab-2 array formula.

The sheet is the deliverable; this module exists so the transform it encodes
can be tested against normalize.py and so the expected-output fixture can be
regenerated when the taxonomy changes. run.py does not import it.

Kept deliberately literal — it mirrors what the spreadsheet formula does,
including the fact that the sheet trusts its own dropdowns and performs no
alias resolution. A value the dropdowns cannot produce is passed through
unchanged rather than corrected, exactly as the formula would.
"""

from columns import FIXED_VALUES, GENRE_METAFIELD, TEMPLATE_COLUMNS
from handles import HandleAllocator, derive_handle
from taxonomy import genre_handle

FILL_COLUMNS = [
    "Title",
    "Format",
    "Type",
    "Genre 1",
    "Genre 2",
    "Genre 3",
    "Price",
    "Description",
    "Image URL",
    "Extra tags",
]


def _cell(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _extra_tags(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def fill_row_to_import_row(row: dict, allocator: HandleAllocator) -> dict:
    """One tab-1 row -> one tab-2 row, in TEMPLATE_COLUMNS order."""
    title = _cell(row, "Title")
    media_format = _cell(row, "Format")
    product_type = _cell(row, "Type")
    genres = [g for g in (_cell(row, f"Genre {n}") for n in (1, 2, 3)) if g]
    image = _cell(row, "Image URL")

    out = {column: "" for column in TEMPLATE_COLUMNS}
    out.update(FIXED_VALUES)
    out["Status"] = "Active"

    out["Handle"] = allocator.allocate(
        derive_handle(title, media_format, product_type)
    )
    out["Title"] = title
    out["Body (HTML)"] = row.get("Description") or ""
    out["Vendor"] = media_format
    out["Tags"] = ", ".join(
        [t for t in [product_type, media_format] if t]
        + genres
        + _extra_tags(row.get("Extra tags"))
    )
    out["Option1 Value"] = genres[0] if genres else ""
    out["Variant Price"] = "0" if product_type == "Rental" else _cell(row, "Price")
    out["Image Src"] = image
    out["Image Alt Text"] = f"{title} poster" if image else ""
    out[GENRE_METAFIELD] = "; ".join(
        handle for handle in (genre_handle(g) for g in genres) if handle
    )
    return out


def fill_rows_to_import_rows(rows: list[dict]) -> list[dict]:
    """Every tab-1 row, sharing one allocator so repeats get -2 / -3."""
    allocator = HandleAllocator()
    return [fill_row_to_import_row(row, allocator) for row in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 -m unittest tests.formatting_scripts.test_sheet_transform -v
```

Expected: PASS, 8 tests.

- [ ] **Step 5: Run the whole suite to confirm nothing regressed**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 -m unittest discover -s tests/formatting_scripts -p "test_*.py" 2>&1 | tail -5
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add formatting-scripts/sheet_transform.py tests/formatting_scripts/test_sheet_transform.py
git commit -m "feat: sheet transform module mirroring the tab-2 array formula"
```

---

### Task 2: Scaffold CSV and expected-output fixture

**Files:**
- Create: `formatting-scripts/client-template/client-upload-template.csv`
- Create: `formatting-scripts/client-template/client-upload-template.expected.csv`
- Create: `formatting-scripts/client-template/generate_expected.py`
- Test: `tests/formatting_scripts/test_client_template_files.py`

**Interfaces:**
- Consumes: `sheet_transform.FILL_COLUMNS`, `sheet_transform.fill_rows_to_import_rows` (Task 1).
- Produces: the two CSVs. `client-upload-template.csv` is what the client imports into Google Sheets; `client-upload-template.expected.csv` is the cell-for-cell answer key the manual sheet-build pass in Task 5 checks tab 2 against.

- [ ] **Step 1: Write the failing test**

Create `tests/formatting_scripts/test_client_template_files.py`:

```python
import csv
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "formatting-scripts"))

from columns import TEMPLATE_COLUMNS
from sheet_transform import FILL_COLUMNS, fill_rows_to_import_rows

TEMPLATE_DIR = os.path.join(ROOT, "formatting-scripts", "client-template")
FILL_CSV = os.path.join(TEMPLATE_DIR, "client-upload-template.csv")
EXPECTED_CSV = os.path.join(TEMPLATE_DIR, "client-upload-template.expected.csv")


def _read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class TestScaffold(unittest.TestCase):
    def test_fill_csv_header_matches_fill_columns(self):
        with open(FILL_CSV, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, FILL_COLUMNS)

    def test_fill_csv_has_one_rental_and_one_floor_sale_example(self):
        rows = _read(FILL_CSV)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(r["Type"] for r in rows), ["Floor Sale", "Rental"]
        )

    def test_expected_csv_header_matches_template_columns(self):
        with open(EXPECTED_CSV, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, TEMPLATE_COLUMNS)

    def test_expected_csv_is_what_the_transform_produces(self):
        produced = fill_rows_to_import_rows(_read(FILL_CSV))
        self.assertEqual(_read(EXPECTED_CSV), produced)


class TestGenerator(unittest.TestCase):
    def test_generator_is_idempotent(self):
        before = open(EXPECTED_CSV, encoding="utf-8").read()
        subprocess.run(
            [sys.executable, os.path.join(TEMPLATE_DIR, "generate_expected.py")],
            check=True,
            cwd=ROOT,
        )
        self.assertEqual(open(EXPECTED_CSV, encoding="utf-8").read(), before)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 -m unittest tests.formatting_scripts.test_client_template_files -v
```

Expected: FAIL — `FileNotFoundError` on `client-upload-template.csv`.

- [ ] **Step 3: Write the scaffold CSV**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
mkdir -p formatting-scripts/client-template
cat > formatting-scripts/client-template/client-upload-template.csv <<'CSV'
Title,Format,Type,Genre 1,Genre 2,Genre 3,Price,Description,Image URL,Extra tags
Rushmore,VHS,Rental,Comedy,,,,"A precocious student falls for a teacher at Rushmore Academy, and into rivalry with a gruff industrialist for her affection.",https://example.com/posters/rushmore.jpg,
Little Shop of Horrors,Blu-Ray,Floor Sale,Musical,Comedy,Horror,19.99,"A meek flower-shop worker discovers a mysterious, blood-hungry plant that promises fame and fortune at a monstrous price.",https://example.com/posters/little-shop-of-horrors.jpg,Criterion Collection
CSV
```

- [ ] **Step 4: Write the generator**

Create `formatting-scripts/client-template/generate_expected.py`:

```python
#!/usr/bin/env python3
"""Regenerate client-upload-template.expected.csv from the scaffold.

Run this after any taxonomy change, then re-run the test suite. The
expected file is the answer key the manual sheet-build pass checks the
spreadsheet's tab 2 against, cell for cell.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from columns import TEMPLATE_COLUMNS
from sheet_transform import fill_rows_to_import_rows

FILL_CSV = os.path.join(HERE, "client-upload-template.csv")
EXPECTED_CSV = os.path.join(HERE, "client-upload-template.expected.csv")


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

- [ ] **Step 5: Generate the expected CSV**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 formatting-scripts/client-template/generate_expected.py
```

Expected: `wrote .../client-upload-template.expected.csv (2 rows)`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 -m unittest tests.formatting_scripts.test_client_template_files -v
```

Expected: PASS, 5 tests.

- [ ] **Step 7: Commit**

```bash
git add formatting-scripts/client-template/ tests/formatting_scripts/test_client_template_files.py
git commit -m "feat: client upload scaffold CSV and expected-output fixture"
```

---

### Task 3: The tab-2 array formula

**Files:**
- Create: `formatting-scripts/client-template/import-tab-formula.txt`

**Interfaces:**
- Consumes: the column order of `TEMPLATE_COLUMNS` and the tab-1 layout from Task 2.
- Produces: the formula text the guide (Task 4) tells the client to paste, and which the manual pass in Task 5 verifies against `client-upload-template.expected.csv`.

This task has no automated test — Google Sheets formulas cannot be executed from here. Its correctness gate is Task 5.

- [ ] **Step 1: Write the formula file**

Create `formatting-scripts/client-template/import-tab-formula.txt`:

```
LITTLE MOVIE STORE — upload sheet, tab 2 ("Shopify import")

Paste the formula below into cell A1 of tab 2. Nothing else goes on that
tab. It reads tab 1 ("Add movies") and emits the header row plus one row
per filled-in movie — it grows and shrinks on its own, so there is never
anything to drag down.

Tab 1 columns, in order (A-J):
  A Title   B Format   C Type   D Genre 1   E Genre 2   F Genre 3
  G Price   H Description   I Image URL   J Extra tags

Tab 3 is named `mappings` and holds ONLY this table, starting in A1:

  Comedy            comedy
  Action            action
  Drama             drama
  Kids & Family     kids-family
  Sci-Fi            sci-fi
  Thriller          thriller
  Horror            horror
  Romantic Comedy   romantic-comedy
  Musical           musical
  Fantasy           fantasy
  Documentary       documentary
  Foreign           foreign
  Holiday           holiday

------------------------------------------------------------------
PASTE INTO TAB 2, CELL A1:
------------------------------------------------------------------

=LET(
  raw,     IFERROR(FILTER('Add movies'!A2:J, 'Add movies'!A2:A<>""), ""),
  empty,   COLUMNS(raw) = 1,
  src,     IF(empty, {"","","","","","","","","",""}, raw),
  n,       IF(empty, 0, ROWS(src)),
  title,   INDEX(src,,1),
  fmt,     INDEX(src,,2),
  typ,     INDEX(src,,3),
  g1,      INDEX(src,,4),
  g2,      INDEX(src,,5),
  g3,      INDEX(src,,6),
  price,   INDEX(src,,7),
  descr,   INDEX(src,,8),
  img,     INDEX(src,,9),
  extra,   INDEX(src,,10),
  slug,    LAMBDA(t, REGEXREPLACE(REGEXREPLACE(REGEXREPLACE(LOWER(TRIM(TO_TEXT(t))), "['’]", ""), "[^a-z0-9]+", "-"), "^-+|-+$", "")),
  gh,      LAMBDA(g, IF(g="", "", IFERROR(VLOOKUP(g, mappings!$A:$B, 2, FALSE), ""))),
  base,    MAP(title, fmt, typ, LAMBDA(t, f, y, slug(t) & "-" & slug(f) & "-" & slug(y))),
  handle,  MAP(SEQUENCE(n), LAMBDA(i, LET(b, INDEX(base, i), k, COUNTIF(ARRAY_CONSTRAIN(base, i, 1), b), IF(k = 1, b, b & "-" & k)))),
  konst,   LAMBDA(v, MAP(title, LAMBDA(x, v))),
  tags,    MAP(typ, fmt, g1, g2, g3, extra, LAMBDA(y, f, a, b, c, e, TEXTJOIN(", ", TRUE, y, f, a, b, c, e))),
  priceo,  MAP(typ, price, LAMBDA(y, p, IF(y = "Rental", "0", TO_TEXT(p)))),
  alt,     MAP(title, img, LAMBDA(t, i, IF(i = "", "", t & " poster"))),
  genres,  MAP(g1, g2, g3, LAMBDA(a, b, c, TEXTJOIN("; ", TRUE, gh(a), gh(b), gh(c)))),
  o1,      MAP(g1, g2, g3, LAMBDA(a, b, c, IF(a <> "", a, IF(b <> "", b, c)))),
  header,  {"Handle","Title","Body (HTML)","Vendor","Product Category","Tags","Status","Option1 Name","Option1 Value","Variant Inventory Tracker","Variant Inventory Qty","Variant Inventory Policy","Variant Fulfillment Service","Variant Price","Image Src","Image Alt Text","Genre (product.metafields.shopify.genre)"},
  body,    HSTACK(handle, title, descr, fmt, konst("Media > Videos"), tags, konst("Active"), konst("Genre"), o1, konst("shopify"), konst("1"), konst("deny"), konst("manual"), priceo, img, alt, genres),
  IF(n = 0, header, VSTACK(header, body))
)

------------------------------------------------------------------
NOTES FOR WHOEVER BUILDS THE SHEET
------------------------------------------------------------------

* The 17 output columns and their order are fixed — they are the contract
  in formatting-scripts/columns.py:TEMPLATE_COLUMNS. Do not add, remove or
  reorder them.

* `handle` is the only non-trivial part. COUNTIF over ARRAY_CONSTRAIN gives
  each row a count of how many earlier rows (inclusive) share its base
  handle, so the first Rushmore VHS rental is `rushmore-vhs-rental` and the
  next two are `-2` and `-3`. It is O(n^2); if a 200+ row batch feels slow,
  replace `base` and `handle` with two helper columns in tab 2 columns S and
  T and reference those instead.

* `slug` deletes apostrophes and collapses every other non-alphanumeric run
  to a single hyphen, so `The Monkey's Uncle` becomes `the-monkeys-uncle`
  and `Amélie` becomes `am-lie`. That matches
  formatting-scripts/handles.py:slugify exactly. Accented titles are fixed
  by typing over that one cell.

* `konst` exists because a bare string in HSTACK would not repeat down the
  rows. It maps the constant over `title` purely to get an array of the
  right height.

* `TO_TEXT` around the price stops Sheets from formatting 19.99 as a locale
  number with a comma decimal separator on export.
```

- [ ] **Step 2: Sanity-check the formula's column count against the contract**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 - <<'PY'
import re, sys
sys.path.insert(0, "formatting-scripts")
from columns import TEMPLATE_COLUMNS

text = open("formatting-scripts/client-template/import-tab-formula.txt", encoding="utf-8").read()

header_line = re.search(r'header,\s*\{(.+?)\},', text, re.S).group(1)
header = re.findall(r'"((?:[^"]|"")*)"', header_line)
assert header == TEMPLATE_COLUMNS, (
    "formula header does not match TEMPLATE_COLUMNS\n"
    f"formula:  {header}\ncontract: {TEMPLATE_COLUMNS}"
)

body = re.search(r'body,\s*HSTACK\((.+?)\),\n', text, re.S).group(1)
depth = 0
parts = 1
for ch in body:
    if ch == "(":
        depth += 1
    elif ch == ")":
        depth -= 1
    elif ch == "," and depth == 0:
        parts += 1
assert parts == len(TEMPLATE_COLUMNS), f"HSTACK has {parts} args, expected {len(TEMPLATE_COLUMNS)}"

print(f"OK — formula header and HSTACK both carry {parts} columns, matching the contract")
PY
```

Expected: `OK — formula header and HSTACK both carry 17 columns, matching the contract`.

- [ ] **Step 3: Commit**

```bash
git add formatting-scripts/client-template/import-tab-formula.txt
git commit -m "feat: tab-2 array formula for the client upload sheet"
```

---

### Task 4: The client guide

**Files:**
- Create: `formatting-scripts/client-template/client-upload-guide.md`

**Interfaces:**
- Consumes: the fill-tab layout (Task 2) and the formula file (Task 3).
- Produces: the client-facing document. Nothing downstream depends on it.

- [ ] **Step 1: Write the guide**

Create `formatting-scripts/client-template/client-upload-guide.md` with exactly this content:

````markdown
# Little Movie Store — product upload sheet

This sheet turns a short list of movies into a file Shopify can import. You
fill in one tab; a second tab builds the import file for you.

You only ever **add** products with this sheet. Editing prices, fixing a
description or deleting a product all happen in the Shopify admin.

**Start a fresh copy of the sheet for each batch.** File → Make a copy,
delete the old rows, fill in the new ones.

---

## One-time setup

Do this once, on your master copy.

1. **Create the sheet.** In Google Sheets: File → Import → Upload
   `client-upload-template.csv` → "Replace spreadsheet". Rename the tab that
   appears to **`Add movies`**. It has the ten columns you fill in, plus two
   example rows — look at them, then delete them before your first real batch.

2. **Add the `mappings` tab.** Add a second sheet, name it exactly
   `mappings`, and paste this table starting in cell A1:

   | | |
   |---|---|
   | Comedy | comedy |
   | Action | action |
   | Drama | drama |
   | Kids & Family | kids-family |
   | Sci-Fi | sci-fi |
   | Thriller | thriller |
   | Horror | horror |
   | Romantic Comedy | romantic-comedy |
   | Musical | musical |
   | Fantasy | fantasy |
   | Documentary | documentary |
   | Foreign | foreign |
   | Holiday | holiday |

   Right-click the tab → Hide sheet. You never need to look at it again.

3. **Add the `Shopify import` tab.** Add a third sheet, name it exactly
   `Shopify import`, and paste the formula from `import-tab-formula.txt`
   into cell **A1**. Nothing else goes on this tab.

4. **Add the dropdowns** on the `Add movies` tab. Select the whole column,
   then Data → Data validation → Dropdown:

   - **Format** (column B): `VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`
   - **Type** (column C): `Rental`, `Floor Sale`
   - **Genre 1, 2, 3** (columns D, E, F): "Dropdown (from a range)" →
     `mappings!A1:A13`

That's the whole setup. From here you only ever touch the `Add movies` tab.

---

## Filling in a movie

One row per physical copy. **Three copies of the same tape means three
rows** — select the row and press Ctrl+D twice.

**Always fill in:**

| Column | What goes in it |
|---|---|
| Title | The movie title, as you'd want it on the website |
| Format | Pick from the dropdown |
| Type | `Rental` or `Floor Sale` |
| Genre 1 | Pick from the dropdown — this is the shelf genre, and it prints on the barcode label |
| Description | A sentence or two about the film |
| Image URL | A public web address for the poster image |

**Fill in when it applies:**

| Column | When |
|---|---|
| Price | Floor Sale rows only. Leave blank on rentals — they're priced by membership, not a shelf price |
| Genre 2, Genre 3 | If the film genuinely fits more than one genre. Website only; doesn't affect the label |
| Extra tags | Curation labels, comma-separated — e.g. `Criterion Collection, A24` |

Holiday is a **genre**, not an extra tag — pick it in a Genre dropdown.

Always pick from the dropdowns rather than typing. `Blu-Ray` and `BLU-RAY`
typed by hand become two separate options in the website's filters.

---

## Uploading a batch

1. Click the **`Shopify import`** tab.
2. File → Download → **Comma-separated values (.csv)**. That downloads the
   tab you're looking at — no need to select or copy anything.
3. In Shopify: **Products → Import → Add file**, choose the file you just
   downloaded, then **Import products**.
4. **Read the summary Shopify shows you.** It tells you how many products
   were *created* and how many were *updated*. On a batch of new movies it
   should be **all created and none updated**. If it says anything was
   updated, see "When a movie gets updated instead of added" below.

---

## When a movie gets updated instead of added

Every product needs its own web address, and the sheet builds one from the
title, the format and the type — `rushmore-vhs-rental`. If two copies of the
same movie are in the same batch, the sheet notices and names the second one
`rushmore-vhs-rental-2`.

What it can't see is what you uploaded **last time**. If you add another
Rushmore VHS rental in a later batch, it builds `rushmore-vhs-rental` again,
Shopify recognises that address, and **updates the existing product instead
of creating a new one** — so you end up with one product where you wanted
two, and only one barcode.

If the import summary says something was updated when you expected all new:
tell your developer which titles were in the batch. It's fixable, and it's
caught by the regular catalogue cleanup anyway — but the sooner it's known,
the less there is to untangle.

**Unusual characters:** an accented or symbol-heavy title makes an ugly web
address — `Amélie` becomes `am-lie`. It still works. If you'd rather it read
properly, type over that one cell on the `Shopify import` tab (e.g.
`amelie-dvd-rental`). The rest of the column keeps working.

---

## Two things this sheet does not do

**1. It does not make a rental rentable.**

A row marked `Rental` becomes a product on the website with the right
labels, genre and poster. It is **not** yet something a member can borrow.
Adding it to the rental system — and recording how many physical copies you
have — is a separate job done inside the Supercycle app, not in this sheet.

**Ask your developer to do this** after a batch of rentals goes up.

**2. It does not merge duplicate copies.**

Uploading the same film several times is expected and fine — those are real
separate copies. Tidying them up is a periodic job your developer runs.

---

## Adding a new format

Two steps, and the second one needs your developer:

1. Add it to the **Format** dropdown (Data → Data validation on column B).
2. Ask your developer to add it to the theme setting **Recognised media
   formats** (Online Store → Themes → Customize → Theme settings). Until
   that's done the new format won't show as a badge on the product page and
   won't appear in the website's Format filter.

## Adding a new genre

You can't, and you don't need to. The thirteen genres in the dropdown are
Shopify's own standard film-genre list — it's fixed, and it's complete. If a
film doesn't fit any of them, use the closest one and put the more specific
label in **Extra tags**.
````

- [ ] **Step 2: Verify the guide is consistent with the shipped files**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 - <<'PY'
import csv, sys
sys.path.insert(0, "formatting-scripts")
from taxonomy import FORMATS, GENRES

base = "formatting-scripts/client-template/"
guide = open(base + "client-upload-guide.md", encoding="utf-8").read()
header = next(csv.reader(open(base + "client-upload-template.csv", encoding="utf-8")))

for column in header:
    assert column in guide, f"guide never mentions the {column!r} column"
for label, handle in GENRES.items():
    assert f"| {label} | {handle} |" in guide, f"mappings table missing {label}"
for fmt in FORMATS:
    assert f"`{fmt}`" in guide, f"guide missing format {fmt}"
for phrase in ["Add movies", "mappings", "Shopify import", "Ctrl+D",
               "created", "updated", "Supercycle"]:
    assert phrase in guide, f"guide missing {phrase!r}"

print("OK — guide covers all 10 columns, 13 genres, 6 formats and the caveats")
PY
```

Expected: `OK — guide covers all 10 columns, 13 genres, 6 formats and the caveats`.

- [ ] **Step 3: Commit**

```bash
git add formatting-scripts/client-template/client-upload-guide.md
git commit -m "docs: client upload sheet guide"
```

---

### Task 5: Build the sheet and run the dev-store acceptance import

**This task is performed by a human, not an agent.** It needs a Google account and a browser. It is the gate the 2026-07-19 plan never passed.

**Files:** none created; findings recorded in this plan.

**Interfaces:**
- Consumes: all four files from Tasks 2–4.
- Produces: a verified Google Sheet and a PASS/FAIL record. Nothing downstream depends on it, but no part of this may reach the client before it passes.

- [ ] **Step 1: Build the sheet**

Follow `client-upload-guide.md` → "One-time setup", start to finish, exactly as written. Note any step where the guide is wrong or unclear — that is the point of doing it this way.

- [ ] **Step 2: Check tab 2 against the answer key**

With the two example rows from `client-upload-template.csv` in the `Add movies` tab, compare the `Shopify import` tab cell-for-cell against `client-upload-template.expected.csv`.

Every cell must match. If any differs, the formula in `import-tab-formula.txt` is wrong — fix the formula, not the expected file. The expected file is generated from the tested Python transform and is the authority.

Pay particular attention to:
- `Handle` — `rushmore-vhs-rental` and `little-shop-of-horrors-blu-ray-floor-sale`
- `Variant Price` — `0` on the rental, `19.99` (not `19,99`) on the floor sale
- `Genre (product.metafields.shopify.genre)` — `comedy` and `musical; comedy; horror`
- `Tags` — `Rental, VHS, Comedy` and `Floor Sale, Blu-Ray, Musical, Comedy, Horror, Criterion Collection`

- [ ] **Step 3: Test the duplicate-copy behaviour**

Duplicate the Rushmore row twice (Ctrl+D). Confirm tab 2 now shows
`rushmore-vhs-rental`, `rushmore-vhs-rental-2`, `rushmore-vhs-rental-3`.
Delete the two extra rows again.

- [ ] **Step 4: Check performance at realistic batch size**

Duplicate rows until the `Add movies` tab holds ~200. Confirm tab 2 still
recalculates within a few seconds. If it does not, apply the helper-column
fallback described in `import-tab-formula.txt` and re-run Step 2.

Delete the padding rows.

- [ ] **Step 5: Import into the DEV store**

Download the `Shopify import` tab as CSV.

**Confirm the store before importing — this is the dev store, not production:**
`lms-sandbox-lutsfahz.myshopify.com` → Products → Import → Add file → Import products.

- [ ] **Step 5b: Save the export as the sheet↔contract seam fixture**

This is the one artifact in the whole build that is **not** generated from
`TEMPLATE_COLUMNS`, so it is the only thing that can genuinely disagree with
it. A fixture this repo generates itself can only compare the constant
against a header built from that same constant — which is why the seam check
lives here rather than in `test_columns.py`.

Copy the CSV you just downloaded into the repo:

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
cp ~/Downloads/<the-downloaded-file>.csv \
   formatting-scripts/client-template/client-upload-template.sheet-export.csv
```

Add this test to `tests/formatting_scripts/test_client_template_files.py`:

```python
SHEET_EXPORT_CSV = os.path.join(
    TEMPLATE_DIR, "client-upload-template.sheet-export.csv"
)


class TestSheetExportSeam(unittest.TestCase):
    """The real spreadsheet's own output against the column contract.

    Unlike every other fixture here, this file is produced by Google Sheets,
    not by TEMPLATE_COLUMNS — so it can actually disagree, which is the whole
    point. If someone edits the tab-2 formula and this test fails, the formula
    drifted from the contract.
    """

    def test_sheet_export_header_matches_template_columns(self):
        with open(SHEET_EXPORT_CSV, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, TEMPLATE_COLUMNS)

    def test_sheet_export_rows_match_the_transform(self):
        self.assertEqual(_read(SHEET_EXPORT_CSV), _read(EXPECTED_CSV))
```

Run it:

```bash
python3 -m unittest tests.formatting_scripts.test_client_template_files -v
```

Expected: PASS. **A failure here means the spreadsheet formula and the Python
transform disagree** — fix the formula in `import-tab-formula.txt` and
re-export, since the Python side is the tested one.

- [ ] **Step 6: Verify both products landed**

Open each imported product in the dev admin and confirm:

| Field | Rushmore | Little Shop of Horrors |
|---|---|---|
| Handle | `rushmore-vhs-rental` | `little-shop-of-horrors-blu-ray-floor-sale` |
| Vendor | `VHS` | `Blu-Ray` |
| Product category | `Media > Videos` | `Media > Videos` |
| Variant option | `Genre` / `Comedy` | `Genre` / `Musical` |
| Price | `0.00` | `19.99` |
| Inventory | tracked, qty `1`, policy deny | tracked, qty `1`, policy deny |
| `shopify.genre` metafield | `Comedy` | `Musical`, `Comedy`, `Horror` — **three values** |
| Tags | `Rental, VHS, Comedy` | `Floor Sale, Blu-Ray, Musical, Comedy, Horror, Criterion Collection` |
| Image | loaded from the URL | loaded from the URL |
| Description | present | present |

Record PASS/FAIL per field. **If the multi-genre metafield did not land as
three values**, the `"; "` delimiter is wrong — fix `sheet_transform.py`,
regenerate the expected CSV, fix the formula, and re-run this task.

- [ ] **Step 7: Delete the test products**

Dev admin → Products → select both → Delete. They import with real handles;
leaving them pollutes the dev catalogue.

- [ ] **Step 8: Commit any corrections**

If Steps 1–6 required changes to the guide, formula, transform or fixture:

```bash
git add formatting-scripts/client-template/ formatting-scripts/sheet_transform.py
git commit -m "fix: correct upload sheet after dev-store acceptance import"
```

If nothing needed changing, skip this step.

---

### Task 6: Fix B — format whitelist becomes a theme setting

**Files:**
- Modify: `theme/lms-redesign-v4/config/settings_schema.json` (append a group)
- Modify: `theme/lms-redesign-v4/sections/main-movie.liquid:25`
- Modify: `theme/lms-redesign-v4/snippets/lms-product-card.liquid:28`

**Interfaces:**
- Produces: theme setting `settings.lms_known_formats`, a comma-separated string. Read by both Liquid files. No later task consumes it.

- [ ] **Step 1: Pull production before touching the theme**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338
git status --porcelain theme/lms-redesign-v4
```

Review anything the pull changed and commit it separately before continuing.
The client edits section settings live; a blind push would discard that work.

- [ ] **Step 2: Add the theme setting**

Append a new group to `theme/lms-redesign-v4/config/settings_schema.json`.
The file is a JSON array of groups — add this as the final element:

```json
{
  "name": "Little Movie Store",
  "settings": [
    {
      "type": "text",
      "id": "lms_known_formats",
      "label": "Recognised media formats",
      "default": "VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX",
      "info": "Comma-separated, uppercase. A product whose Vendor matches one of these shows a format badge and appears in the Format filter. Add a new format here after adding it to the upload sheet's dropdown. Leaving this blank falls back to the built-in list."
    }
  ]
}
```

Apply it with a script rather than by hand, so the file stays valid JSON:

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
python3 - <<'PY'
import json

path = "theme/lms-redesign-v4/config/settings_schema.json"
schema = json.load(open(path, encoding="utf-8"))

assert not any(
    s.get("id") == "lms_known_formats"
    for group in schema
    for s in group.get("settings", [])
), "lms_known_formats already exists"

schema.append({
    "name": "Little Movie Store",
    "settings": [{
        "type": "text",
        "id": "lms_known_formats",
        "label": "Recognised media formats",
        "default": "VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX",
        "info": (
            "Comma-separated, uppercase. A product whose Vendor matches one of "
            "these shows a format badge and appears in the Format filter. Add a "
            "new format here after adding it to the upload sheet's dropdown. "
            "Leaving this blank falls back to the built-in list."
        ),
    }],
})

with open(path, "w", encoding="utf-8") as handle:
    json.dump(schema, handle, indent=2, ensure_ascii=False)
    handle.write("\n")

print("added lms_known_formats;", len(schema), "groups total")
PY
```

Expected: `added lms_known_formats; 19 groups total`.

- [ ] **Step 3: Read the setting in `main-movie.liquid`**

Replace line 25 of `theme/lms-redesign-v4/sections/main-movie.liquid`:

```liquid
  assign known_formats = 'VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX' | split: ','
```

with:

```liquid
  # The recognised-format list is a theme setting so a new format needs no
  # code change. Falls back to the built-in list when the setting is blank,
  # so clearing it can never blank every badge on the storefront.
  assign format_setting = settings.lms_known_formats | default: 'VHS,DVD,BLU-RAY,4K,LASERDISC,BETAMAX'
  assign known_formats = format_setting | upcase | replace: ', ', ',' | split: ','
```

- [ ] **Step 4: Read the setting in `lms-product-card.liquid`**

Replace line 28 of `theme/lms-redesign-v4/snippets/lms-product-card.liquid`
with the identical five lines from Step 3.

- [ ] **Step 5: Confirm both files now read the setting and no literal remains**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox/theme/lms-redesign-v4"
grep -c "settings.lms_known_formats" sections/main-movie.liquid snippets/lms-product-card.liquid
grep -n "assign known_formats = 'VHS" sections/main-movie.liquid snippets/lms-product-card.liquid || echo "no hardcoded whitelist remains"
```

Expected: `1` for each file, then `no hardcoded whitelist remains`.

- [ ] **Step 6: Lint the theme**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme check --path theme/lms-redesign-v4 2>&1 | tail -20
```

Expected: no new offences in the two edited files. Pre-existing offences
elsewhere are not this task's problem — compare against `git stash`ing the
change if unsure.

- [ ] **Step 7: Push to production and verify**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 \
  --only config/settings_schema.json \
  --only sections/main-movie.liquid \
  --only snippets/lms-product-card.liquid \
  --allow-live
```

Then in the production admin: Online Store → Themes → Customize → Theme
settings → **Little Movie Store** → confirm "Recognised media formats" is
present and pre-filled. Load a VHS movie PDP and a collection page and
confirm the format badge still renders.

- [ ] **Step 8: Commit**

```bash
git add theme/lms-redesign-v4/config/settings_schema.json \
        theme/lms-redesign-v4/sections/main-movie.liquid \
        theme/lms-redesign-v4/snippets/lms-product-card.liquid
git commit -m "feat: recognised media formats becomes a theme setting"
```

---

### Task 7: Fix A — the template migration script

Builds the tool. It performs no mutation in this task: Tasks 8–10 run it.

**Files:**
- Create: `scripts/set-product-templates.sh`
- Modify: `scripts/set-movie-template.sh` (deprecation banner only)

**Interfaces:**
- Produces: `scripts/set-product-templates.sh <retail|clear-movie> [--apply]`.
  `retail` sets `templateSuffix = retail` on non-movie products;
  `clear-movie` clears the `movie` suffix from everything that carries it.
  Dry run unless `--apply`. Tasks 8 and 10 invoke it.

- [ ] **Step 1: Write the script**

Create `scripts/set-product-templates.sh`, modelled on the existing
`set-movie-template.sh` (same auth model, same pagination, same dry-run
default):

```bash
#!/usr/bin/env bash
# Two one-off migrations that invert the product-template default, so that
# imported movies need no post-import step ever again.
#
# WHY: Shopify's product-CSV import cannot set a template suffix. With the
# retail layout as the theme default, every imported movie landed on a page
# with a $0.00 "Buy now" button until someone ran set-movie-template.sh.
# Movies are 7,004 of 7,014 products, so the default is backwards. After this
# migration templates/product.json IS the movie layout and only the handful
# of non-movie products carry a suffix.
#
# MODES
#   retail       set templateSuffix=retail on non-movie products
#   clear-movie  clear the `movie` suffix wherever it is still set
#
# PREDICATE for `retail` — Vendor "Supercycle" OR tag "online-store". This is
# the same predicate as formatting-scripts/normalize.py:is_non_catalogue_product
# and it selects exactly the membership plans, the shirt and the bumper
# sticker. Do NOT use "vendor is not a format": six real movies carry Vendor
# "Little Movie Store" and would be misfiled onto the retail template.
#
# DRY RUN BY DEFAULT. Pass --apply to commit.
#
# Auth: uses the Shopify CLI's own session. Run once first if needed:
#   shopify store auth --store <store> --scopes write_products
#
# Usage:
#   ./scripts/set-product-templates.sh retail
#   ./scripts/set-product-templates.sh retail --apply
#   ./scripts/set-product-templates.sh clear-movie --apply
#   SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com ./scripts/set-product-templates.sh retail

set -euo pipefail
STORE="${SHOPIFY_STORE:-p0wkgv-wy.myshopify.com}"

MODE="${1:-}"
APPLY=false
if [[ "${2:-}" == "--apply" ]]; then
  APPLY=true
elif [[ -n "${2:-}" ]]; then
  echo "Unknown argument: $2 (expected --apply or nothing)" >&2
  exit 1
fi

case "$MODE" in
  retail)
    SEARCH_QUERY="vendor:Supercycle OR tag:online-store"
    TARGET_SUFFIX="retail"
    REQUIRED_TEMPLATE="templates/product.retail.json"
    ;;
  clear-movie)
    SEARCH_QUERY="template_suffix:movie"
    TARGET_SUFFIX=""
    REQUIRED_TEMPLATE="templates/product.json"
    ;;
  *)
    echo "Usage: $0 <retail|clear-movie> [--apply]" >&2
    exit 1
    ;;
esac

echo "Store: ${STORE}"
echo "Mode:  ${MODE} -> templateSuffix '${TARGET_SUFFIX}'"
$APPLY && echo "       APPLY (will modify products)" || echo "       DRY RUN (pass --apply to commit)"
echo

# --- Preflight: the live theme must contain the template we're pointing at --
THEME_Q='query Theme($f: [String!]) {
  themes(first: 1, roles: [MAIN]) {
    nodes { id name files(filenames: $f, first: 1) { nodes { filename } } }
  }
}'
THEME_VARS=$(jq -n --arg f "$REQUIRED_TEMPLATE" '{f: [$f]}')
THEME_RESP=$(shopify store execute --store "$STORE" -j -q "$THEME_Q" -v "$THEME_VARS")
THEME_NAME=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].name // empty')
HAS_TEMPLATE=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].files.nodes[0].filename // empty')

if [[ -z "$THEME_NAME" ]]; then
  echo "✗ Could not read the live theme from ${STORE}" >&2
  exit 1
fi
if [[ -z "$HAS_TEMPLATE" ]]; then
  echo "✗ Live theme '${THEME_NAME}' has no ${REQUIRED_TEMPLATE}." >&2
  echo "  Push the theme first, or these products will render a broken page." >&2
  exit 1
fi
echo "✓ Live theme '${THEME_NAME}' has ${REQUIRED_TEMPLATE}"
echo

FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q) {
    edges { cursor node { id title vendor templateSuffix } }
    pageInfo { hasNextPage }
  }
}'
SET_TEMPLATE='mutation SetTemplate($id: ID!, $suffix: String) {
  productUpdate(product: { id: $id, templateSuffix: $suffix }) {
    product { id templateSuffix }
    userErrors { field message }
  }
}'

AFTER="null"
CHANGED=0
SKIPPED=0
FAILED=0

while :; do
  VARS=$(jq -n --arg q "$SEARCH_QUERY" --argjson after "$AFTER" '{q: $q, after: $after}')
  RESP=$(shopify store execute --store "$STORE" -j -q "$FIND" -v "$VARS")
  EDGES=$(echo "$RESP" | jq -c '.products.edges[]?')
  if [[ -z "$EDGES" ]]; then break; fi

  while IFS= read -r EDGE; do
    PRODUCT_ID=$(echo "$EDGE" | jq -r '.node.id')
    TITLE=$(echo "$EDGE" | jq -r '.node.title')
    VENDOR=$(echo "$EDGE" | jq -r '.node.vendor')
    CURRENT=$(echo "$EDGE" | jq -r '.node.templateSuffix // ""')

    if [[ "$CURRENT" == "$TARGET_SUFFIX" ]]; then
      SKIPPED=$((SKIPPED + 1))
      continue
    fi

    if ! $APPLY; then
      CHANGED=$((CHANGED + 1))
      echo "  would set [${VENDOR}] ${TITLE}: '${CURRENT}' -> '${TARGET_SUFFIX}'"
      continue
    fi

    if [[ -z "$TARGET_SUFFIX" ]]; then
      SET_VARS=$(jq -n --arg id "$PRODUCT_ID" '{id: $id, suffix: null}')
    else
      SET_VARS=$(jq -n --arg id "$PRODUCT_ID" --arg suffix "$TARGET_SUFFIX" '{id: $id, suffix: $suffix}')
    fi
    SET_RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$SET_TEMPLATE" -v "$SET_VARS")
    SET_ERR=$(echo "$SET_RESP" | jq -r '.productUpdate.userErrors[0].message // empty')
    if [[ -n "$SET_ERR" ]]; then
      FAILED=$((FAILED + 1))
      echo "  ✗ ${TITLE}: ${SET_ERR}"
    else
      CHANGED=$((CHANGED + 1))
      echo "  ✓ [${VENDOR}] ${TITLE}"
    fi
  done <<< "$EDGES"

  HAS_NEXT=$(echo "$RESP" | jq -r '.products.pageInfo.hasNextPage')
  if [[ "$HAS_NEXT" != "true" ]]; then break; fi
  LAST_CURSOR=$(echo "$RESP" | jq -r '.products.edges[-1].cursor')
  AFTER=$(jq -n --arg c "$LAST_CURSOR" '$c')
done

echo
if $APPLY; then
  echo "✓ Done: ${CHANGED} changed, ${SKIPPED} already correct, ${FAILED} failed."
else
  echo "Dry run: ${CHANGED} product(s) would change, ${SKIPPED} already correct."
  echo "Re-run with --apply to commit."
fi
[[ "$FAILED" -eq 0 ]]
```

- [ ] **Step 2: Make it executable and check it parses**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
chmod +x scripts/set-product-templates.sh
bash -n scripts/set-product-templates.sh && echo "syntax OK"
./scripts/set-product-templates.sh 2>&1 | head -2
```

Expected: `syntax OK`, then the usage line and exit 1.

- [ ] **Step 3: Mark the old script deprecated**

Insert after line 2 of `scripts/set-movie-template.sh`:

```bash
# DEPRECATED (2026-09-09). The movie layout is now templates/product.json,
# the theme default, so imported movies need no suffix at all. Use
# scripts/set-product-templates.sh. Kept only as a repair tool for a store
# that has not had the template migration applied.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/set-product-templates.sh scripts/set-movie-template.sh
git commit -m "feat: product-template migration script for the default inversion"
```

---

### Task 8: Fix A migration steps 1–2 — add the retail template, move the non-movies

**Mutates production.** Each step is gated; do not batch them.

**Files:**
- Create: `theme/lms-redesign-v4/templates/product.retail.json`

**Interfaces:**
- Consumes: `scripts/set-product-templates.sh` (Task 7).
- Produces: a live `product.retail.json` and exactly four products carrying `templateSuffix = retail`. Task 9 depends on both.

- [ ] **Step 1: Pull production**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338
git status --porcelain theme/lms-redesign-v4
```

Commit anything the pull brought in before continuing.

- [ ] **Step 2: Create the retail template as a copy of today's default**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox/theme/lms-redesign-v4"
cp templates/product.json templates/product.retail.json
python3 -c "
import json,re
raw=open('templates/product.retail.json').read()
json.loads(raw[raw.index('{'):])
print('product.retail.json is valid JSON')
"
```

Expected: `product.retail.json is valid JSON`.

- [ ] **Step 3: Push ONLY the new template**

Nothing references it yet, so this changes nothing that renders.

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 \
  --only templates/product.retail.json --allow-live
```

- [ ] **Step 4: Dry-run the retail migration and check the count**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh retail
```

Expected: the preflight passes, and it lists **4 products** — two Supercycle
plan products (`Little Movie Club -- 1 Year`, `Little Movie Club`), the
shirt, and the bumper sticker.

**If it lists anything else — especially anything that looks like a film —
STOP.** The predicate is wrong for this store's current data. Do not apply.

- [ ] **Step 5: Apply**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh retail --apply
```

Expected: `✓ Done: 4 changed, 0 already correct, 0 failed.`

- [ ] **Step 6: Verify the membership page still works**

This is the step that protects online enrollment. In a browser, load the
production membership page and confirm the Membership Plans block still
renders with a working add-to-cart. Load the shirt's product page and
confirm it still shows price and add-to-cart.

**If either is broken, revert immediately:**

```bash
SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/set-product-templates.sh clear-movie --apply
```

(That clears any suffix set in error; then investigate before retrying.)

- [ ] **Step 7: Commit**

```bash
git add theme/lms-redesign-v4/templates/product.retail.json
git commit -m "feat: add product.retail.json ahead of the template default swap"
```

---

### Task 9: Fix A migration step 3 — the movie layout becomes the default

**Mutates production.** After this push, every product with no suffix renders
the movie layout.

**Files:**
- Modify: `theme/lms-redesign-v4/templates/product.json`

**Interfaces:**
- Consumes: Task 8's `product.retail.json` and the four retail-suffixed products.
- Produces: `product.json` containing the movie layout. Task 10 depends on it.

- [ ] **Step 1: Confirm the preconditions from Task 8 actually hold**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh retail
```

Expected: `Dry run: 0 product(s) would change, 4 already correct.`

**If any product would still change, Task 8 did not finish. Go back.**

- [ ] **Step 2: Replace product.json with the movie layout**

`product.movie.json` is a single section reference, so this is a small file:

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox/theme/lms-redesign-v4"
cat > templates/product.json <<'JSON'
/*
 * ------------------------------------------------------------
 * IMPORTANT: The contents of this file are auto-generated.
 *
 * This file may be updated by the Shopify admin theme editor
 * or related systems. Please exercise caution as any changes
 * made to this file may be overwritten.
 * ------------------------------------------------------------
 */
{
  "sections": {
    "main": {
      "type": "main-movie",
      "settings": {}
    }
  },
  "order": [
    "main"
  ]
}
JSON
diff <(sed '1,9d' templates/product.json) <(sed '1,9d' templates/product.movie.json) \
  && echo "product.json now matches product.movie.json"
```

Expected: `product.json now matches product.movie.json`.

- [ ] **Step 3: Push**

`product.movie.json` stays in place and unchanged, so movies still carrying
the `movie` suffix keep rendering from it. Movies without a suffix now get
the movie layout from `product.json`. The four non-movies use
`product.retail.json`. All three are correct — there is no broken window.

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 \
  --only templates/product.json --allow-live
```

- [ ] **Step 4: Verify all three template paths in a browser**

| Check | Expect |
|---|---|
| A movie that carries the `movie` suffix | read-only PDP, no buy button |
| A movie with no suffix (import one throwaway product, or clear one movie's suffix by hand in admin) | read-only PDP, no buy button |
| The membership page | plan block with working add-to-cart |
| The shirt | price and add-to-cart |

**If an unsuffixed movie shows a Buy now button, stop and roll back:**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
git checkout theme/lms-redesign-v4/templates/product.json
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 \
  --only templates/product.json --allow-live
```

- [ ] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/templates/product.json
git commit -m "feat: movie layout becomes the default product template"
```

---

### Task 10: Fix A migration steps 4–5 — clear the suffixes, retire the old template

**Mutates ~7,004 products on production.** Run it when you can watch it
finish and check the result.

**Files:**
- Delete: `theme/lms-redesign-v4/templates/product.movie.json`

**Interfaces:**
- Consumes: `scripts/set-product-templates.sh` (Task 7) and the default swap (Task 9).
- Produces: a store where no product carries the `movie` suffix and only the four non-movies carry any suffix at all. Nothing downstream depends on it.

- [ ] **Step 1: Dry-run the clear and check the count**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh clear-movie 2>&1 | tail -3
```

Expected: roughly 7,000 products would change. The exact number will differ
from the 2026-09-08 export figure — the client keeps uploading. A number in
the low thousands or higher is expected; a number in the tens means the
`template_suffix:movie` search predicate is not matching and you should stop.

- [ ] **Step 2: Apply**

This is thousands of API calls and will take a while.

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh clear-movie --apply 2>&1 | tee /tmp/clear-movie.log | tail -5
```

Expected: `✓ Done: N changed, 0 already correct, 0 failed.`

**If any failed**, re-run the same command — it is idempotent and skips
products already correct.

- [ ] **Step 3: Confirm nothing still carries the suffix**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
./scripts/set-product-templates.sh clear-movie 2>&1 | tail -2
```

Expected: `Dry run: 0 product(s) would change, 0 already correct.`

- [ ] **Step 4: Spot-check the storefront before deleting the template**

Load three movie PDPs and confirm all render read-only with no buy button.
They are now all being served by `product.json`.

- [ ] **Step 5: Delete product.movie.json**

Only now — no product references it.

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
rm theme/lms-redesign-v4/templates/product.movie.json
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 \
  --nodelete=false --allow-live
```

If `theme push` will not remove a remote file, delete
`templates/product.movie.json` in the production theme's code editor
(Online Store → Themes → ⋯ → Edit code) instead.

- [ ] **Step 6: Final verification — the whole point of Fix A**

Import one throwaway product to production via the sheet's CSV — no template
suffix, as the sheet always produces. Load its PDP.

**It must render the read-only movie template with no buy button, with no
script having been run.** That is the gap closed.

Delete the throwaway product afterwards.

- [ ] **Step 7: Commit**

```bash
git add -A theme/lms-redesign-v4/templates/
git commit -m "chore: retire product.movie.json after the template default swap"
```

---

### Task 11: Update the project docs

**Files:**
- Modify: `CLAUDE.md` (roadmap item #3, Conventions)
- Modify: `formatting-scripts/README.md` ("The loop", step 3)

**Interfaces:**
- Consumes: the outcome of every prior task. Produces nothing.

- [ ] **Step 1: Fix the pipeline README's now-wrong step 3**

`formatting-scripts/README.md` tells the operator to run
`scripts/set-movie-template.sh` after every import. After Task 10 that is
false and following it would be a no-op at best. Replace that numbered step
with:

```markdown
3. **No template step is needed.** `templates/product.json` IS the movie
   layout as of 2026-09-09, so imported movies render the read-only PDP with
   no post-import script. Only non-movie products (the membership plans, the
   shirt, the bumper sticker) carry a `retail` suffix — set with
   `scripts/set-product-templates.sh retail --apply` if you add one.
```

- [ ] **Step 2: Update the CLAUDE.md roadmap entry**

Roadmap item #3 describes the deliverable as "one-product-per-movie+format".
That contradicts the confirmed one-row-per-copy model. Replace the
parenthetical in item #3 with:

```markdown
(Rental/Floor Sale tag, `shopify.genre`, format in `Vendor`, **one product
per physical copy**). Delivered 2026-09-09 —
`formatting-scripts/client-template/`, spec
`docs/superpowers/specs/2026-09-09-client-upload-template-rebuild-design.md`.
```

- [ ] **Step 3: Add the template-default fact to Conventions**

Append to the Conventions list in `CLAUDE.md`:

```markdown
- **`templates/product.json` is the movie layout** (since 2026-09-09). Movies
  need no template suffix; the four non-movie products carry `retail`. Never
  reintroduce a buy button here — see the Supercycle integration contract.
```

- [ ] **Step 4: Verify the stale instruction is gone**

```bash
cd "/Users/liamparis/web-projects/personal/Little Movie Store/LMS-sandbox"
grep -rn "set-movie-template" formatting-scripts/README.md CLAUDE.md || echo "no stale references remain"
```

Expected: `no stale references remain`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md formatting-scripts/README.md
git commit -m "docs: record the template default swap and the delivered upload template"
```

---

## Self-review notes

**Spec coverage.** Two tabs → Tasks 2–4. Ten fill columns → Task 1 `FILL_COLUMNS`, Task 2 scaffold. Seventeen import columns in `TEMPLATE_COLUMNS` order → Task 1 test, Task 3 Step 2 check. `mappings` tab, 13 genres → Tasks 3, 4. Handle derivation and `-2`/`-3` → Task 1 tests, Task 5 Step 3. Cross-batch collision documented → Task 4 guide, "When a movie gets updated instead of added". Fix A five-step migration → Tasks 7–10, one task per gate. Fix B → Task 6. "Still needs a developer" stated plainly → Task 4 guide, "Two things this sheet does not do". Validation items 1–3 → Tasks 1, 5, and the per-step verifications in 8–10. Deliverables under `formatting-scripts/client-template/` → Tasks 2–4.

**Deliberate deviations from the spec.** The spec lists three deliverable files; this plan ships a fourth, `client-upload-template.expected.csv`, plus its generator. Without it the manual pass in Task 5 has nothing to check the formula against, and the spec's own concern — that a Python mirror can drift from the Sheets formula it mirrors — goes unaddressed. Task 11 is also not in the spec; it exists because Task 10 makes `formatting-scripts/README.md` step 3 actively wrong.

**Known gap, carried deliberately.** The Python transform and the Sheets formula are two implementations of one thing. The test suite pins the Python to the pipeline; only Task 5 Step 2 pins the formula to the Python. If someone edits the formula later without re-running Task 5, drift is undetectable from here. That is inherent to shipping a spreadsheet and is why Task 5 is a gate rather than a suggestion.

**Type consistency.** `FILL_COLUMNS`, `fill_row_to_import_row`, `fill_rows_to_import_rows` are named identically in Tasks 1, 2 and their tests. `HandleAllocator.allocate` and `derive_handle(title, media_format, product_type)` match `formatting-scripts/handles.py`. `genre_handle(label)` matches `taxonomy.py`. `GENRE_METAFIELD`, `FIXED_VALUES`, `TEMPLATE_COLUMNS`, `FORMATTED_TAG` match `columns.py`. `set-product-templates.sh <retail|clear-movie> [--apply]` is invoked with that exact signature in Tasks 8, 9 and 10.
