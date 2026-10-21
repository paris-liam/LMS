# Libib Tag Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily job that makes the Libib tags `new arrival` and `community pick`, and the Shopify product tag `community-pick`, match Shopify.

**Architecture:** A new `python3 -m catalog libib tags` command. It reads Shopify (products tagged `new-arrival`, Active `community_pick` entries, products tagged `community-pick`), exports Libib, and computes a change list with pure, unit-tested functions. It then shows that list through the existing `Plan`/`confirm` approval flow, writes the Shopify tags with `tagsAdd`/`tagsRemove`, and edits each Libib item's tags in the browser, opening the item by barcode and verifying after reload. A GitHub Actions workflow runs the Libib selftest and then `libib tags --unattended` once a day.

**Tech Stack:** Python 3.11 (stdlib + Playwright only), `unittest`, Shopify Admin GraphQL `2026-07` via `catalog/shopify/api.py`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-20-libib-tag-sync-design.md`

## Global Constraints

- Libib tags written: exactly `new arrival` and `community pick`. Shopify tags read: `new-arrival` and `community-pick`. Shopify tag written: `community-pick` only.
- Never change any other Libib tag or field. Never use Libib CSV import. Never write `call_number`.
- Default store: `config.DEFAULT_STORE` (`p0wkgv-wy.myshopify.com`, production).
- Tags go only on the matched copy (Shopify variant barcode = Libib copy barcode). There is no sibling-copy grouping.
- **The repo is public, and so are its Actions logs.** Never print a barcode or call number in logs, plan lines or the report. Identify items by title plus Libib item `id`. Don't upload screenshots as artifacts.
- Unattended runs make at most `--max-changes` changes (default **25**, counting Libib items plus Shopify products). Above that limit the run changes nothing, exits 2, and needs `--dry-run` → `--approve <code>`.
- Secrets come only from env or `.env`: `LIBIB_EMAIL`, `LIBIB_PASSWORD`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET` (via `config.require_env`).
- Playwright is imported only through `catalog.libib.venv.sync_playwright(<command>)`.
- Test command: `python3 -m unittest discover -s tests/catalog -p "test_*.py"` (900 tests pass on `main` today).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A barcode search that lands on the wrong item.** Libib search may match on a call number or part of a number. Before editing, the job must confirm the opened item's copy barcode equals the target, or skip the item with an error. (Task 3, live probe step.)
2. **Tags we don't own must survive.** `blu-ray, Drama`, odd casing, and Libib's lowercasing and reordering on save. Only our two tags change. The check after reload compares normalized sets. (Task 1, `apply_tag_change` tests.)
3. **One barcode on two Libib items** (duplicate barcodes have existed). Neither item is touched, and the case is reported. (Task 1, `test_ambiguous_barcode_touches_neither_item`.)
4. **A bad or partial read must not cause mass removal.** A Shopify GraphQL error aborts the run before anything is written. An empty Libib export aborts. The 25-change cap stops whatever slips through. (Tasks 2 and 4.)
5. **Community Pick entries in odd states.** A Draft entry, an entry with an empty or deleted product, or a pick on a Floor Sale (non-rental) product. Draft and empty entries are ignored. A non-rental pick gets the Shopify tag only and no Libib change. (Tasks 1 and 2.)

---

## File Structure

| File | Responsibility |
|---|---|
| `catalog/libib/tags.py` (create) | Pure logic: tag names, Libib change list, Shopify change list, tag-string edit |
| `catalog/libib/tags_shopify.py` (create) | Shopify GraphQL reads into `ShopifyState`, `tagsAdd`/`tagsRemove` writes, client from env |
| `catalog/libib/browser.py` (modify) | `open_item_by_barcode`, `set_item_tags`, a shared search helper |
| `catalog/libib/tag_editor.py` (create) | Browser loop over Libib changes with retries and a CSV report (like `fix.run_fixer`) |
| `catalog/libib/selftest.py` (modify) | New check "search by barcode" and a `barcode` parameter |
| `catalog/libib/tags_command.py` (create) | `libib tags` parser and `run_tags_command` |
| `catalog/libib/command.py` (modify) | Call `tags_command.register(sub)` and pass `--barcode` to selftest |
| `.github/workflows/libib-tags.yml` (create) | Daily schedule + manual run |
| `.gitignore`, `catalog/README.md`, `claudedocs/lms-admin-instructions.md` (modify) | Report dir, docs, client steps |
| `tests/catalog/test_libib_tags.py`, `test_libib_tags_shopify.py`, `test_libib_tags_command.py` (create) | Tests |

---

### Task 1: Reconciliation logic

**Files:**
- Create: `catalog/libib/tags.py`
- Test: `tests/catalog/test_libib_tags.py`

**Interfaces:**
- Consumes: `catalog.libib.fields.normalized_tag_set(tags: str) -> set[str]`; Libib items as returned by `catalog.libib.exports.load_libib` (dicts with `id`, `title`, `barcode`, `tags`, …).
- Produces:
  - Constants `SHOPIFY_NEW_ARRIVAL = "new-arrival"`, `SHOPIFY_COMMUNITY_PICK = "community-pick"`, `LIBIB_NEW_ARRIVAL = "new arrival"`, `LIBIB_COMMUNITY_PICK = "community pick"`, `MANAGED_LIBIB_TAGS = frozenset({LIBIB_NEW_ARRIVAL, LIBIB_COMMUNITY_PICK})`.
  - `@dataclass(frozen=True) class Product: id: str; title: str; tags: tuple[str, ...]; barcodes: tuple[str, ...]` with property `is_rental -> bool` (True when `"Rental"` is one of `tags`, compared case-insensitively).
  - `@dataclass(frozen=True) class ShopifyState: new_arrivals: tuple[Product, ...]; picked: tuple[Product, ...]; tagged_picks: tuple[Product, ...]`
  - `@dataclass(frozen=True) class LibibChange: item_id: str; title: str; barcode: str; add: frozenset[str]; remove: frozenset[str]`
  - `@dataclass(frozen=True) class ShopifyChange: product_id: str; title: str; action: str  # "add" | "remove"`
  - `@dataclass(frozen=True) class Unmatched: title: str; reason: str`
  - `libib_changes(items: list[dict], state: ShopifyState) -> tuple[list[LibibChange], list[Unmatched]]`
  - `shopify_changes(state: ShopifyState) -> list[ShopifyChange]`
  - `apply_tag_change(current: str, add: Iterable[str], remove: Iterable[str]) -> str`

- [ ] **Step 1: Write the failing tests** in `tests/catalog/test_libib_tags.py` (`unittest.TestCase`). Use the helpers `item(id, barcode, tags, title="T")` → a dict shaped like `load_libib` output, and `product(id, barcodes, tags=("Rental",), title="T")` → `Product`.

```python
def test_new_arrival_added_to_matched_item(self):
    changes, unmatched = libib_changes([item("a", "111", "blu-ray, drama")],
                                       ShopifyState((product("p1", ("111",)),), (), ()))
    self.assertEqual(changes, [LibibChange("a", "T", "111", frozenset({"new arrival"}), frozenset())])
    self.assertEqual(unmatched, [])

def test_tag_removed_when_shopify_no_longer_has_it(self):
    changes, _ = libib_changes([item("a", "111", "drama, New Arrival")], ShopifyState((), (), ()))
    self.assertEqual(changes[0].remove, frozenset({"new arrival"}))

def test_already_correct_item_has_no_change(self):
    changes, _ = libib_changes([item("a", "111", "drama, new arrival")],
                               ShopifyState((product("p1", ("111",)),), (), ()))
    self.assertEqual(changes, [])

def test_only_the_picked_copy_is_tagged(self):
    items = [item("a", "111", "vhs", "Legend"), item("b", "222", "vhs", "Legend")]
    changes, _ = libib_changes(items, ShopifyState((), (product("p1", ("111",)),), ()))
    self.assertEqual([c.item_id for c in changes], ["a"])
    self.assertEqual(changes[0].add, frozenset({"community pick"}))

def test_non_rental_pick_has_no_libib_change_and_is_not_unmatched(self):
    changes, unmatched = libib_changes([], ShopifyState((), (product("p1", ("999",), tags=("Floor Sale",)),), ()))
    self.assertEqual((changes, unmatched), ([], []))

def test_rental_with_no_libib_item_is_unmatched(self):
    _, unmatched = libib_changes([], ShopifyState((product("p1", ("111",), title="Bottoms"),), (), ()))
    self.assertEqual(unmatched, [Unmatched("Bottoms", "no Libib item has this barcode")])

def test_product_without_barcode_is_unmatched(self):
    _, unmatched = libib_changes([], ShopifyState((product("p1", (), title="X"),), (), ()))
    self.assertEqual(unmatched, [Unmatched("X", "no barcode in Shopify")])

def test_ambiguous_barcode_touches_neither_item(self):
    items = [item("a", "111", "new arrival"), item("b", "111", "vhs")]
    changes, unmatched = libib_changes(items, ShopifyState((), (), ()))
    self.assertEqual(changes, [])
    self.assertEqual([u.reason for u in unmatched], ["barcode is on 2 Libib items"])

def test_changes_are_sorted_by_title_then_item_id(self):  # stable approval fingerprint
    items = [item("b", "2", "", "Zed"), item("a", "1", "", "Alpha")]
    state = ShopifyState((product("p1", ("2",)), product("p2", ("1",))), (), ())
    self.assertEqual([c.item_id for c in libib_changes(items, state)[0]], ["a", "b"])

def test_shopify_changes_add_and_remove(self):
    state = ShopifyState((), (product("p1", ("1",), title="A"),),
                         (product("p2", ("2",), tags=("Rental", "community-pick"), title="B"),))
    self.assertEqual(shopify_changes(state), [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "remove")])

def test_shopify_pick_already_tagged_is_unchanged(self):
    p = product("p1", ("1",), tags=("Rental", "community-pick"))
    self.assertEqual(shopify_changes(ShopifyState((), (p,), (p,))), [])

def test_apply_keeps_other_tags(self):
    self.assertEqual(apply_tag_change("blu-ray, fantasy", {"new arrival"}, ()), "blu-ray, fantasy, new arrival")

def test_apply_removes_case_insensitively(self):
    self.assertEqual(apply_tag_change("blu-ray, New Arrival, Drama", (), {"new arrival"}), "blu-ray, Drama")

def test_apply_is_idempotent(self):
    self.assertEqual(apply_tag_change("drama, new arrival", {"new arrival"}, ()), "drama, new arrival")
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m unittest tests.catalog.test_libib_tags -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'catalog.libib.tags'`

- [ ] **Step 3: Implement `catalog/libib/tags.py`.** Rules the tests don't fully pin:
  - Build a barcode → set-of-item-ids index from items with a non-blank `barcode`. A barcode on more than one item makes all those items "excluded": they get no change in either direction, and there's one `Unmatched(title_of_first, f"barcode is on {n} Libib items")` per barcode.
  - Desired Libib tags per item: `new arrival` if any `new_arrivals` product's barcode maps to exactly that one item; `community pick` likewise from `picked`, but only for `is_rental` products. Non-rental picks are skipped silently. A `new_arrivals` or rental `picked` product with no barcode, or with no barcode matching any item, gives one `Unmatched` each.
  - Change per non-excluded item: `current = normalized_tag_set(tags) & MANAGED_LIBIB_TAGS`, `add = desired - current`, `remove = current - desired`. Emit only when either set is non-empty.
  - `shopify_changes`: `add` for `picked` products whose tags lack `community-pick`; `remove` for `tagged_picks` products whose id isn't in `picked`. De-duplicate by product id, sort by title then id.
  - `apply_tag_change`: split on `,`, strip, drop blanks. Drop tokens whose lowercase form is in `remove`, and duplicates by lowercase. Keep the remaining tokens in their original order and case. Append each `add` tag not already present, sorted. Join with `", "`.

- [ ] **Step 4: Run them and confirm they pass**

Run: `python3 -m unittest tests.catalog.test_libib_tags -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add catalog/libib/tags.py tests/catalog/test_libib_tags.py
git commit -m "libib tags: reconciliation logic for new arrival / community pick"
```

---

### Task 2: Shopify reads and writes

**Files:**
- Create: `catalog/libib/tags_shopify.py`
- Test: `tests/catalog/test_libib_tags_shopify.py`

**Interfaces:**
- Consumes: `Product`, `ShopifyState`, `ShopifyChange`, `SHOPIFY_NEW_ARRIVAL`, `SHOPIFY_COMMUNITY_PICK` from Task 1; `catalog.shopify.writer.ApiStore` (`.gql(query, **variables) -> dict`, which raises `RuntimeError` on GraphQL `errors`); `catalog.shopify.api.request_token`, `make_executor`.
- Produces:
  - `read_state(gql: Callable[..., dict]) -> ShopifyState`, where `gql` has the signature of `ApiStore.gql`
  - `write_changes(gql, changes: list[ShopifyChange]) -> list[dict]`. Each result is `{"title", "action", "status": "updated"|"error", "message"}`.
  - `store_from_env(store: str) -> ApiStore`, using `config.require_env(ENV_SHOPIFY_CLIENT_ID / ENV_SHOPIFY_CLIENT_SECRET)`

- [ ] **Step 1: Write the failing tests** with a fake `gql` that returns canned pages keyed by query text, and records mutation calls.

```python
def test_reads_new_arrivals_with_exact_tag_only(self):
    # tag:new-arrival search may also return e.g. "new-arrival-old"; keep exact matches only
    state = read_state(fake_gql(new_arrivals=[node("p1", tags=["Rental", "new-arrival"], barcodes=["111"]),
                                              node("p2", tags=["Rental", "new-arrival-old"])]))
    self.assertEqual([p.id for p in state.new_arrivals], ["p1"])
    self.assertEqual(state.new_arrivals[0].barcodes, ("111",))

def test_paginates_products(self):  # two pages via pageInfo.hasNextPage / endCursor
    ...assert both pages' products are present

def test_only_active_picks_with_a_product_count(self):
    state = read_state(fake_gql(picks=[pick("ACTIVE", node("p1")), pick("DRAFT", node("p2")),
                                       pick("ACTIVE", None)]))
    self.assertEqual([p.id for p in state.picked], ["p1"])

def test_pick_without_publishable_capability_counts_as_active(self):
    state = read_state(fake_gql(picks=[pick(None, node("p1"))]))
    self.assertEqual([p.id for p in state.picked], ["p1"])

def test_graphql_error_propagates(self):
    with self.assertRaises(RuntimeError):
        read_state(failing_gql())

def test_write_uses_tags_add_and_tags_remove(self):
    gql = fake_gql()
    write_changes(gql, [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "remove")])
    self.assertEqual(gql.mutations, [("tagsAdd", "p1", ["community-pick"]), ("tagsRemove", "p2", ["community-pick"])])

def test_write_records_user_errors_and_continues(self):
    results = write_changes(fake_gql(user_error_for="p1"),
                            [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "add")])
    self.assertEqual([r["status"] for r in results], ["error", "updated"])
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m unittest tests.catalog.test_libib_tags_shopify -v`
Expected: ERROR, module not found

- [ ] **Step 3: Implement `catalog/libib/tags_shopify.py`.** Queries:
  - `products(first: 250, after: $after, query: $q)` with `q` = `"tag:new-arrival"`, then `"tag:community-pick"`. Select `nodes { id title tags variants(first: 10) { nodes { barcode } } } pageInfo { hasNextPage endCursor }`. Keep only nodes whose `tags` contain the exact tag. Blank barcodes are dropped.
  - `metaobjects(type: "community_pick", first: 250, after: $after)` with `nodes { capabilities { publishable { status } } field(key: "product") { reference { ... on Product { id title tags variants(first: 10) { nodes { barcode } } } } } }`. An entry counts when the status is `ACTIVE` or the capability is absent, and the reference is non-null.
  - Mutations: `tagsAdd(id: $id, tags: $tags) { userErrors { message } }` and `tagsRemove(...)`. A non-empty `userErrors` or a raised exception gives an `error` result for that product, and the loop continues.
  - `store_from_env`: `ApiStore(api.make_executor(store, api.request_token(store, id, secret)), store)`.

- [ ] **Step 4: Run them and confirm they pass**

Run: `python3 -m unittest tests.catalog.test_libib_tags_shopify -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add catalog/libib/tags_shopify.py tests/catalog/test_libib_tags_shopify.py
git commit -m "libib tags: Shopify reads (new arrivals, community picks) and tag writes"
```

---

### Task 3: Libib browser steps, selftest check, live probe

**Files:**
- Modify: `catalog/libib/browser.py` (around `open_item`, lines 72–102)
- Create: `catalog/libib/tag_editor.py`
- Modify: `catalog/libib/selftest.py` (`build_checks`, `run_selftest`), `catalog/libib/command.py` (selftest parser and `run_selftest_command`)
- Test: `tests/catalog/test_libib_playwright.py` (venv-message case), `tests/catalog/test_libib_command.py` (selftest `--barcode` passthrough)

**Interfaces:**
- Consumes: `LibibChange`, `apply_tag_change` (Task 1); `normalized_tag_set`; the existing `_open_edit_section(page, selector, section)`.
- Produces:
  - `browser.BARCODE_SEARCH = "{barcode}"`. This is the search text format, and the probe in Step 5 may change it.
  - `browser.open_item_by_barcode(page, barcode: str, verify: bool = True) -> tuple[str, str] | None`. `None` means opened. With `verify`, it opens the Copies panel and returns `("error", "search hit is a different item")` unless the first copy row's barcode input equals `barcode`.
  - `browser.set_item_tags(page, barcode: str, add: frozenset[str], remove: frozenset[str]) -> tuple[str, str]`, returning status `updated` / `skipped` / `error`.
  - `tag_editor.run_tag_editor(changes: list[LibibChange], report_path, email: str, password: str, headless: bool) -> list[dict]`. Report columns are `item_id, title, add, remove, status, message`, with **no barcode column**.
  - `selftest.run_selftest(email, password, call_number, evidence_dir, headless=True, include_import_page=True, barcode: str | None = None)`. `barcode` defaults to `call_number`.

- [ ] **Step 1: Write the failing tests.** In `test_libib_playwright.py`, add `test_tags` asserting `run_tag_editor([...], Path("/tmp/r.csv"), "e", "p", True)` raises the venv `CatalogError` naming `.venv-libib/bin/python -m catalog libib tags`. In `test_libib_command.py`, assert that `libib selftest --call-number 01111111 --barcode 2010000002155` calls the injected runner with `barcode="2010000002155"`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m unittest tests.catalog.test_libib_playwright tests.catalog.test_libib_command -v`
Expected: the two new tests FAIL or ERROR

- [ ] **Step 3: Implement.**
  - In `browser.py`, extract the body of `open_item` into `_open_search(page, query: str, what: str)`, and make `open_item` call `_open_search(page, f"call:{call_number}", "call number")` with unchanged messages. `open_item_by_barcode` calls `_open_search(page, BARCODE_SEARCH.format(barcode=barcode), "barcode")`, then verifies as described above.
  - `set_item_tags` does the following:
    1. Open with verify, then reopen with `verify=False`, because the Copies panel leaves the Edit button unreliable (see `sync_item`).
    2. `_open_edit_section(page, "input.tags-autocomplete[name='tags']", "tng-section")`.
    3. Compute `new = apply_tag_change(field.input_value(), add, remove)`. If its normalized set equals the current one, return `skipped`.
    4. Otherwise `fill(new)`, click `input#edit-item-submit`, and wait 1000 ms.
    5. Reopen, read the tags field again, then `page.goto(LIBIB_SETTINGS_URL)` to leave without saving.
    6. Return `error` with `"tags did not persist"` unless the normalized sets match.
  - Messages never include the barcode.
  - `tag_editor.run_tag_editor` mirrors `fix.run_fixer`: `venv.sync_playwright("tags")`, one login, retries via `fix.ITEM_ATTEMPTS` / `RETRY_PAUSE_MS`, the CSV report flushed per row, and `log.progress(index, total, title, ...)`.
  - Selftest gets a check `("search by barcode", ...)` right after `"search by call number"`, calling `open_item_by_barcode(page, barcode, verify=True)`. Add a `--barcode` option to the selftest parser (help: "copy barcode for the barcode-search check (default: the call number)").

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: OK

- [ ] **Step 5: Live probe on the client's Libib account (read-only).** Run both commands:

```bash
.venv-libib/bin/python -m catalog libib selftest --skip-import-matching
.venv-libib/bin/python -m catalog libib selftest --skip-import-matching --barcode 2010000002155
```

`2010000002155` is The Curse, a new-flow item with an empty call number. The second command still uses the default call number for the other checks.
Expected: both print `OK: all N steps work.`
- If "search by barcode" fails on either one, retry with `BARCODE_SEARCH = "barcode:{barcode}"`.
- If neither format gives exactly one verified hit for both a legacy 8-digit barcode and a `201…` barcode, **stop and report to the user**. The spec says writing `call_number` needs their approval.

- [ ] **Step 6: Commit**

```bash
git add catalog/libib/browser.py catalog/libib/tag_editor.py catalog/libib/selftest.py catalog/libib/command.py tests/catalog/test_libib_playwright.py tests/catalog/test_libib_command.py
git commit -m "libib: open items by barcode, tags-only edit, selftest barcode-search check"
```

---

### Task 4: `libib tags` command

**Files:**
- Create: `catalog/libib/tags_command.py`
- Modify: `catalog/libib/command.py` (`register`: add `tags_command.register(sub)` before `status`)
- Modify: `.gitignore` (add `libib-tags/`)
- Test: `tests/catalog/test_libib_tags_command.py`

**Interfaces:**
- Consumes: Tasks 1–3; `transfer.run_browser_export(email, password, dest_dir, headless) -> (barcodes, collection)`; `exports.load_libib`; `plan.Plan`, `plan.confirm`, `plan.add_approval_args`, `plan.ApprovalRefused`.
- Produces:
  - `DEFAULT_MAX_CHANGES = 25`
  - `@dataclass class TagDeps: read_shopify: Callable[[], ShopifyState]; export_libib: Callable[[Path], tuple[Path, Path]]; write_shopify: Callable[[list[ShopifyChange]], list[dict]]; edit_libib: Callable[[list[LibibChange], Path], list[dict]]`
  - `default_deps(args) -> TagDeps`, wired to `store_from_env(args.store)`, `run_browser_export`, `write_changes`, `run_tag_editor` (headless from `args.headless`)
  - `run_tags_command(args, deps: TagDeps | None = None) -> int`
  - CLI: `libib tags [--dry-run] [--approve CODE] [--unattended] [--max-changes N] [--store S] [--headless] [--report-dir DIR]`. `--report-dir` defaults to `libib-tags/`. `--unattended` and `--approve` are mutually exclusive.

- [ ] **Step 1: Write the failing tests.** Fakes record calls. The `_approval` patch pins the fingerprint to `"ok"`, as in `test_libib_command.py`.

```python
def test_unattended_under_limit_applies_without_prompt(self):
    code = run(["--unattended"], changes=3)
    self.assertEqual(code, 0); self.assertTrue(deps.edit_libib.called); self.assertTrue(deps.write_shopify.called)

def test_unattended_over_limit_changes_nothing_and_exits_2(self):
    code = run(["--unattended", "--max-changes", "2"], changes=3)
    self.assertEqual(code, 2); self.assertFalse(deps.edit_libib.called); self.assertFalse(deps.write_shopify.called)

def test_over_limit_proceeds_with_approval_code(self):
    self.assertEqual(run(["--approve", "ok"], changes=30), 0)

def test_dry_run_changes_nothing(self):
    self.assertEqual(run(["--dry-run"], changes=3), 0); self.assertFalse(deps.edit_libib.called)

def test_no_terminal_and_no_flag_refuses(self):
    with self.assertRaises(ApprovalRefused): run([], changes=1, stdin=io.StringIO())

def test_nothing_to_change_skips_browser(self):
    self.assertEqual(run(["--unattended"], changes=0), 0); self.assertFalse(deps.edit_libib.called)

def test_empty_libib_export_aborts_before_writes(self):
    with self.assertRaises(InputShapeError): run(["--unattended"], libib_rows=0)
    self.assertFalse(deps.write_shopify.called)

def test_shopify_read_error_aborts_before_export(self):
    with self.assertRaises(RuntimeError): run(["--unattended"], shopify_error=True)
    self.assertFalse(deps.export_libib.called)

def test_any_item_error_exits_1(self):
    self.assertEqual(run(["--unattended"], changes=2, libib_statuses=["updated", "error"]), 1)

def test_output_never_contains_barcodes(self):
    out = run_capturing(["--dry-run"], changes=2, unmatched=1)   # fixture barcodes like "92029178"
    self.assertNotIn("92029178", out)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m unittest tests.catalog.test_libib_tags_command -v`
Expected: ERROR, module not found

- [ ] **Step 3: Implement `run_tags_command`.** The order matters:
  1. `deps.read_shopify()` comes first, so a Shopify failure stops the run before Libib is touched.
  2. Export Libib into a `tempfile.TemporaryDirectory()`, so no export files are left behind.
  3. `load_libib(...)`. Zero items raises `InputShapeError("Libib export has no Rental Library items — not changing anything")`.
  4. Compute `libib_changes` and `shopify_changes`.
  5. Build `Plan(title="libib tags", count=len(libib)+len(shopify), summary=[counts…], samples=[...], warnings=[f"unmatched: {u.title} — {u.reason}" …])`. Sample lines look like `libib   + new arrival  − community pick   Legend  [item 0cpkzfbdcu]` and `shopify + community-pick   Legend`.
  6. Decide whether to proceed:
     - `--dry-run`: `confirm(dry_run=True)`, return 0.
     - `--unattended` with count > `max_changes`: log `"{count} changes is over the unattended limit of {max} — nothing changed. Review with --dry-run and re-run with --approve <code>."` and return 2.
     - `--unattended` within the limit: `confirm(plan, dry_run=False, preapproved=True)`.
     - Otherwise: `confirm(plan, dry_run=False, approve=args.approve)`.
  7. Shopify writes, then `deps.edit_libib(changes, report_dir / f"{timestamp}.csv")`.
  8. Log a summary of updated, skipped and error counts. Return 1 if any result has status `error`, else 0.
  
  A `confirm` that returns False (count 0, or declined) returns 0.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: OK

- [ ] **Step 5: Dry run against production (read-only):** `.venv-libib/bin/python -m catalog libib tags --dry-run --headless`
Expected: the change list prints, followed by an approval code. Don't approve yet; the first real run belongs to Task 6.

- [ ] **Step 6: Commit**

```bash
git add catalog/libib/tags_command.py catalog/libib/command.py .gitignore tests/catalog/test_libib_tags_command.py
git commit -m "libib tags: command with dry run, approval, and unattended change limit"
```

---

### Task 5: Daily workflow and docs

**Files:**
- Create: `.github/workflows/libib-tags.yml`
- Modify: `catalog/README.md` (new subsection under "Stage 4 — Libib"), `claudedocs/lms-admin-instructions.md` (Community Picks client steps 7 and the "To remove…" paragraph, plus one line in New Arrivals)

- [ ] **Step 1: Write the workflow.** Base it on the draft in `claudedocs/2026-09-29-libib-selftest-github-actions.md`:
  - `on: schedule: - cron: "0 12 * * *"` (12:00 UTC; Task 6 may move it) and `workflow_dispatch`.
  - `permissions: contents: read`, `concurrency: { group: libib, cancel-in-progress: false }`, `timeout-minutes: 45`.
  - Steps: checkout → setup-python `3.11` → `pip install playwright` → `python -m playwright install --with-deps chromium` → `python -m catalog libib selftest --skip-import-matching` → `python -m catalog libib tags --unattended --headless`.
  - Env from secrets: `LIBIB_EMAIL`, `LIBIB_PASSWORD`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`.
  - No artifact upload.

- [ ] **Step 2: Validate the YAML:** `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/libib-tags.yml'))"` (if PyYAML is missing, use `ruby -ryaml -e 'YAML.load_file(".github/workflows/libib-tags.yml")'`). Expected: no output.

- [ ] **Step 3: Update the docs.**
  - README: what `libib tags` does, the four flags, the 25 limit and how to get past it, and that it runs daily from Actions.
  - Admin instructions:
    - Replace Community Pick step 7 with "The `community-pick` product tag and the Libib `community pick` tag are added automatically within a day. Don't add them by hand."
    - Change "To remove… also remove the tag" to say removal is automatic too.
    - Under New Arrivals, add "The Libib public page mirrors this as the `new arrival` tag, within a day."

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/libib-tags.yml catalog/README.md claudedocs/lms-admin-instructions.md
git commit -m "libib tags: daily GitHub Actions run and client docs"
```

---

### Task 6: Production rollout (needs the user, writes to production) — run AFTER Task 9

Each write step needs the user's go-ahead in the moment.

- [ ] **Step 1: The user turns off** the "New Arrival tag auto-expiry (daily sweep)" Flow on production, because the job now owns expiry (spec "New arrivals"). "New Arrival auto-tag" stays on. Keep the cron at 12:00 UTC.
- [ ] **Step 2: Check the Shopify app's scopes.** The app behind `SHOPIFY_CLIENT_ID` must have `write_products` and `read_metaobjects` (`config.py` calls the pipeline app read-only, while `tools/rental-sync/README.md` lists writes). If unsure, run Step 4 on one Shopify change first. A 403 means adding the scope in the Dev Dashboard.
- [ ] **Step 3: Record a `join_id`.** Pick one item from the dry-run list and record its `join_id` via the public search (`claudedocs/2026-10-13-libib-item-links-join-id.md`).
- [ ] **Step 4: First real run, locally.** Run `--dry-run`, show the list to the user, then run `--approve <code>` after they agree.
  Expected: exit 0, every row `updated` or `skipped`.
- [ ] **Step 5: Verify.**
  - The Libib public page shows `new arrival` / `community pick` on the expected titles.
  - The Shopify shop-all "Community picks" toggle still works.
  - The Step 3 item's `join_id` is unchanged. If it changed, tell the user, because stored Libib links break.
- [ ] **Step 6: Merge.** The user adds the four repo secrets (Settings → Secrets and variables → Actions). Merge the branch to `main`, since scheduled workflows run only from the default branch. Then Actions → "Libib tags" → Run workflow.
  Expected: green, and the log ends with nothing to change or a small update count.
- [ ] **Step 7: Tell the user** that GitHub disables scheduled workflows after 60 days with no repo activity, and that the failure email goes to whoever last edited the workflow file.

---

## Part 2 — newest titles, adjustable settings (revised 2026-10-20)

The spec's "New arrivals" section replaces Goal 1's mirroring: the job picks the newest `count` titles itself, in both Shopify and Libib. Tasks 7–9 change Tasks 1, 2 and 4's code. Task 6 runs after them.

### Task 7: Settings file

**Files:**
- Create: `catalog/libib/tag_settings.json`, `catalog/libib/tag_settings.py`
- Test: `tests/catalog/test_libib_tag_settings.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class TagSettings: new_arrivals_count: int; new_arrivals_max_age_days: int | None; max_changes: int`; `SETTINGS_PATH = Path(__file__).with_name("tag_settings.json")`; `load_settings(path=SETTINGS_PATH) -> TagSettings`.
- JSON shape: `{"new_arrivals": {"count": 50, "max_age_days": null}, "max_changes": 125}`.

- [ ] **Step 1: Write the failing tests.**
  - `test_shipped_file_loads` gives `TagSettings(50, None, 125)`.
  - `test_max_age_days_number` gives `7`.
  - `test_rejects_zero_count`, `test_rejects_non_integer_count` (`"50"`), `test_rejects_negative_max_age`, `test_rejects_missing_key` and `test_rejects_bad_json` each raise `InputShapeError`, with a message naming the file and the key.
- [ ] **Step 2: Run the tests and confirm they fail:** `python3 -m unittest tests.catalog.test_libib_tag_settings -v`. Expected: ERROR, module not found.
- [ ] **Step 3: Implement.** `bool` is not accepted as an int.
- [ ] **Step 4: Run the tests and confirm they pass:** the same command passes.
- [ ] **Step 5: Commit** with "libib tags: adjustable settings file".

### Task 8: Newest-titles logic

**Files:**
- Modify: `catalog/libib/tags.py`, `tests/catalog/test_libib_tags.py`

**Interfaces:**
- Consumes: `TagSettings` (Task 7). From `catalog.duplicates.match`: `normalize_title`, `title_year`, `product_format`.
- Produces:
  - `Product` gains `vendor: str = ""` and `created_at: str = ""` (ISO 8601 from Shopify), added after `barcodes`.
  - `ShopifyState(rentals, picked, tagged_picks, tagged_new_arrivals=())`. `rentals` holds every `Rental` product and replaces `new_arrivals`.
  - `ShopifyChange(product_id, title, tag, action)` gains a `tag` field.
  - `title_key(p: Product) -> tuple[str, str, str]`
  - `@dataclass(frozen=True) class TagPlan: libib: list[LibibChange]; shopify: list[ShopifyChange]; unmatched: list[Unmatched]; new_arrival_titles: int`
  - `plan_tags(items: list[dict], state: ShopifyState, settings: TagSettings, now: datetime) -> TagPlan`. This replaces `libib_changes`/`shopify_changes` as the entry point; both may stay as helpers.

- [ ] **Step 1: Update and write tests.** Rewrite the existing new-arrival tests against `plan_tags` with `TagSettings(count, None, 125)`, and add these:
  - `test_newest_titles_are_tagged_in_both_places`: 3 eligible titles, count 2. The two newest get Libib `+ new arrival` and Shopify `+ new-arrival`. The oldest gets nothing.
  - `test_copies_count_as_one_title`: 3 copies of "Legend" (VHS) plus 1 "Alien" (VHS), count 2. All 4 products are tagged.
  - `test_format_and_year_separate_titles`: "Legend" VHS and "Legend" DVD are 2 titles; "Halloween (1978)" and "Halloween (2018)" are 2 titles.
  - `test_title_age_is_its_first_copy`: an old title gets a new copy. It isn't among the newest, and its new copy isn't tagged.
  - `test_old_title_drops_out_when_newer_arrive`: a currently tagged item and product outside the top `count` get removals.
  - `test_not_in_libib_or_not_rental_loses_shopify_tag`: `tagged_new_arrivals` contains a Floor Sale product and a rental with no Libib item, and both get Shopify `- new-arrival`. Neither takes a slot.
  - `test_max_age_days_drops_old_titles`: with `now` fixed, `max_age_days=7` and count 50, a title created 8 days ago isn't tagged and one created 6 days ago is.
  - `test_ambiguous_barcode_rental_is_not_eligible`.
  - `test_rentals_missing_from_libib_are_not_listed_unmatched`, to avoid noise from the whole catalogue.
  - Update the Shopify Community Pick tests for `ShopifyChange`'s new `tag` field.
- [ ] **Step 2: Run the tests and confirm the new ones fail:** `python3 -m unittest tests.catalog.test_libib_tags -v`.
- [ ] **Step 3: Implement.**
  - **Eligible:** an `is_rental` product with a barcode that maps to exactly one, non-excluded Libib item.
  - **Group:** by `title_key`. Arrival = `min(created_at)` across the group.
  - **Filter and sort:** drop groups older than `max_age_days` when it's set. Sort the rest by arrival, newest first, ties broken by key, and take `count`.
  - **Desired sets:** the Shopify desired set is those groups' product ids. The Libib desired set is their item ids.
  - **Community Picks:** keep the existing rules. The two Shopify tags are separate `ShopifyChange`s.
  - **Order:** keep sorting by title, then id.
- [ ] **Step 4: Run the full suite and confirm it passes:** `python3 -m unittest discover -s tests/catalog -p "test_*.py"`. Expected: OK. The command and Shopify tests are updated in Task 9, so run this after Task 9 if the signatures break them first.
- [ ] **Step 5: Commit** with "libib tags: newest N titles are new arrivals, in Shopify and Libib".

### Task 9: Shopify reads, command, workflow, docs

**Files:**
- Modify: `catalog/libib/tags_shopify.py`, `catalog/libib/tags_command.py`, `.github/workflows/libib-tags.yml`, `catalog/README.md`, `claudedocs/lms-admin-instructions.md`
- Test: `tests/catalog/test_libib_tags_shopify.py`, `tests/catalog/test_libib_tags_command.py`

**Interfaces:**
- Consumes: Tasks 7–8.
- Produces:
  - `read_state(gql) -> ShopifyState` reads `tag:Rental`, keeping exact `Rental` matches compared case-insensitively. It also reads `vendor` and `createdAt`, plus `tag:new-arrival` and the picks. Zero rentals raises `InputShapeError("Shopify returned no Rental products — not changing anything")`.
  - `write_changes` writes `change.tag`.
  - `TagDeps` gains `now: Callable[[], datetime]`, defaulting to UTC now.
  - The `--max-changes` default comes from `load_settings().max_changes`. A new `--settings PATH` option overrides the settings file.

- [ ] **Step 1: Write and update the tests.**
  - `test_zero_rentals_raises`, `test_reads_vendor_and_created_at`, `test_writes_change_tag`.
  - The command tests switch to `rentals=...`.
  - `test_max_changes_default_comes_from_settings` uses a temp settings file with `max_changes: 2`, 3 changes and `--unattended`, and expects exit 2.
  - `test_summary_names_the_new_arrival_rule` expects output containing `newest 50 titles`.
- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement.**
  - The workflow gets `timeout-minutes: 120`.
  - README: the new rule and the settings file.
  - Admin instructions, New Arrivals section: "the newest 50 titles (set in `catalog/libib/tag_settings.json`), all copies; older titles drop out as new ones arrive; the 7-day expiry Flow is off."
- [ ] **Step 4: Run the full suite, then a read-only production dry run:** `.venv-libib/bin/python -m catalog libib tags --dry-run --headless`. Expected: the dry run says the newest 50 titles get `new arrival`, and lists the Shopify `- new-arrival` removals.
- [ ] **Step 5: Commit** with "libib tags: settings-driven new arrivals in the command, workflow and docs".
