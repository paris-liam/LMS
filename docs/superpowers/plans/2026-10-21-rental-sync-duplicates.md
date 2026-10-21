# Rental sync duplicates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The rental sync app flags new Libib items that duplicate an existing Libib item, adds new copies of an already-synced Libib item to its Shopify product as a variant, and creates a new multi-copy Libib item as one product with a variant per copy.

**Architecture:** Detection stays in `prepare` (pure: Libib rows + Shopify barcode set). A new `matches.py` resolves sibling barcodes to Shopify products (I/O). A new `add_copy.py` adds a variant to an existing product. `create.py` moves from one copy to one Libib item (a group of copies). The browser gains two card types in step 3, groups copies by Libib item for create, and calls a new `add_copy` endpoint in step 5.

**Tech Stack:** Python 3 stdlib (`unittest`), Shopify Admin GraphQL (`config.SHOPIFY_API_VERSION`), vanilla JS (no build), `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-21-rental-sync-duplicates-design.md` (extends `docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`).

## Global Constraints

- Same movie = same title **and** same format (Libib format tag / Shopify Vendor).
- Shopify match is **by sibling barcode only** — no fuzzy Shopify search.
- Every match is client-approved; a Libib duplicate can always be dismissed with **"Not a duplicate"**.
- A sibling match offers **"Add as a copy of this product"** or **"Skip this run"** (never "create new").
- Variant fields for every copy: barcode = Libib `201…` barcode, price `0.00`, `taxable: false`, inventory tracked, `inventoryPolicy: DENY`, quantity `1` at the one location.
- `Genre` stays **Option 1**; the per-copy option is **Option 2**, named `Copy`, values `Copy 1`, `Copy 2`, … (next = highest existing number + 1).
- Adding a copy never changes title, description, Vendor, genre metafield, image, or existing variants; it adds the tag `Barcode Not Printed`.
- Server re-derives everything from Libib fields; the browser only chooses copies, a poster URL, and a product id.
- All testing against the **dev store** (`lms-sandbox-lutsfahz.myshopify.com`) and the developer's **test Libib account**. Never production.
- Copy for the client is plain English; follow the existing tone in `tools/rental-sync/app.js`.
- Tests: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_*.py"` and `node --test tests/rental_sync/*.test.js` — both green at every commit.

## Review Focus

1. **Double-click / rerun on "Add as a copy"** — the second call must return `skipped_exists`, never add a second variant with the same barcode. (Task 5, `test_add_copy_twice_is_skipped`.)
2. **Product changed in admin between prepare and add** (deleted, Vendor changed, `Rental` tag removed) — `failed` with a plain message, nothing written. (Task 5, `test_refuses_*`.)
3. **A Libib item whose synced copies sit on two products** (pre-cleanup data) — set aside "combine them first", never guess. (Task 3, `test_siblings_on_two_products_set_aside`.)
4. **Gaps in Copy numbers** (Copy 1, Copy 3 after a deletion) — next is Copy 4, never a repeated value. (Task 5, `test_next_copy_number_skips_gaps`.)
5. **A flagged or matched copy that also has a set-aside reason** (misspelt tag) — the set-aside reason wins; it isn't offered as a duplicate or match. (Task 2, `test_set_aside_wins_over_flags`.)

---

### Task 1: Developer check — labels and option shape (human gate)

Not code. The developer does this in the dev store admin; the implementer stops and waits for the result.

- [ ] **Step 1:** On the dev store, duplicate a rental product. Give it a second option `Copy` (`Copy 1`, `Copy 2`) and a second variant with a different barcode, `Genre` still Option 1.
- [ ] **Step 2:** In Retail Barcode Labels, try to print **only** the `Copy 2` variant with the LMS: RENTAL template. Record: can a single variant be printed? Does the label show the genre (Option 1), not `Copy 2`?
- [ ] **Step 3:** Open the product on the dev storefront and in a collection grid. Record: any variant picker, swatch, or "Copy" text visible?
- [ ] **Step 4:** Write the three answers into the spec's "Open item" section and commit.

**Stop condition:** if a single variant can't be printed, or the label shows `Copy N` as the genre, or the storefront shows the option — stop and bring it to the developer before Task 7.

---

### Task 2: Libib duplicate detection

**Files:**
- Create: `catalog/rental_sync/libib_duplicates.py`
- Test: `tests/catalog/test_rental_sync_libib_duplicates.py`

**Interfaces:**
- Consumes: `catalog.duplicates.match.normalize_title`, `fuzzy_match`, `editions`, `is_box_set`, `title_year`; `catalog.rental_sync.transform.transform`.
- Produces:
  - `same_title(a: str, b: str) -> bool`
  - `find_libib_duplicates(items: list[dict], candidate_ids: set[str]) -> dict[str, dict]` — maps a flagged item id to the other item's summary `{"item_id", "title", "format", "genres": [names], "copies": int, "created"}`.

Rules: `same_title` first moves a trailing `, The` / `, A` / `, An` to the front (Libib's sorted-title form), then is true when `editions` and `is_box_set` agree, bracketed years don't conflict (both present and different → false), and normalized titles are equal or `fuzzy_match`. An item = all rows sharing `id`; its title/tags/format come from its first row, `created` = earliest row. Only items in `candidate_ids` can be flagged; they're compared with every **other** item in `items` (any barcode, synced or not) of the same format. Items whose `transform` has set-aside reasons are never flagged. If the other item is also a candidate, only the later one (by `created`, then `id`) is flagged. Several matches → the earliest-created other item.

- [ ] **Step 1: Write the failing tests**

```python
class TestSameTitle(unittest.TestCase):
    def test_exact_and_normalized(self):
        self.assertTrue(same_title("The Godfather", "Godfather"))
        self.assertTrue(same_title("The Godfather", "Godfather, The"))
        self.assertTrue(same_title("Jaws", "JAWS"))
    def test_fuzzy_typo(self):
        self.assertTrue(same_title("Terminator 2 Judgment Day", "Terminator 2 Judgement Day"))
    def test_sequel_number_differs(self):
        self.assertFalse(same_title("Rocky II", "Rocky III"))
    def test_edition_differs(self):
        self.assertFalse(same_title("Alien", "Alien Director's Cut"))
    def test_conflicting_years(self):
        self.assertFalse(same_title("Halloween (1978)", "Halloween (2018)"))
    def test_same_title_no_years_matches(self):
        self.assertTrue(same_title("Halloween", "Halloween"))

class TestFindLibibDuplicates(unittest.TestCase):
    # rows shaped like load_libib(): id, title, barcode, call_number, tags, description, collection, created
    def test_flags_new_item_matching_old_item(self): ...       # new "Jaws" dvd vs old "Jaws" dvd -> {new_id: {"item_id": old_id, ...}}
    def test_different_format_not_flagged(self): ...           # "Jaws" vhs vs "Jaws" dvd -> {}
    def test_only_candidates_flagged(self): ...                # old item not in candidate_ids is never a key
    def test_both_new_flags_only_later(self): ...              # two candidates, later created is the key
    def test_set_aside_wins_over_flags(self): ...              # candidate with tag "horor" -> not flagged
    def test_summary_counts_copies(self): ...                  # other item with 2 rows -> "copies": 2
```

- [ ] **Step 2:** Run `python3 -m unittest tests.catalog.test_rental_sync_libib_duplicates -v` (from repo root, or the discover command). Expected: FAIL, module not found.
- [ ] **Step 3:** Implement both functions in `catalog/rental_sync/libib_duplicates.py`. Module docstring in the style of the siblings (what it decides, that it's pure).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Rental sync: detect Libib items that duplicate another item`.

---

### Task 3: `prepare` groups by Libib item, flags duplicates, marks siblings

**Files:**
- Modify: `catalog/rental_sync/transform.py` (`LIBIB_FIELDS` gains `"id"`)
- Modify: `catalog/rental_sync/prepare.py`
- Create: `catalog/rental_sync/matches.py`
- Modify: `catalog/rental_sync/shopify.py` (new read `product_summary`)
- Test: `tests/catalog/test_rental_sync_prepare.py`, `tests/catalog/test_rental_sync_matches.py`, `tests/catalog/test_rental_sync_shopify.py`

**Interfaces:**
- Consumes: `find_libib_duplicates` (Task 2); `RentalShop.barcode_owner(barcode) -> {"id","handle"} | None` (exists).
- Produces:
  - Each copy dict in `prepare()["ready"]` / `["set_aside"]` gains `"item_id": str`, `"siblings_in_shopify": list[str]` (new-flow barcodes of other copies of the same item already in Shopify), `"libib_duplicate": dict | None` (Task 2 summary), `"match": None` (filled by `attach_matches`).
  - `RentalShop.product_summary(product_id: str) -> {"id","handle","title","vendor","tags": list[str],"image": str,"copies": int} | None`
  - `attach_matches(result: dict, shop, store: str) -> dict` in `matches.py` — for each ready copy with siblings: one owner → `copy["match"] = {**product_summary, "admin_url"}`; owners on 2+ products → move to `set_aside` with `"This Libib item is on several Shopify products — combine them first"` and add `"products": [admin_url, …]` to the copy. Owner lookups cached per barcode, summaries per product.

Rules in `prepare`: a copy's `libib_duplicate` is set only when its item has **no** siblings in Shopify (`candidate_ids` = items with ≥1 new copy and no copy already in Shopify). Set-aside copies keep `libib_duplicate`/`match` as `None`. `prepare`'s signature is unchanged; `web._prepare` calls `attach_matches` after it.

- [ ] **Step 1: Write the failing tests**

```python
# test_rental_sync_prepare.py
def test_copy_carries_item_id(self): ...                       # ready[0]["item_id"] == "a1"
def test_new_copy_of_synced_item_lists_siblings(self): ...     # item a4 has 2010000000038 in Shopify + new 2010000000045 -> siblings_in_shopify == ["2010000000038"], libib_duplicate is None
def test_duplicate_item_flagged(self): ...                     # new item b1 "Jaws" vhs vs a1 "Jaws" vhs -> ready copy of b1 has libib_duplicate["item_id"] == "a1"
# test_rental_sync_matches.py (FakeShop gains product_summary)
def test_one_owner_becomes_match(self): ...                    # copy["match"]["handle"] == owner handle, admin_url set
def test_siblings_on_two_products_set_aside(self): ...         # moved from ready to set_aside, reason text exact, "products" has 2 urls
def test_owner_lookup_cached(self): ...                        # 3 copies of one item -> barcode_owner called once per sibling barcode
# test_rental_sync_shopify.py
def test_product_summary_counts_variants(self): ...            # FakeExecute variant nodes x2 -> "copies": 2
def test_product_summary_missing_product(self): ...            # product: null -> None
```

- [ ] **Step 2:** Run the discover command. Expected: the new tests FAIL.
- [ ] **Step 3:** Add `"id"` to `LIBIB_FIELDS`; implement `prepare` changes, `matches.attach_matches`, `RentalShop.product_summary` (query `product(id:) { id handle title vendor tags featuredMedia { preview { image { url } } } variantsCount { count } }`); extend `FakeShop` in `tests/catalog/tests_rental_sync_fakes.py` with `product_summary`; call `attach_matches` in `web._prepare`.
- [ ] **Step 4:** Run both test commands. Expected: PASS (existing prepare/web tests still green).
- [ ] **Step 5:** Commit: `Rental sync: group copies by Libib item, flag duplicates, find sibling products`.

---

### Task 4: `create` makes one product per Libib item

**Files:**
- Modify: `catalog/rental_sync/create.py`, `catalog/rental_sync/shopify.py` (`READ_BACK` → `variants(first: 100)` with `selectedOptions { name value }`)
- Modify: `tests/catalog/tests_rental_sync_fakes.py` (`FakeShop.read_back` returns every variant)
- Test: `tests/catalog/test_rental_sync_create.py`

**Interfaces:**
- Produces:
  - `create_item(shop, items: list[dict], poster: dict | None, sleep=time.sleep) -> dict` replaces `create_copy`. Result as today plus `"barcodes": list[str]`; `"barcode"` = first barcode (sorted).
  - `handle_for(copy)` unchanged, applied to the first copy by sorted barcode.
  - `product_set_input(copies: list[dict], handle, location_id, genre_ids, poster)`: 1 copy → today's shape exactly; 2+ copies → options `Genre` (pos 1) and `Copy` (pos 2, `Copy 1..N` in barcode order), one variant per copy.
  - `verify(node, copies, handle, publication_id)` checks variant count == len(copies) and each expected barcode's variant (taxable, tracked, qty 1).

Rules: all items must share one `id` and pass transform, else `failed` "not ready". Rerun safety: look up every barcode's owner; none → create; all on one product → `_existing` verify → `skipped_exists`; otherwise `failed` "Some of these copies are already in Shopify — run the sync again so they're added as copies".

- [ ] **Step 1: Write the failing tests**

```python
def test_two_copies_one_product(self): ...          # created input has 2 variants, options ["Genre","Copy"], values Copy 1/Copy 2
def test_one_copy_keeps_single_option(self): ...    # options == [Genre] only (today's shape)
def test_mixed_item_ids_refused(self): ...          # status "failed", nothing created
def test_partly_in_shopify_fails(self): ...         # one barcode owned -> failed, message contains "added as copies"
def test_all_in_shopify_skipped(self): ...          # both owned by one product, verify ok -> skipped_exists
def test_verify_checks_each_variant(self): ...      # lose quantity on second variant -> problems mention its barcode
```

Update existing `create_copy` tests to call `create_item(shop, [item], …)`.

- [ ] **Step 2:** Run. Expected: new tests FAIL.
- [ ] **Step 3:** Implement. Keep the existing messages for single-copy paths unchanged.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `Rental sync: create one product per Libib item, a variant per copy`.

---

### Task 5: Add a copy to an existing product

**Files:**
- Create: `catalog/rental_sync/add_copy.py`
- Modify: `catalog/rental_sync/shopify.py` (reads/writes below), `tests/catalog/tests_rental_sync_fakes.py`
- Test: `tests/catalog/test_rental_sync_add_copy.py`

**Interfaces:**
- Consumes: `transform`, `RentalShop.barcode_owner`, `location_id`, `admin_url` (create.py).
- Produces:
  - `add_copy(shop, item: dict, product_id: str) -> dict` — result `{"status": "added"|"skipped_exists"|"failed", "barcode", "title", "handle", "admin_url", "message", "problems"}`.
  - `next_copy_number(values: list[str]) -> int` — highest `Copy N` + 1; no values → 2 (the existing variant becomes `Copy 1`).
  - `RentalShop.product_for_copy(product_id) -> dict | None` — id, handle, title, vendor, tags, `options { name values }`, `variants(first: 100) { id barcode taxable inventoryQuantity inventoryItem { tracked } selectedOptions { name value } }`.
  - `RentalShop.add_copy_option(product_id) -> None` — `productOptionsCreate(productId, options: [{name: "Copy", position: 2, values: [{name: "Copy 1"}]}], variantStrategy: LEAVE_AS_IS)`.
  - `RentalShop.add_variant(product_id, variant_input: dict) -> None` — `productVariantsBulkCreate`.
  - `RentalShop.add_tags(product_id, tags: list[str]) -> None` — `tagsAdd`.

Order: transform (set aside → failed "not ready") → barcode owner (same product → verify that variant → `skipped_exists`; other product → `failed`) → `product_for_copy` (missing → failed "That Shopify product no longer exists"; no `Rental` tag or `vendor != copy["format"]` → failed naming the mismatch; no `Genre` option → failed "unexpected product shape — contact Liam") → add `Copy` option if absent → add variant (`Genre` = the product's one Genre value, `Copy N`, variant fields per Global Constraints) → add tag → read back: new variant correct and the existing variants' barcodes unchanged → `added`. Validate every new mutation and its input field names (`inventoryQuantities` on `ProductVariantsBulkInput`) against `config.SHOPIFY_API_VERSION` with the `shopify-plugin:shopify` skill before writing them.

- [ ] **Step 1: Write the failing tests**

```python
def test_adds_variant_and_tag(self): ...             # status "added"; variant barcode/price/taxable/qty; tag added
def test_first_copy_adds_option(self): ...           # product without Copy option -> add_copy_option called once, new variant "Copy 2"
def test_next_copy_number_skips_gaps(self):
    self.assertEqual(next_copy_number(["Copy 1", "Copy 3"]), 4)
    self.assertEqual(next_copy_number([]), 2)
def test_add_copy_twice_is_skipped(self): ...        # second call -> skipped_exists, one variant with that barcode
def test_refuses_missing_product(self): ...
def test_refuses_wrong_format(self): ...             # vendor "VHS", copy "DVD" -> failed, nothing written
def test_refuses_non_rental(self): ...
def test_barcode_on_other_product_fails(self): ...
def test_existing_variants_untouched(self): ...      # read back loses an old barcode -> problems non-empty
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `Rental sync: add a copy to an existing product as a variant`.

---

### Task 6: Endpoints

**Files:**
- Modify: `catalog/rental_sync/web.py`
- Create: `api/rental_sync/add_copy.py` (same 4-line `class handler(make_handler("add_copy"))` shape as `api/rental_sync/create.py`)
- Test: `tests/catalog/test_rental_sync_web.py`

**Interfaces:**
- `POST create` body: `{"items": [libib, …], "poster": {...} | null}` (1–50 items) → `create_item`.
- `POST add_copy` body: `{"item": libib, "product_id": "gid://shopify/Product/<digits>"}` → `add_copy`. Any other `product_id` → 400 "That product link isn't valid — reload the page and start again."
- `_finish` counts gain `"added"`.

- [ ] **Step 1:** Write failing tests: `test_create_takes_items_list`, `test_create_rejects_empty_items`, `test_add_copy_route`, `test_add_copy_rejects_bad_product_id`, `test_add_copy_requires_login`, `test_finish_counts_added`, and the existing "every api file is a class statement" test covering `add_copy.py`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `Rental sync: create takes a Libib item, new add_copy endpoint`.

---

### Task 7: Front end

Blocked by Task 1's answers.

**Files:**
- Modify: `tools/rental-sync/logic.js`, `tools/rental-sync/app.js`, `tools/rental-sync/index.html`, `tools/rental-sync/styles.css`
- Test: `tests/rental_sync/logic.test.js`

**Interfaces (logic.js, exported):**
- `groupForCreate(copies) -> [{item_id, copies}]` — keeps first-seen order.
- `choiceState(copies, choices) -> {dupes, matches, blocked: bool}` — `choices` is a `Map` barcode → `"not_duplicate" | "add" | "skip"`; `blocked` while any match lacks a choice.
- `applyChoices(copies, choices) -> {create, add, setAside}` — undismissed Libib duplicates → set aside with "In Libib, delete *<title>* and add this copy to *<other title>* instead. It will show up next time you sync."; `skip` → set aside with "If this copy isn't the same movie, move it to its own item in Libib."
- `createPayload(group, poster) -> {items, poster}`; `addCopyPayload(copy) -> {item, product_id}`.
- `summarize(results)` gains `added`; `finishPayload` sends `added`.
- `barcodesToPrint(results) -> string[]` — barcodes from `created` (all `barcodes`) and `added`.

**UI:** step 3 adds "Possible duplicates in Libib" (both items side by side + **Not a duplicate**) and "Already in Shopify?" (Libib copy beside the product: title, format, genres, poster, copies, admin link + **Add as a copy** / **Skip this run**) above Set aside; "Looks good" disabled while `blocked`. Step 4 shows one poster card per create group (keyed by the group's first barcode). Step 5 runs creates, then add_copies, one request at a time; results gain "Added as a copy"; the print block shows when anything was created or added, and lists `barcodesToPrint` with "Print labels for these barcodes only" (wording per Task 1's outcome).

- [ ] **Step 1:** Write failing node tests for each helper above, including `blocked` true with one unchosen match and `applyChoices` set-aside texts exactly as written.
- [ ] **Step 2:** Run `node --test tests/rental_sync/*.test.js`. Expected: FAIL.
- [ ] **Step 3:** Implement helpers, then wire `app.js` / `index.html`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `Rental sync page: duplicate and copy cards, add copies, barcodes to print`.

---

### Task 8: Libib tag job reads every variant

**Files:**
- Modify: `catalog/libib/tags_shopify.py:26,37` (`variants(first: 5)` → `variants(first: 100)`)
- Test: `tests/catalog/test_libib_tags_shopify.py`

- [ ] **Step 1:** Failing test `test_reads_more_than_five_barcodes`: a product node with 7 variants → `Product.barcodes` has 7.
- [ ] **Step 2:** Run `python3 -m unittest discover -s tests/catalog -p "test_libib_tags*.py"`. Expected: FAIL (if the fake doesn't enforce the limit, assert the query text contains `variants(first: 100)` instead).
- [ ] **Step 3:** Change both queries.
- [ ] **Step 4:** Run. Expected: PASS. Also add a `test_libib_tags.py` case: one product with two barcodes from one Libib item counts once in the newest-50 and gets one join id.
- [ ] **Step 5:** Commit: `libib tags: read every variant's barcode`.

---

### Task 9: Docs

**Files:** `tools/rental-sync/client-guide.md`, `tools/rental-sync/README.md`, `claudedocs/2026-10-15-rental-sync-app-followups.md`

- [ ] **Step 1:** Client guide: "Adding another copy of a movie" (add a copy to the existing Libib item, never a new item); what the two new cards mean and what each button does; printing only the listed barcodes.
- [ ] **Step 2:** README: `add_copy` endpoint, `create` body change, the dev-store Preview setup from Task 10.
- [ ] **Step 3:** Follow-ups doc: note this feature, and that go-live waits for the cleanup project.
- [ ] **Step 4:** Commit: `Docs: rental sync duplicates and copies`.

---

### Task 10: End-to-end on the dev store (with the developer)

- [ ] **Step 1 (developer):** In Vercel, set the **Preview** env `SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com` (Production untouched). Confirm the dev store's app has the scopes in `catalog/rental_sync/shopify.py`'s docstring.
- [ ] **Step 2:** Push the branch; open its Preview URL; confirm the header names the dev store.
- [ ] **Step 3 (developer, test Libib account):** Run each spec scenario, exporting both CSVs each time: new movie → created; new item with two copies → one product, two variants; second item for the same movie → flagged → in Libib delete it and add a copy to the first → re-run → "Already in Shopify?" → Add → variant added, tag on; remake → Not a duplicate → created; re-run → nothing new; Skip this run → set aside.
- [ ] **Step 4:** For each product, check in admin: variants, barcodes, Copy option values, qty, untaxed, Online Store only, tag. Check the storefront PDP and a collection grid show no Copy option.
- [ ] **Step 5:** Playwright walk-through of the preview (login → upload → both card types → create → results → print list).
- [ ] **Step 6:** Record results in the follow-ups doc; commit. Production stays untouched until the cleanup project is done and the developer says go.
