# Daily Libib + Shopify Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily GitHub Action in the private `paris-liam/LMS-data` repo saves both Libib Rental Library exports plus every production Shopify product and variant, in the admin product-CSV format, and commits only when something changed.

**Architecture:** A new `catalog/backup/` package in the public `LMS` repo, run through `python3 -m catalog backup --out DIR`. Libib reuses `transfer.run_browser_export` and copies the files byte-for-byte. Shopify reads everything with one Admin API bulk operation and turns each product into admin-export rows with a pure formatter. The workflow and README live in `LMS-data`, which checks out `LMS` `main` and commits the output.

**Tech Stack:** Python 3.13 (stdlib only plus Playwright 1.63.0 for Libib), `unittest`, Shopify Admin GraphQL `2026-07` (`config.SHOPIFY_API_VERSION`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-21-daily-data-backup-design.md`

## Global Constraints

- Production store: `p0wkgv-wy.myshopify.com` (`config.DEFAULT_STORE`). Dev store for checks: `lms-sandbox-lutsfahz.myshopify.com`.
- Shopify credentials: `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` through `catalog/shopify/api.py:request_token` + `make_executor`. The only mutation sent is `bulkOperationRunQuery`, which starts a read; nothing writes to Shopify or Libib.
- Libib credentials: `LIBIB_EMAIL` / `LIBIB_PASSWORD` (`config.ENV_LIBIB_EMAIL` / `ENV_LIBIB_PASSWORD`).
- Output files under `--out`: `libib/barcodes.csv`, `libib/library.csv`, `shopify/products.csv` (or `shopify/products-1.csv`, `-2`, … when over 15 MB).
- Split limit: 15 MB = `15_000_000` bytes, UTF-8, split only between handles.
- **No real store or Libib data in the `LMS` repo**, including test fixtures (synthetic only) and the reference admin exports (keep them outside both repos).
- Logs: file names and counts only, never row contents, credentials or tokens.
- No image copies; `Image Src` keeps Shopify's URL.
- Left-out metafield namespaces (not readable faithfully; listed in the README): any namespace starting with `shopify--discovery--` or `app--`, and `supercycle`.
- Schedule `0 8 * * *` (08:00 UTC) plus `workflow_dispatch`.
- Commit message: `Backup YYYY-MM-DD — libib <barcodes>/<library> rows, shopify <n> products`. A failed source is written as `libib FAILED` / `shopify FAILED`.
- Code style: match `catalog/`. Module docstrings, small functions, `CatalogError` subclasses for expected failures, `register(subparsers)` command modules.

## Review Focus

1. **A product whose image count and variant count differ** (shirt: 5 variants, 3 images; movie: 1 variant, 5 images). Rows = max(variants, images), with variant and image fields filled independently. Test: `test_rows_pair_variants_and_images_by_index` (Task 3).
2. **Descriptions with commas, quotes and newlines.** The written CSV must read back to the same `Body (HTML)`. Test: `test_written_csv_round_trips_awkward_html` (Task 4).
3. **A metafield type the formatter has no rule for** (e.g. `rating`, `dimension`). Write Shopify's raw `value` instead of crashing; Verify 1 shows whether the admin agrees. Test: `test_unknown_metafield_type_writes_raw_value` (Task 3).
4. **A bulk operation that ends `FAILED`/`CANCELED`/`EXPIRED`, or `COMPLETED` with no `url`** (zero results). It must raise, not write an empty products file. Tests: `test_failed_bulk_operation_raises`, `test_completed_without_url_reads_zero_products` + `test_zero_products_keeps_old_file` (Tasks 2, 4).
5. **A previous run's split files when this run doesn't split.** Stale `products-N.csv` / `products.csv` must be removed so the restore folder isn't ambiguous. Test: `test_single_file_removes_stale_parts` (Task 4).

---

## File structure

```
catalog/backup/__init__.py        package docstring
catalog/backup/guard.py           check_csv: refuse empty / non-CSV / wrong-header files
catalog/backup/libib.py           backup_libib: export → guard → copy byte-for-byte
catalog/backup/bulk.py            run_bulk_query + assemble_products (bulk JSONL → nested product dicts)
catalog/backup/shopify_csv.py     admin-export header + product → rows formatting (pure)
catalog/backup/shopify.py         read_store + write_products + backup_shopify
catalog/backup/compare.py         compare_exports: our CSV vs an admin export (for Verify 1)
catalog/backup/command.py         `backup` and `backup-compare` CLI commands, summary line
catalog/backup/queries/bulk_run.graphql
catalog/backup/queries/bulk_status.graphql
catalog/backup/queries/publications.graphql
catalog/backup/queries/metafield_definitions.graphql
catalog/backup/queries/products_bulk.graphql   the bulk query text (a template with %(publication_id)s)
tests/catalog/test_backup_guard.py
tests/catalog/test_backup_libib.py
tests/catalog/test_backup_bulk.py
tests/catalog/test_backup_shopify_csv.py
tests/catalog/test_backup_shopify.py
tests/catalog/test_backup_compare.py
tests/catalog/test_backup_command.py
catalog/cli.py                    add backup_command to COMMANDS
catalog/README.md, CLAUDE.md      document the command / roadmap line
LMS-data repo (separate clone):   .github/workflows/daily-backup.yml, README.md; delete libib-login-test.yml
```

Shared result type, defined in `catalog/backup/guard.py` (Task 1) so every task can import it without cycles:

```python
@dataclass
class SourceResult:
    name: str            # "libib" | "shopify"
    ok: bool
    summary: str         # "3962/3962 rows" | "7031 products" | "FAILED"
    error: str = ""      # one line, no row contents
```

Run single test files with: `python3 -m unittest discover -s tests/catalog -p "<file>.py" -v` (from the repo root).

---

### Task 1: CSV guard + result type

**Files:**
- Create: `catalog/backup/__init__.py`, `catalog/backup/guard.py`
- Test: `tests/catalog/test_backup_guard.py`

**Interfaces:**
- Produces: `SourceResult` (above); `check_csv(path: Path, required: tuple[str, ...]) -> int`, which returns the number of data rows and raises `InputShapeError` (from `catalog.errors`) when the file is unreadable as UTF-8 CSV, its header lacks any `required` column, or it has zero data rows. The message names the file and the reason, never row contents.
- Constants: `LIBIB_BARCODES_REQUIRED = ("id", "barcode", "title")`, `LIBIB_LIBRARY_REQUIRED = ("id", "title", "call_number")`, `SHOPIFY_REQUIRED = ("Handle", "Title", "Status")`.

- [ ] **Step 1: Write the failing tests**: `test_counts_data_rows` (header + 3 rows → 3), `test_missing_required_column_raises` (message contains the column name), `test_zero_rows_raises`, `test_html_page_raises` (file holding `<!DOCTYPE html><html>…` → raises), `test_counts_rows_with_embedded_newlines` (a quoted field containing `\n` still counts as one row). Build files in `tempfile.TemporaryDirectory()`; use read with `encoding="utf-8-sig"`.
- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: catalog.backup`).
- [ ] **Step 3: Implement** `guard.py` with `csv.reader`; treat `UnicodeDecodeError` / `csv.Error` as `InputShapeError`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `git add catalog/backup tests/catalog/test_backup_guard.py && git commit -m "backup: CSV guard for refusing empty or malformed exports"`

### Task 2: Bulk operation runner + JSONL assembly

**Files:**
- Create: `catalog/backup/bulk.py`, `catalog/backup/queries/bulk_run.graphql`, `catalog/backup/queries/bulk_status.graphql`
- Test: `tests/catalog/test_backup_bulk.py`

**Interfaces:**
- Consumes: an `execute(store, query_path, variables) -> payload` as returned by `catalog.shopify.api.make_executor`.
- Produces:
  - `run_bulk_query(execute, store: str, query: str, *, sleep=time.sleep, urlopen=urllib.request.urlopen, poll_seconds: float = 5, timeout_seconds: float = 1800, clock=time.monotonic) -> list[dict]`: starts the job, polls until a terminal status, downloads the JSONL and returns one dict per line.
  - `assemble_products(lines: list[dict]) -> list[dict]`: products with `variants`, `media`, `metafields` lists, each metafield with a `references` list, in JSONL order.

`bulk_run.graphql`:
```graphql
mutation ($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation { id status }
    userErrors { field message }
  }
}
```
`bulk_status.graphql`:
```graphql
query ($id: ID!) {
  bulkOperation(id: $id) { id status errorCode objectCount url partialDataUrl }
}
```

Assembly rule: a line without `__parentId` is a product. A line with `__parentId` is attached by its `__typename`: `ProductVariant` → parent's `variants`, `Metafield` → parent's `metafields`, `Metaobject`/`Product` with a `Metafield` parent → that metafield's `references`, and any other typename whose parent is a product → `media`. Children can appear before parents in the file, so index everything by `id` first, then attach.

- [ ] **Step 1: Write the failing tests**
  - `test_runs_polls_and_downloads`: fake `execute` returns `CREATED` on the run, then `RUNNING`, then `COMPLETED` with `url="https://x/f.jsonl"`. Fake `urlopen` returns two JSON lines; the result equals those two dicts and `sleep` was called twice with `5`.
  - `test_user_errors_raise`: run returns `userErrors=[{"message": "bad query"}]` → `ShopifyError` containing `bad query`.
  - `test_failed_bulk_operation_raises`: status `FAILED`, `errorCode="ACCESS_DENIED"` → `ShopifyError` containing `ACCESS_DENIED`. Same for `CANCELED` and `EXPIRED`.
  - `test_completed_without_url_reads_zero_products`: `COMPLETED`, `url=None` → `[]`.
  - `test_times_out`: never completes; with `timeout_seconds=10, poll_seconds=5` it raises `ShopifyError` mentioning the timeout after at most 3 polls (fake `sleep` advances a fake clock passed as `clock=`).
  - `test_assembles_children_out_of_order`: lines in the order variant, metaobject reference, product, metafield, media → one product with 1 variant, 1 media, 1 metafield holding 1 reference.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `bulk.py`.** Download with `urlopen(url, timeout=120)` and split on newlines, skipping blank lines. Module docstring: this is the one mutation the backup sends; it starts a read-only export job.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `"backup: Shopify bulk operation runner and JSONL assembly"`

### Task 3: Admin-export formatter (pure)

**Files:**
- Create: `catalog/backup/shopify_csv.py`
- Test: `tests/catalog/test_backup_shopify_csv.py`

**Interfaces:**
- Consumes: assembled product dicts from Task 2, shaped by the bulk query in Task 4 (field names below).
- Produces:
  - `@dataclass(frozen=True) class MetafieldColumn: name: str; namespace: str; key: str`, plus property `header -> str` = `f"{name} (product.metafields.{namespace}.{key})"`.
  - `split_definitions(definitions: list[dict]) -> tuple[list[MetafieldColumn], list[MetafieldColumn]]`: takes `{name, namespace, key}` dicts and returns (kept, left_out), each sorted by `(namespace, key)`. Left out = namespace starts with `shopify--discovery--` or `app--`, or equals `supercycle`.
  - `build_header(columns: list[MetafieldColumn]) -> list[str]`: `BEFORE_METAFIELDS + [c.header for c in columns] + AFTER_METAFIELDS`.
  - `product_rows(product: dict, columns: list[MetafieldColumn]) -> list[dict]`: every row has every header key (missing = `""`).
  - `format_metafield(metafield: dict) -> str`.

Header constants (from the 2026-09-20 production admin export; Task 7 corrects them against a fresh one):
```python
BEFORE_METAFIELDS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Option1 Linked To", "Option2 Name", "Option2 Value", "Option2 Linked To",
    "Option3 Name", "Option3 Value", "Option3 Linked To", "Variant SKU", "Variant Grams",
    "Variant Inventory Tracker", "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price", "Variant Compare At Price", "Variant Requires Shipping",
    "Variant Taxable", "Unit Price Total Measure", "Unit Price Total Measure Unit", "Unit Price Base Measure",
    "Unit Price Base Measure Unit", "Variant Barcodes", "Image Src", "Image Position", "Image Alt Text",
    "Gift Card", "SEO Title", "SEO Description",
]
AFTER_METAFIELDS = ["Variant Image", "Variant Weight Unit", "Variant Tax Code", "Cost per item", "Status"]
```

Row rules (observed in the 2026-09-20 export):
- Rows per product = `max(len(variants), len(images), 1)`, where images = `media` nodes with `__typename == "MediaImage"`, in order. Variants are sorted by `position`.
- **Row 0 only:** Title, Body (HTML) (`descriptionHtml` as-is), Vendor, Product Category (`category.fullName`, or `""` when there's no category), Type (`productType`), Tags (`", ".join(tags)`), Published (`published` → `true`/`false`), Option1–3 Name (from `options` sorted by `position`), Option*N* Linked To (`product.metafields.{ns}.{key}` when `linkedMetafield` is set), Gift Card (`isGiftCard`), SEO Title/Description (`seo.title`/`seo.description` or `""`), every metafield column, Status (lowercase).
- **Every variant row *k*:** Option*N* Value (the `selectedOptions` value whose name matches option *N*), Variant SKU, Variant Grams, Variant Inventory Tracker (`shopify` if `inventoryItem.tracked`, else `""`), Variant Inventory Qty (`str(inventoryQuantity)`), Variant Inventory Policy (lowercase `inventoryPolicy`), Variant Fulfillment Service (`manual`), Variant Price / Compare At Price / Cost per item (`f"{Decimal(x):.2f}"`, `""` when null; cost = `inventoryItem.unitCost.amount`), Variant Requires Shipping (`inventoryItem.requiresShipping`), Variant Taxable (`taxable`), Unit Price fields (`unitPriceMeasurement.quantityValue` / lowercase `quantityUnit` / `referenceValue` / lowercase `referenceUnit`, all `""` when `quantityValue` is null), Variant Barcodes (`barcode` or `""`), Variant Image (`image.url` or `""`), Variant Weight Unit, Variant Tax Code (always `""`; no tax codes are in use).
- **Every image row *k*:** Image Src (`image.url`), Image Position (`str(k + 1)`), Image Alt Text (`image.altText` or `""`).
- Booleans are lowercase `true`/`false`.
- Weight: `inventoryItem.measurement.weight {unit, value}`. Grams = value × {`POUNDS`: 453.59237, `OUNCES`: 28.349523125, `KILOGRAMS`: 1000, `GRAMS`: 1}, written as `str(round(grams, 1))` (so `0` → `"0.0"`). Unit → {`POUNDS`: `lb`, `OUNCES`: `oz`, `KILOGRAMS`: `kg`, `GRAMS`: `g`}. No measurement → both `""`.
- `format_metafield`: a type ending in `metaobject_reference` or `product_reference` → `"; ".join(handles of references)`. Any other `list.*` → `"; ".join(str(v) for v in json.loads(value))`. Anything else → `value` unchanged.

- [ ] **Step 1: Write the failing tests** with synthetic dicts. Keep one fixture builder per shape at the top of the file.
  - `test_header_places_metafields_between_seo_and_variant_image`.
  - `test_split_definitions_sorts_and_leaves_out_app_namespaces`: input `custom.year`, `shopify.genre`, `custom.country`, `shopify--discovery--product_recommendation.related_products`, `supercycle.methods`, `app--123.x` → kept `[custom.country, custom.year, shopify.genre]`; left out has the other three.
  - `test_rows_pair_variants_and_images_by_index`: a shirt with 5 variants (`s, m, l, xl, 2xl`) and 3 images → 5 rows. Row 0 has Title + `Option1 Name="Size"` + `Option1 Linked To="product.metafields.shopify.size"` + `Image Position="1"`. Row 3 has `Option1 Value="xl"` and `Image Src=""`. Rows 1–4 have `Title=""`. A movie with 1 variant and 5 images → 5 rows, where rows 1–4 have only Handle + image fields filled.
  - `test_default_title_product`: options `[{"name": "Title", "position": 1}]`, selectedOptions `[{"name": "Title", "value": "Default Title"}]` → `Option1 Name="Title"`, `Option1 Value="Default Title"`.
  - `test_product_with_no_images_has_one_row_per_variant`.
  - `test_variant_values`: price `"5"` → `"5.00"`, compareAtPrice null → `""`, tracked → `"shopify"`, policy `"DENY"` → `"deny"`, weight `{POUNDS, 0}` → grams `"0.0"`, unit `"lb"`, requiresShipping False → `"false"`, inventoryQuantity -3 → `"-3"`.
  - `test_metaobject_list_writes_handles`: `list.metaobject_reference` with references `beige`, `white` → `"beige; white"`. `test_single_metaobject_reference` → `"eng-english"`. `test_text_list_joins_with_semicolons`: `'["a","b"]'` → `"a; b"`. `test_unknown_metafield_type_writes_raw_value`: type `rating`, value `'{"value":"4.5"}'` → same string.
  - `test_missing_category_is_blank`, `test_published_flags` (`True` → `"true"`), `test_status_lowercase`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `shopify_csv.py`.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `"backup: format products as Shopify admin-export rows"`

### Task 4: Shopify read + write + `backup_shopify`

**Files:**
- Create: `catalog/backup/shopify.py`, `catalog/backup/queries/publications.graphql`, `catalog/backup/queries/metafield_definitions.graphql`, `catalog/backup/queries/products_bulk.graphql`
- Test: `tests/catalog/test_backup_shopify.py`

**Interfaces:**
- Consumes: `run_bulk_query`, `assemble_products` (Task 2); `split_definitions`, `build_header`, `product_rows`, `MetafieldColumn` (Task 3); `check_csv`, `SHOPIFY_REQUIRED`, `SourceResult` (Task 1).
- Produces:
  - `read_store(execute, store: str, **bulk_kwargs) -> tuple[list[dict], list[MetafieldColumn], list[MetafieldColumn]]`: (products sorted by handle, kept columns, left-out columns). `bulk_kwargs` are passed through to `run_bulk_query`, so tests can inject `sleep`/`urlopen`.
  - `write_products(shopify_dir: Path, header: list[str], products_rows: list[list[dict]], max_bytes: int = 15_000_000) -> list[Path]`: one inner list per product. Writes `products.csv`, or `products-1.csv`…`products-N.csv` when the encoded size passes `max_bytes`, never splitting a product. Removes any `products.csv` / `products-*.csv` this call didn't write. Returns the written paths.
  - `backup_shopify(out_dir: Path, read: Callable[[], tuple[list[dict], list[MetafieldColumn], list[MetafieldColumn]]]) -> SourceResult`: builds rows, writes them to a temp dir first, runs `check_csv` on each part (`SHOPIFY_REQUIRED`), then moves them into `out_dir/"shopify"`. Returns `summary=f"{len(products)} products"`. On any exception it returns `ok=False, summary="FAILED", error=<one line>` and leaves the existing files untouched.

`publications.graphql`: `query { publications(first: 25) { nodes { id name } } }`. The Online Store publication is the node named `"Online Store"`; if there isn't exactly one, raise `ShopifyError`.
`metafield_definitions.graphql`: `query ($cursor: String) { metafieldDefinitions(ownerType: PRODUCT, first: 250, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { name namespace key } } }`. Paginate until done.
`products_bulk.graphql` (formatted with `% {"publication_id": id}` before sending):
```graphql
{
  products {
    edges { node {
      __typename id handle title descriptionHtml vendor productType tags status isGiftCard
      category { fullName }
      seo { title description }
      published: publishedOnPublication(publicationId: "%(publication_id)s")
      options { name position linkedMetafield { namespace key } }
      variants { edges { node {
        __typename id position sku price compareAtPrice taxable barcode inventoryQuantity inventoryPolicy
        selectedOptions { name value }
        image { url }
        unitPriceMeasurement { quantityValue quantityUnit referenceValue referenceUnit }
        inventoryItem { tracked requiresShipping unitCost { amount } measurement { weight { unit value } } }
      } } }
      media { edges { node { __typename ... on MediaImage { id image { url altText } } } } }
      metafields { edges { node {
        __typename id namespace key type value
        references { edges { node { __typename ... on Metaobject { id handle } ... on Product { id handle } } } }
      } } }
    } }
  }
}
```
That's 5 connections, nested at most 2 deep, which is within bulk-operation limits. If API `2026-07` rejects a field (e.g. `ProductVariant.image`), switch to its documented replacement and say so in the commit message.

- [ ] **Step 1: Write the failing tests**: fake `execute` serving publications, two pages of definitions and a bulk run, plus a fake `urlopen` serving synthetic JSONL.
  - `test_read_store_sorts_by_handle_and_splits_columns`.
  - `test_read_store_needs_one_online_store`: zero or two "Online Store" nodes → `ShopifyError`.
  - `test_bulk_query_carries_publication_id`: the `query` variable sent to `bulk_run.graphql` contains the publication gid.
  - `test_written_csv_round_trips_awkward_html`: Body `<p>a, "b"\nc</p>` survives write → `csv.DictReader` read.
  - `test_splits_on_product_boundaries`: `max_bytes` set small → several parts, each starting with the header, no handle in two parts, concatenated rows equal the unsplit rows.
  - `test_single_file_removes_stale_parts`: pre-create `products-1.csv`, `products-2.csv` → after a small write only `products.csv` exists. And the reverse: a split write removes `products.csv`.
  - `test_zero_products_keeps_old_file`: existing `shopify/products.csv` with content X; `read` returns no products → `ok=False`, file still X.
  - `test_read_failure_returns_failed_result`: `read` raises `ShopifyError("boom")` → `SourceResult("shopify", False, "FAILED", "boom")`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `shopify.py`.** Measure size with `len(line.encode("utf-8"))` per CSV line rendered through `csv.writer` into `io.StringIO`. Write with `newline=""`, `encoding="utf-8"`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `"backup: read every product with a bulk operation and write admin-format CSVs"`

### Task 5: Libib backup

**Files:**
- Create: `catalog/backup/libib.py`
- Test: `tests/catalog/test_backup_libib.py`

**Interfaces:**
- Consumes: `check_csv`, `LIBIB_BARCODES_REQUIRED`, `LIBIB_LIBRARY_REQUIRED`, `SourceResult` (Task 1). In production, `export = lambda dest: transfer.run_browser_export(email, password, dest, headless)`, which returns `(barcodes_path, library_path)`.
- Produces: `backup_libib(out_dir: Path, export: Callable[[Path], tuple[Path, Path]]) -> SourceResult`. It exports into a `tempfile.TemporaryDirectory()`, checks both files, then `shutil.copyfile`s them to `out_dir/"libib"/"barcodes.csv"` and `"library.csv"`. If either check fails, it copies neither. Summary: `f"{barcode_rows}/{library_rows} rows"`. On any exception: `ok=False, summary="FAILED"`, with the exception class and message as `error`. A `PlaywrightTimeoutError` reads as `"Libib login or export timed out"`.

- [ ] **Step 1: Write the failing tests**
  - `test_copies_exports_byte_for_byte`: the fake export writes files with CRLF line endings and a BOM → the destination bytes are identical.
  - `test_summary_counts_both_files`: 3 barcode rows, 2 library rows → `"3/2 rows"`.
  - `test_bad_library_export_keeps_both_old_files`: the library file is an HTML page → `ok=False`, and the existing `barcodes.csv` and `library.csv` are unchanged.
  - `test_export_exception_is_a_failed_result`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `libib.py`.** Don't import Playwright at module level; `transfer` is imported inside the command's default wiring (Task 6).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `"backup: Libib exports copied byte-for-byte after a sanity check"`

### Task 6: `backup` command, CLI wiring, docs

**Files:**
- Create: `catalog/backup/command.py`
- Modify: `catalog/cli.py` (import `from catalog.backup import command as backup_command`, append to `COMMANDS`), `catalog/README.md` (a "Backup" section: what it writes, flags, that it runs daily from `LMS-data`), `CLAUDE.md` (one line under the roadmap: daily backup to private `paris-liam/LMS-data`, spec path)
- Test: `tests/catalog/test_backup_command.py`

**Interfaces:**
- Consumes: `backup_libib` (Task 5), `backup_shopify`, `read_store` (Task 4), `SourceResult` (Task 1).
- Produces:
  - `register(subparsers)` adds `backup` with `--out DIR` (required), `--store` (default `config.DEFAULT_STORE`), `--only {libib,shopify}` (default both), `--headless`, `--message-file PATH` (write the commit message there), `--date YYYY-MM-DD` (default today, UTC).
  - `summary_line(results: list[SourceResult], day: date) -> str`. With both OK: `"Backup 2026-10-22 — libib 3962/3962 rows, shopify 7031 products"`. With Libib failed: `"Backup 2026-10-22 — libib FAILED, shopify 7031 products"`.
  - `run_backup(args, deps: BackupDeps) -> int`, where `@dataclass class BackupDeps: libib: Callable[[Path], SourceResult]; shopify: Callable[[Path], SourceResult]`. It runs the selected sources in order libib, then shopify, each regardless of the other's outcome. It prints one line per source (`libib: 3962/3962 rows` or `libib: FAILED — <error>`), writes `--message-file`, and returns `0` if all OK, else `1`.
  - `default_deps(args) -> BackupDeps` reads env through `config.require_env` only for the sources selected. The Shopify read uses `api.make_executor(store, api.request_token(...))`.

- [ ] **Step 1: Write the failing tests**
  - `test_summary_line_both_ok`, `test_summary_line_libib_failed`.
  - `test_runs_shopify_even_when_libib_fails`: the fake libib returns failed, the fake shopify is OK → exit `1`, shopify was called, and the message file contains `libib FAILED, shopify 2 products`.
  - `test_only_flag_runs_one_source`.
  - `test_parser_registers_backup`: `build_parser().parse_args(["backup", "--out", "x"])` has `func`.
  - `test_output_has_no_row_contents`: the fake sources' errors carry no data; just assert the printed lines match `^(libib|shopify): ` exactly once each.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `command.py`, wire `cli.py`, write the docs.**
- [ ] **Step 4: Run the new tests, then the whole suite** `python3 -m unittest discover -s tests/catalog`. Expect all PASS, including `test_cli.py`.
- [ ] **Step 5: Commit** `"backup: python3 -m catalog backup command"`

### Task 7: Format check against real admin exports (needs the developer)

**Files:**
- Create: `catalog/backup/compare.py`; add a `backup-compare OURS ADMIN_EXPORT [--ignore COLUMN ...]` command in `command.py` (`--ignore` repeatable, feeds `ignore_columns`)
- Modify (if the comparison demands it): `catalog/backup/shopify_csv.py`
- Test: `tests/catalog/test_backup_compare.py`

**Interfaces:**
- Produces: `compare_exports(ours: Path, theirs: Path, ignore_columns: set[str]) -> list[str]`, a list of human-readable differences: header differences first, then per handle and column `"<handle> row <n> <column>: ours=<…> theirs=<…>"`, capped at 200 lines plus a count. Rows are grouped by handle, and a handle's rows are compared in order. Read raw with `csv.DictReader` (not `load_export`, which renames `Variant Barcodes`). The CLI prints the list and exits `1` if it's non-empty. It may print values: it only runs locally on files the developer owns, never in Actions.

- [ ] **Step 1: Write the failing tests**: `test_identical_files_have_no_differences`, `test_reports_header_and_value_differences`, `test_ignores_listed_columns`, `test_reports_missing_handles_both_ways`.
- [ ] **Step 2: Run, expect FAIL.** **Step 3: Implement.** **Step 4: Run, expect PASS.** **Step 5: Commit** `"backup: compare a backup CSV with a Shopify admin export"`
- [ ] **Step 6: Ask the developer for two fresh admin exports** (Shopify admin → Products → Export → All products → CSV): one from **production** and one from the **dev store**. Save them **outside both repos**, e.g. the session scratchpad. Never commit them.
- [ ] **Step 7: Header check.** Compare the production export's header with `build_header(kept)` from a production `read_store`. Run: `python3 -m catalog backup --only shopify --out <scratch>/prod` then `python3 -m catalog backup-compare <scratch>/prod/shopify/products.csv <prod-export.csv>`, and look only at the header lines. Update `BEFORE_METAFIELDS` / `AFTER_METAFIELDS` to the fresh header. The left-out metafield columns are expected header differences; list them for the README.
- [ ] **Step 8: Value check on the dev store.** Run `python3 -m catalog backup --only shopify --store lms-sandbox-lutsfahz.myshopify.com --out <scratch>/dev`, then `backup-compare` against the dev export with `--ignore` for the left-out columns. Fix each class of difference in `shopify_csv.py` with a new unit test per rule. Repeat until the only differences left can be explained (e.g. live inventory moving between the two exports). Record anything left over in the README's caveats.
- [ ] **Step 9: Commit** `"backup: match the current admin export format"`

### Task 8: `LMS-data` workflow + README, end-to-end runs (needs the developer)

**Files (in a clone of `paris-liam/LMS-data` at `/Users/liamparis/web-projects/personal/Little Movie Store/LMS-data`; use `GH_TOKEN=$(gh auth token --user paris-liam)` — the active `gh` account can't push there):**
- Create: `.github/workflows/daily-backup.yml`, `README.md`
- Delete: `.github/workflows/libib-login-test.yml`

Before this task: merge Tasks 1–7 to `LMS` `main` and push, because the workflow checks out `main`. **Ask the developer before pushing to `main`.** The developer adds the secrets `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` to `LMS-data` themselves (`gh secret set … --repo paris-liam/LMS-data`); an agent isn't allowed to upload credentials.

`daily-backup.yml`:
```yaml
name: Daily backup

on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: daily-backup
  cancel-in-progress: false

jobs:
  backup:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v5
        with:
          path: data
      - uses: actions/checkout@v5
        with:
          repository: paris-liam/LMS
          path: lms
      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
      - uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-1.63.0-chromium
      - name: Install Playwright
        run: |
          pip install playwright==1.63.0
          playwright install --with-deps chromium
      - name: Back up Libib and Shopify
        id: backup
        working-directory: lms
        env:
          LIBIB_EMAIL: ${{ secrets.LIBIB_EMAIL }}
          LIBIB_PASSWORD: ${{ secrets.LIBIB_PASSWORD }}
          SHOPIFY_CLIENT_ID: ${{ secrets.SHOPIFY_CLIENT_ID }}
          SHOPIFY_CLIENT_SECRET: ${{ secrets.SHOPIFY_CLIENT_SECRET }}
        run: |
          set +e
          python -m catalog backup --out ../data --headless --message-file "$RUNNER_TEMP/message.txt"
          echo "status=$?" >> "$GITHUB_OUTPUT"
      - name: Commit changes
        working-directory: data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          if git diff --cached --quiet; then echo "No changes"; exit 0; fi
          git commit -F "$RUNNER_TEMP/message.txt"
          git push
      - name: Fail if a source failed
        if: steps.backup.outputs.status != '0'
        run: exit 1
```
(If `actions/cache@v4` warns about Node 20, use the current major version.)

`README.md` must cover the spec's README section: what each file is; history = daily snapshots; **client restore steps** (find the date in the commit history → open `shopify/products.csv` at that commit → Download raw → Shopify admin → Products → Import → tick "Overwrite products with matching handles" → Import); what a restore can't bring back (images of deleted products; template suffix: list the products whose `templateSuffix` is `retail`, confirmed with a quick read-only query, and say they must be set back to `retail` by hand; the left-out metafield columns from Task 7); that Libib files are Libib's own exports and their restore isn't covered; that private repos don't get GitHub's 60-day inactivity auto-disable for scheduled workflows.

- [ ] **Step 1:** Clone `LMS-data`, add both files, delete the test workflow, commit (`"Daily backup workflow and README"`) and push. If the push is blocked, hand the developer the exact command.
- [ ] **Step 2: First manual run:** `gh workflow run daily-backup.yml --repo paris-liam/LMS-data`, then `gh run watch`. Expect: the run succeeds and one commit adds `libib/barcodes.csv`, `libib/library.csv` and `shopify/products.csv`, with a message matching `^Backup \d{4}-\d{2}-\d{2} — libib \d+/\d+ rows, shopify \d+ products$`.
- [ ] **Step 3: No-change run:** run it again right away. Expect: success and "No changes" in the log, or a commit whose diff only touches live fields (inventory, Libib `updated`). Explain which in the hand-off.
- [ ] **Step 4: Failure run:** the developer temporarily sets `LIBIB_PASSWORD` to a wrong value, then runs the workflow. Expect: the Shopify file is committed if it changed, the Libib files are unchanged, the run is marked failed, and GitHub sends a failure email to `paris-liam`. The developer restores the real secret afterwards.
- [ ] **Step 5: Round trip on the dev store (never production):** (a) back up the dev store from the CLI: `python3 -m catalog backup --only shopify --store lms-sandbox-lutsfahz.myshopify.com --out <scratch>/roundtrip`; (b) the developer, in the dev admin, changes the title, tags and price on 3 products (a movie with a genre, a Floor Sale item, the shirt) and deletes one more; (c) the developer imports `<scratch>/roundtrip/shopify/products.csv` with "Overwrite products with matching handles"; (d) confirm genre, tags, status, published, price, barcode and inventory match the backup again (a re-run of (a) into a new folder plus `backup-compare` against the first backup should show no differences for those 4 handles).
- [ ] **Step 6:** Watch the first two scheduled runs (08:00 UTC) and report their commit messages.
