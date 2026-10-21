# Homepage links to Libib — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Shopify homepage send customers to the public Libib page:
- the movie posters open their own Libib item
- "Rental Library", "BROWSE THE LIBRARY", "View all" and "+ N more" open the Libib main page

**Architecture:**
- **The job:** the daily `libib tags` job already matches each `new-arrival` / `community-pick` product to one Libib item. It gains a lookup step: it searches the public Libib page by that item's copy barcode, finds the item's `join_id`, and plans `custom.libib_join_id` metafield writes. Those writes go into the existing approval `Plan`.
- **The theme:** one snippet builds the Libib URL, and the two homepage sections use it for every poster. The hero, footer and menu links are setting/admin changes.

**Tech Stack:** Python 3 stdlib (`urllib`, `unittest`), Shopify Admin GraphQL `2026-07`, Shopify Liquid (Horizon 4.1.1).

**Spec:** `docs/superpowers/specs/2026-10-20-libib-poster-links-design.md`

## Global Constraints

- **Libib URLs:**
  - Libib base URL: `https://www.libib.com/u/littlemoviestore`
  - item URL: `https://www.libib.com/u/littlemoviestore?id=<join_id>`
  - lookup: `POST https://www.libib.com/u/littlemoviestore/search` with form fields `keywords=<copy barcode>&library_id=2603141&offset=0&limit=50`. Join ids are the unique `data-join-id="(\d+)"` values in the response's `item-info`.
- **Metafield:** `custom.libib_join_id`, type `number_integer`, storefront `PUBLIC_READ`.
- **No barcode or call number in anything printed, logged, raised, reported or committed.** The repo and its Actions logs are public. Identify items by product title, Libib item id and `join_id`.
- **Fallbacks and same tab:** a homepage poster with no `join_id` links to the Libib base URL. All Libib links open in the same tab (no `target`).
- **Never stop the tag work.** A failed lookup never stops tag changes, and it keeps the stored value.
- **Guarded clears.** A value is cleared only when its own lookup succeeded with zero hits, at least one lookup in the same run returned exactly one hit, and the run would clear no more than **10** values. Otherwise every clear is dropped, with one warning.
- **Throttle:** leave 0.5 s between lookups.
- **Production rules:**
  - Production (`p0wkgv-wy.myshopify.com`, live theme `166751961338`) is the target.
  - Confirm the live theme with `shopify theme list`.
  - Pull before every push, and push with `--only <files> --allow-live`.
  - Every production write gets the user's approval first.
- **Work location:** work only in `.worktrees/libib-poster-links` (branch `feature/libib-poster-links`). Never `git checkout` in the main folder.
- **Test commands:**
  - `python3 -m unittest discover -s tests/catalog -p "test_*.py"` must pass. It passes today.
  - `shopify theme check --path theme/lms-redesign-v4` must report no new offenses.

## Review Focus

1. **The endpoint replies with something unexpected.** For example an HTML error page, `outcome: error`, or a timeout. Expected: the lookup counts as *failed*, not as zero hits, so nothing is cleared. Covered by `test_non_json_reply_is_a_failure` and `test_failed_lookup_keeps_stored_value` (Task 2).
2. **Every lookup returns zero** because the endpoint changed. Expected: no clears, one warning. Covered by `test_no_clears_without_a_successful_lookup` (Task 2).
3. **A Community Pick that is also a new arrival** shows up as one target. Expected: one lookup and one write. Covered by `test_product_in_both_lists_is_one_target` (Task 1).
4. **A `LookupFailed` message carrying the barcode.** For example, urllib's error text echoing the request body. Expected: the barcode never appears. Covered by `test_errors_never_contain_the_barcode` (Task 2) and `test_output_never_contains_barcodes`, extended in Task 4.
5. **A stored value that's a string or blank in Shopify** (`metafield.value` is always a string). Expected: it's parsed to an `int`, or `None` when blank or not a number, and never compared as a string. Covered by `test_join_id_metafield_is_parsed` (Task 3).

---

## File structure

| File | Role |
|---|---|
| `catalog/libib/links.py` (new) | The join_id lookup over HTTP and the pure planning of metafield changes |
| `catalog/libib/tags.py` | `Product.libib_join_id`, `LinkTarget`, `TagPlan.link_targets` (pure) |
| `catalog/libib/tags_shopify.py` | Read the metafield, and write it with `metafieldsSet` / `metafieldsDelete` |
| `catalog/libib/tags_command.py` | Wires the lookup into the run and the `Plan` |
| `catalog/libib/selftest.py` | Read-only "join_id lookup" check |
| `theme/lms-redesign-v4/snippets/lms-libib-url.liquid` (new) | Outputs the Libib base URL or item URL |
| `theme/lms-redesign-v4/snippets/lms-product-card.liquid` | `link_to_libib` parameter |
| `theme/lms-redesign-v4/sections/lms-new-releases.liquid` | Posters, "View all" and "+ N more" go to Libib |
| `theme/lms-redesign-v4/sections/lms-staff-picks.liquid` | Posters go to Libib |
| `theme/lms-redesign-v4/templates/index.json`, `sections/footer-group.json` | Hero button and footer link (merchant-editable: pull first) |

---

### Task 1: `tags.py` — link targets in the tag plan

**Files:**
- Modify: `catalog/libib/tags.py` (`Product`, `TagPlan`, `plan_tags`)
- Test: `tests/catalog/test_libib_tags.py`

**Interfaces:**
- Produces:
  - `Product.libib_join_id: int | None = None`, a new last field.
  - `@dataclass(frozen=True) LinkTarget(product_id: str, title: str, item_id: str, barcode: str, stored: int | None)`. `barcode` is never printed.
  - `TagPlan.link_targets: tuple[LinkTarget, ...] = ()`, a new last field.
  - `plan_tags` fills `link_targets`: one per product, by product id, for every product in `arrivals` plus every rental in `state.picked` whose `libib.item_for(p)` is set. The barcode is `libib.by_id[item_id]["barcode"]`. Sort by `(title.lower(), product_id)`.

- [ ] **Step 1: Write the failing tests** in `TestLinkTargets`, using the file's `item` / `product` / `state` / `plan` helpers.
  - `test_new_arrivals_and_picks_are_targets`: one new-arrival rental plus one picked rental, each matched to its own item. `{t.product_id for t in p.link_targets}` is both ids, and each `item_id` and `barcode` matches its item.
  - `test_product_in_both_lists_is_one_target`: the same product is new and picked, so there's exactly one target.
  - `test_floor_sale_pick_is_not_a_target`: a picked product tagged `("Floor Sale",)` gives no target.
  - `test_unmatched_pick_is_not_a_target`: a picked rental whose barcode isn't in Libib gives no target.
  - `test_stored_value_is_carried`: a `Product` with `libib_join_id=42` gives a target with `stored == 42`.

- [ ] **Step 2: Run the tests to verify they fail.** Run `python3 -m unittest tests.catalog.test_libib_tags -v`. Expected: the new tests fail on `AttributeError: link_targets`, and the existing tests still pass.

- [ ] **Step 3: Implement.** Add the fields and the dataclass, then build targets in `plan_tags` from the `arrivals` list and the picks loop it already has. Update the module docstring with one line about link targets.

- [ ] **Step 4: Run the tests to verify they pass.** Run `python3 -m unittest tests.catalog.test_libib_tags -v`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "libib tags: plan lists each homepage product's Libib item for link lookups"`

### Task 2: `links.py` — lookup and change planning

**Files:**
- Create: `catalog/libib/links.py`
- Test: `tests/catalog/test_libib_links.py`

**Interfaces:**
- Consumes: `catalog.libib.tags.LinkTarget` (Task 1) and `Unmatched`.
- Produces:
  - **Constants:** `SEARCH_URL = "https://www.libib.com/u/littlemoviestore/search"`, `LIBRARY_ID = "2603141"`, `MAX_CLEARS = 10`, `LOOKUP_DELAY = 0.5`
  - `class LookupFailed(Exception)`
  - `parse_join_ids(payload: dict) -> list[str]`: unique, in first-seen order. Raises `LookupFailed` when `payload.get("outcome") != "success"`.
  - `lookup_join_ids(barcode: str, urlopen=urllib.request.urlopen) -> list[str]`: POSTs the form, with a timeout of 30 s. Raises `LookupFailed` on any URL error, HTTP error or bad JSON. The message is the exception class name plus HTTP status only, never the request.
  - `@dataclass(frozen=True) JoinIdChange(product_id: str, title: str, item_id: str, old: int | None, new: int | None)`. `new is None` means clear.
  - `plan_join_ids(targets: Sequence[LinkTarget], lookup: Callable[[str], list[str]], sleep=time.sleep) -> tuple[list[JoinIdChange], list[Unmatched]]`

- [ ] **Step 1: Write the failing tests** in `tests/catalog/test_libib_links.py`. `t(pid, stored=None)` builds `LinkTarget(pid, f"Movie {pid}", f"item-{pid}", f"9202{pid}", stored)`. `lookup` is a fake that takes a dict `barcode -> list | Exception`. Pass `sleep=lambda s: None`.
  - `test_parse_unique_join_ids`: `parse_join_ids({"outcome": "success", "item-info": '<a data-join-id="5"></a><b data-join-id="5"></b><c data-join-id="7">'})` gives `["5", "7"]`.
  - `test_parse_error_outcome_raises`: `{"outcome": "error"}` raises `LookupFailed`.
  - `test_non_json_reply_is_a_failure`: a fake `urlopen` returning `b"<html>"` raises `LookupFailed`.
  - `test_errors_never_contain_the_barcode`: a fake `urlopen` raising `urllib.error.URLError("keywords=92021234")` raises `LookupFailed` whose `str()` doesn't contain `"92021234"`.
  - `test_one_hit_sets_value`: target `stored=None`, lookup `["169565504"]` gives `[JoinIdChange(pid, title, item, None, 169565504)]`.
  - `test_unchanged_value_makes_no_change`: `stored=169565504`, lookup `["169565504"]` gives no changes.
  - `test_several_hits_keep_value_and_report`: `stored=1`, lookup `["2", "3"]` gives no changes and one `Unmatched` whose reason contains `"2 Libib items"`.
  - `test_zero_hits_clears_when_another_lookup_succeeded`: two targets, A `stored=9` → `[]` and B → `["4"]`. The result includes `JoinIdChange(A…, 9, None)`.
  - `test_no_clears_without_a_successful_lookup`: two targets, both stored and both `[]`. No changes, and exactly one `Unmatched` warning containing `"no lookup succeeded"`.
  - `test_too_many_clears_are_all_dropped`: 11 stored targets → `[]` plus one → `["4"]`. The changes are only the set for the last target, and one warning contains `"11"` and `"10"`.
  - `test_failed_lookup_keeps_stored_value`: `stored=9` and the lookup raises `LookupFailed("HTTPError 503")`. No changes, and one `Unmatched` whose reason contains `"HTTPError 503"`.
  - `test_zero_hits_without_stored_value_is_reported_only`: `stored=None`, `[]` gives no changes and one `Unmatched` `"not found on the public Libib page"`.

- [ ] **Step 2: Run the tests to verify they fail.** Run `python3 -m unittest tests.catalog.test_libib_links -v`. Expected: `ModuleNotFoundError: catalog.libib.links`.

- [ ] **Step 3: Implement `links.py`.**
  - Request: encode the body with `urllib.parse.urlencode`, and send header `Content-Type: application/x-www-form-urlencoded`.
  - Parsing: `re.findall(r'data-join-id="(\d+)"', payload.get("item-info", ""))`, de-duplicated in order.
  - `plan_join_ids` makes one pass that classifies each target as ok / several / zero / failed, sleeping `LOOKUP_DELAY` between lookups. It then applies the clear guard from Global Constraints. Module docstring: say why the endpoint is unofficial and that no barcode is ever printed.

- [ ] **Step 4: Run the tests to verify they pass.** Run `python3 -m unittest tests.catalog.test_libib_links -v`. Expected: all pass.

- [ ] **Step 5: Commit.**
  ```bash
  git add catalog/libib/links.py tests/catalog/test_libib_links.py
  git commit -m "libib links: look up join_ids on the public page and plan metafield changes"
  ```

### Task 3: `tags_shopify.py` — read and write the metafield

**Files:**
- Modify: `catalog/libib/tags_shopify.py`
- Test: `tests/catalog/test_libib_tags_shopify.py`

**Interfaces:**
- Consumes: `JoinIdChange` (Task 2) and `Product.libib_join_id` (Task 1).
- Produces:
  - `PRODUCTS` and `COMMUNITY_PICKS` also select `libibJoinId: metafield(namespace: "custom", key: "libib_join_id") { value }`.
  - `_product` sets `libib_join_id` from that value: `int(value)` when it's all digits, otherwise `None`.
  - `write_join_ids(gql: Gql, changes: list[JoinIdChange]) -> list[dict]`. Each result dict is `{"title", "tag": "libib_join_id", "action": "set"|"clear", "status": "updated"|"error", "message"}`, the same shape as `write_changes`.
  - **Set:** `metafieldsSet(metafields: [{ownerId, namespace: "custom", key: "libib_join_id", type: "number_integer", value: str(new)}])`.
  - **Clear:** `metafieldsDelete(metafields: [{ownerId, namespace: "custom", key: "libib_join_id"}])`.
  - Both read `userErrors { message }`. An exception becomes an error result, as in `write_changes`.

- [ ] **Step 1: Write the failing tests**, following the file's existing fake-`gql` pattern.
  - `test_join_id_metafield_is_parsed`: nodes with `libibJoinId` set to `{"value": "169565504"}`, `None`, `{"value": ""}` and `{"value": "abc"}` give `169565504`, `None`, `None` and `None`.
  - `test_write_join_ids_set_and_clear`: one set change and one clear change. The fake records two mutations, the first with `type == "number_integer"` and `value == "7"`, the second a delete. Both results have `status == "updated"`.
  - `test_write_join_ids_user_error`: a `userErrors` reply gives `status == "error"` with the message.

- [ ] **Step 2: Run the tests to verify they fail.** Run `python3 -m unittest tests.catalog.test_libib_tags_shopify -v`.

- [ ] **Step 3: Implement**, and update the module docstring to mention the metafield.

- [ ] **Step 4: Run the tests to verify they pass.** Same command. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "libib tags: read and write custom.libib_join_id"`

### Task 4: `tags_command.py` — the lookup in the run and the approval plan

**Files:**
- Modify: `catalog/libib/tags_command.py`
- Modify: `tests/catalog/test_libib_tags_command.py` (`Fakes.deps`, new tests)
- Modify: `claudedocs/2026-10-20-libib-tags-job-overview.md`. Add the lookup to "How a run works", and `links.py` to "Files". Add the endpoint caveat to "Hard constraints".

**Interfaces:**
- Consumes: `plan_join_ids`, `lookup_join_ids` and `JoinIdChange` (Task 2), `TagPlan.link_targets` (Task 1), `write_join_ids` (Task 3).
- Produces:
  - `TagDeps` gets two new **required** fields after `edit_libib`: `lookup_join_id: Callable[[str], list[str]]` and `write_join_ids: Callable[[list[JoinIdChange]], list[dict]]`.
  - `default_deps` wires `links.lookup_join_ids` and `lambda c: tags_shopify.write_join_ids(store.gql, c)`.

Run order after `plan_tags`:
1. `links, link_warnings = plan_join_ids(tags.link_targets, deps.lookup_join_id)`.
2. Add `len(links)` to the `Plan` `count`.
3. Add a summary line: `f"Libib links: {len(tags.link_targets)} looked up, {len(links)} to change"`.
4. Add sample lines: `f"link     set {c.new:<28} {c.title}  [item {c.item_id}]"` or `f"link     clear{'':<27} {c.title}  [item {c.item_id}]"`.
5. Add each warning as `f"link: {u.title} — {u.reason}"`.
6. After `confirm`, `results += deps.write_join_ids(links)` when `links` isn't empty. Do this after the Shopify tag writes and before the Libib edits.

Link writes don't count toward the unattended limit.

- [ ] **Step 1: Update `Fakes`.**
  - `Fakes.deps()` passes `self.lookup_join_id`, a fake that returns `self.join_ids.get(barcode, [])` (the `join_ids` dict comes from a new `join_ids=None` init option).
  - It also passes `self.write_join_ids`, which records the changes and returns updated results.
  - Confirm the existing tests still pass: `python3 -m unittest tests.catalog.test_libib_tags_command -v`.

- [ ] **Step 2: Write the failing tests.**
  - `test_dry_run_lists_link_changes_without_writing`: one new-arrival rental with `join_ids={barcode(0): ["555"]}`. The output contains `"link     set 555"`, and `write_join_ids` was never called.
  - `test_approved_run_writes_links`: the same setup with approval. `write_join_ids` received one `JoinIdChange` with `new == 555`.
  - `test_unattended_limit_ignores_link_writes`: `max_changes` is 0 Libib edits and there's one link change. The exit code isn't 2, and links are written.
  - Extend `test_output_never_contains_barcodes` so its run includes link lookups. No `barcode(i)` value appears in the output.

- [ ] **Step 3: Run the tests to verify they fail.** Run `python3 -m unittest tests.catalog.test_libib_tags_command -v`.

- [ ] **Step 4: Implement.** Also update the module docstring and the overview doc.

- [ ] **Step 5: Run the full suite.** Run `python3 -m unittest discover -s tests/catalog -p "test_*.py"`. Expected: all pass (975 plus the new tests).

- [ ] **Step 6: Commit.** `git commit -am "libib tags: look up and store each homepage product's Libib link"`

### Task 5: Selftest check for the lookup

**Files:**
- Modify: `catalog/libib/selftest.py` (`build_checks`)
- Test: `tests/catalog/test_libib_transfer.py` (the selftest tests near line 366)

**Interfaces:**
- Consumes: `links.lookup_join_ids` (Task 2).
- Produces: a check named `"join_id lookup"`, appended after `"search by barcode"`.
  - It calls `links.lookup_join_ids(barcode)`.
  - It raises `AssertionError(f"public search returned {n} items, expected 1")` unless exactly one id comes back.
  - It returns `"1 item"`.
  - It ignores `page`.

- [ ] **Step 1: Write the failing tests.**
  - `test_join_id_lookup_check_passes_on_one_hit`: patch `catalog.libib.links.lookup_join_ids` to return `["1"]`, then call `dict(build_checks("01111111", include_import_page=False))["join_id lookup"](None, {})`. It returns `"1 item"`.
  - `test_join_id_lookup_check_fails_on_zero`: the patch returns `[]`, so the check raises `AssertionError`, and the message doesn't contain `"01111111"`.

- [ ] **Step 2: Run the tests to verify they fail.** Run `python3 -m unittest tests.catalog.test_libib_transfer -v`.

- [ ] **Step 3: Implement.** If a test pins the ordered list of check names, update it.

- [ ] **Step 4: Run the full suite.** Run `python3 -m unittest discover -s tests/catalog -p "test_*.py"`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "libib selftest: check the public join_id lookup"`

### Task 6: Theme — homepage posters and New Arrivals buttons

**Files:**
- Create: `theme/lms-redesign-v4/snippets/lms-libib-url.liquid`
- Modify: `theme/lms-redesign-v4/snippets/lms-product-card.liquid` (the comment block, and the `<a href>` at line 57)
- Modify: `theme/lms-redesign-v4/sections/lms-new-releases.liquid` (the header comment, the card render, "View all", "+ N more")
- Modify: `theme/lms-redesign-v4/sections/lms-staff-picks.liquid` (the header comment, and the poster `<a>`)

**Interfaces:**
- Produces:
  - `{% render 'lms-libib-url', join_id: <int or blank> %}` outputs `https://www.libib.com/u/littlemoviestore`, plus `?id=<join_id>` when `join_id` isn't blank. No whitespace: use `{%- -%}`. The base URL is hardcoded in this one snippet.
  - Card parameter `link_to_libib` (boolean, default false). When it's true, the href is `{% render 'lms-libib-url', join_id: card_product.metafields.custom.libib_join_id.value %}`.

- [ ] **Step 1: Check for drift on production.** Pull the four existing files from production into a scratch dir:
  ```bash
  shopify theme pull --store p0wkgv-wy.myshopify.com --theme 166751961338 --path <scratch> --only snippets/lms-product-card.liquid --only sections/lms-new-releases.liquid --only sections/lms-staff-picks.liquid
  ```
  Diff each against `git show HEAD:<path>`. Expected: no differences. If there are any, stop and show the user.

- [ ] **Step 2: Implement.**
  - Create the snippet, and add the card parameter.
  - In `lms-new-releases`, pass `link_to_libib: true`. Point both buttons at `{% render 'lms-libib-url' %}`, and drop the now-unused `all_movies_url` guard on them.
  - In `lms-staff-picks`, set the poster `href` from `pick_product.metafields.custom.libib_join_id.value`.
  - Update the comments to describe the new targets.

- [ ] **Step 3: Lint.** Run `shopify theme check --path theme/lms-redesign-v4`. Expected: no new offenses in the four files.

- [ ] **Step 4: Check the rendered output on the dev store** (`lms-sandbox-lutsfahz.myshopify.com`, theme `142364311614`).
  - Push only these four files to the dev store. The CLAUDE.md dev-store rule allows this for testing; ask first if unsure.
  - Fetch the homepage with the storefront password (`Lms`) in a cookie jar.
  - Expected: every New Arrivals and Community Picks poster `href` starts with `https://www.libib.com/u/littlemoviestore`, and both New Arrivals buttons equal the base URL. Dev products have no `join_id`, so the posters show the base URL. This tests the fallback.

- [ ] **Step 5: Commit.** `git add theme/lms-redesign-v4/snippets theme/lms-redesign-v4/sections/lms-new-releases.liquid theme/lms-redesign-v4/sections/lms-staff-picks.liquid && git commit -m "theme: homepage posters and New Arrivals buttons open Libib"`

### Task 7: Hero button and footer link (merchant-editable files)

**Files:**
- Modify: `theme/lms-redesign-v4/templates/index.json`: the `button_secondary` link (`"shopify://collections/all-movies"`)
- Modify: `theme/lms-redesign-v4/sections/footer-group.json`: the `href="/collections/all-movies"` and `title="/collections/all-movies"` in the "Rental Library" rich-text

- [ ] **Step 1: Pull both files from production** into the worktree: `--only templates/index.json --only sections/footer-group.json`. Then run `git diff`. If there are incoming changes, commit them on their own first (`"theme: sync index.json and footer-group.json from production"`), so the next commit holds only our change.

- [ ] **Step 2: Edit the values.**
  - In `index.json`, set `button_secondary.settings.link` to `https://www.libib.com/u/littlemoviestore`.
  - In `footer-group.json`, set the Rental Library anchor's `href` to the same URL and drop its `title` attribute.
  - Use a JSON-aware edit. If either file has a leading `/* … */` comment, keep it.
  - `git diff` must show only these two values.

- [ ] **Step 3: Commit.** `git commit -am "theme: hero and footer Rental Library links go to Libib"`

### Task 8: Rollout on production (each step needs the user's go-ahead)

There's no code in this task. Every step is a production write, so state the target store and wait for approval before each one.

- [ ] **Step 1: Create the metafield definition.** Run this mutation once with the job's app credentials (`store_from_env("p0wkgv-wy.myshopify.com").gql`):
  ```graphql
  metafieldDefinitionCreate(definition: {name: "Libib join id", namespace: "custom", key: "libib_join_id", type: "number_integer", ownerType: PRODUCT, access: {storefront: PUBLIC_READ}})
  ```
  Expected: no `userErrors`.

- [ ] **Step 2: Dry run from the branch.** Run `.venv-libib/bin/python -m catalog libib tags --dry-run --headless`. Expected:
  - "Libib links: ~54 looked up, ~54 to change"
  - `link set …` lines
  - no tag changes beyond the day's normal ones
  - no barcodes in the output

  Show the user the summary and warnings.

- [ ] **Step 3: Approved run.** `--approve <code>`. Then spot-check 3 products in the admin. Each value should open the right movie at `https://www.libib.com/u/littlemoviestore?id=<value>`.

- [ ] **Step 4: Theme push.**
  - Run `shopify theme list` and confirm `166751961338` is `[live]`.
  - Re-pull the Task 6 and 7 files, and confirm there's no drift since then.
  - Push:
    ```bash
    shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme 166751961338 --only snippets/lms-libib-url.liquid --only snippets/lms-product-card.liquid --only sections/lms-new-releases.liquid --only sections/lms-staff-picks.liquid --only templates/index.json --only sections/footer-group.json --allow-live
    ```

- [ ] **Step 5: Verify the storefront.**
  - Fetch the production homepage with password `shaoff`.
  - Expected: New Arrivals and Community Picks posters link to `…?id=<digits>`, except Floor Sale picks, which link to the base URL. The hero, footer and New Arrivals buttons link to the base URL.

- [ ] **Step 6: Menu (manual).** In admin, Content → Menus → Main menu, change "Rental Library" to `https://www.libib.com/u/littlemoviestore`. The user or client does this by hand, not through the API. Then re-fetch the homepage and check the header link.

- [ ] **Step 7: Merge and follow the daily run.**
  - Merge the branch with superpowers:finishing-a-development-branch, so the daily Action runs the new job.
  - After the next scheduled run, check its log. The selftest should list "join_id lookup" passing, and `libib tags` should show "0 to change" for links.
