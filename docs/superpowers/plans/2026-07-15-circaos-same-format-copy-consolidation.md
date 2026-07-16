# CircaOS same-format copy consolidation — Implementation Plan (LOW PRIORITY / future imports)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CircaOS reformat emit **one product per movie+format** (with an inventory quantity), instead of one product per physical copy, and emit a per-copy **items manifest** that seeds Supercycle item creation.

**Architecture:** Pure-Python CSV transform in `data-cleanup/circaos_reformat.py`. A shared iterator (`iter_format_products`) becomes the single source of the handle/format grouping, consumed by both the product transform and a new items-manifest builder — so the two never drift. `transform_circaos_group`'s public return shape is left unchanged to avoid churn across its 9 call sites.

**Tech Stack:** Python 3.13 stdlib (`csv`, `unittest`). Tests run with `python3 -m unittest`. No pytest.

## Why this is LOW PRIORITY

The live catalogue (`export-7.15-9.55.csv`) has **zero** `-copy-N` products and only 6 same-title+format collisions (handled by the manual cleanup checklist). The current pipeline's same-format `-copy-N` fan-out **never fired on real data**. This plan hardens the pipeline for a *future* bulk import that contains genuine same-format multiples; it changes nothing about today's catalogue. Do the manual `2026-07-15-duplicate-product-cleanup-checklist.md` and A3 first; this can wait.

## Global Constraints

- **Preserve existing behavior for:** single-copy products (unchanged handle, keeps its barcode), different-format splits (still one product each, format-suffixed handle), review/skip classification, and extra-image-row pass-through onto the first product only.
- **Only same-format multiples change:** they collapse to one product with `Variant Inventory Qty` = copy count and a blanked variant barcode (the per-copy barcodes move to the items manifest).
- **Items manifest Handle must equal the product Handle** it belongs to (a later step joins Handle → Variant Shopify ID for the Supercycle items CSV). Both derive it from the same `handle_for_format` helper — do not duplicate that logic.
- **Test cycle:** `python3 -m unittest tests.data_cleanup.test_circaos_reformat` (currently **37 tests green**). No new offense may be introduced; changed tests must be updated in the same task.
- Run all commands from repo root `/Users/liamparis/web-projects/personal/LMS-sandbox`.

---

### Task 1: Collapse same-format copies into one product with a quantity

**Files:**
- Modify: `data-cleanup/circaos_reformat.py` (replace `build_product_handles` at lines 90-105; rewrite the loop in `transform_circaos_group` at lines 133-152)
- Test: `tests/data_cleanup/test_circaos_reformat.py` (update `test_split_same_format_produces_two_products`)

**Interfaces:**
- Produces:
  - `group_real_rows_by_format(real_rows, vendor, tags_str) -> list[tuple[str|None, list[dict]]]` — format (metaobject handle or None) → its rows, first-seen order.
  - `handle_for_format(base_handle: str, fmt: str|None, multi_format: bool) -> str` — `base_handle` when single-format, else `f"{base_handle}-{FORMAT_HANDLE_SUFFIX.get(fmt,'copy')}"`.
  - `iter_format_products(rows) -> Iterator[tuple[str, str|None, list[dict]]]` — yields `(handle, fmt, group_rows)` per output product for an in-scope Condition group; yields nothing otherwise.
  - `transform_circaos_group` unchanged signature `(status, products, reason)`; each product now sets `Variant Inventory Qty` and blanks `Variant Barcode` when >1 copy.

- [ ] **Step 1: Update the failing test to the new expectation**

In `tests/data_cleanup/test_circaos_reformat.py`, replace `test_split_same_format_produces_two_products` with:

```python
    def test_split_same_format_produces_one_product_with_qty(self):
        rows = [
            make_row(Handle="split-same", Vendor="DVD", Tags="Drama, Rental",
                     **{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(Handle="split-same", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        status, products, reason = transform_circaos_group(rows)
        self.assertEqual(status, "in_scope")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0][0]["Handle"], "split-same")
        self.assertEqual(products[0][0][FORMAT_COLUMN], "dvd")
        self.assertEqual(products[0][0]["Variant Inventory Qty"], "2")
        self.assertEqual(products[0][0]["Variant Barcode"], "")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m unittest tests.data_cleanup.test_circaos_reformat.TestTransformCircaosGroup.test_split_same_format_produces_one_product_with_qty -v`
Expected: FAIL — current code returns 2 products (`split-same` + `split-same-copy-2`).

- [ ] **Step 3: Replace `build_product_handles` with format-grouping helpers**

In `data-cleanup/circaos_reformat.py`, delete `build_product_handles` (lines 90-105) and add:

```python
def group_real_rows_by_format(
    real_rows: list[dict], vendor: str, tags_str: str
) -> list[tuple[str | None, list[dict]]]:
    """Group real variant rows by resolved media-format, first-seen order."""
    groups: dict[str | None, list[dict]] = {}
    order: list[str | None] = []
    for r in real_rows:
        fmt = resolve_circaos_format(vendor, tags_str, r["Variant Barcode"].strip())
        if fmt not in groups:
            groups[fmt] = []
            order.append(fmt)
        groups[fmt].append(r)
    return [(fmt, groups[fmt]) for fmt in order]


def handle_for_format(base_handle: str, fmt: str | None, multi_format: bool) -> str:
    if not multi_format:
        return base_handle
    return f"{base_handle}-{FORMAT_HANDLE_SUFFIX.get(fmt, 'copy')}"


def iter_format_products(rows: list[dict]):
    """Yield (handle, fmt, group_rows) for each output product of an in-scope
    Condition group. Yields nothing for review/skip groups. Single source of
    the handle/format grouping shared by transform_circaos_group and the
    items manifest builder."""
    first = rows[0]
    status, _ = classify_circaos_row(first)
    if status != "in_scope":
        return
    vendor = first["Vendor"].strip()
    tags_str = first["Tags"]
    real_rows = [r for r in rows if r["Option1 Value"].strip()]
    fmt_groups = group_real_rows_by_format(real_rows, vendor, tags_str)
    multi_format = len(fmt_groups) > 1
    base_handle = first["Handle"]
    for fmt, group_rows in fmt_groups:
        yield handle_for_format(base_handle, fmt, multi_format), fmt, group_rows
```

- [ ] **Step 4: Rewrite the product loop in `transform_circaos_group`**

Replace the body from `real_rows = ...` through `return "in_scope", products, None` (lines 128-154) with:

```python
    real_rows = [r for r in rows if r["Option1 Value"].strip()]
    extra_image_rows = [r for r in rows if not r["Option1 Value"].strip()]

    products = []
    for i, (new_handle, fmt, group_rows) in enumerate(iter_format_products(rows)):
        real_row = group_rows[0]
        copy_count = len(group_rows)
        new_row = dict(real_row)
        new_row["Handle"] = new_handle
        new_row["Vendor"] = FIXED_VENDOR
        new_row["Product Category"] = FIXED_CATEGORY
        new_row["Option1 Name"] = "Title"
        new_row["Option1 Value"] = "Default Title"
        new_row["Option2 Name"] = ""
        new_row["Option2 Value"] = ""
        new_row["Variant SKU"] = ""
        new_row["Variant Inventory Qty"] = str(copy_count)
        if copy_count > 1:
            new_row["Variant Barcode"] = ""
        new_row[GENRE_COLUMN] = genre or ""
        new_row[FORMAT_COLUMN] = fmt or ""
        new_row["Tags"] = new_tags

        product_rows = [new_row]
        if i == 0:
            product_rows += [dict(r) for r in extra_image_rows]
        products.append(product_rows)

    return "in_scope", products, None
```

(The `vendor`, `tags_str`, `genre`, `new_tags` assignments above this block at lines 123-126 are unchanged.)

- [ ] **Step 5: Run the full circaos test module**

Run: `python3 -m unittest tests.data_cleanup.test_circaos_reformat -v`
Expected: PASS. `test_split_different_format_produces_two_products` still passes (two format groups → `split-diff-bluray` / `split-diff-dvd`), `test_extra_image_rows_pass_through_on_first_product_only` still passes, and the new qty test passes. If `build_product_handles` is referenced by any remaining import (check the test file's import block), remove it from the import list.

- [ ] **Step 6: Run the whole data_cleanup suite (no regressions elsewhere)**

Run: `python3 -m unittest discover -s tests/data_cleanup -v`
Expected: all green (37 baseline, adjusted for the renamed test).

- [ ] **Step 7: Commit**

```bash
git add data-cleanup/circaos_reformat.py tests/data_cleanup/test_circaos_reformat.py
git commit -m "feat(data-cleanup): collapse same-format CircaOS copies into one product with quantity"
```

---

### Task 2: Emit a per-copy items manifest (Supercycle items seed)

**Files:**
- Modify: `data-cleanup/circaos_reformat.py` (add `build_items_manifest`)
- Modify: `data-cleanup/run_pipeline.py` (write the manifest CSV in `main`)
- Test: `tests/data_cleanup/test_circaos_reformat.py` (add a manifest test)

**Interfaces:**
- Consumes: `iter_format_products` (Task 1).
- Produces: `build_items_manifest(rows: list[dict]) -> list[dict]` — one row per physical copy across the whole export, keys `Handle`, `Serial`, `SKU`. `Serial` = the copy's `Variant Barcode`; `SKU` mirrors it. Handle equals the owning product's handle.

- [ ] **Step 1: Write the failing manifest test**

Add to `tests/data_cleanup/test_circaos_reformat.py` (import `build_items_manifest` in the top import block):

```python
class TestItemsManifest(unittest.TestCase):
    def test_one_row_per_copy_with_matching_handle(self):
        rows = [
            make_row(Handle="split-same", Vendor="DVD", Tags="Drama, Rental",
                     **{"Variant Barcode": "191-DVDSPL-001A"}),
            make_row(Handle="split-same", Vendor="", Tags="",
                     **{"Variant Barcode": "191-DVDSPL-002A"}),
        ]
        manifest = build_items_manifest(rows)
        self.assertEqual(len(manifest), 2)
        self.assertEqual(manifest[0], {"Handle": "split-same", "Serial": "191-DVDSPL-001A", "SKU": "191-DVDSPL-001A"})
        self.assertEqual(manifest[1], {"Handle": "split-same", "Serial": "191-DVDSPL-002A", "SKU": "191-DVDSPL-002A"})

    def test_skips_out_of_scope_groups(self):
        # review group (no genre-like tag) contributes no items
        manifest = build_items_manifest([make_row(Tags="Rental")])
        self.assertEqual(manifest, [])
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m unittest tests.data_cleanup.test_circaos_reformat.TestItemsManifest -v`
Expected: FAIL — `build_items_manifest` not defined.

- [ ] **Step 3: Implement `build_items_manifest`**

Add to `data-cleanup/circaos_reformat.py` (near `build_output`):

```python
ITEM_MANIFEST_FIELDS = ["Handle", "Serial", "SKU"]


def build_items_manifest(rows: list[dict]) -> list[dict]:
    """One manifest row per physical copy across the export, for seeding
    Supercycle items. Serial = the copy's original CircaOS barcode."""
    manifest: list[dict] = []
    for _handle, group in group_rows_by_handle(rows):
        for product_handle, _fmt, group_rows in iter_format_products(group):
            for copy_row in group_rows:
                serial = copy_row["Variant Barcode"].strip()
                manifest.append(
                    {"Handle": product_handle, "Serial": serial, "SKU": serial}
                )
    return manifest
```

- [ ] **Step 4: Run the manifest test**

Run: `python3 -m unittest tests.data_cleanup.test_circaos_reformat.TestItemsManifest -v`
Expected: PASS.

- [ ] **Step 5: Wire the manifest output into `run_pipeline.py`**

In `data-cleanup/run_pipeline.py`, import it and write the file in `main`. Add to the import at line 25:

```python
from circaos_reformat import (
    extract_genre_from_tags, resolve_circaos_format, transform_circaos_group,
    build_items_manifest, ITEM_MANIFEST_FIELDS,
)
```

Then in `main` (near the other `write_csv` calls around line 206), after loading `rows`, add:

```python
    items_manifest = build_items_manifest(rows)
    items_path = reformatted_path.parent / "supercycle_items_manifest.csv"
    write_csv(items_path, ITEM_MANIFEST_FIELDS, items_manifest)
    print(f"Wrote {len(items_manifest)} item rows to {items_path.name}")
```

(Match the exact `rows` variable name and `reformatted_path` in scope — read `main` first to confirm; if `rows` isn't in `main`'s scope, load via `load_export` as the other steps do.)

- [ ] **Step 6: Run the pipeline test + full suite**

Run: `python3 -m unittest tests.data_cleanup.test_run_pipeline tests.data_cleanup.test_circaos_reformat -v`
Expected: PASS. If `test_run_pipeline` asserts an exact set of output files, update it to include `supercycle_items_manifest.csv`.

- [ ] **Step 7: Smoke-test against the real export**

Run the pipeline over the live export and eyeball the manifest:

```bash
cd data-cleanup && python3 run_pipeline.py --input "7.15-9.55/export-7.15-9.55.csv" --outdir /tmp/lms-pipeline-smoke 2>/dev/null | tail -5
head -5 /tmp/lms-pipeline-smoke/supercycle_items_manifest.csv
```

(Confirm the exact `run_pipeline.py` CLI flags first — read its `argparse` in `main`. Adjust flag names to match.)
Expected: a manifest with one `Handle,Serial,SKU` row per rental copy; today that's ~one per rental product since there are no same-format multiples.

- [ ] **Step 8: Commit**

```bash
git add data-cleanup/circaos_reformat.py data-cleanup/run_pipeline.py tests/data_cleanup/test_circaos_reformat.py
git commit -m "feat(data-cleanup): emit Supercycle items manifest (one row per rental copy)"
```

---

## Downstream note (not in this plan)

The manifest is keyed by **Handle**, not Variant Shopify ID (which only exists after products are imported to Shopify). Turning it into a Supercycle Items CSV is a later, separate step: export products from Shopify → join Handle → Variant Shopify ID → add `Visibility=available`, `Status=processed` columns → import via Supercycle → Inventory. That join belongs with the A3 bulk-import work, not here.

## Self-review against intent

- **One product per movie+format with qty** → Task 1 (`iter_format_products` + qty). ✅
- **Different formats still split** → preserved (multi-format branch of `handle_for_format`), `test_split_different_format_produces_two_products` stays green. ✅
- **Per-copy items seed** → Task 2 (`build_items_manifest`). ✅
- **No handle drift between products and items** → both consume `iter_format_products`. ✅
- **Type consistency:** `iter_format_products` yields `(handle, fmt, group_rows)` and is consumed with that exact unpacking in both `transform_circaos_group` and `build_items_manifest`. ✅
- **Placeholder scan:** Steps 5/7 of Task 2 say "confirm exact variable/flag names by reading `main`" — that's a real safety instruction (the pipeline's `main` wasn't fully read here), not a code placeholder; the code to add is complete. ✅
