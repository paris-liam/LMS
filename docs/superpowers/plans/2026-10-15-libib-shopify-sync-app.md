# Libib → Shopify Rental Sync App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A password-protected webapp where the client uploads Libib's two Rental Library exports, reviews the new `201…` copies, fixes posters, and creates one Shopify rental product per copy himself.

**Architecture:** All logic lives in a new, HTTP-free package `catalog/rental_sync/` (transform → prepare → posters → create, plus a small Shopify client) reusing the existing `catalog/` code. Thin Vercel Python functions in `api/rental_sync/` call it through one testable dispatcher (`catalog/rental_sync/web.py`). A static, build-free front end in `tools/rental-sync/` walks the client through five steps and drives product creation one request per copy.

**Tech Stack:** Python 3.12 standard library only (Vercel Python runtime; local tests run on 3.14), `unittest`; plain HTML/CSS/JS with `node:test` for the pure JS helpers; Shopify Admin GraphQL `2026-07` (`catalog.config.SHOPIFY_API_VERSION`); TMDB search via `catalog/tmdb`.

**Spec:** `docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`

## Global Constraints

- New-flow scope: barcode matches `^201[0-9]{10}$` exactly. 8-digit barcodes (including ones that start `201`, e.g. `20144890`) are legacy and out of scope.
- One Shopify product per physical copy (per Libib barcode). Create-only: never update or delete an existing product.
- Product: handle `slug(title)-slug(format)-rental-<barcode>`; Vendor = format (`VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`); category `Media > Videos` (`gid://shopify/TaxonomyCategory/me-7`); tags `Rental`, `Barcode Not Printed`, plus extra tags; status `ACTIVE`; option `Genre` = first genre's name; `shopify.genre` = genre metaobject IDs in order; variant barcode = Libib barcode, price `0.00`, taxable `false`, tracked, policy `DENY`, quantity `1` at the only location; **Online Store only, never Point of Sale**.
- Set aside (not created): blank title, no format, more than one format, no genre, a misspelt format/genre tag, a barcode on two Libib copies. Warnings only: title noise (`[`, `]`, `(`, `)`, `edition`), more than 3 genres, blank description, extra tags.
- Libib is the source of truth: the app never edits Libib, and review fields are read-only except the poster.
- Secrets only in Vercel env vars: `SYNC_PASSWORD`, `SESSION_SECRET`, `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `TMDB_API_KEY`. Never log the password, cookie or tokens. Nothing from a run is committed (the repo is public).
- Session cookie: HMAC-SHA256, `HttpOnly; Secure; SameSite=Strict`, 12 hours. Failed login sleeps ~2 s.
- Pasted poster URLs must be `https://`; the server never fetches them.
- Build and verify on the **dev store** (`lms-sandbox-lutsfahz.myshopify.com`) first; switch `SHOPIFY_STORE` to production (`p0wkgv-wy.myshopify.com`) only in Task 13.
- `catalog/` stays standard-library only. Code must run on Python 3.12 (no 3.13+ features).
- Run the whole Python suite with `python3 -m unittest discover -s tests/catalog -p "test_*.py"` and the JS suites with `node --test tests/review_picker/*.test.js tests/rental_sync/*.test.js`; both must stay green after every task.

## Review Focus

1. **Legacy 8-digit barcodes that start with `201`** (e.g. `20144890`, which exist in today's Libib export) must be ignored by the app, never offered for creation. Pinned in Task 2 (`test_legacy_201_eight_digit_is_out_of_scope`).
2. **Libib exports saved with a BOM, Windows line endings, and multi-line quoted descriptions** must load exactly like a clean export. Pinned in Task 2 (`test_bom_crlf_and_multiline_description`).
3. **Messy tag strings** — `"VHS, vhs ,Horror,,"`, mixed case, doubled commas, `Blu Ray`, `Kids & Family` — must resolve to one format and the right genres without false set-asides. Pinned in Task 1 (`test_messy_tag_string`).
4. **`<`, `>` and `&` in a Libib description or title** must reach Shopify as text, not markup, and render as text in the app. Pinned in Task 4 (`test_description_is_escaped`); the front end only ever uses `textContent` (Task 8).
5. **Session expiring mid-run** (the 12 h cookie runs out during review or creation) must show the login box and then carry on with the same request, losing nothing. Pinned in Task 7 (`api retries the same request after login`) via `logic.makeApi`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `catalog/core/barcodes.py` (modify) | add `NEW_FLOW_BARCODE`, `is_new_flow_barcode` |
| `catalog/libib/exports.py` (modify) | `load_libib` also returns each copy's `created` |
| `catalog/errors.py` (modify) | add `SetupError` |
| `catalog/rental_sync/__init__.py` | package docstring |
| `catalog/rental_sync/transform.py` | one Libib copy → copy record (fields, set-aside reasons, warnings); vocabulary |
| `catalog/rental_sync/prepare.py` | decode uploads, load the exports, diff against Shopify, split ready / set aside |
| `catalog/rental_sync/shopify.py` | `RentalShop`: reads, writes and token cache for the app |
| `catalog/rental_sync/create.py` | create one copy: rerun checks, `productSet`, publish, read back, verify |
| `catalog/rental_sync/posters.py` | TMDB poster lookup per copy |
| `catalog/rental_sync/auth.py` | password check, session cookie sign/verify |
| `catalog/rental_sync/web.py` | route dispatcher `respond()` + Vercel `make_handler()` |
| `api/rental_sync/{login,status,prepare,posters,create,finish}.py` | three-line Vercel entry points |
| `vercel.json`, `.vercelignore` | Vercel project config at the repo root |
| `tools/rental-sync/logic.js` | pure front-end helpers (tested with `node:test`) |
| `tools/rental-sync/index.html`, `app.js`, `styles.css` | the five-step UI |
| `tools/rental-sync/guide/*.png` | Libib export screenshots |
| `tools/rental-sync/README.md`, `client-guide.md` | deploy notes, client instructions |
| `catalog/libib/diff.py` (modify) | ignore new-flow copies |
| `catalog/apply/merge.py` (modify) | new-flow rentals: poster/alt/tags only |
| `catalog/audit/rules.py` (modify) | accept new-flow barcodes; flag taxable / unpublished / wrong handle |
| `tests/catalog/test_rental_sync_*.py`, `tests/catalog/tests_rental_sync_fakes.py` | Python tests and fakes |
| `tests/rental_sync/logic.test.js` | JS tests |

---

### Task 1: Copy transform

**Files:**
- Modify: `catalog/core/barcodes.py`
- Modify: `catalog/libib/exports.py:34-42`
- Create: `catalog/rental_sync/__init__.py`
- Create: `catalog/rental_sync/transform.py`
- Test: `tests/catalog/test_rental_sync_transform.py`
- Test: `tests/catalog/test_libib_exports.py` (add one test)

**Interfaces:**
- Consumes: `catalog.core.handles.slugify(text) -> str`; `catalog.core.taxonomy.FORMATS`, `GENRES`, `canonical_format`, `canonical_genre`.
- Produces:
  - `catalog.core.barcodes.is_new_flow_barcode(value) -> bool`
  - `load_libib(...)` items gain key `"created": str`
  - `catalog.rental_sync.transform.LIBIB_FIELDS = ("barcode", "title", "tags", "description", "created")`
  - `transform(item: dict) -> dict` returning a **copy record**:
    `{"barcode": str, "title": str, "description": str, "format": str ("" unless exactly one), "genres": [{"handle": str, "name": str}], "extra_tags": [str], "created": str, "set_aside": [str], "warnings": [str], "libib": {field: str for field in LIBIB_FIELDS}}`
  - `misspelling_of(tag: str) -> str | None` (returns the vocabulary handle it looks like)
  - `vocabulary() -> {"formats": [str], "genres": [str]}`

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_rental_sync_transform.py`:

```python
import unittest

from catalog.core.barcodes import is_new_flow_barcode
from catalog.rental_sync.transform import edit_distance, misspelling_of, transform, vocabulary


def item(**overrides):
    base = {"barcode": "2010000000014", "title": "Jaws", "tags": "horror, vhs",
            "description": "A shark.", "created": "2026-10-14 10:00:00"}
    base.update(overrides)
    return base


class TestBarcodes(unittest.TestCase):
    def test_new_flow_barcode(self):
        self.assertTrue(is_new_flow_barcode("2010000000014"))
        self.assertTrue(is_new_flow_barcode(" 2010000000014 "))
        self.assertFalse(is_new_flow_barcode("20144890"))        # legacy 8-digit that starts 201
        self.assertFalse(is_new_flow_barcode("2020000000014"))
        self.assertFalse(is_new_flow_barcode("201000000001"))    # 12 digits
        self.assertFalse(is_new_flow_barcode(""))
        self.assertFalse(is_new_flow_barcode(None))


class TestTransform(unittest.TestCase):
    def test_clean_copy(self):
        copy = transform(item())
        self.assertEqual(copy["title"], "Jaws")
        self.assertEqual(copy["format"], "VHS")
        self.assertEqual(copy["genres"], [{"handle": "horror", "name": "Horror"}])
        self.assertEqual(copy["extra_tags"], [])
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["warnings"], [])
        self.assertEqual(copy["libib"], item())

    def test_every_format_maps_to_vendor(self):
        expected = {"vhs": "VHS", "dvd": "DVD", "blu-ray": "Blu-Ray", "4k": "4K",
                    "laserdisc": "Laserdisc", "betamax": "Betamax"}
        for tag, vendor in expected.items():
            self.assertEqual(transform(item(tags=f"{tag}, drama"))["format"], vendor)

    def test_genre_order_is_libib_order_and_names_come_from_the_taxonomy(self):
        copy = transform(item(tags="kids-family, sci-fi, vhs"))
        self.assertEqual(copy["genres"], [{"handle": "kids-family", "name": "Kids & Family"},
                                          {"handle": "sci-fi", "name": "Sci-Fi"}])

    def test_whitespace_collapsed(self):
        copy = transform(item(title="  The   Thing ", description=" A\n  shapeshifter. "))
        self.assertEqual((copy["title"], copy["description"]), ("The Thing", "A shapeshifter."))

    def test_messy_tag_string(self):
        copy = transform(item(tags="VHS, vhs ,Horror,, Kids & Family"))
        self.assertEqual(copy["format"], "VHS")
        self.assertEqual([g["handle"] for g in copy["genres"]], ["horror", "kids-family"])
        self.assertEqual(copy["set_aside"], [])
        spaced = transform(item(tags="Blu Ray, sci fi, SCI_FI"))
        self.assertEqual((spaced["format"], [g["handle"] for g in spaced["genres"]]), ("Blu-Ray", ["sci-fi"]))
        self.assertEqual(spaced["set_aside"], [])

    def test_blank_title_sets_aside(self):
        self.assertIn("title is blank", transform(item(title="   "))["set_aside"])

    def test_no_format_sets_aside(self):
        copy = transform(item(tags="horror"))
        self.assertEqual((copy["format"], copy["set_aside"]), ("", ["no format tag"]))

    def test_two_formats_set_aside(self):
        copy = transform(item(tags="vhs, dvd, horror"))
        self.assertEqual(copy["format"], "")
        self.assertEqual(copy["set_aside"], ["more than one format tag (VHS, DVD)"])

    def test_no_genre_sets_aside(self):
        self.assertEqual(transform(item(tags="vhs"))["set_aside"], ["no genre tag"])

    def test_misspellings_set_aside_and_name_the_term(self):
        for tag, meant in (("horor", "horror"), ("bluray", "blu-ray"), ("scifi", "sci-fi"),
                           ("thrillers", "thriller"), ("dvds", "dvd"), ("ld", "laserdisc"), ("kids", "kids-family")):
            copy = transform(item(tags=f"vhs, drama, {tag}"))
            self.assertEqual(copy["set_aside"], [f"tag '{tag}' looks like a misspelling of '{meant}'"], tag)
            self.assertEqual(copy["extra_tags"], [], tag)

    def test_real_extra_tags_pass_through_with_a_warning(self):
        copy = transform(item(tags="vhs, horror, criterion, OOP, signed, music"))
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["extra_tags"], ["criterion", "OOP", "signed", "music"])
        self.assertEqual(copy["warnings"], ["extra tags: criterion, OOP, signed, music"])

    def test_warnings(self):
        copy = transform(item(title="Jaws [VHS]", description="",
                              tags="vhs, horror, drama, action, comedy"))
        self.assertEqual(copy["set_aside"], [])
        self.assertEqual(copy["warnings"], ["title may need cleanup", "4 genres — usually 1–3", "no description"])
        self.assertIn("title may need cleanup", transform(item(title="Heat (Special Edition)"))["warnings"])


class TestHelpers(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance("horror", "horror"), 0)
        self.assertEqual(edit_distance("horor", "horror"), 1)
        self.assertEqual(edit_distance("hororr", "horror"), 1)   # adjacent swap counts once
        self.assertEqual(edit_distance("music", "musical"), 2)

    def test_misspelling_of_ignores_short_and_far_tags(self):
        self.assertIsNone(misspelling_of("oop"))
        self.assertIsNone(misspelling_of("criterion"))
        self.assertIsNone(misspelling_of("music"))   # 5 letters: only 1 edit allowed

    def test_vocabulary(self):
        vocab = vocabulary()
        self.assertEqual(vocab["formats"], ["vhs", "dvd", "blu-ray", "4k", "laserdisc", "betamax"])
        self.assertIn("kids-family", vocab["genres"])
        self.assertEqual(len(vocab["genres"]), 15)


if __name__ == "__main__":
    unittest.main()
```

Add to `tests/catalog/test_libib_exports.py`, inside `TestLoadLibib`:

```python
    def test_created_is_passed_through(self):
        self.barcodes.write_text(BARCODE_HEADER + ",created\n"
                                 'a1,movie,2010000000014,Jaws,Rental Library,"vhs, horror",, 2026-10-14 10:00 \n',
                                 encoding="utf-8")
        items = load_libib(self.barcodes, self.collection)
        self.assertEqual(items[0]["created"], "2026-10-14 10:00")

    def test_created_is_blank_when_the_export_has_no_column(self):
        self.assertEqual(load_libib(self.barcodes, self.collection)[0]["created"], "")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_transform.py" -v; python3 -m unittest discover -s tests/catalog -p "test_libib_exports.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync'`, `ImportError: cannot import name 'is_new_flow_barcode'`, and `KeyError: 'created'`.

- [ ] **Step 3: Implement**

Append to `catalog/core/barcodes.py`:

```python
# New-flow rentals (2026-10-15): Libib generates the barcode (13 digits
# starting 201) and the rental sync app creates the Shopify product from it.
# An 8-digit barcode that happens to start 201 is a legacy rental, not this.
NEW_FLOW_BARCODE = re.compile(r"^201[0-9]{10}$")


def is_new_flow_barcode(value) -> bool:
    return bool(NEW_FLOW_BARCODE.match((value or "").strip()))
```

In `catalog/libib/exports.py`, inside the `items.append({...})` dict in `load_libib`, add after `"collection": item_collection,`:

```python
            "created": (r.get("created") or "").strip(),
```

Create `catalog/rental_sync/__init__.py`:

```python
"""The rental sync app: Libib's Rental Library exports in, one Shopify rental
product per new 201… copy out. HTTP-free; api/rental_sync/ wraps it.
Spec: docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md"""
```

Create `catalog/rental_sync/transform.py`:

```python
"""One Libib copy -> what the rental sync app would create, why it can't be
created yet (set-aside reasons) and what looks off (warnings).

Pure. Libib is the source of truth: nothing here corrects a value, it only
reads it and reports, so a problem is fixed in Libib and picked up next run.
"""

import re

from catalog.core.handles import slugify
from catalog.core.taxonomy import FORMATS, GENRES, canonical_format, canonical_genre

LIBIB_FIELDS = ("barcode", "title", "tags", "description", "created")
FORMAT_BY_TAG = {slugify(f): f for f in FORMATS}
GENRE_NAME_BY_HANDLE = {handle: name for name, handle in GENRES.items()}
VOCABULARY = sorted(set(FORMAT_BY_TAG) | set(GENRE_NAME_BY_HANDLE))
MAX_GENRES = 3
TITLE_NOISE = re.compile(r"[\[\]()]|edition", re.IGNORECASE)


def _collapse(text) -> str:
    return " ".join((text or "").split())


def split_tags(raw) -> list[str]:
    """Libib's comma-separated tags, trimmed, blanks and case-repeats dropped."""
    seen: set[str] = set()
    tags = []
    for tag in (raw or "").split(","):
        tag = _collapse(tag)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags


def edit_distance(a: str, b: str) -> int:
    """Optimal-string-alignment distance: insert, delete, substitute, or swap
    two neighbouring letters, each costing 1."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def misspelling_of(tag: str) -> str | None:
    """The format/genre handle a non-vocabulary tag most likely meant, or None.
    A known alias ('bluray', 'ld', 'kids') always counts. Otherwise a tag of 4+
    characters within 1 edit (4-5 characters) or 2 edits (6+) of a term."""
    alias = canonical_format(tag) or canonical_genre(tag)
    if alias:
        return slugify(alias) if alias in FORMATS else GENRES[alias]
    key = slugify(tag)
    if len(key) < 4:
        return None
    limit = 1 if len(key) <= 5 else 2
    best = min(VOCABULARY, key=lambda term: (edit_distance(key, term), term))
    return best if edit_distance(key, best) <= limit else None


def vocabulary() -> dict:
    return {"formats": [slugify(f) for f in FORMATS], "genres": list(GENRES.values())}


def transform(item: dict) -> dict:
    """`item` is a load_libib() row (barcode, title, tags, description, created)."""
    title = _collapse(item.get("title"))
    description = _collapse(item.get("description"))
    formats: list[str] = []
    genres: list[str] = []
    extras: list[str] = []
    set_aside: list[str] = []
    warnings: list[str] = []

    for tag in split_tags(item.get("tags")):
        key = slugify(tag)
        if key in FORMAT_BY_TAG:
            if FORMAT_BY_TAG[key] not in formats:
                formats.append(FORMAT_BY_TAG[key])
        elif key in GENRE_NAME_BY_HANDLE:
            if key not in genres:
                genres.append(key)
        else:
            meant = misspelling_of(tag)
            if meant:
                set_aside.append(f"tag '{tag}' looks like a misspelling of '{meant}'")
            else:
                extras.append(tag)

    if not title:
        set_aside.append("title is blank")
    if not formats:
        set_aside.append("no format tag")
    elif len(formats) > 1:
        set_aside.append(f"more than one format tag ({', '.join(formats)})")
    if not genres:
        set_aside.append("no genre tag")

    if title and TITLE_NOISE.search(title):
        warnings.append("title may need cleanup")
    if len(genres) > MAX_GENRES:
        warnings.append(f"{len(genres)} genres — usually 1–3")
    if not description:
        warnings.append("no description")
    if extras:
        warnings.append("extra tags: " + ", ".join(extras))

    return {
        "barcode": (item.get("barcode") or "").strip(),
        "title": title,
        "description": description,
        "format": formats[0] if len(formats) == 1 else "",
        "genres": [{"handle": h, "name": GENRE_NAME_BY_HANDLE[h]} for h in genres],
        "extra_tags": extras,
        "created": (item.get("created") or "").strip(),
        "set_aside": set_aside,
        "warnings": warnings,
        "libib": {field: item.get(field) or "" for field in LIBIB_FIELDS},
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_transform.py" -v; python3 -m unittest discover -s tests/catalog -p "test_libib_exports.py" -v`
Expected: PASS. If `test_misspellings_set_aside_and_name_the_term` fails for `kids` or `ld`, print `canonical_genre("kids")` / `canonical_format("ld")` — they must resolve through the alias tables in `catalog/core/taxonomy.py`; fix the lookup, not the test.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: OK (the `created` key must not break existing `load_libib` callers).

```bash
git add catalog/core/barcodes.py catalog/libib/exports.py catalog/rental_sync/__init__.py catalog/rental_sync/transform.py tests/catalog/test_rental_sync_transform.py tests/catalog/test_libib_exports.py
git commit -m "rental_sync: Libib copy transform with set-aside rules and misspelling check"
```

---

### Task 2: Prepare — uploads in, ready / set aside out

**Files:**
- Create: `catalog/rental_sync/prepare.py`
- Test: `tests/catalog/test_rental_sync_prepare.py`

**Interfaces:**
- Consumes: `transform(item) -> dict`, `is_new_flow_barcode`, `load_libib(barcode_path, collection_path, collection="Rental Library") -> list[dict]` (raises `InputShapeError`).
- Produces:
  - `MAX_FILE_BYTES = 5 * 1024 * 1024`
  - `decode_upload(encoded: str, label: str) -> bytes` (base64 of gzip; raises `InputShapeError`)
  - `load_uploads(barcodes: bytes, library: bytes) -> list[dict]` (raises `InputShapeError`)
  - `prepare(items: list[dict], shopify_barcodes: set[str]) -> dict` →
    `{"ready": [copy], "set_aside": [copy], "already_in_shopify": int, "not_new_flow": int}`; both lists ordered by `created`, then title.

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_rental_sync_prepare.py`:

```python
import base64
import gzip
import unittest

from catalog.errors import InputShapeError
from catalog.rental_sync.prepare import MAX_FILE_BYTES, decode_upload, load_uploads, prepare

BARCODES = "\n".join([
    "id,item_type,barcode,title,collection,tags,call_number,created",
    'a1,movie,2010000000014,Jaws,Rental Library,"vhs, horror",,2026-10-14 10:00:00',
    'a2,movie,2010000000021,Heat,Rental Library,"dvd, horor",,2026-10-14 09:00:00',
    'a3,movie,20144890,Old Rental,Rental Library,"vhs, drama",20144890,2026-09-16',
    'a4,movie,2010000000038,Already There,Rental Library,"vhs, comedy",,2026-10-13',
]) + "\n"
LIBRARY = "\n".join([
    "id,item_type,title,collection,description,call_number",
    "a1,movie,Jaws,Rental Library,A shark.,",
    "a2,movie,Heat,Rental Library,A heist.,",
    "a3,movie,Old Rental,Rental Library,Old.,20144890",
    "a4,movie,Already There,Rental Library,Here.,",
]) + "\n"


def encode(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data)).decode()


class TestDecodeUpload(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(decode_upload(encode(b"id,barcode\n"), "Barcodes export"), b"id,barcode\n")

    def test_not_base64(self):
        with self.assertRaisesRegex(InputShapeError, "Barcodes export upload is unreadable"):
            decode_upload("%%%not base64%%%", "Barcodes export")

    def test_not_gzip(self):
        with self.assertRaisesRegex(InputShapeError, "Library export upload is unreadable"):
            decode_upload(base64.b64encode(b"plain text").decode(), "Library export")

    def test_over_the_limit_after_decompressing(self):
        with self.assertRaisesRegex(InputShapeError, "over 5 MB"):
            decode_upload(encode(b"x" * (MAX_FILE_BYTES + 1)), "Library export")

    def test_missing(self):
        with self.assertRaisesRegex(InputShapeError, "Choose the Barcodes export"):
            decode_upload("", "Barcodes export")


class TestLoadUploads(unittest.TestCase):
    def test_loads_and_joins(self):
        items = load_uploads(BARCODES.encode(), LIBRARY.encode())
        self.assertEqual([i["barcode"] for i in items], ["2010000000014", "2010000000021", "20144890", "2010000000038"])
        self.assertEqual(items[0]["description"], "A shark.")
        self.assertEqual(items[0]["created"], "2026-10-14 10:00:00")

    def test_bom_crlf_and_multiline_description(self):
        barcodes = ("﻿" + BARCODES.replace("\n", "\r\n")).encode("utf-8")
        library = ("﻿" + LIBRARY.replace("a1,movie,Jaws,Rental Library,A shark.,",
                                              'a1,movie,Jaws,Rental Library,"A shark,\r\nat sea.",')
                   .replace("\n", "\r\n")).encode("utf-8")
        items = load_uploads(barcodes, library)
        self.assertEqual(items[0]["barcode"], "2010000000014")
        self.assertEqual(" ".join(items[0]["description"].split()), "A shark, at sea.")

    def test_swapped_files(self):
        with self.assertRaisesRegex(InputShapeError, "swapped"):
            load_uploads(LIBRARY.encode(), BARCODES.encode())

    def test_wrong_file_names_the_box(self):
        with self.assertRaisesRegex(InputShapeError, "Barcodes export.csv is missing column"):
            load_uploads(b"id,title\n1,x\n", LIBRARY.encode())

    def test_not_text(self):
        with self.assertRaisesRegex(InputShapeError, "isn't a CSV"):
            load_uploads(b"\xff\xfe\x00\x01\x02", LIBRARY.encode())


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.items = load_uploads(BARCODES.encode(), LIBRARY.encode())

    def test_split(self):
        result = prepare(self.items, {"2010000000038"})
        self.assertEqual([c["title"] for c in result["ready"]], ["Jaws"])
        self.assertEqual([c["title"] for c in result["set_aside"]], ["Heat"])
        self.assertEqual(result["already_in_shopify"], 1)
        self.assertEqual(result["not_new_flow"], 1)

    def test_legacy_201_eight_digit_is_out_of_scope(self):
        result = prepare(self.items, set())
        barcodes = {c["barcode"] for c in result["ready"] + result["set_aside"]}
        self.assertNotIn("20144890", barcodes)

    def test_order_is_created_then_title(self):
        result = prepare(self.items, set())
        self.assertEqual([c["title"] for c in result["ready"]], ["Already There", "Jaws"])

    def test_duplicate_barcode_sets_both_aside(self):
        dup = dict(self.items[0], id="a9", title="Jaws Again")
        result = prepare(self.items + [dup], set())
        aside = [c for c in result["set_aside"] if c["barcode"] == "2010000000014"]
        self.assertEqual(len(aside), 2)
        self.assertIn("barcode 2010000000014 is on 2 Libib copies", aside[0]["set_aside"])
        self.assertNotIn("2010000000014", [c["barcode"] for c in result["ready"]])

    def test_nothing_new(self):
        result = prepare(self.items, {"2010000000014", "2010000000021", "2010000000038"})
        self.assertEqual((result["ready"], result["set_aside"], result["already_in_shopify"]), ([], [], 3))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_prepare.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.prepare'`.

- [ ] **Step 3: Implement**

Create `catalog/rental_sync/prepare.py`:

```python
"""Uploaded Libib exports -> the copies the app offers to create.

The browser gzips each CSV and base64-encodes it (keeps two growing exports
under Vercel's 4.5 MB request limit). A copy is new when its 201… barcode is
on no Shopify variant; date added is shown, never used to decide.
"""

import base64
import binascii
import csv
import tempfile
import zlib
from collections import Counter
from pathlib import Path

from catalog.core.barcodes import is_new_flow_barcode
from catalog.errors import InputShapeError
from catalog.libib.exports import load_libib
from catalog.rental_sync.transform import transform

MAX_FILE_BYTES = 5 * 1024 * 1024
BARCODES_NAME = "Barcodes export.csv"
LIBRARY_NAME = "Library export.csv"


def decode_upload(encoded: str, label: str) -> bytes:
    if not encoded:
        raise InputShapeError(f"Choose the {label} file.")
    unreadable = f"The {label} upload is unreadable — choose the file again."
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InputShapeError(unreadable) from None
    inflater = zlib.decompressobj(wbits=31)  # gzip framing
    try:
        data = inflater.decompress(compressed, MAX_FILE_BYTES + 1)
    except zlib.error:
        raise InputShapeError(unreadable) from None
    if len(data) > MAX_FILE_BYTES or inflater.unconsumed_tail:
        raise InputShapeError(f"The {label} is over 5 MB — is it the right Libib export?")
    return data


def _header(data: bytes) -> set[str]:
    first_line = data.decode("utf-8-sig", errors="replace").splitlines()[:1]
    return set(next(csv.reader(first_line), [])) if first_line else set()


def load_uploads(barcodes: bytes, library: bytes) -> list[dict]:
    barcodes_header, library_header = _header(barcodes), _header(library)
    if "barcode" not in barcodes_header and "description" in barcodes_header and "barcode" in library_header:
        raise InputShapeError("The two files are swapped — put the Barcodes export in the first box "
                              "and the Library export in the second.")
    with tempfile.TemporaryDirectory() as tmp:
        barcodes_path, library_path = Path(tmp) / BARCODES_NAME, Path(tmp) / LIBRARY_NAME
        barcodes_path.write_bytes(barcodes)
        library_path.write_bytes(library)
        try:
            return load_libib(barcodes_path, library_path)
        except (UnicodeDecodeError, csv.Error):
            raise InputShapeError("One of the files isn't a CSV — export it from Libib again.") from None


def _order(item: dict) -> tuple[str, str]:
    return (item.get("created") or "", (item.get("title") or "").lower())


def prepare(items: list[dict], shopify_barcodes: set[str]) -> dict:
    new_flow = [i for i in items if is_new_flow_barcode(i.get("barcode"))]
    counts = Counter(i["barcode"] for i in new_flow)
    ready, set_aside, in_shopify = [], [], 0
    for item in sorted(new_flow, key=_order):
        if item["barcode"] in shopify_barcodes:
            in_shopify += 1
            continue
        copy = transform(item)
        if counts[item["barcode"]] > 1:
            copy["set_aside"].append(f"barcode {item['barcode']} is on {counts[item['barcode']]} Libib copies")
        (set_aside if copy["set_aside"] else ready).append(copy)
    return {"ready": ready, "set_aside": set_aside, "already_in_shopify": in_shopify,
            "not_new_flow": len(items) - len(new_flow)}
```

Note: `load_libib` names the file in its own error (`"Barcodes export.csv is missing column(s) …"`), which is why the temp files carry those names.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_prepare.py" -v`
Expected: PASS. If `test_not_text` passes through instead of raising, check `load_libib` opens with `encoding="utf-8-sig"` (it does) — `\xff\xfe…` is invalid UTF-8 and raises `UnicodeDecodeError` from `csv.DictReader`.

- [ ] **Step 5: Commit**

```bash
git add catalog/rental_sync/prepare.py tests/catalog/test_rental_sync_prepare.py
git commit -m "rental_sync: decode uploaded Libib exports and split new copies"
```

---

### Task 3: Shopify client

**Files:**
- Modify: `catalog/errors.py`
- Create: `catalog/rental_sync/shopify.py`
- Create: `tests/catalog/tests_rental_sync_fakes.py`
- Test: `tests/catalog/test_rental_sync_shopify.py`

**Interfaces:**
- Consumes: `catalog.shopify.api.request_token(store, client_id, client_secret) -> str`, `api.make_executor(store, token) -> execute(store, query_obj, variables) -> payload`, `catalog.shopify.writer.ApiStore(execute, store).gql(query, **variables) -> data` (raises `RuntimeError` on GraphQL `errors`), `is_new_flow_barcode`.
- Produces:
  - `catalog.errors.SetupError(CatalogError)`
  - `cached_token(store, client_id, client_secret, now=time.time, request=api.request_token) -> str`
  - `shop_from_env(env: dict) -> RentalShop`
  - `class RentalShop(execute, store)` with attribute `store: str` and methods:
    `gql(query, **variables) -> dict`, `mutate(query, root, **variables) -> dict`,
    `new_flow_barcodes() -> set[str]`, `barcode_owner(barcode) -> str | None` (handle),
    `handle_taken(handle) -> bool`, `location_id() -> str`, `online_store_publication_id() -> str`,
    `genre_ids(handles: list[str]) -> list[str]`, `last_run() -> dict | None`, `save_last_run(summary: dict) -> None`,
    `product_set(product_input: dict) -> {"id", "handle"}`, `publish(product_id, publication_id) -> None`,
    `read_back(product_id) -> dict` (raw node: `handle, tags, variants.nodes[barcode, taxable, inventoryQuantity, inventoryItem.tracked], resourcePublicationsV2.nodes[publication{id,name}], media.nodes[status]`)
  - Fakes for later tasks: `FakeExecute`, `FakeShop`, `ONLINE_STORE_ID`, `POS_ID`.
  - Errors: GraphQL `ACCESS_DENIED` → `SetupError`; other GraphQL errors and `userErrors` → `ShopifyError`; several/zero locations, missing Online Store, unknown genre → `SetupError`.

- [ ] **Step 1: Add `SetupError` and the fakes**

Append to `catalog/errors.py`:

```python
class SetupError(CatalogError):
    """The app or store is misconfigured (missing scope, setting, location or
    channel) — something only the developer can fix."""
```

Create `tests/catalog/tests_rental_sync_fakes.py`:

```python
"""Fakes for the rental sync tests: a GraphQL executor and a RentalShop."""

ONLINE_STORE_ID = "gid://shopify/Publication/1"
POS_ID = "gid://shopify/Publication/2"


class FakeExecute:
    """execute(store, query_obj, variables) answering by the first matching
    substring of the query text. A payload may be a callable(variables)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, store, query, variables):
        text = query.read_text()
        self.calls.append((text, dict(variables)))
        for needle, payload in self.responses:
            if needle in text:
                return payload(variables) if callable(payload) else payload
        raise AssertionError(f"unexpected query: {text[:120]}")


class FakeShop:
    """Duck-types RentalShop for create.py and web.py tests."""

    store = "lms-sandbox-lutsfahz.myshopify.com"

    def __init__(self, barcodes=(), handles=(), set_error=None, publish_error=None, media=("READY",),
                 extra_channels=(), lose=(), location_error=None, barcodes_error=None, last=None):
        self.barcodes = {b: f"existing-{b}" for b in barcodes}
        self.handles = set(handles)
        self.set_error, self.publish_error = set_error, publish_error
        self.media = list(media)
        self.extra_channels = list(extra_channels)
        self.lose = set(lose)
        self.location_error, self.barcodes_error = location_error, barcodes_error
        self.last = last
        self.created, self.published, self.saved = [], [], []
        self.nodes = {}
        self.reads = 0

    def barcode_owner(self, barcode):
        return self.barcodes.get(barcode)

    def handle_taken(self, handle):
        return handle in self.handles

    def location_id(self):
        if self.location_error:
            raise self.location_error
        return "gid://shopify/Location/1"

    def genre_ids(self, handles):
        return [f"gid://shopify/Metaobject/{h}" for h in handles]

    def online_store_publication_id(self):
        return ONLINE_STORE_ID

    def product_set(self, product_input):
        if self.set_error:
            raise self.set_error
        self.created.append(product_input)
        pid = f"gid://shopify/Product/{100 + len(self.created)}"
        self.barcodes[product_input["variants"][0]["barcode"]] = product_input["handle"]
        self.handles.add(product_input["handle"])
        self.nodes[pid] = product_input
        return {"id": pid, "handle": product_input["handle"]}

    def publish(self, product_id, publication_id):
        if self.publish_error:
            raise self.publish_error
        self.published.append((product_id, publication_id))

    def read_back(self, product_id):
        self.reads += 1
        p = self.nodes[product_id]
        v = p["variants"][0]
        status = self.media[min(self.reads - 1, len(self.media) - 1)]
        pubs = [{"publication": {"id": pub, "name": "Online Store"}} for prod, pub in self.published if prod == product_id]
        pubs += [{"publication": {"id": POS_ID, "name": name}} for name in self.extra_channels]
        return {
            "id": product_id,
            "handle": p["handle"],
            "tags": [] if "tags" in self.lose else list(p["tags"]),
            "variants": {"nodes": [{
                "barcode": v["barcode"],
                "taxable": True if "taxable" in self.lose else v["taxable"],
                "inventoryQuantity": 0 if "quantity" in self.lose else v["inventoryQuantities"][0]["quantity"],
                "inventoryItem": {"tracked": v["inventoryItem"]["tracked"]},
            }]},
            "resourcePublicationsV2": {"nodes": pubs},
            "media": {"nodes": [{"status": status}] if p.get("files") else []},
        }

    def new_flow_barcodes(self):
        if self.barcodes_error:
            raise self.barcodes_error
        return set(self.barcodes)

    def last_run(self):
        return self.last

    def save_last_run(self, summary):
        self.saved.append(summary)
        self.last = summary
```

- [ ] **Step 2: Write the failing tests**

`tests/catalog/test_rental_sync_shopify.py`:

```python
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeExecute  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync import shopify as rs  # noqa: E402
from catalog.rental_sync.shopify import RentalShop, cached_token  # noqa: E402

STORE = "lms-sandbox-lutsfahz.myshopify.com"


def shop(responses):
    execute = FakeExecute(responses)
    return RentalShop(execute, STORE), execute


def data(payload):
    return {"data": payload}


class TestReads(unittest.TestCase):
    def test_new_flow_barcodes_paginates_and_filters(self):
        pages = {
            None: {"nodes": [{"barcode": "2010000000014"}, {"barcode": "20144890"}],
                   "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
            "c1": {"nodes": [{"barcode": " 2010000000021 "}, {"barcode": None}],
                   "pageInfo": {"hasNextPage": False, "endCursor": None}},
        }
        s, execute = shop([("productVariants(first: 250", lambda v: data({"productVariants": pages[v["after"]]}))])
        self.assertEqual(s.new_flow_barcodes(), {"2010000000014", "2010000000021"})
        self.assertIn('barcode:201*', execute.calls[0][0])

    def test_barcode_owner_needs_an_exact_match(self):
        s, _ = shop([("productVariants(first: 10", data({"productVariants": {"nodes": [
            {"barcode": "20100000000140", "product": {"handle": "other"}},
            {"barcode": "2010000000014", "product": {"handle": "jaws-vhs-rental-2010000000014"}}]}}))])
        self.assertEqual(s.barcode_owner("2010000000014"), "jaws-vhs-rental-2010000000014")
        s2, _ = shop([("productVariants(first: 10", data({"productVariants": {"nodes": []}}))])
        self.assertIsNone(s2.barcode_owner("2010000000014"))

    def test_handle_taken_needs_an_exact_match(self):
        s, _ = shop([("products(first: 5", data({"products": {"nodes": [{"handle": "jaws-vhs-rental-2010000000014-2"}]}}))])
        self.assertFalse(s.handle_taken("jaws-vhs-rental-2010000000014"))

    def test_exactly_one_location(self):
        one, _ = shop([("locations(", data({"locations": {"nodes": [{"id": "gid://shopify/Location/1", "name": "Shop"}]}}))])
        self.assertEqual(one.location_id(), "gid://shopify/Location/1")
        two, _ = shop([("locations(", data({"locations": {"nodes": [{"id": "a", "name": "Shop"}, {"id": "b", "name": "Warehouse"}]}}))])
        with self.assertRaisesRegex(SetupError, "exactly one active Shopify location, found 2: Shop, Warehouse"):
            two.location_id()

    def test_online_store_publication(self):
        s, _ = shop([("publications(", data({"publications": {"nodes": [
            {"id": "p2", "name": "Point of Sale"}, {"id": "p1", "name": "Online Store"}]}}))])
        self.assertEqual(s.online_store_publication_id(), "p1")
        none, _ = shop([("publications(", data({"publications": {"nodes": [{"id": "p2", "name": "Point of Sale"}]}}))])
        with self.assertRaisesRegex(SetupError, "Online Store"):
            none.online_store_publication_id()

    def test_genre_ids_cached_and_unknown_is_setup(self):
        s, execute = shop([("metaobjectByHandle", lambda v: data({"metaobjectByHandle":
                                                                   {"id": f"gid://m/{v['h']}"} if v["h"] != "nope" else None}))])
        self.assertEqual(s.genre_ids(["horror", "drama"]), ["gid://m/horror", "gid://m/drama"])
        s.genre_ids(["horror"])
        self.assertEqual(len(execute.calls), 2)
        with self.assertRaisesRegex(SetupError, "no genre value 'nope'"):
            s.genre_ids(["nope"])

    def test_last_run(self):
        s, _ = shop([("metafield(", data({"shop": {"metafield": {"value": json.dumps({"created": 3})}}}))])
        self.assertEqual(s.last_run(), {"created": 3})
        blank, _ = shop([("metafield(", data({"shop": {"metafield": None}}))])
        self.assertIsNone(blank.last_run())
        garbled, _ = shop([("metafield(", data({"shop": {"metafield": {"value": "{oops"}}}))])
        self.assertIsNone(garbled.last_run())


class TestWrites(unittest.TestCase):
    def test_save_last_run(self):
        s, execute = shop([("shop { id }", data({"shop": {"id": "gid://shopify/Shop/1"}})),
                           ("metafieldsSet", data({"metafieldsSet": {"userErrors": []}}))])
        s.save_last_run({"created": 2})
        sent = execute.calls[1][1]["m"][0]
        self.assertEqual((sent["ownerId"], sent["namespace"], sent["key"], sent["type"]),
                         ("gid://shopify/Shop/1", "lms", "rental_sync_last_run", "json"))
        self.assertEqual(json.loads(sent["value"]), {"created": 2})

    def test_product_set_returns_the_product(self):
        s, execute = shop([("productSet", data({"productSet": {"product": {"id": "gid://p/1", "handle": "h"},
                                                               "userErrors": []}}))])
        self.assertEqual(s.product_set({"title": "Jaws"}), {"id": "gid://p/1", "handle": "h"})
        self.assertIn("synchronous: true", execute.calls[0][0])

    def test_user_errors_raise_shopify_error(self):
        s, _ = shop([("productSet", data({"productSet": {"product": None,
                                                         "userErrors": [{"field": ["handle"], "message": "Handle taken"}]}}))])
        with self.assertRaisesRegex(ShopifyError, "Handle taken"):
            s.product_set({"title": "Jaws"})

    def test_publish_sends_the_publication(self):
        s, execute = shop([("publishablePublish", data({"publishablePublish": {"userErrors": []}}))])
        s.publish("gid://p/1", "gid://pub/1")
        self.assertEqual(execute.calls[0][1], {"id": "gid://p/1", "input": [{"publicationId": "gid://pub/1"}]})


class TestErrors(unittest.TestCase):
    def test_access_denied_is_setup(self):
        s, _ = shop([("locations(", {"errors": [{"message": "Access denied", "extensions": {"code": "ACCESS_DENIED"}}]})])
        with self.assertRaisesRegex(SetupError, "missing a permission"):
            s.location_id()

    def test_other_graphql_errors_are_shopify(self):
        s, _ = shop([("locations(", {"errors": [{"message": "Internal error"}]})])
        with self.assertRaisesRegex(ShopifyError, "Internal error"):
            s.location_id()


class TestToken(unittest.TestCase):
    def setUp(self):
        rs._tokens.clear()

    def test_reused_until_expiry(self):
        clock, issued = [1000.0], []

        def request(store, cid, secret):
            issued.append(store)
            return f"t{len(issued)}"

        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t1")
        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t1")
        clock[0] += rs.TOKEN_LIFETIME_SECONDS + 1
        self.assertEqual(cached_token(STORE, "id", "s", now=lambda: clock[0], request=request), "t2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_shopify.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.shopify'`.

- [ ] **Step 4: Implement**

Create `catalog/rental_sync/shopify.py`:

```python
"""The rental sync app's Shopify access: the reads behind the barcode diff and
setup checks, the last-run metafield, and the writes create.py makes.

Uses the same Dev Dashboard custom app as the pipeline (client credentials
grant). A Vercel instance that stays warm reuses its token; a cold one asks
for a new one. Scopes needed: read/write_products, write_inventory,
read_locations, read/write_publications.
"""

import json
import time

from catalog.core.barcodes import is_new_flow_barcode
from catalog.errors import SetupError, ShopifyError
from catalog.shopify import api
from catalog.shopify.writer import ApiStore

TOKEN_LIFETIME_SECONDS = 23 * 3600   # Shopify issues 24 h tokens
LAST_RUN_NAMESPACE, LAST_RUN_KEY = "lms", "rental_sync_last_run"
ONLINE_STORE = "Online Store"

_tokens: dict[tuple[str, str], tuple[str, float]] = {}


def cached_token(store, client_id, client_secret, now=time.time, request=api.request_token) -> str:
    key = (store, client_id)
    token, expires = _tokens.get(key, ("", 0.0))
    if token and expires > now():
        return token
    token = request(store, client_id, client_secret)
    _tokens[key] = (token, now() + TOKEN_LIFETIME_SECONDS)
    return token


NEW_FLOW_BARCODES = """
query($after: String) {
  productVariants(first: 250, after: $after, query: "barcode:201*") {
    nodes { barcode }
    pageInfo { hasNextPage endCursor }
  }
}"""
VARIANTS_BY_BARCODE = """
query($q: String!) { productVariants(first: 10, query: $q) { nodes { barcode product { handle } } } }"""
PRODUCTS_BY_HANDLE = """
query($q: String!) { products(first: 5, query: $q) { nodes { handle } } }"""
LOCATIONS = """
query { locations(first: 10, includeInactive: false) { nodes { id name } } }"""
PUBLICATIONS = """
query { publications(first: 25) { nodes { id name } } }"""
GENRE_BY_HANDLE = """
query($h: String!) { metaobjectByHandle(handle: {type: "shopify--genre", handle: $h}) { id } }"""
LAST_RUN = """
query { shop { metafield(namespace: "lms", key: "rental_sync_last_run") { value } } }"""
SHOP_ID = """
query { shop { id } }"""
SET_METAFIELDS = """
mutation($m: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $m) { userErrors { field message } } }"""
PRODUCT_SET = """
mutation($input: ProductSetInput!) {
  productSet(input: $input, synchronous: true) { product { id handle } userErrors { field message } }
}"""
PUBLISH = """
mutation($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}"""
READ_BACK = """
query($id: ID!) {
  product(id: $id) {
    id handle tags
    variants(first: 5) { nodes { barcode taxable inventoryQuantity inventoryItem { tracked } } }
    resourcePublicationsV2(first: 20, onlyPublished: true) { nodes { publication { id name } } }
    media(first: 5) { nodes { status } }
  }
}"""


class RentalShop:
    def __init__(self, execute, store: str):
        self.store = store
        self._api = ApiStore(execute, store)
        self._genre_ids: dict[str, str] = {}

    def gql(self, query: str, **variables) -> dict:
        try:
            return self._api.gql(query, **variables)
        except RuntimeError as exc:
            if "ACCESS_DENIED" in str(exc):
                raise SetupError(f"the Shopify app is missing a permission: {exc}") from None
            raise ShopifyError(f"Shopify returned an error: {exc}") from None

    def mutate(self, query: str, root: str, **variables) -> dict:
        result = self.gql(query, **variables)[root]
        errors = result.get("userErrors") or []
        if errors:
            raise ShopifyError("; ".join(e.get("message", "") for e in errors))
        return result

    # reads

    def new_flow_barcodes(self) -> set[str]:
        found: set[str] = set()
        after = None
        while True:
            page = self.gql(NEW_FLOW_BARCODES, after=after)["productVariants"]
            found |= {(n.get("barcode") or "").strip() for n in page["nodes"]}
            if not page["pageInfo"]["hasNextPage"]:
                return {b for b in found if is_new_flow_barcode(b)}
            after = page["pageInfo"]["endCursor"]

    def barcode_owner(self, barcode: str) -> str | None:
        nodes = self.gql(VARIANTS_BY_BARCODE, q=f"barcode:{barcode}")["productVariants"]["nodes"]
        return next((n["product"]["handle"] for n in nodes if (n.get("barcode") or "").strip() == barcode), None)

    def handle_taken(self, handle: str) -> bool:
        nodes = self.gql(PRODUCTS_BY_HANDLE, q=f"handle:{handle}")["products"]["nodes"]
        return any(n["handle"] == handle for n in nodes)

    def location_id(self) -> str:
        nodes = self.gql(LOCATIONS)["locations"]["nodes"]
        if len(nodes) != 1:
            names = ", ".join(n["name"] for n in nodes) or "none"
            raise SetupError(f"expected exactly one active Shopify location, found {len(nodes)}: {names}")
        return nodes[0]["id"]

    def online_store_publication_id(self) -> str:
        nodes = self.gql(PUBLICATIONS)["publications"]["nodes"]
        matches = [n["id"] for n in nodes if n["name"] == ONLINE_STORE]
        if len(matches) != 1:
            raise SetupError(f"found {len(matches)} '{ONLINE_STORE}' sales channels in Shopify — expected one")
        return matches[0]

    def genre_ids(self, handles: list[str]) -> list[str]:
        for handle in handles:
            if handle not in self._genre_ids:
                node = self.gql(GENRE_BY_HANDLE, h=handle)["metaobjectByHandle"]
                if not node:
                    raise SetupError(f"Shopify has no genre value '{handle}' (shopify--genre metaobject)")
                self._genre_ids[handle] = node["id"]
        return [self._genre_ids[h] for h in handles]

    def last_run(self) -> dict | None:
        node = self.gql(LAST_RUN)["shop"]["metafield"]
        if not node:
            return None
        try:
            return json.loads(node["value"])
        except (TypeError, ValueError):
            return None

    def read_back(self, product_id: str) -> dict:
        return self.gql(READ_BACK, id=product_id)["product"]

    # writes

    def save_last_run(self, summary: dict) -> None:
        shop_id = self.gql(SHOP_ID)["shop"]["id"]
        self.mutate(SET_METAFIELDS, "metafieldsSet", m=[{
            "ownerId": shop_id, "namespace": LAST_RUN_NAMESPACE, "key": LAST_RUN_KEY,
            "type": "json", "value": json.dumps(summary)}])

    def product_set(self, product_input: dict) -> dict:
        return self.mutate(PRODUCT_SET, "productSet", input=product_input)["product"]

    def publish(self, product_id: str, publication_id: str) -> None:
        self.mutate(PUBLISH, "publishablePublish", id=product_id, input=[{"publicationId": publication_id}])


def shop_from_env(env: dict) -> RentalShop:
    store = env["SHOPIFY_STORE"].strip()
    token = cached_token(store, env["SHOPIFY_CLIENT_ID"].strip(), env["SHOPIFY_CLIENT_SECRET"].strip())
    return RentalShop(api.make_executor(store, token), store)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_shopify.py" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add catalog/errors.py catalog/rental_sync/shopify.py tests/catalog/tests_rental_sync_fakes.py tests/catalog/test_rental_sync_shopify.py
git commit -m "rental_sync: Shopify client for barcode diff, setup checks and last run"
```

---

### Task 4: Create one copy

**Files:**
- Create: `catalog/rental_sync/create.py`
- Test: `tests/catalog/test_rental_sync_create.py`

**Interfaces:**
- Consumes: `transform(item) -> copy record`; `is_new_flow_barcode`; `slugify`; `catalog.shopify.writer.MOVIE_CATEGORY_IDS["Media > Videos"]`; a `RentalShop`-shaped `shop` (Task 3); `ShopifyError`, `SetupError`.
- Produces:
  - `FIXED_TAGS = ("Rental", "Barcode Not Printed")`
  - `handle_for(copy) -> str`, `description_html(text) -> str`, `admin_url(store, product_id) -> str`
  - `product_set_input(copy, handle, location_id, genre_ids, poster: dict | None) -> dict`
  - `verify(node, copy, handle, publication_id) -> list[str]`
  - `create_copy(shop, item: dict, poster: dict | None, sleep=time.sleep) -> dict` → **create result**:
    `{"status": "created" | "skipped_exists" | "failed", "barcode", "title", "handle", "admin_url", "poster": "ok" | "failed" | "none", "message", "problems": [str]}`.
    `item` = the copy's `libib` dict; `poster` = `{"url": "https://…", "alt": str}` or `None`. `SetupError` propagates; `ShopifyError` becomes `failed`.

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_rental_sync_create.py`:

```python
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import ONLINE_STORE_ID, FakeShop  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync.create import admin_url, create_copy, description_html, handle_for  # noqa: E402
from catalog.rental_sync.transform import transform  # noqa: E402

POSTER = {"url": "https://image.tmdb.org/t/p/w1280/jaws.jpg", "alt": "Jaws (1975) poster"}


def item(**overrides):
    base = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror, thriller, criterion",
            "description": "A shark.", "created": "2026-10-14"}
    base.update(overrides)
    return base


def run(shop, poster=POSTER, **overrides):
    sleeps = []
    result = create_copy(shop, item(**overrides), poster, sleep=sleeps.append)
    return result, sleeps


class TestHelpers(unittest.TestCase):
    def test_handle(self):
        self.assertEqual(handle_for(transform(item(title="The Monkey's Uncle", tags="blu-ray, comedy"))),
                         "the-monkeys-uncle-blu-ray-rental-2010000000014")

    def test_description_is_escaped(self):
        self.assertEqual(description_html("Tom & Jerry <b>live</b>"), "<p>Tom &amp; Jerry &lt;b&gt;live&lt;/b&gt;</p>")
        self.assertEqual(description_html(""), "")

    def test_admin_url(self):
        self.assertEqual(admin_url("lms-sandbox-lutsfahz.myshopify.com", "gid://shopify/Product/42"),
                         "https://admin.shopify.com/store/lms-sandbox-lutsfahz/products/42")


class TestCreate(unittest.TestCase):
    def test_creates_with_every_field(self):
        shop = FakeShop()
        result, _ = run(shop)
        self.assertEqual(result["status"], "created", result)
        self.assertEqual(result["poster"], "ok")
        self.assertEqual(result["admin_url"], "https://admin.shopify.com/store/lms-sandbox-lutsfahz/products/101")
        sent = shop.created[0]
        self.assertEqual(sent["handle"], "jaws-vhs-rental-2010000000014")
        self.assertEqual((sent["title"], sent["vendor"], sent["status"]), ("Jaws", "VHS", "ACTIVE"))
        self.assertEqual(sent["descriptionHtml"], "<p>A shark.</p>")
        self.assertEqual(sent["category"], "gid://shopify/TaxonomyCategory/me-7")
        self.assertEqual(sent["tags"], ["Rental", "Barcode Not Printed", "criterion"])
        self.assertEqual(sent["productOptions"], [{"name": "Genre", "position": 1, "values": [{"name": "Horror"}]}])
        variant = sent["variants"][0]
        self.assertEqual(variant["optionValues"], [{"optionName": "Genre", "name": "Horror"}])
        self.assertEqual((variant["barcode"], variant["price"], variant["taxable"], variant["inventoryPolicy"]),
                         ("2010000000014", "0.00", False, "DENY"))
        self.assertEqual(variant["inventoryItem"], {"tracked": True})
        self.assertEqual(variant["inventoryQuantities"],
                         [{"locationId": "gid://shopify/Location/1", "name": "available", "quantity": 1}])
        metafield = sent["metafields"][0]
        self.assertEqual((metafield["namespace"], metafield["key"], metafield["type"]),
                         ("shopify", "genre", "list.metaobject_reference"))
        self.assertEqual(json.loads(metafield["value"]),
                         ["gid://shopify/Metaobject/horror", "gid://shopify/Metaobject/thriller"])
        self.assertEqual(sent["files"], [{"originalSource": POSTER["url"], "alt": POSTER["alt"], "contentType": "IMAGE"}])
        self.assertEqual(shop.published, [("gid://shopify/Product/101", ONLINE_STORE_ID)])

    def test_no_poster(self):
        shop = FakeShop()
        result, _ = run(shop, poster=None)
        self.assertEqual((result["status"], result["poster"]), ("created", "none"))
        self.assertNotIn("files", shop.created[0])

    def test_pasted_poster_without_alt_gets_title_alt(self):
        shop = FakeShop()
        run(shop, poster={"url": "https://example.com/p.jpg", "alt": ""})
        self.assertEqual(shop.created[0]["files"][0]["alt"], "Jaws poster")

    def test_barcode_already_in_shopify_is_skipped(self):
        shop = FakeShop(barcodes=["2010000000014"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "skipped_exists")
        self.assertIn("existing-2010000000014", result["message"])
        self.assertEqual(shop.created, [])

    def test_double_submit_creates_once(self):
        shop = FakeShop()
        first, _ = run(shop)
        second, _ = run(shop)
        self.assertEqual((first["status"], second["status"]), ("created", "skipped_exists"))
        self.assertEqual(len(shop.created), 1)

    def test_handle_already_in_shopify_is_skipped(self):
        shop = FakeShop(handles=["jaws-vhs-rental-2010000000014"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "skipped_exists")
        self.assertEqual(shop.created, [])

    def test_set_aside_copy_is_refused(self):
        shop = FakeShop()
        result, _ = run(shop, tags="vhs, horor")
        self.assertEqual(result["status"], "failed")
        self.assertIn("looks like a misspelling", result["message"])
        self.assertEqual(shop.created, [])

    def test_legacy_barcode_is_refused(self):
        shop = FakeShop()
        result, _ = run(shop, barcode="20144890")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(shop.created, [])

    def test_product_set_error_fails_without_publishing(self):
        shop = FakeShop(set_error=ShopifyError("Handle has already been taken"))
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Handle has already been taken", result["message"])
        self.assertEqual(shop.published, [])

    def test_publish_error_says_the_product_exists(self):
        shop = FakeShop(publish_error=ShopifyError("Publication not found"))
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["admin_url"])
        self.assertIn("created in Shopify but", result["message"])
        self.assertIn("Publication not found", result["message"])

    def test_verify_mismatches_fail(self):
        shop = FakeShop(lose=["taxable", "quantity", "tags"])
        result, _ = run(shop)
        self.assertEqual(result["status"], "failed")
        self.assertIn("charges tax", result["problems"])
        self.assertIn("quantity is 0, not 1", result["problems"])
        self.assertIn("missing tags: Rental, Barcode Not Printed, criterion", result["problems"])

    def test_also_on_point_of_sale_fails(self):
        result, _ = run(FakeShop(extra_channels=["Point of Sale"]))
        self.assertEqual(result["status"], "failed")
        self.assertIn("also on Point of Sale", result["problems"])

    def test_poster_that_shopify_could_not_fetch(self):
        result, _ = run(FakeShop(media=["PROCESSING", "FAILED"]))
        self.assertEqual((result["status"], result["poster"]), ("created", "failed"))

    def test_poster_still_processing_counts_as_ok_after_a_bounded_wait(self):
        result, sleeps = run(FakeShop(media=["PROCESSING"]))
        self.assertEqual((result["status"], result["poster"]), ("created", "ok"))
        self.assertLessEqual(sum(sleeps), 20)
        self.assertTrue(sleeps)

    def test_setup_errors_propagate(self):
        with self.assertRaises(SetupError):
            run(FakeShop(location_error=SetupError("two locations")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_create.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.create'`.

- [ ] **Step 3: Implement**

Create `catalog/rental_sync/create.py`:

```python
"""Create one Libib copy as a Shopify rental product, then read it back and
check it landed as intended.

Rerun-safe: a copy whose barcode or handle is already in Shopify is skipped,
so a double-click, a second tab or a re-run after a crash never duplicates.
Shopify fields are always derived here from the Libib values, never taken
from the browser.
"""

import html
import json
import time

from catalog.core.barcodes import is_new_flow_barcode
from catalog.core.handles import slugify
from catalog.errors import ShopifyError
from catalog.rental_sync.transform import transform
from catalog.shopify.writer import MOVIE_CATEGORY_IDS

FIXED_TAGS = ("Rental", "Barcode Not Printed")
CATEGORY_ID = MOVIE_CATEGORY_IDS["Media > Videos"]
MEDIA_WAIT_SECONDS = 20
MEDIA_POLL_SECONDS = 2
MAX_ALT_LENGTH = 500


def handle_for(copy: dict) -> str:
    return f"{slugify(copy['title'])}-{slugify(copy['format'])}-rental-{copy['barcode']}"


def description_html(text: str) -> str:
    return f"<p>{html.escape(text, quote=False)}</p>" if text else ""


def admin_url(store: str, product_id: str) -> str:
    return f"https://admin.shopify.com/store/{store.split('.')[0]}/products/{product_id.rsplit('/', 1)[-1]}"


def _tags(copy: dict) -> list[str]:
    return list(FIXED_TAGS) + copy["extra_tags"]


def product_set_input(copy: dict, handle: str, location_id: str, genre_ids: list[str], poster: dict | None) -> dict:
    genre = copy["genres"][0]["name"]
    product = {
        "title": copy["title"],
        "handle": handle,
        "descriptionHtml": description_html(copy["description"]),
        "vendor": copy["format"],
        "category": CATEGORY_ID,
        "tags": _tags(copy),
        "status": "ACTIVE",
        "productOptions": [{"name": "Genre", "position": 1, "values": [{"name": genre}]}],
        "variants": [{
            "optionValues": [{"optionName": "Genre", "name": genre}],
            "barcode": copy["barcode"],
            "price": "0.00",
            "taxable": False,
            "inventoryPolicy": "DENY",
            "inventoryItem": {"tracked": True},
            "inventoryQuantities": [{"locationId": location_id, "name": "available", "quantity": 1}],
        }],
        "metafields": [{"namespace": "shopify", "key": "genre", "type": "list.metaobject_reference",
                        "value": json.dumps(genre_ids)}],
    }
    if poster:
        alt = (poster.get("alt") or f"{copy['title']} poster")[:MAX_ALT_LENGTH]
        product["files"] = [{"originalSource": poster["url"], "alt": alt, "contentType": "IMAGE"}]
    return product


def verify(node: dict, copy: dict, handle: str, publication_id: str) -> list[str]:
    problems = []
    if node["handle"] != handle:
        problems.append(f"handle is {node['handle']}, not {handle}")
    variants = node["variants"]["nodes"]
    if len(variants) != 1:
        problems.append(f"has {len(variants)} variants, not 1")
    else:
        variant = variants[0]
        if (variant.get("barcode") or "").strip() != copy["barcode"]:
            problems.append(f"barcode is {variant.get('barcode')!r}")
        if variant.get("taxable") is not False:
            problems.append("charges tax")
        if variant.get("inventoryQuantity") != 1:
            problems.append(f"quantity is {variant.get('inventoryQuantity')}, not 1")
        if not (variant.get("inventoryItem") or {}).get("tracked"):
            problems.append("inventory is not tracked")
    missing = [t for t in _tags(copy) if t not in node["tags"]]
    if missing:
        problems.append("missing tags: " + ", ".join(missing))
    published = {n["publication"]["id"]: n["publication"]["name"] for n in node["resourcePublicationsV2"]["nodes"]}
    if publication_id not in published:
        problems.append("not on the Online Store")
    others = sorted(name for pid, name in published.items() if pid != publication_id)
    if others:
        problems.append("also on " + ", ".join(others))
    return problems


def _poster_status(node: dict) -> str:
    statuses = [m["status"] for m in node["media"]["nodes"]]
    if not statuses:
        return "failed"
    return "failed" if "FAILED" in statuses else "ok"


def _read_settled(shop, product_id: str, wait_for_media: bool, sleep) -> dict:
    node = shop.read_back(product_id)
    waited = 0
    while wait_for_media and waited < MEDIA_WAIT_SECONDS and any(
            m["status"] in ("UPLOADED", "PROCESSING") for m in node["media"]["nodes"]):
        sleep(MEDIA_POLL_SECONDS)
        waited += MEDIA_POLL_SECONDS
        node = shop.read_back(product_id)
    return node


def create_copy(shop, item: dict, poster: dict | None, sleep=time.sleep) -> dict:
    copy = transform(item)
    result = {"status": "failed", "barcode": copy["barcode"], "title": copy["title"], "handle": "",
              "admin_url": "", "poster": "none", "message": "", "problems": []}
    if not is_new_flow_barcode(copy["barcode"]):
        return {**result, "message": "not ready: barcode is not a 13-digit 201… Libib barcode"}
    if copy["set_aside"]:
        return {**result, "message": "not ready: " + "; ".join(copy["set_aside"])}
    handle = handle_for(copy)
    result["handle"] = handle

    try:
        owner = shop.barcode_owner(copy["barcode"])
        if owner:
            return {**result, "status": "skipped_exists", "message": f"already in Shopify ({owner})"}
        if shop.handle_taken(handle):
            return {**result, "status": "skipped_exists", "message": f"a product with handle {handle} already exists"}
        location = shop.location_id()
        genre_ids = shop.genre_ids([g["handle"] for g in copy["genres"]])
        publication = shop.online_store_publication_id()
        product = shop.product_set(product_set_input(copy, handle, location, genre_ids, poster))
    except ShopifyError as exc:
        return {**result, "message": str(exc)}

    result["admin_url"] = admin_url(shop.store, product["id"])
    try:
        shop.publish(product["id"], publication)
        node = _read_settled(shop, product["id"], bool(poster), sleep)
    except ShopifyError as exc:
        return {**result, "message": f"created in Shopify but not finished ({exc}) — open it in Shopify admin, "
                                     f"publish it to the Online Store and check its details"}

    problems = verify(node, copy, handle, publication)
    if problems:
        return {**result, "problems": problems,
                "message": "created in Shopify but needs checking: " + "; ".join(problems)}
    return {**result, "status": "created", "poster": _poster_status(node) if poster else "none"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_create.py" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalog/rental_sync/create.py tests/catalog/test_rental_sync_create.py
git commit -m "rental_sync: create one rental product per copy, rerun-safe, verified"
```

---

### Task 5: Poster lookup

**Files:**
- Create: `catalog/rental_sync/posters.py`
- Test: `tests/catalog/test_rental_sync_posters.py`

**Interfaces:**
- Consumes: `catalog.tmdb.match.match_product(row, fetch_fn) -> MatchResult(kind, best, reason)` (kinds `confident|ambiguous|none|error`; raises `CatalogError` for a bad key), `poster_url(best)`, `alt_text_for(title, best)`; `GENRE_METAFIELD`.
- Produces: `lookup_poster(copy: dict, fetch_fn) -> dict` → **poster result**:
  `{"barcode", "kind": "confident" | "unsure" | "none" | "error", "url", "alt", "candidate": {"title", "year"} | None, "reason"}`.

- [ ] **Step 1: Write the failing tests**

`tests/catalog/test_rental_sync_posters.py`:

```python
import unittest
from unittest import mock

from catalog.core.columns import GENRE_METAFIELD
from catalog.errors import CatalogError
from catalog.rental_sync.posters import lookup_poster
from catalog.rental_sync.transform import transform
from catalog.tmdb.match import POSTER_BASE_URL, MatchResult

COPY = transform({"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror, thriller",
                  "description": "A shark.", "created": ""})
BEST = {"title": "Jaws", "release_date": "1975-06-20", "poster_path": "/jaws.jpg"}


def lookup(result):
    with mock.patch("catalog.rental_sync.posters.match_product", return_value=result) as matcher:
        out = lookup_poster(COPY, fetch_fn=lambda q, y: {})
    return out, matcher.call_args.args[0]


class TestLookupPoster(unittest.TestCase):
    def test_row_shape_sent_to_the_matcher(self):
        _, row = lookup(MatchResult("none", None, "no TMDB match"))
        self.assertEqual(row, {"Title": "Jaws", "Body (HTML)": "A shark.", "Vendor": "VHS",
                               GENRE_METAFIELD: "horror; thriller"})

    def test_confident(self):
        out, _ = lookup(MatchResult("confident", BEST, "confident TMDB match"))
        self.assertEqual(out, {"barcode": "2010000000014", "kind": "confident", "url": f"{POSTER_BASE_URL}/jaws.jpg",
                               "alt": "Jaws (1975) poster", "candidate": {"title": "Jaws", "year": "1975"},
                               "reason": "confident TMDB match"})

    def test_ambiguous_is_unsure(self):
        out, _ = lookup(MatchResult("ambiguous", BEST, "ambiguous match"))
        self.assertEqual((out["kind"], out["url"]), ("unsure", f"{POSTER_BASE_URL}/jaws.jpg"))

    def test_match_without_a_poster_is_none(self):
        out, _ = lookup(MatchResult("confident", dict(BEST, poster_path=None), "confident TMDB match"))
        self.assertEqual((out["kind"], out["url"], out["reason"]), ("none", "", "TMDB has no poster for this film"))

    def test_none_and_error(self):
        self.assertEqual(lookup(MatchResult("none", None, "no TMDB match"))[0]["kind"], "none")
        out, _ = lookup(MatchResult("error", None, "TMDB request failed: timeout"))
        self.assertEqual((out["kind"], out["reason"]), ("error", "TMDB request failed: timeout"))

    def test_bad_key_propagates(self):
        with mock.patch("catalog.rental_sync.posters.match_product", side_effect=CatalogError("TMDB rejected")):
            with self.assertRaises(CatalogError):
                lookup_poster(COPY, fetch_fn=lambda q, y: {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_posters.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.posters'`.

- [ ] **Step 3: Implement**

Create `catalog/rental_sync/posters.py`:

```python
"""TMDB poster for one copy, through the audit's matcher. Only a confident
match is pre-filled in the app; an ambiguous one is offered as "Not sure —
check this" and stays blank until the client accepts it."""

from catalog.core.columns import GENRE_METAFIELD
from catalog.tmdb.match import alt_text_for, match_product, poster_url

KINDS = {"confident": "confident", "ambiguous": "unsure", "none": "none", "error": "error"}


def lookup_poster(copy: dict, fetch_fn) -> dict:
    row = {"Title": copy["title"], "Body (HTML)": copy["description"], "Vendor": copy["format"],
           GENRE_METAFIELD: "; ".join(g["handle"] for g in copy["genres"])}
    result = match_product(row, fetch_fn)
    out = {"barcode": copy["barcode"], "kind": KINDS[result.kind], "url": "", "alt": "", "candidate": None,
           "reason": result.reason}
    if out["kind"] in ("confident", "unsure"):
        url = poster_url(result.best)
        if not url:
            return {**out, "kind": "none", "reason": "TMDB has no poster for this film"}
        best = result.best
        out.update(url=url, alt=alt_text_for(copy["title"], best),
                   candidate={"title": best.get("title", ""), "year": (best.get("release_date") or "")[:4]})
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_posters.py" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalog/rental_sync/posters.py tests/catalog/test_rental_sync_posters.py
git commit -m "rental_sync: TMDB poster lookup per copy"
```

---

### Task 6: Auth, HTTP layer and Vercel entry points

**Files:**
- Create: `catalog/rental_sync/auth.py`
- Create: `catalog/rental_sync/web.py`
- Create: `api/rental_sync/login.py`, `status.py`, `prepare.py`, `posters.py`, `create.py`, `finish.py`
- Create: `vercel.json`, `.vercelignore`
- Test: `tests/catalog/test_rental_sync_auth.py`, `tests/catalog/test_rental_sync_web.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5; `catalog.tmdb.client.make_fetcher(api_key)`; `shop_from_env(env)`.
- Produces:
  - `auth.COOKIE_NAME`, `auth.SESSION_SECONDS`, `password_matches(given, expected) -> bool`, `new_session(secret, now) -> str`, `session_cookie(value) -> str`, `session_valid(cookie_header, secret, now) -> bool`
  - `web.Deps(env, shop, fetcher, now, sleep, log)`, `web.respond(route, method, headers, body, deps) -> (status: int, headers: list[tuple[str, str]], body: bytes)`, `web.make_handler(route, deps_factory=default_deps)`
  - HTTP API (all JSON; errors are `{"error": {"kind": "auth"|"input"|"shopify"|"setup", "message", "detail"}}`):
    - `POST /api/rental_sync/login` `{password}` → `200 {"ok": true}` + `Set-Cookie`, or `401`
    - `GET /api/rental_sync/status` → `{"store", "last_run"}`
    - `POST /api/rental_sync/prepare` `{barcodes, library}` (base64 gzip) → prepare result + `"vocabulary"`
    - `POST /api/rental_sync/posters` `{copies: [copy record] (≤5)}` → `{"posters": [poster result]}`
    - `POST /api/rental_sync/create` `{item: libib dict, poster: {url, alt} | null}` → create result
    - `POST /api/rental_sync/finish` `{created, skipped, failed, set_aside}` → `{"last_run"}`

- [ ] **Step 1: Write the failing auth tests**

`tests/catalog/test_rental_sync_auth.py`:

```python
import unittest

from catalog.rental_sync.auth import (
    COOKIE_NAME, SESSION_SECONDS, new_session, password_matches, session_cookie, session_valid,
)

SECRET = "s3cret"


class TestAuth(unittest.TestCase):
    def test_password(self):
        self.assertTrue(password_matches("hunter2", "hunter2"))
        self.assertFalse(password_matches("hunter3", "hunter2"))
        self.assertFalse(password_matches("", ""))

    def test_session_round_trip(self):
        value = new_session(SECRET, 1000)
        self.assertTrue(session_valid(f"other=1; {COOKIE_NAME}={value}", SECRET, 1001))

    def test_expired(self):
        value = new_session(SECRET, 1000)
        self.assertFalse(session_valid(f"{COOKIE_NAME}={value}", SECRET, 1000 + SESSION_SECONDS + 1))

    def test_tampered_or_wrong_secret(self):
        expiry, _, sig = new_session(SECRET, 1000).partition(".")
        self.assertFalse(session_valid(f"{COOKIE_NAME}={int(expiry) + 999}.{sig}", SECRET, 1001))
        self.assertFalse(session_valid(f"{COOKIE_NAME}={expiry}.{sig}", "other", 1001))
        self.assertFalse(session_valid(f"{COOKIE_NAME}=garbage", SECRET, 1001))
        self.assertFalse(session_valid("", SECRET, 1001))
        self.assertFalse(session_valid('bad"cookie', SECRET, 1001))

    def test_cookie_attributes(self):
        header = session_cookie("v")
        for part in (f"{COOKIE_NAME}=v", "Path=/", f"Max-Age={SESSION_SECONDS}", "HttpOnly", "Secure", "SameSite=Strict"):
            self.assertIn(part, header)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_auth.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.auth'`.

- [ ] **Step 3: Implement `auth.py`**

Create `catalog/rental_sync/auth.py`:

```python
"""One shared password, then a signed session cookie. The cookie carries only
its expiry and an HMAC of it; there is no server-side session store."""

import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie

COOKIE_NAME = "lms_rental_sync"
SESSION_SECONDS = 12 * 3600


def password_matches(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _sign(secret: str, expiry: int) -> str:
    return hmac.new(secret.encode("utf-8"), str(expiry).encode("ascii"), hashlib.sha256).hexdigest()


def new_session(secret: str, now: float) -> str:
    expiry = int(now) + SESSION_SECONDS
    return f"{expiry}.{_sign(secret, expiry)}"


def session_cookie(value: str) -> str:
    return f"{COOKIE_NAME}={value}; Path=/; Max-Age={SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict"


def session_valid(cookie_header: str, secret: str, now: float) -> bool:
    jar = SimpleCookie()
    try:
        jar.load(cookie_header or "")
    except CookieError:
        return False
    morsel = jar.get(COOKIE_NAME)
    if morsel is None:
        return False
    expiry_text, _, signature = morsel.value.partition(".")
    if not expiry_text.isdigit():
        return False
    expiry = int(expiry_text)
    return expiry > now and hmac.compare_digest(signature, _sign(secret, expiry))
```

- [ ] **Step 4: Run the auth tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_auth.py" -v`
Expected: PASS.

- [ ] **Step 5: Write the failing web tests**

`tests/catalog/test_rental_sync_web.py`:

```python
import base64
import gzip
import importlib.util
import json
import sys
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeShop  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync.auth import COOKIE_NAME, new_session  # noqa: E402
from catalog.rental_sync.web import ROUTES, Deps, respond  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ENV = {"SYNC_PASSWORD": "pw", "SESSION_SECRET": "secret", "SHOPIFY_STORE": "lms-sandbox-lutsfahz.myshopify.com",
       "SHOPIFY_CLIENT_ID": "id", "SHOPIFY_CLIENT_SECRET": "cs", "TMDB_API_KEY": "tk"}
NOW = 1_800_000_000.0
BARCODES = ("id,item_type,barcode,title,collection,tags,call_number,created\n"
            'a1,movie,2010000000014,Jaws,Rental Library,"vhs, horror",,2026-10-14\n')
LIBRARY = "id,item_type,title,collection,description,call_number\na1,movie,Jaws,Rental Library,A shark.,\n"


def upload(text):
    return base64.b64encode(gzip.compress(text.encode())).decode()


class Harness:
    def __init__(self, shop=None, env=None, fetch_results=None):
        self.shop = shop or FakeShop()
        self.sleeps, self.logs = [], []
        self.deps = Deps(env=dict(ENV if env is None else env), shop=lambda env: self.shop,
                         fetcher=lambda env: (lambda q, y: {"results": fetch_results or []}),
                         now=lambda: NOW, sleep=self.sleeps.append, log=self.logs.append)

    def call(self, route, body=None, method=None, cookie=True):
        headers = {"cookie": f"{COOKIE_NAME}={new_session('secret', NOW)}"} if cookie else {}
        method = method or ("GET" if route == "status" else "POST")
        raw = json.dumps(body).encode() if isinstance(body, (dict, list)) else (body or b"")
        status, out_headers, out = respond(route, method, headers, raw, self.deps)
        return status, dict(out_headers), json.loads(out)


class TestGuards(unittest.TestCase):
    def test_missing_setting_is_setup_error(self):
        status, _, body = Harness(env={**ENV, "SESSION_SECRET": ""}).call("status")
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertIn("SESSION_SECRET", body["error"]["detail"])

    def test_unknown_route_and_wrong_method(self):
        h = Harness()
        self.assertEqual(h.call("nope")[0], 404)
        self.assertEqual(h.call("prepare", method="GET")[0], 405)

    def test_every_route_but_login_needs_a_session(self):
        h = Harness()
        for route in ("status", "prepare", "posters", "create", "finish"):
            status, _, body = h.call(route, {}, cookie=False)
            self.assertEqual((status, body["error"]["kind"]), (401, "auth"), route)

    def test_invalid_json_is_input_error(self):
        status, _, body = Harness().call("prepare", b"{not json")
        self.assertEqual((status, body["error"]["kind"]), (400, "input"))


class TestLogin(unittest.TestCase):
    def test_wrong_password_waits(self):
        h = Harness()
        status, headers, _ = h.call("login", {"password": "nope"}, cookie=False)
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(h.sleeps, [2])

    def test_right_password_sets_cookie(self):
        status, headers, body = Harness().call("login", {"password": "pw"}, cookie=False)
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertIn(f"{COOKIE_NAME}=", headers["Set-Cookie"])


class TestRoutes(unittest.TestCase):
    def test_status(self):
        status, headers, body = Harness(shop=FakeShop(last={"created": 3})).call("status")
        self.assertEqual((status, body), (200, {"store": "lms-sandbox-lutsfahz.myshopify.com", "last_run": {"created": 3}}))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_prepare(self):
        status, _, body = Harness().call("prepare", {"barcodes": upload(BARCODES), "library": upload(LIBRARY)})
        self.assertEqual(status, 200)
        self.assertEqual([c["title"] for c in body["ready"]], ["Jaws"])
        self.assertIn("vhs", body["vocabulary"]["formats"])

    def test_prepare_bad_upload_and_swapped(self):
        h = Harness()
        self.assertEqual(h.call("prepare", {"barcodes": "%%", "library": upload(LIBRARY)})[0], 400)
        status, _, body = h.call("prepare", {"barcodes": upload(LIBRARY), "library": upload(BARCODES)})
        self.assertEqual(status, 400)
        self.assertIn("swapped", body["error"]["message"])

    def test_prepare_when_shopify_is_down(self):
        h = Harness(shop=FakeShop(barcodes_error=ShopifyError("could not reach store")))
        status, _, body = h.call("prepare", {"barcodes": upload(BARCODES), "library": upload(LIBRARY)})
        self.assertEqual((status, body["error"]["kind"]), (503, "shopify"))
        self.assertIn("Nothing has been changed", body["error"]["message"])

    def test_posters(self):
        copy = {"libib": {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror",
                          "description": "", "created": ""}}
        status, _, body = Harness().call("posters", {"copies": [copy]})
        self.assertEqual((status, body["posters"][0]["kind"]), (200, "none"))
        self.assertEqual(Harness().call("posters", {"copies": [copy] * 6})[0], 400)

    def test_create(self):
        h = Harness()
        item = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror", "description": "", "created": ""}
        status, _, body = h.call("create", {"item": item, "poster": None})
        self.assertEqual((status, body["status"]), (200, "created"))
        self.assertTrue(any("2010000000014" in line and "created" in line for line in h.logs))
        bad = h.call("create", {"item": item, "poster": {"url": "http://x/p.jpg", "alt": ""}})
        self.assertEqual(bad[0], 400)

    def test_create_setup_error(self):
        h = Harness(shop=FakeShop(location_error=SetupError("found 2 locations")))
        item = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror", "description": "", "created": ""}
        status, _, body = h.call("create", {"item": item, "poster": None})
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertIn("contact Liam", body["error"]["message"])

    def test_finish(self):
        h = Harness()
        status, _, body = h.call("finish", {"created": 2, "skipped": 1, "failed": 0, "set_aside": 3})
        self.assertEqual(status, 200)
        self.assertEqual(h.shop.saved[0], {"created": 2, "skipped": 1, "failed": 0, "set_aside": 3,
                                           "finished_at": "2027-01-15T08:00:00+00:00"})
        self.assertEqual(h.call("finish", {"created": "lots"})[0], 400)

    def test_unexpected_error_is_logged_not_leaked(self):
        class Broken(FakeShop):
            def last_run(self):
                raise ZeroDivisionError("boom")
        h = Harness(shop=Broken())
        status, _, body = h.call("status")
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertTrue(any("ZeroDivisionError" in line for line in h.logs))


class TestEntryPoints(unittest.TestCase):
    def test_every_route_has_a_vercel_function(self):
        files = {p.stem for p in (REPO / "api" / "rental_sync").glob("*.py")}
        self.assertEqual(files, set(ROUTES))

    def test_entry_points_import_and_expose_a_handler(self):
        for route in ROUTES:
            path = REPO / "api" / "rental_sync" / f"{route}.py"
            spec = importlib.util.spec_from_file_location(f"api_rental_sync_{route}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(issubclass(module.handler, BaseHTTPRequestHandler), route)


if __name__ == "__main__":
    unittest.main()
```

Note: `NOW = 1_800_000_000` is `2027-01-15T08:00:00+00:00`.

- [ ] **Step 6: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_web.py" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog.rental_sync.web'`.

- [ ] **Step 7: Implement `web.py`**

Create `catalog/rental_sync/web.py`:

```python
"""HTTP layer for the rental sync app's Vercel functions.

Every route goes through respond(), which the tests call directly;
make_handler() adapts it to the BaseHTTPRequestHandler class Vercel's Python
runtime looks for. Messages are written for the client; technical detail goes
in "detail" (shown behind "Show details") and the function log.
"""

import json
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Callable

from catalog.errors import CatalogError, InputShapeError, SetupError, ShopifyError
from catalog.rental_sync.auth import new_session, password_matches, session_cookie, session_valid
from catalog.rental_sync.create import create_copy
from catalog.rental_sync.posters import lookup_poster
from catalog.rental_sync.prepare import decode_upload, load_uploads, prepare
from catalog.rental_sync.transform import LIBIB_FIELDS, transform, vocabulary

REQUIRED_SETTINGS = ("SYNC_PASSWORD", "SESSION_SECRET", "SHOPIFY_STORE", "SHOPIFY_CLIENT_ID",
                     "SHOPIFY_CLIENT_SECRET", "TMDB_API_KEY")
MAX_BODY_BYTES = 4 * 1024 * 1024
POSTER_BATCH_MAX = 5
FAILED_LOGIN_DELAY_SECONDS = 2
SETUP_MESSAGE = "Something's wrong with the app setup — contact Liam."
SHOPIFY_MESSAGE = "Shopify didn't respond — try again in a few minutes. Nothing has been changed."


@dataclass
class Deps:
    env: dict
    shop: Callable
    fetcher: Callable
    now: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = field(default=print)


def default_deps() -> Deps:
    from catalog.rental_sync.shopify import shop_from_env
    from catalog.tmdb.client import make_fetcher
    return Deps(env=dict(os.environ), shop=shop_from_env, fetcher=lambda env: make_fetcher(env["TMDB_API_KEY"]))


Response = tuple[int, list[tuple[str, str]], bytes]


def _json(status: int, payload: dict, extra_headers=()) -> Response:
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"),
               *extra_headers]
    return status, headers, json.dumps(payload).encode("utf-8")


def _error(status: int, kind: str, message: str, detail: str = "") -> Response:
    return _json(status, {"error": {"kind": kind, "message": message, "detail": detail}})


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _item(raw) -> dict:
    if not isinstance(raw, dict):
        raise InputShapeError("That request was missing the Libib copy — reload the page and start again.")
    return {k: str(raw.get(k) or "") for k in LIBIB_FIELDS}


def _login(payload: dict, deps: Deps) -> Response:
    if password_matches(_text(payload, "password"), deps.env["SYNC_PASSWORD"]):
        cookie = session_cookie(new_session(deps.env["SESSION_SECRET"], deps.now()))
        return _json(200, {"ok": True}, [("Set-Cookie", cookie)])
    deps.sleep(FAILED_LOGIN_DELAY_SECONDS)
    return _error(401, "auth", "That password isn't right.")


def _status(payload: dict, deps: Deps) -> Response:
    shop = deps.shop(deps.env)
    return _json(200, {"store": shop.store, "last_run": shop.last_run()})


def _prepare(payload: dict, deps: Deps) -> Response:
    barcodes = decode_upload(_text(payload, "barcodes"), "Barcodes export")
    library = decode_upload(_text(payload, "library"), "Library export")
    items = load_uploads(barcodes, library)
    result = prepare(items, deps.shop(deps.env).new_flow_barcodes())
    deps.log(f"prepare: {len(result['ready'])} ready, {len(result['set_aside'])} set aside, "
             f"{result['already_in_shopify']} already in Shopify")
    return _json(200, {**result, "vocabulary": vocabulary()})


def _posters(payload: dict, deps: Deps) -> Response:
    copies = payload.get("copies")
    if not isinstance(copies, list) or not 1 <= len(copies) <= POSTER_BATCH_MAX:
        raise InputShapeError(f"Send between 1 and {POSTER_BATCH_MAX} copies at a time.")
    fetch = deps.fetcher(deps.env)
    copies = [transform(_item(c.get("libib") if isinstance(c, dict) else None)) for c in copies]
    return _json(200, {"posters": [lookup_poster(copy, fetch) for copy in copies]})


def _create(payload: dict, deps: Deps) -> Response:
    item = _item(payload.get("item"))
    poster = payload.get("poster")
    if poster is not None:
        url = str((poster or {}).get("url") or "").strip() if isinstance(poster, dict) else ""
        if not url.startswith("https://"):
            raise InputShapeError("Poster links must start with https://")
        poster = {"url": url, "alt": str(poster.get("alt") or "")}
    result = create_copy(deps.shop(deps.env), item, poster, sleep=deps.sleep)
    deps.log(f"create {result['barcode']} {result['status']} {result['title']!r} {result['message']}".rstrip())
    return _json(200, result)


def _finish(payload: dict, deps: Deps) -> Response:
    try:
        counts = {k: int(payload.get(k) or 0) for k in ("created", "skipped", "failed", "set_aside")}
    except (TypeError, ValueError):
        raise InputShapeError("The run summary was malformed.") from None
    summary = {**counts, "finished_at": datetime.fromtimestamp(deps.now(), timezone.utc).isoformat(timespec="seconds")}
    deps.shop(deps.env).save_last_run(summary)
    return _json(200, {"last_run": summary})


ROUTES = {"login": _login, "status": _status, "prepare": _prepare, "posters": _posters,
          "create": _create, "finish": _finish}


def respond(route: str, method: str, headers: dict, body: bytes, deps: Deps) -> Response:
    try:
        missing = [name for name in REQUIRED_SETTINGS if not (deps.env.get(name) or "").strip()]
        if missing:
            raise SetupError(f"missing setting(s): {', '.join(missing)}")
        handler = ROUTES.get(route)
        if handler is None:
            return _error(404, "input", "Not found.")
        if method != ("GET" if route == "status" else "POST"):
            return _error(405, "input", "Method not allowed.")
        if route != "login" and not session_valid(headers.get("cookie", ""), deps.env["SESSION_SECRET"], deps.now()):
            return _error(401, "auth", "Please log in again.")
        payload = {}
        if method == "POST":
            try:
                payload = json.loads(body or b"{}")
            except ValueError:
                raise InputShapeError("That request wasn't readable — reload the page and try again.") from None
            if not isinstance(payload, dict):
                raise InputShapeError("That request wasn't readable — reload the page and try again.")
        return handler(payload, deps)
    except InputShapeError as exc:
        return _error(400, "input", str(exc))
    except ShopifyError as exc:
        deps.log(f"{route}: Shopify error: {exc}")
        return _error(503, "shopify", SHOPIFY_MESSAGE, str(exc))
    except CatalogError as exc:  # SetupError, MissingEnvError, a rejected TMDB key
        deps.log(f"{route}: setup error: {exc}")
        return _error(500, "setup", SETUP_MESSAGE, str(exc))
    except Exception as exc:  # a bug: log it, don't leak a traceback to the page
        deps.log(f"{route}: unexpected error\n{traceback.format_exc()}")
        return _error(500, "setup", SETUP_MESSAGE, f"unexpected error: {type(exc).__name__}")


def make_handler(route: str, deps_factory=default_deps):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str) -> None:
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_BODY_BYTES:
                status, headers, body = _error(413, "input", "That upload is too big — is it the right Libib export?")
            else:
                raw = self.rfile.read(length) if length else b""
                lowered = {k.lower(): v for k, v in self.headers.items()}
                status, headers, body = respond(route, method, lowered, raw, deps_factory())
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

        def log_message(self, *args):
            pass  # the default writes every request line to stderr; respond() logs what matters

    return Handler
```

- [ ] **Step 8: Create the Vercel entry points**

Create each of the six files below; they differ only in the route name. `api/rental_sync/login.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("login")
```

`api/rental_sync/status.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("status")
```

`api/rental_sync/prepare.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("prepare")
```

`api/rental_sync/posters.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("posters")
```

`api/rental_sync/create.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("create")
```

`api/rental_sync/finish.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.rental_sync.web import make_handler  # noqa: E402

handler = make_handler("finish")
```

- [ ] **Step 9: Create the Vercel config**

`vercel.json` (repo root):

```json
{
  "functions": {
    "api/rental_sync/*.py": { "maxDuration": 60, "includeFiles": "catalog/**" }
  },
  "rewrites": [
    { "source": "/", "destination": "/tools/rental-sync/index.html" }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Content-Security-Policy", "value": "default-src 'self'; img-src 'self' https: data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "no-referrer" }
      ]
    }
  ]
}
```

`.vercelignore` (repo root) — deploy only what the app needs:

```
/*
!/api
!/catalog
!/tools
/tools/*
!/tools/rental-sync
!/vercel.json
__pycache__/
*.pyc
```

- [ ] **Step 10: Run the web tests and the whole suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rental_sync_web.py" -v`
Expected: PASS.
Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: OK.

- [ ] **Step 11: Commit**

```bash
git add catalog/rental_sync/auth.py catalog/rental_sync/web.py api/rental_sync vercel.json .vercelignore tests/catalog/test_rental_sync_auth.py tests/catalog/test_rental_sync_web.py
git commit -m "rental_sync: password session, HTTP dispatcher and Vercel functions"
```

---

### Task 7: Front-end logic

**Files:**
- Create: `tools/rental-sync/logic.js`
- Test: `tests/rental_sync/logic.test.js`

**Interfaces:**
- Consumes: the HTTP API from Task 6 (shapes only).
- Produces (`window.RentalSyncLogic` in the browser, `module.exports` in Node):
  `MAX_FILE_BYTES`, `POSTER_BATCH_SIZE`, `gzipBase64(text) -> Promise<string>`, `fileProblem(file, label) -> string`,
  `batches(list, size) -> array[]`, `byCreatedThenTitle(a, b)`, `shortDate(text)`,
  `isHttpsUrl(text)`, `initialPoster(result) -> poster state`, `acceptSuggestion(poster)`, `pastedPoster(poster, text)`,
  `createPayload(copy, poster) -> {item, poster}`, `summarize(results) -> {created, skipped, failed, posterFailed}`,
  `finishPayload(summary, setAsideCount)`, `printBarcodesUrl(store)`, `describeLastRun(lastRun)`,
  `makeApi({fetch, requireLogin}) -> api(path, body?) -> Promise<data>`.
  Poster state: `{url, alt, original: {url, alt}, suggestion: {url, alt, title, year} | null, note}`.

- [ ] **Step 1: Write the failing tests**

`tests/rental_sync/logic.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const L = require('../../tools/rental-sync/logic.js');

test('gzipBase64 round-trips through gunzip', async () => {
  const text = 'id,barcode\n1,2010000000014\n'.repeat(1000);
  const encoded = await L.gzipBase64(text);
  assert.equal(zlib.gunzipSync(Buffer.from(encoded, 'base64')).toString(), text);
});

test('fileProblem', () => {
  assert.equal(L.fileProblem(null, 'Barcodes export'), 'Choose the Barcodes export file.');
  assert.match(L.fileProblem({ size: L.MAX_FILE_BYTES + 1 }, 'Library export'), /over 5 MB/);
  assert.equal(L.fileProblem({ size: 10 }, 'Library export'), '');
});

test('batches', () => {
  assert.deepEqual(L.batches([1, 2, 3, 4, 5, 6, 7], 5), [[1, 2, 3, 4, 5], [6, 7]]);
  assert.deepEqual(L.batches([], 5), []);
});

test('byCreatedThenTitle and shortDate', () => {
  const list = [{ created: '2026-10-14', title: 'b' }, { created: '2026-10-13', title: 'z' }, { created: '2026-10-14', title: 'A' }];
  assert.deepEqual(list.sort(L.byCreatedThenTitle).map((c) => c.title), ['z', 'A', 'b']);
  assert.equal(L.shortDate('2026-10-14 10:00:00'), '2026-10-14');
  assert.equal(L.shortDate(''), '—');
});

test('isHttpsUrl', () => {
  assert.equal(L.isHttpsUrl('https://image.tmdb.org/t/p/w1280/a.jpg'), true);
  assert.equal(L.isHttpsUrl(' https://x.com/a.jpg '), true);
  assert.equal(L.isHttpsUrl('http://x.com/a.jpg'), false);
  assert.equal(L.isHttpsUrl('javascript:alert(1)'), false);
  assert.equal(L.isHttpsUrl(''), false);
});

const confident = { barcode: 'b', kind: 'confident', url: 'https://t/j.jpg', alt: 'Jaws (1975) poster', candidate: { title: 'Jaws', year: '1975' }, reason: '' };
const unsure = { ...confident, kind: 'unsure' };

test('initialPoster per kind', () => {
  assert.equal(L.initialPoster(confident).url, 'https://t/j.jpg');
  const u = L.initialPoster(unsure);
  assert.equal(u.url, '');
  assert.deepEqual(u.suggestion, { url: 'https://t/j.jpg', alt: 'Jaws (1975) poster', title: 'Jaws', year: '1975' });
  assert.equal(L.initialPoster({ kind: 'none', reason: 'no TMDB match' }).note, 'No poster found');
  assert.equal(L.initialPoster({ kind: 'error', reason: 'timeout' }).note, 'Poster lookup failed — paste a link or leave it blank');
});

test('acceptSuggestion and pastedPoster', () => {
  const accepted = L.acceptSuggestion(L.initialPoster(unsure));
  assert.equal(accepted.url, 'https://t/j.jpg');
  const pasted = L.pastedPoster(L.initialPoster(confident), 'https://mine/p.jpg');
  assert.deepEqual([pasted.url, pasted.alt, pasted.note], ['https://mine/p.jpg', '', '']);
  assert.equal(L.pastedPoster(pasted, '').url, 'https://t/j.jpg');            // clearing restores TMDB's
  assert.equal(L.pastedPoster(pasted, 'http://x/p.jpg').note, 'Links must start with https://');
});

test('createPayload only sends https posters', () => {
  const copy = { libib: { barcode: 'b', title: 'Jaws', tags: 'vhs, horror', description: '', created: '' } };
  assert.deepEqual(L.createPayload(copy, L.initialPoster(confident)),
    { item: copy.libib, poster: { url: 'https://t/j.jpg', alt: 'Jaws (1975) poster' } });
  assert.deepEqual(L.createPayload(copy, L.initialPoster(unsure)), { item: copy.libib, poster: null });
  assert.deepEqual(L.createPayload(copy, { url: 'http://x', alt: '' }), { item: copy.libib, poster: null });
  assert.deepEqual(L.createPayload(copy, undefined), { item: copy.libib, poster: null });
});

test('summarize and finishPayload', () => {
  const s = L.summarize([
    { status: 'created', poster: 'ok' }, { status: 'created', poster: 'failed' },
    { status: 'skipped_exists' }, { status: 'failed' }]);
  assert.deepEqual([s.created.length, s.posterFailed.length, s.skipped.length, s.failed.length], [2, 1, 1, 1]);
  assert.deepEqual(L.finishPayload(s, 4), { created: 2, skipped: 1, failed: 1, set_aside: 4 });
});

test('printBarcodesUrl', () => {
  assert.equal(L.printBarcodesUrl('lms-sandbox-lutsfahz.myshopify.com'),
    'https://admin.shopify.com/store/lms-sandbox-lutsfahz/products?tag=Barcode%20Not%20Printed');
});

test('describeLastRun', () => {
  assert.equal(L.describeLastRun(null), 'No sync yet.');
  const text = L.describeLastRun({ finished_at: '2026-10-14T19:12:00+00:00', created: 18 });
  assert.match(text, /^Last successful sync: Oct 14, 2026/);
  assert.match(text, /18 created$/);
});

function fakeResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('api retries the same request after login', async () => {
  const calls = [];
  let logins = 0;
  const replies = [fakeResponse(401, { error: { message: 'Please log in again.' } }), fakeResponse(200, { ok: 1 })];
  const api = L.makeApi({
    fetch: async (url, options) => { calls.push([url, options.body]); return replies.shift(); },
    requireLogin: async () => { logins += 1; },
  });
  assert.deepEqual(await api('create', { item: { barcode: 'b' } }), { ok: 1 });
  assert.equal(logins, 1);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], calls[1]);
});

test('api surfaces server messages and network failures', async () => {
  const api = L.makeApi({
    fetch: async () => fakeResponse(503, { error: { message: "Shopify didn't respond", detail: 'HTTP 502' } }),
    requireLogin: async () => {},
  });
  await assert.rejects(api('status'), (e) => e.message === "Shopify didn't respond" && e.detail === 'HTTP 502');
  const offline = L.makeApi({ fetch: async () => { throw new TypeError('Failed to fetch'); }, requireLogin: async () => {} });
  await assert.rejects(offline('status'), /Couldn't reach the sync app/);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `node --test tests/rental_sync/logic.test.js`
Expected: FAIL — `Cannot find module '../../tools/rental-sync/logic.js'`.

- [ ] **Step 3: Implement**

Create `tools/rental-sync/logic.js`:

```js
// Pure helpers for the rental sync page. Loaded as a plain <script> in the
// browser (window.RentalSyncLogic) and with require() in the node tests.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RentalSyncLogic = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const POSTER_BATCH_SIZE = 5;
  const PRINT_TAG = 'Barcode Not Printed';

  async function gzipBase64(text) {
    const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'));
    const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  }

  function fileProblem(file, label) {
    if (!file) return `Choose the ${label} file.`;
    if (file.size > MAX_FILE_BYTES) return `The ${label} is over 5 MB — is it the right Libib export?`;
    return '';
  }

  function batches(list, size = POSTER_BATCH_SIZE) {
    const out = [];
    for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
    return out;
  }

  function byCreatedThenTitle(a, b) {
    const created = (a.created || '').localeCompare(b.created || '');
    return created || (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase());
  }

  function shortDate(text) {
    return text ? String(text).slice(0, 10) : '—';
  }

  function isHttpsUrl(text) {
    try {
      return new URL(String(text).trim()).protocol === 'https:';
    } catch (_) {
      return false;
    }
  }

  function initialPoster(result) {
    const base = { url: '', alt: '', original: { url: '', alt: '' }, suggestion: null, note: '' };
    if (result.kind === 'confident') {
      return { ...base, url: result.url, alt: result.alt, original: { url: result.url, alt: result.alt } };
    }
    if (result.kind === 'unsure') {
      const c = result.candidate || {};
      return { ...base, suggestion: { url: result.url, alt: result.alt, title: c.title || '', year: c.year || '' } };
    }
    if (result.kind === 'error') return { ...base, note: 'Poster lookup failed — paste a link or leave it blank' };
    return { ...base, note: 'No poster found' };
  }

  function acceptSuggestion(poster) {
    const s = poster.suggestion;
    return { ...poster, url: s.url, alt: s.alt, original: { url: s.url, alt: s.alt }, note: '' };
  }

  function pastedPoster(poster, text) {
    const url = String(text || '').trim();
    if (!url) return { ...poster, url: poster.original.url, alt: poster.original.alt, note: '' };
    return { ...poster, url, alt: '', note: isHttpsUrl(url) ? '' : 'Links must start with https://' };
  }

  function createPayload(copy, poster) {
    const usable = poster && isHttpsUrl(poster.url);
    return { item: copy.libib, poster: usable ? { url: poster.url.trim(), alt: poster.alt || '' } : null };
  }

  function summarize(results) {
    const out = { created: [], skipped: [], failed: [], posterFailed: [] };
    for (const r of results) {
      if (r.status === 'created') {
        out.created.push(r);
        if (r.poster === 'failed') out.posterFailed.push(r);
      } else if (r.status === 'skipped_exists') {
        out.skipped.push(r);
      } else {
        out.failed.push(r);
      }
    }
    return out;
  }

  function finishPayload(summary, setAsideCount) {
    return { created: summary.created.length, skipped: summary.skipped.length,
      failed: summary.failed.length, set_aside: setAsideCount };
  }

  function printBarcodesUrl(store) {
    const slug = String(store || '').split('.')[0];
    return `https://admin.shopify.com/store/${encodeURIComponent(slug)}/products?tag=${encodeURIComponent(PRINT_TAG)}`;
  }

  function describeLastRun(lastRun) {
    if (!lastRun) return 'No sync yet.';
    const when = new Date(lastRun.finished_at).toLocaleString('en-US', {
      dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/New_York' });
    return `Last successful sync: ${when} — ${lastRun.created} created`;
  }

  // fetch wrapper: JSON in/out; a 401 waits for requireLogin() and then
  // re-sends the exact same request, so an expired session loses nothing.
  function makeApi({ fetch, requireLogin }) {
    return async function api(path, body) {
      const options = body === undefined
        ? { method: 'GET', credentials: 'same-origin' }
        : { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
      let res;
      try {
        res = await fetch(`/api/rental_sync/${path}`, options);
      } catch (_) {
        throw new Error("Couldn't reach the sync app — check the internet connection and try again.");
      }
      let data = {};
      try { data = await res.json(); } catch (_) { /* not JSON: use the status below */ }
      if (res.status === 401 && path !== 'login') {
        await requireLogin();
        return api(path, body);
      }
      if (!res.ok) {
        const error = new Error((data.error && data.error.message) || `Something went wrong (${res.status}).`);
        error.detail = (data.error && data.error.detail) || '';
        throw error;
      }
      return data;
    };
  }

  return { MAX_FILE_BYTES, POSTER_BATCH_SIZE, gzipBase64, fileProblem, batches, byCreatedThenTitle, shortDate,
    isHttpsUrl, initialPoster, acceptSuggestion, pastedPoster, createPayload, summarize, finishPayload,
    printBarcodesUrl, describeLastRun, makeApi };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/rental_sync/logic.test.js`
Expected: PASS (Node 18+ provides `Blob`, `Response`, `CompressionStream`, `btoa` globally).

- [ ] **Step 5: Commit**

```bash
git add tools/rental-sync/logic.js tests/rental_sync/logic.test.js
git commit -m "rental-sync: front-end helpers (upload encoding, posters, api with re-login)"
```

---

### Task 8: Front-end page

**Files:**
- Create: `tools/rental-sync/index.html`, `tools/rental-sync/styles.css`, `tools/rental-sync/app.js`
- Create: `tools/rental-sync/guide/export-barcodes.png`, `tools/rental-sync/guide/export-library.png`

**Interfaces:**
- Consumes: `window.RentalSyncLogic` (Task 7); HTTP API (Task 6).
- Produces: the page served at `/` (via `vercel.json` rewrite). No exports.

Rule for this task: Libib text is only ever inserted with `textContent` / text nodes (the `el()` helper below) — never `innerHTML`.

- [ ] **Step 1: Create `index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>Rental Sync</title>
  <link rel="stylesheet" href="/tools/rental-sync/styles.css">
</head>
<body>
  <header class="top">
    <h1>Rental Sync <span class="muted">Libib → Shopify</span></h1>
    <p class="muted small">Store: <span id="store-name">…</span></p>
  </header>

  <ol id="steps" class="steps" aria-label="Progress">
    <li>Upload</li><li>New copies</li><li>Details</li><li>Posters</li><li>Create</li>
  </ol>

  <main>
    <section data-step="1">
      <p id="last-run" class="last-run">Checking the last sync…</p>
      <details class="guide" open>
        <summary>How to export from Libib</summary>
        <ol>
          <li>In Libib, open <strong>Settings</strong> (libib.com/settings).</li>
          <li>Open <strong>Export Barcode Data</strong>, choose <strong>Rental Library</strong>, and click export.
            The file's name starts with <code>barcodes_</code>.</li>
          <li>Open <strong>Export Collection Data</strong>, choose <strong>Rental Library</strong>, and click export.
            The file's name starts with <code>library_</code>.</li>
          <li>Upload them below — <code>barcodes_…</code> in the first box, <code>library_…</code> in the second.</li>
        </ol>
        <div class="guide-shots">
          <figure><img src="/tools/rental-sync/guide/export-barcodes.png" alt="Libib Settings, Export Barcode Data with Rental Library selected"><figcaption>Barcodes export</figcaption></figure>
          <figure><img src="/tools/rental-sync/guide/export-library.png" alt="Libib Settings, Export Collection Data with Rental Library selected"><figcaption>Library export</figcaption></figure>
        </div>
      </details>
      <form id="upload-form" class="upload">
        <label>Barcodes export <span class="muted small">(barcodes_….csv)</span>
          <input id="barcodes-file" type="file" accept=".csv,text/csv"></label>
        <label>Library export <span class="muted small">(library_….csv)</span>
          <input id="library-file" type="file" accept=".csv,text/csv"></label>
        <button id="find-button" type="submit">Find new rentals</button>
      </form>
      <div id="upload-error" role="alert"></div>
    </section>

    <section data-step="2" hidden>
      <h2>New copies found</h2>
      <p id="found-summary"></p>
      <table id="found-table" class="found">
        <thead><tr><th scope="col"><span class="visually-hidden">Include</span></th><th scope="col">Title</th><th scope="col">Barcode</th><th scope="col">Added in Libib</th></tr></thead>
        <tbody id="found-rows"></tbody>
      </table>
      <p class="muted small">Unticked copies are skipped this time and show up again next time.
        Not what you expected? Re-export from Libib and upload again.</p>
      <div class="actions">
        <button id="found-back" type="button" class="secondary">Back</button>
        <button id="found-continue" type="button">Continue</button>
      </div>
    </section>

    <section data-step="3" hidden>
      <div id="set-aside" class="set-aside" hidden>
        <h2>Set aside — fix these in Libib</h2>
        <p>These won't sync this time. Fix them in Libib and they'll show up next time you sync.</p>
        <div class="vocab">
          <p><strong>Formats (exactly one):</strong> <span id="vocab-formats"></span></p>
          <p><strong>Genres (1–3):</strong> <span id="vocab-genres"></span></p>
        </div>
        <div id="set-aside-cards" class="cards"></div>
      </div>
      <h2 id="ready-heading">Ready to sync</h2>
      <p class="muted small">These details come from Libib. To change one, edit it in Libib and start again.</p>
      <div id="ready-cards" class="cards"></div>
      <div class="actions">
        <button id="details-back" type="button" class="secondary">Back</button>
        <button id="details-continue" type="button">Looks good</button>
      </div>
    </section>

    <section data-step="4" hidden>
      <h2>Posters</h2>
      <p class="muted small">Posters come from TMDB. Paste an image link (https://…) to replace or add one, or leave it blank.</p>
      <div id="poster-cards" class="cards posters"></div>
      <div class="actions">
        <button id="posters-back" type="button" class="secondary">Back</button>
        <button id="posters-continue" type="button" disabled>Looking up posters…</button>
      </div>
    </section>

    <section data-step="5" hidden>
      <h2>Creating products in Shopify</h2>
      <div class="progress"><div id="progress-bar" class="progress-bar"></div></div>
      <p id="progress-text" class="muted small"></p>
      <ul id="create-rows" class="create-rows"></ul>
      <div id="results"></div>
      <div id="print-block" class="print" hidden>
        <h3>Next: print and apply barcodes</h3>
        <ol>
          <li>Open the products tagged <strong>Barcode Not Printed</strong> in Shopify.</li>
          <li>Print their labels with Retail Barcode Labels and stick each on its copy.</li>
          <li>Remove the <strong>Barcode Not Printed</strong> tag from each product you labelled.</li>
        </ol>
        <a id="print-link" class="button" target="_blank" rel="noopener">Print barcodes in Shopify</a>
      </div>
      <div class="actions">
        <button id="restart" type="button" class="secondary" hidden>Start a new sync</button>
      </div>
    </section>
  </main>

  <div id="login" class="login" hidden>
    <form id="login-form" class="login-box">
      <h2>Log in</h2>
      <label>Password <input id="password" type="password" autocomplete="current-password" required></label>
      <p id="login-error" class="error" role="alert"></p>
      <button type="submit">Log in</button>
    </form>
  </div>

  <script src="/tools/rental-sync/logic.js"></script>
  <script src="/tools/rental-sync/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `styles.css`**

```css
:root {
  --brick: #973123;
  --mahogany: #3a2018;
  --sage: #5f8d7a;
  --parchment: #fff9ef;
  --ink: #2a1c16;
  --muted: #6d5d55;
  --line: #e6dccd;
  --error: #b3261e;
  --warn-bg: #fff1d6;
  --aside-bg: #fbe9e6;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--parchment); color: var(--ink);
  font: 16px/1.5 -apple-system, system-ui, "Segoe UI", sans-serif; }
.top, main, .steps { max-width: 960px; margin: 0 auto; padding: 0 16px; }
.top { padding-top: 24px; }
h1 { color: var(--brick); margin: 0; font-size: 1.6rem; }
h2 { font-size: 1.25rem; margin: 1.5rem 0 .5rem; }
h3 { font-size: 1rem; margin: 0 0 .25rem; }
.muted { color: var(--muted); font-weight: normal; }
.small { font-size: .875rem; }
.mono { font-family: ui-monospace, Menlo, monospace; font-size: .85rem; }
.error { color: var(--error); }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
code { background: #f3ebde; padding: 0 4px; }

.steps { display: flex; gap: 4px; list-style: none; padding-top: 16px; padding-bottom: 8px; counter-reset: step; flex-wrap: wrap; }
.steps li { counter-increment: step; flex: 1 1 0; min-width: 90px; padding: 6px 8px; border-bottom: 3px solid var(--line);
  color: var(--muted); font-size: .875rem; }
.steps li::before { content: counter(step) ". "; }
.steps li.current { border-color: var(--brick); color: var(--ink); font-weight: 600; }
.steps li.done { border-color: var(--sage); }

button, .button { display: inline-block; border: 0; background: var(--brick); color: #fff; padding: 10px 18px;
  font: inherit; font-weight: 600; cursor: pointer; text-decoration: none; }
button.secondary { background: transparent; color: var(--ink); border: 1px solid var(--muted); }
button:disabled { opacity: .5; cursor: not-allowed; }
.actions { display: flex; justify-content: space-between; gap: 12px; margin: 24px 0 48px; }

.last-run { font-weight: 600; }
.guide { background: #fff; border: 1px solid var(--line); padding: 12px 16px; margin: 16px 0; }
.guide summary { cursor: pointer; font-weight: 600; }
.guide-shots { display: flex; gap: 12px; flex-wrap: wrap; }
.guide-shots figure { margin: 0; flex: 1 1 260px; }
.guide-shots img { width: 100%; border: 1px solid var(--line); }
.upload { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; align-items: end; background: #fff;
  border: 1px solid var(--line); padding: 16px; }
.upload label { display: grid; gap: 6px; font-weight: 600; }
.upload button { grid-column: 1 / -1; justify-self: start; }

.found { width: 100%; border-collapse: collapse; background: #fff; }
.found th, .found td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); }

.cards { display: grid; gap: 12px; }
.card { background: #fff; border: 1px solid var(--line); padding: 14px 16px; }
.card.aside { background: var(--aside-bg); border-color: #e8b9b1; }
.card dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 8px 0 0; }
.card dt { color: var(--muted); }
.card dd { margin: 0; overflow-wrap: anywhere; }
.reasons { color: var(--error); margin: 6px 0; padding-left: 20px; }
.warnings { background: var(--warn-bg); margin: 10px 0 0; padding: 6px 10px 6px 28px; font-size: .875rem; }
.set-aside .vocab { font-size: .875rem; }

.posters .poster-card { display: grid; grid-template-columns: 120px 1fr; gap: 16px; }
.poster { width: 120px; aspect-ratio: 2 / 3; background: #f3ebde; display: grid; place-items: center; }
.poster img { width: 100%; height: 100%; object-fit: cover; }
.poster img.suggested { outline: 3px dashed var(--sage); }
.poster-empty { color: var(--muted); font-size: .8rem; }
.poster-card input { width: 100%; padding: 8px; margin-top: 8px; font: inherit; }
.poster-card .note { margin: 4px 0; font-size: .875rem; }

.progress { height: 10px; background: var(--line); }
.progress-bar { height: 100%; width: 0; background: var(--sage); transition: width .2s; }
.create-rows { list-style: none; padding: 0; columns: 2 260px; }
.create-rows .status { display: inline-block; width: 1.4em; font-weight: 700; }
.create-rows .status.created, .create-rows .status.skipped_exists { color: var(--sage); }
.create-rows .status.failed { color: var(--error); }
.result-group { background: #fff; border: 1px solid var(--line); padding: 12px 16px; margin: 12px 0; }
.result-group li { margin: 6px 0; }
.print { background: #eef5f1; border: 1px solid var(--sage); padding: 12px 16px; margin: 16px 0; }

.login { position: fixed; inset: 0; background: rgba(42, 28, 22, .6); display: grid; place-items: center; padding: 16px; }
.login-box { background: var(--parchment); padding: 24px; width: min(360px, 100%); display: grid; gap: 12px; }
.login-box input { width: 100%; padding: 8px; font: inherit; }

@media (max-width: 640px) {
  .upload { grid-template-columns: 1fr; }
  .posters .poster-card { grid-template-columns: 90px 1fr; }
  .poster { width: 90px; }
}
```

- [ ] **Step 3: Create `app.js`**

```js
// The rental sync page: five steps, state kept in memory for the session.
// Libib text only ever goes into the page as text nodes (see el()).
(function () {
  'use strict';
  const L = window.RentalSyncLogic;
  const $ = (id) => document.getElementById(id);
  const state = { store: '', vocabulary: { formats: [], genres: [] }, found: [], selected: new Set(),
    ready: [], setAside: [], posters: new Map(), results: [], creating: false };

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else if (value === true) node.setAttribute(key, '');
      else if (value !== false && value != null) node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child != null && child !== false) node.append(child instanceof Node ? child : String(child));
    }
    return node;
  }

  // --- login + api ------------------------------------------------------
  let loginWaiters = [];
  function requireLogin() {
    $('login').hidden = false;
    $('password').focus();
    return new Promise((resolve) => loginWaiters.push(resolve));
  }
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('login-error').textContent = '';
    let res;
    try {
      res = await fetch('/api/rental_sync/login', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: $('password').value }) });
    } catch (_) {
      $('login-error').textContent = "Couldn't reach the sync app — check the internet connection.";
      return;
    }
    if (!res.ok) { $('login-error').textContent = "That password isn't right."; return; }
    $('password').value = '';
    $('login').hidden = true;
    const waiters = loginWaiters;
    loginWaiters = [];
    waiters.forEach((resolve) => resolve());
  });
  const api = L.makeApi({ fetch: (url, options) => fetch(url, options), requireLogin });

  function showError(container, error) {
    container.replaceChildren(
      el('p', { class: 'error' }, error.message),
      error.detail ? el('details', {}, el('summary', {}, 'Show details'), el('pre', { class: 'small' }, error.detail)) : null);
  }

  function showStep(n) {
    document.querySelectorAll('[data-step]').forEach((s) => { s.hidden = Number(s.dataset.step) !== n; });
    document.querySelectorAll('#steps li').forEach((li, i) => {
      li.classList.toggle('current', i + 1 === n);
      li.classList.toggle('done', i + 1 < n);
    });
    window.scrollTo(0, 0);
  }

  // --- step 1: upload -----------------------------------------------------
  async function loadStatus() {
    try {
      const data = await api('status');
      state.store = data.store;
      $('store-name').textContent = data.store;
      $('last-run').textContent = L.describeLastRun(data.last_run);
    } catch (error) {
      showError($('last-run'), error);
    }
  }

  $('upload-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const out = $('upload-error');
    const button = $('find-button');
    out.replaceChildren();
    const barcodes = $('barcodes-file').files[0];
    const library = $('library-file').files[0];
    const problem = L.fileProblem(barcodes, 'Barcodes export') || L.fileProblem(library, 'Library export');
    if (problem) { out.replaceChildren(el('p', { class: 'error' }, problem)); return; }
    button.disabled = true;
    button.textContent = 'Looking…';
    try {
      const data = await api('prepare', {
        barcodes: await L.gzipBase64(await barcodes.text()),
        library: await L.gzipBase64(await library.text()),
      });
      state.vocabulary = data.vocabulary;
      state.found = [...data.ready, ...data.set_aside].sort(L.byCreatedThenTitle);
      state.selected = new Set(state.found.map((c) => c.barcode));
      renderFound();
      showStep(2);
    } catch (error) {
      showError(out, error);
    } finally {
      button.disabled = false;
      button.textContent = 'Find new rentals';
    }
  });

  // --- step 2: new copies ----------------------------------------------------
  function renderFound() {
    const n = state.found.length;
    $('found-summary').textContent = n
      ? `${n} new ${n === 1 ? 'copy' : 'copies'} in Libib that ${n === 1 ? "isn't" : "aren't"} in Shopify yet.`
      : "Everything in Libib's Rental Library is already in Shopify.";
    $('found-table').hidden = !n;
    $('found-rows').replaceChildren(...state.found.map((copy) => {
      const box = el('input', { type: 'checkbox', checked: true, 'aria-label': `Include ${copy.title || copy.barcode}`,
        onchange: (e) => {
          if (e.target.checked) state.selected.add(copy.barcode); else state.selected.delete(copy.barcode);
          updateFoundButton();
        } });
      return el('tr', {}, el('td', {}, box), el('td', {}, copy.title || '(no title)'),
        el('td', { class: 'mono' }, copy.barcode), el('td', {}, L.shortDate(copy.created)));
    }));
    updateFoundButton();
  }
  function updateFoundButton() {
    const n = state.selected.size;
    $('found-continue').disabled = n === 0;
    $('found-continue').textContent = `Continue with ${n}`;
  }
  $('found-back').addEventListener('click', () => showStep(1));
  $('found-continue').addEventListener('click', () => { renderDetails(); showStep(3); });

  // --- step 3: details --------------------------------------------------------
  function copyCard(copy, isAside) {
    const field = (label, value) => [el('dt', {}, label), el('dd', {}, value || '—')];
    return el('article', { class: isAside ? 'card aside' : 'card' },
      el('h3', {}, copy.title || '(no title)', ' ', el('span', { class: 'mono muted' }, copy.barcode)),
      isAside ? el('ul', { class: 'reasons' }, copy.set_aside.map((r) => el('li', {}, r))) : null,
      el('dl', {},
        field('Format', copy.format),
        field('Genre', copy.genres.map((g) => g.name).join(', ')),
        field('Extra tags', copy.extra_tags.join(', ')),
        field('Description', copy.description)),
      copy.warnings.length ? el('ul', { class: 'warnings' }, copy.warnings.map((w) => el('li', {}, w))) : null);
  }
  function renderDetails() {
    const chosen = state.found.filter((c) => state.selected.has(c.barcode));
    state.ready = chosen.filter((c) => !c.set_aside.length);
    state.setAside = chosen.filter((c) => c.set_aside.length);
    $('set-aside').hidden = !state.setAside.length;
    $('vocab-formats').textContent = state.vocabulary.formats.join(', ');
    $('vocab-genres').textContent = state.vocabulary.genres.join(', ');
    $('set-aside-cards').replaceChildren(...state.setAside.map((c) => copyCard(c, true)));
    $('ready-heading').textContent = state.ready.length ? `${state.ready.length} ready to sync` : 'Nothing ready to sync';
    $('ready-cards').replaceChildren(...state.ready.map((c) => copyCard(c, false)));
    $('details-continue').disabled = !state.ready.length;
  }
  $('details-back').addEventListener('click', () => showStep(2));
  $('details-continue').addEventListener('click', () => { buildPosterCards(); showStep(4); startPosters(); });

  // --- step 4: posters --------------------------------------------------------
  const posterCards = new Map();
  function buildPosterCards() {
    posterCards.clear();
    state.posters = new Map(state.ready.map((c) => [c.barcode, { url: '', alt: '', original: { url: '', alt: '' },
      suggestion: null, note: 'Looking up…' }]));
    $('poster-cards').replaceChildren(...state.ready.map((copy) => {
      const note = el('p', { class: 'note' });
      const img = el('img', { alt: `Poster for ${copy.title}`, hidden: true });
      const empty = el('div', { class: 'poster-empty' }, 'No poster');
      img.addEventListener('error', () => {
        if (img.getAttribute('src')) { note.textContent = "That link didn't load as an image — check it."; note.classList.add('error'); }
      });
      const useIt = el('button', { type: 'button', class: 'secondary', hidden: true, onclick: () => {
        state.posters.set(copy.barcode, L.acceptSuggestion(state.posters.get(copy.barcode)));
        updatePosterCard(copy.barcode);
      } }, 'Use it');
      const input = el('input', { type: 'url', placeholder: 'Paste image URL (https://…)',
        'aria-label': `Poster link for ${copy.title}` });
      input.addEventListener('input', () => {
        state.posters.set(copy.barcode, L.pastedPoster(state.posters.get(copy.barcode), input.value));
        updatePosterCard(copy.barcode);
      });
      posterCards.set(copy.barcode, { img, empty, note, useIt });
      return el('article', { class: 'card poster-card' },
        el('div', { class: 'poster' }, img, empty),
        el('div', {}, el('h3', {}, copy.title),
          el('p', { class: 'muted small' }, `${copy.format} · ${copy.genres.map((g) => g.name).join(', ')}`),
          note, useIt, input));
    }));
    state.ready.forEach((c) => updatePosterCard(c.barcode));
  }
  function updatePosterCard(barcode) {
    const poster = state.posters.get(barcode);
    const card = posterCards.get(barcode);
    const unsure = !poster.url && poster.suggestion;
    const shown = poster.url || (unsure ? poster.suggestion.url : '');
    card.img.hidden = !shown;
    card.empty.hidden = Boolean(shown);
    if (shown && card.img.getAttribute('src') !== shown) card.img.setAttribute('src', shown);
    if (!shown) card.img.removeAttribute('src');
    card.img.classList.toggle('suggested', Boolean(unsure));
    card.note.classList.toggle('error', poster.note.startsWith('Links must'));
    card.note.textContent = unsure
      ? `Not sure — check this: is it “${poster.suggestion.title}” (${poster.suggestion.year || '?'})?`
      : poster.note;
    card.useIt.hidden = !unsure;
  }
  async function startPosters() {
    const button = $('posters-continue');
    button.disabled = true;
    button.textContent = 'Looking up posters…';
    for (const batch of L.batches(state.ready)) {
      try {
        const data = await api('posters', { copies: batch });
        data.posters.forEach((result) => state.posters.set(result.barcode, L.initialPoster(result)));
      } catch (_) {
        batch.forEach((c) => state.posters.set(c.barcode, L.initialPoster({ kind: 'error' })));
      }
      batch.forEach((c) => updatePosterCard(c.barcode));
    }
    button.disabled = false;
    button.textContent = `Create ${state.ready.length} ${state.ready.length === 1 ? 'product' : 'products'} in Shopify`;
  }
  $('posters-back').addEventListener('click', () => showStep(3));
  $('posters-continue').addEventListener('click', startCreate);

  // --- step 5: create -----------------------------------------------------
  function setProgress(done, total) {
    $('progress-bar').style.width = `${total ? Math.round((done / total) * 100) : 100}%`;
    $('progress-text').textContent = `${done} of ${total} done`;
  }
  async function startCreate() {
    if (state.creating) return;
    state.creating = true;
    $('posters-continue').disabled = true;
    showStep(5);
    state.results = [];
    const marks = new Map();
    $('create-rows').replaceChildren(...state.ready.map((copy) => {
      const mark = el('span', { class: 'status' }, '…');
      marks.set(copy.barcode, mark);
      return el('li', {}, mark, ' ', copy.title);
    }));
    for (const [i, copy] of state.ready.entries()) {
      setProgress(i, state.ready.length);
      let result;
      try {
        result = await api('create', L.createPayload(copy, state.posters.get(copy.barcode)));
      } catch (error) {
        result = { status: 'failed', barcode: copy.barcode, title: copy.title, admin_url: '', poster: 'none',
          message: `${error.message} If it was created anyway, the next sync will skip it.`, problems: [] };
      }
      state.results.push(result);
      const mark = marks.get(copy.barcode);
      mark.textContent = result.status === 'failed' ? '✗' : '✓';
      mark.className = `status ${result.status}`;
    }
    setProgress(state.ready.length, state.ready.length);
    const summary = L.summarize(state.results);
    let finishError = null;
    try {
      await api('finish', L.finishPayload(summary, state.setAside.length));
    } catch (error) {
      finishError = error;
    }
    state.creating = false;
    renderResults(summary, finishError);
  }
  function renderResults(summary, finishError) {
    const link = (r) => (r.admin_url ? el('a', { href: r.admin_url, target: '_blank', rel: 'noopener' }, r.title) : r.title);
    const group = (title, items, render) => (items.length
      ? el('section', { class: 'result-group' }, el('h3', {}, `${title} (${items.length})`), el('ul', {}, items.map(render)))
      : null);
    $('results').replaceChildren(
      el('p', { class: 'last-run' }, `${summary.created.length} created, ${summary.skipped.length} already in Shopify, ${summary.failed.length} failed.`),
      group('Failed', summary.failed, (r) => el('li', {}, link(r), ' ', el('span', { class: 'mono muted' }, r.barcode),
        el('p', { class: 'error small' }, r.message))),
      summary.failed.length ? el('p', {}, "Fix the issue and run the sync again — products already created won't be duplicated.") : null,
      group("Created, but the poster didn't load — add it in Shopify admin", summary.posterFailed, (r) => el('li', {}, link(r))),
      group('Created', summary.created, (r) => el('li', {}, link(r))),
      group('Already in Shopify — skipped', summary.skipped, (r) => el('li', {}, r.title, ' ', el('span', { class: 'muted small' }, r.message))),
      finishError ? el('p', { class: 'error small' }, `The products are done, but the "last sync" time wasn't saved: ${finishError.message}`) : null);
    $('print-link').href = L.printBarcodesUrl(state.store);
    $('print-block').hidden = !summary.created.length;
    $('restart').hidden = false;
  }
  $('restart').addEventListener('click', () => window.location.reload());
  window.addEventListener('beforeunload', (event) => {
    if (state.creating) { event.preventDefault(); event.returnValue = ''; }
  });

  showStep(1);
  loadStatus();
})();
```

- [ ] **Step 4: Capture the two guide screenshots**

Log in to Libib (credentials in `.env`: `LIBIB_EMAIL` / `LIBIB_PASSWORD`) at `https://www.libib.com/settings`. Open **Export Barcode Data**, select **Rental Library** (do not click export), and screenshot just that accordion section; repeat for **Export Collection Data**. Crop out the account email and anything outside the section. Save as `tools/rental-sync/guide/export-barcodes.png` and `tools/rental-sync/guide/export-library.png` (PNG, ≤ 300 KB each). Never click anything else on that page — it also holds "Delete Collections".

- [ ] **Step 5: Check the page locally**

There is no local Vercel runtime in this repo, so check the static page only:

Run: `python3 -m http.server 8765 --directory .` (from the repo root), open `http://localhost:8765/tools/rental-sync/index.html`.
Expected: step 1 renders with the guide and screenshots; the login box appears after the `status` call fails (the API is absent locally, so you'll see either the login box or "Couldn't reach the sync app"); no console errors other than the failed `/api/rental_sync/status` request. Stop the server afterwards.

Run: `node --test tests/review_picker/*.test.js tests/rental_sync/*.test.js`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/rental-sync/index.html tools/rental-sync/styles.css tools/rental-sync/app.js tools/rental-sync/guide
git commit -m "rental-sync: five-step page (upload, review, posters, create, results)"
```

---

### Task 9: Deploy a preview and run it end to end on the dev store

**Files:**
- Create: `tools/rental-sync/README.md`
- Modify (only if a check below fails): the file named in that check

**Interfaces:**
- Consumes: everything above.
- Produces: a working Vercel preview against the dev store; verified behaviour; `tools/rental-sync/README.md`.

This task is operational. Steps marked **(developer)** need the Vercel/Shopify/Libib accounts; an agent stops and asks the developer to do them.

- [ ] **Step 1: Install the app on the dev store and check scopes (developer)**

In the Shopify Dev Dashboard, open the custom app used by `catalog/` (its client ID is `SHOPIFY_CLIENT_ID` in `.env`). Make sure the released version has `read_products`, `write_products`, `read_inventory`, `write_inventory`, `read_locations`, `read_publications`, `write_publications`, `read_metaobjects`. Release a new version if any are missing and install it on `lms-sandbox-lutsfahz.myshopify.com`. Then confirm the reads work from this machine:

```bash
python3 - <<'EOF'
from catalog import config
from catalog.rental_sync.shopify import shop_from_env
env = {"SHOPIFY_STORE": "lms-sandbox-lutsfahz.myshopify.com",
       "SHOPIFY_CLIENT_ID": config.require_env("SHOPIFY_CLIENT_ID"),
       "SHOPIFY_CLIENT_SECRET": config.require_env("SHOPIFY_CLIENT_SECRET")}
shop = shop_from_env(env)
print("location", shop.location_id())
print("online store", shop.online_store_publication_id())
print("genres", shop.genre_ids(["horror", "comedy"]))
print("201 barcodes", len(shop.new_flow_barcodes()))
print("last run", shop.last_run())
EOF
```

Expected: one location ID, an Online Store publication ID, two metaobject IDs, a count, `last run None`. A `SetupError` here names exactly what to fix.

- [ ] **Step 2: Create the Vercel project (developer)**

In Vercel: **Add New Project** → import `paris-liam/LMS` → **Root Directory: the repo root** (leave blank) → Framework preset **Other** → no build command, no output directory. Environment variables (Preview and Production): `SYNC_PASSWORD` (a new passphrase for the client), `SESSION_SECRET` (`python3 -c "import secrets; print(secrets.token_hex(32))"`), `SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `TMDB_API_KEY`. Deploy. Then confirm the existing review picker project still has **Root Directory `tools/review-picker`** and still deploys (its root setting means it never sees the repo-root `vercel.json`).

- [ ] **Step 3: Smoke-test the deployment**

Replace `<url>` with the deployment URL:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<url>/                                  # 200 (the page)
curl -s https://<url>/api/rental_sync/status                                              # 401 {"error": {"kind": "auth", ...}}
curl -s -o /dev/null -w "%{http_code}\n" https://<url>/runs/                              # 404 (not deployed)
curl -s -o /dev/null -w "%{http_code}\n" https://<url>/theme/lms-redesign-v4/layout/theme.liquid   # 404
```

Expected: as commented. If `status` returns a 500 with `ModuleNotFoundError: catalog`, the function bundle is missing `catalog/` — check `includeFiles` in `vercel.json` and that `.vercelignore` keeps `/catalog`, redeploy, and re-run.

- [ ] **Step 4: Add test copies to Libib (developer)**

In Libib's Rental Library add, with Libib's generated `201…` barcodes and **blank Call #**:
1. "Rental Sync Test Clean" — tags `vhs, horror, criterion`, a description containing `Tom & Jerry <b>`.
2. "Rental Sync Test Two Copies" — tags `dvd, comedy`, **two copies** of the one item.
3. "Rental Sync Test Typo" — tags `vhs, horor`.
4. "Rental Sync Test No Genre" — tag `blu-ray` only.

Then export both CSVs from Libib Settings (Rental Library).

**These items are in the client's real Libib.** Step 8 deletes them; until then don't point the app at production.

- [ ] **Step 5: Walk the flow in a browser**

Use the Playwright MCP (`mcp__playwright__browser_*`) or a normal browser against `https://<url>/`:
1. Wrong password → "That password isn't right."; right password → step 1 shows "No sync yet." and the dev store name.
2. Upload the two files swapped → "The two files are swapped…". Upload them correctly → step 2 lists exactly the five test copies (plus any real new-flow copies already in Libib — note them, untick them).
3. Step 3: "Typo" is set aside with "tag 'horor' looks like a misspelling of 'horror'"; "No Genre" is set aside with "no genre tag"; the vocabulary lists show; "Clean" shows the warning "extra tags: criterion" and its description renders `Tom & Jerry <b>` as text.
4. Step 4: posters load in turn; paste `http://example.com/x.jpg` into one → "Links must start with https://"; clear it → the TMDB poster returns; paste a real `https://` image link into another → preview shows.
5. Step 5: "Create 3 products"; all three ✓; results list them with admin links; "Print barcodes in Shopify" opens the admin products list **filtered to the `Barcode Not Printed` tag**. If the filter isn't applied, find the URL the admin uses when filtering by that tag manually, update `printBarcodesUrl` and its test in `logic.js` / `logic.test.js`, and commit (`git commit -m "rental-sync: fix the admin tag-filter link"`).
6. Reload the page: step 1 now shows "Last successful sync: … — 3 created".

- [ ] **Step 6: Check the created products on the dev store**

For each of the three, in Shopify admin (or via GraphQL):
- handle `rental-sync-test-…-<format>-rental-<barcode>`; Vendor; category `Media > Videos`; tags `Rental`, `Barcode Not Printed` (+ `criterion` on Clean)
- Genre option = first genre; the genre metafield shows the genre(s)
- one variant: barcode = Libib barcode, price 0, **Charge tax off**, tracked, quantity 1
- **Sales channels: Online Store only — not Point of Sale**
- poster present (or the "poster didn't load" note if TMDB had none)
- "Clean" description shows `Tom & Jerry <b>` literally
- "Two Copies": two products with different barcodes

- [ ] **Step 7: Re-run and session checks**

1. Re-upload the same exports → step 2 shows only "Typo" and "No Genre" (the three created copies are now in Shopify).
2. Fix "Typo" in Libib (`horror`), re-export, upload → it moves to ready; create it → ✓.
3. Session expiry: in the browser devtools delete the `lms_rental_sync` cookie while on step 4, then click Create → the login box appears; log in → creation continues with no lost state.
4. Double submit: on the results page nothing re-creates; re-uploading shows nothing new for those barcodes.

- [ ] **Step 8: Clean up the test data (developer)**

Delete the five test copies (four items) from Libib, and delete the four test products from the dev store. Keep the dev-store `lms.rental_sync_last_run` metafield; it's harmless.

- [ ] **Step 9: Write `tools/rental-sync/README.md` and commit**

```markdown
# Rental sync app

The client's page for turning new Libib rentals into Shopify products.
Design: `docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`.
Client instructions: `client-guide.md`.

## Layout

- `tools/rental-sync/` — the page (no build step): `index.html`, `app.js`, `logic.js`, `styles.css`, `guide/`.
- `api/rental_sync/*.py` — Vercel Python functions, three lines each, all calling
  `catalog/rental_sync/web.py`. Logic and tests live in `catalog/rental_sync/`.
- `vercel.json` / `.vercelignore` (repo root) — function config, the `/` rewrite, security
  headers, and a deploy allow-list (only `api/`, `catalog/`, `tools/rental-sync/`).

## Vercel project (one-time)

Root Directory = repo root, Framework = Other, no build. Env vars (Preview + Production):
`SYNC_PASSWORD`, `SESSION_SECRET`, `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`,
`TMDB_API_KEY`. `SHOPIFY_STORE` decides which store products are created in.
The review picker is a separate Vercel project rooted at `tools/review-picker`.

## Shopify app scopes

read/write_products, read/write_inventory, read_locations, read/write_publications,
read_metaobjects — installed on whichever store `SHOPIFY_STORE` names.

## Tests

    python3 -m unittest discover -s tests/catalog -p "test_rental_sync_*.py"
    node --test tests/rental_sync/*.test.js

## Logs

Vercel → project → Logs: one line per created copy (barcode, status, title, message).
Never the password, cookie or tokens.
```

```bash
git add tools/rental-sync/README.md
git commit -m "rental-sync: deploy notes"
```

---

### Task 10: Legacy Libib tooling ignores new-flow copies

**Files:**
- Modify: `catalog/libib/diff.py:76-93`
- Test: `tests/catalog/test_libib_diff.py`

**Interfaces:**
- Consumes: `is_new_flow_barcode` (Task 1).
- Produces: `diff()` never reports a new-flow Libib item (as orphan, duplicate or match) or a new-flow Shopify rental (as blocked). `libib fix` / `sync` / `prepare` act only on `diff()` output, so they inherit this.

- [ ] **Step 1: Write the failing tests**

Add to `TestDiff` in `tests/catalog/test_libib_diff.py`:

```python
    def test_new_flow_libib_items_are_not_orphans(self):
        result = diff([rental()], [item(), item(item_id="n1", call="", barcode="2010000000014", title="New")], {})
        self.assertEqual(result.in_sync, ["jaws"])
        self.assertEqual(result.orphans, [])

    def test_new_flow_shopify_rentals_are_not_blocked(self):
        new = rental(handle="new-vhs-rental-2010000000014", barcode="2010000000014")
        result = diff([rental(), new], [item()], {})
        self.assertEqual(result.blocked, [])
        self.assertEqual(result.in_sync, ["jaws"])
        self.assertNotIn("new-vhs-rental-2010000000014", [e["handle"] for e in result.eligible])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_libib_diff.py" -v`
Expected: FAIL — the Libib item lands in `orphans` ("no call number") and the Shopify rental in `blocked` ("barcode is not 8 digits").

- [ ] **Step 3: Implement**

In `catalog/libib/diff.py`, change the import:

```python
from catalog.core.barcodes import barcode_owners, is_new_flow_barcode, is_rental_barcode
```

At the top of `diff()`, right after `result = DiffResult()`:

```python
    # New-flow copies (13-digit 201… barcodes) belong to the rental sync app,
    # which creates their Shopify products from Libib; this diff manages only
    # the legacy 8-digit rentals.
    items = [i for i in items if not is_new_flow_barcode(i["barcode"])]
```

Inside the `for row in rows:` loop, right after `call = (row.get("Variant Barcode") or "").strip()`:

```python
        if is_new_flow_barcode(call):
            continue
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_libib_*.py" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalog/libib/diff.py tests/catalog/test_libib_diff.py
git commit -m "libib: diff/fix/sync leave the sync app's 201… copies alone"
```

---

### Task 11: `apply` only sets the poster on new-flow rentals

**Files:**
- Modify: `catalog/apply/merge.py`
- Test: `tests/catalog/test_apply_merge.py`

**Interfaces:**
- Consumes: `is_new_flow_barcode`.
- Produces: `merge()` drops any planned change to a new-flow rental (row `Variant Barcode` is `201…` 13-digit) whose field is not `Image Src`, `Image Alt Text` or `Tags`, recording `(handle, "new-flow rental: <field> comes from Libib")` in `result.ignored`. The handle's `result.applied` entry keeps only the allowed fields; if none remain it is removed.

- [ ] **Step 1: Write the failing tests**

Add to `tests/catalog/test_apply_merge.py`:

```python
NEW = "jaws-vhs-rental-2010000000014"


class TestNewFlowRentals(unittest.TestCase):
    def test_only_poster_alt_and_tags_reach_a_new_flow_rental(self):
        rows = [row(NEW, **{"Variant Barcode": "2010000000014"})]
        autofix = {NEW: {"changes": {"Vendor": "DVD", "Tags": "Rental", "Image Alt Text": "Jaws poster"},
                         "rules": ["format-alias", "poster-tag-sync", "alt-text-missing"]}}
        pick = Pick("rentals", NEW, "manual", image_src="https://x/p.jpg", overview="A new description.")
        result = merge(rows, autofix, [pick], {NEW: {"batch": "rentals", "status": "queued"}})
        self.assertEqual({f for (_, f) in changes_of(result)}, {"Tags", "Image Alt Text", "Image Src"})
        self.assertIn((NEW, "new-flow rental: Vendor comes from Libib"), result.ignored)
        self.assertIn((NEW, "new-flow rental: Body (HTML) comes from Libib"), result.ignored)
        self.assertEqual(set(result.applied[NEW]), {"Image Src", "Image Alt Text"})

    def test_legacy_rentals_are_unaffected(self):
        result = merge([row()], {"the-thing": {"changes": {"Vendor": "Blu-Ray"}, "rules": []}}, [], {})
        self.assertEqual(changes_of(result), {("the-thing", "Vendor"): ("Blu-Ray", "auto-fix")})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_apply_merge.py" -v`
Expected: FAIL — the Vendor and Body (HTML) changes are present.

- [ ] **Step 3: Implement**

In `catalog/apply/merge.py`, add to the imports:

```python
from catalog.core.barcodes import is_new_flow_barcode
```

Add below `CHANGE_COLUMNS`:

```python
# Rentals made by the rental sync app take title, description, Vendor and
# genre from Libib; apply may only give them a poster (and the tag fixes that
# go with it, e.g. Poster_Missing).
NEW_FLOW_FIELDS = {"Image Src", "Image Alt Text", "Tags"}
```

In `merge()`, replace the final line `result.changes = sorted(planned.values(), key=lambda c: (c.handle, c.field))` with:

```python
    for key, change in list(planned.items()):
        row = by_handle.get(change.handle) or {}
        if is_new_flow_barcode(row.get("Variant Barcode")) and change.field not in NEW_FLOW_FIELDS:
            del planned[key]
            result.ignored.append((change.handle, f"new-flow rental: {change.field} comes from Libib"))
            values = result.applied.get(change.handle)
            if values is not None:
                values.pop(change.field, None)
                if not values:
                    del result.applied[change.handle]

    result.changes = sorted(planned.values(), key=lambda c: (c.handle, c.field))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests/catalog -p "test_apply_*.py" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalog/apply/merge.py tests/catalog/test_apply_merge.py
git commit -m "apply: only the poster may change on a sync-app rental"
```

---

### Task 12: Audit understands new-flow rentals

**Files:**
- Modify: `catalog/audit/rules.py:14`, `:130-140`, `:205-235`
- Test: `tests/catalog/test_rules.py`

**Interfaces:**
- Consumes: `is_new_flow_barcode`.
- Produces: a Rental with a `201…` 13-digit barcode no longer gets `rental-barcode-format`. New MANUAL rules on such rentals: `new-flow-rental-unpublished` (`Published` = `FALSE`), `new-flow-rental-taxable` (`Variant Taxable` = `TRUE`), `new-flow-rental-handle` (handle doesn't end `-<barcode>`). Blank `Published` / `Variant Taxable` are not flagged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/catalog/test_rules.py`:

```python
def new_flow(**overrides):
    base = {"Handle": "rushmore-vhs-rental-2010000000014", "Variant Barcode": "2010000000014",
            "Tags": "Rental, Barcode Not Printed", "Published": "TRUE", "Variant Taxable": "FALSE"}
    base.update(overrides)
    return movie(**base)


class TestNewFlowRentals(unittest.TestCase):
    def test_clean_new_flow_rental_has_no_findings(self):
        self.assertEqual(check_row(new_flow()), [])

    def test_blank_channel_and_tax_are_not_flagged(self):
        self.assertEqual(check_row(new_flow(Published="", **{"Variant Taxable": ""})), [])

    def test_unpublished_taxable_and_hand_made_handle(self):
        found = by_rule(check_row(new_flow(Handle="rushmore-vhs-rental", Published="FALSE",
                                           **{"Variant Taxable": "TRUE"})))
        self.assertEqual(found[("new-flow-rental-unpublished", "Published")].bucket, MANUAL)
        self.assertEqual(found[("new-flow-rental-taxable", "Variant Taxable")].bucket, MANUAL)
        self.assertEqual(found[("new-flow-rental-handle", "Handle")].bucket, MANUAL)

    def test_legacy_eight_digit_rules_still_apply(self):
        found = by_rule(check_row(movie(**{"Variant Barcode": "201000000001"})))   # 12 digits: neither shape
        self.assertIn(("rental-barcode-format", "Variant Barcode"), found)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rules.py" -v`
Expected: FAIL — `rental-barcode-format` fires on the clean new-flow rental, and the three new rules don't exist.

- [ ] **Step 3: Implement**

In `catalog/audit/rules.py`, change the import:

```python
from catalog.core.barcodes import RENTAL_BARCODE, barcode_owners, is_new_flow_barcode
```

In `_rental_barcode_findings`, replace the format check:

```python
    if not RENTAL_BARCODE.match(barcode) and not is_new_flow_barcode(barcode):
        return [make("rental-barcode-format", "Variant Barcode", barcode, "", MANUAL,
                     "rental barcodes must be exactly 8 digits (or a 13-digit 201… Libib barcode)")]
    return []
```

Add after `_floor_sale_findings`:

```python
def _new_flow_rental_findings(row, r, make) -> list[Finding]:
    """Rentals the rental sync app created (13-digit 201… barcode) are on the
    Online Store, untaxed, and their handle ends in the barcode. A blank value
    means the source didn't say, so it isn't flagged."""
    barcode = (row.get("Variant Barcode") or "").strip()
    if r.type != "Rental" or not is_new_flow_barcode(barcode):
        return []
    out = []
    if (row.get("Published") or "").strip().upper() == "FALSE":
        out.append(make("new-flow-rental-unpublished", "Published", "FALSE", "TRUE", MANUAL,
                        "sync-app rentals belong on the Online Store — publish it there"))
    if (row.get("Variant Taxable") or "").strip().upper() == "TRUE":
        out.append(make("new-flow-rental-taxable", "Variant Taxable", "TRUE", "FALSE", MANUAL,
                        "rentals aren't taxable — untick Charge tax on the variant"))
    handle = row.get("Handle", "")
    if not handle.endswith(f"-{barcode}"):
        out.append(make("new-flow-rental-handle", "Handle", handle, "", MANUAL,
                        "a sync-app rental's handle ends in its barcode — was it made by hand?"))
    return out
```

In `check_row`, after `findings += _floor_sale_findings(row, r, make)`:

```python
    findings += _new_flow_rental_findings(row, r, make)
```

- [ ] **Step 4: Run the tests and the whole suite**

Run: `python3 -m unittest discover -s tests/catalog -p "test_rules.py" -v`
Expected: PASS.
Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
Expected: OK. If `test_clean_new_flow_rental_has_no_findings` reports a `poster-tag-sync` or other auto-fix finding, compare the `movie()` defaults against the new-flow row before changing any rule — the test row must be a genuinely clean product.

- [ ] **Step 5: Commit**

```bash
git add catalog/audit/rules.py tests/catalog/test_rules.py
git commit -m "audit: accept sync-app rental barcodes; flag tax, channel and handle"
```

---

### Task 13: Docs and production switch

**Files:**
- Create: `tools/rental-sync/client-guide.md`
- Modify: `catalog/README.md` (new section), `CLAUDE.md` (roadmap #3 build status)

**Interfaces:**
- Consumes: the deployed app (Task 9).
- Produces: client and developer docs; the production deployment.

- [ ] **Step 1: Write the client guide**

`tools/rental-sync/client-guide.md`:

```markdown
# Adding rentals: Libib → Shopify

## 1. In Libib

Add each rental to the **Rental Library** collection (UPC lookup or typed in).

- **Title** — as it should appear on the website. Delete extras like `[VHS]` or `(Widescreen Edition)`.
- **Tags** — exactly **one format** and **one to three genres**:
  - Formats: `vhs`, `dvd`, `blu-ray`, `4k`, `laserdisc`, `betamax`
  - Genres: `comedy`, `action`, `drama`, `kids-family`, `sci-fi`, `thriller`, `horror`,
    `romantic-comedy`, `musical`, `fantasy`, `documentary`, `foreign`, `holiday`,
    `special-interest`, `anime`
  - Any other tag is fine and is copied to Shopify — unless it looks like a misspelt format or genre.
- **Description** — optional; it becomes the website description.
- **Barcode** — leave the number Libib generates (starts with `201`). Leave **Call #** blank.
- **More copies of a title** — add a copy to the same Libib item. Each copy becomes its own Shopify product.

## 2. In the sync page

Open the sync page and log in.

1. **Upload** — in Libib go to Settings, export **Barcode Data** and **Collection Data** for the
   Rental Library, and upload both files.
2. **New copies** — check the list. Untick anything you don't want to sync yet.
3. **Details** — anything **set aside** needs fixing in Libib; it will show up next time. Yellow
   notes are just warnings.
4. **Posters** — check each poster. "Not sure — check this" means click **Use it** if it's right.
   Paste an image link (starting `https://`) to replace or add one, or leave it blank.
5. **Create** — wait for every row to finish. Click any title to open it in Shopify.

If something failed, fix what the message says and run the sync again — products already created
are never duplicated.

## 3. In Shopify

Click **Print barcodes in Shopify**, print the labels with Retail Barcode Labels, stick each on its
copy, and remove the **Barcode Not Printed** tag from the products you labelled.
```

- [ ] **Step 2: Add a `catalog/README.md` section**

Append to `catalog/README.md`:

```markdown
## Rental sync app (new-flow rentals)

New rentals are added in Libib (13-digit `201…` barcodes) and created in Shopify by the client
through the rental sync web app — not by this pipeline. Code: `catalog/rental_sync/`, front end
`tools/rental-sync/`, deploy notes `tools/rental-sync/README.md`, design
`docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`.

How the pipeline treats them:

- `libib diff` / `fix` / `sync` ignore new-flow copies on both sides; they manage only the
  legacy 8-digit rentals.
- `apply` may set only `Image Src`, `Image Alt Text` and `Tags` on a new-flow rental; any other
  planned change is listed as ignored ("comes from Libib").
- `audit` accepts the 13-digit barcode and flags a new-flow rental that is unpublished
  (`new-flow-rental-unpublished`), taxable (`new-flow-rental-taxable`), or whose handle doesn't
  end in its barcode (`new-flow-rental-handle`).
```

- [ ] **Step 3: Update `CLAUDE.md` roadmap #3**

In `CLAUDE.md` roadmap item 3, replace `(\`docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md\`, not built;` with `(\`docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md\`, **built and verified on the dev store <YYYY-MM-DD>, live on production <YYYY-MM-DD>** — code \`catalog/rental_sync/\` + \`tools/rental-sync/\`, deploy notes \`tools/rental-sync/README.md\`;` filling in the real dates from `git log` and Step 5 below. If production isn't switched yet when this runs, write only the dev-store date.

- [ ] **Step 4: Run every test and commit**

Run: `python3 -m unittest discover -s tests/catalog -p "test_*.py" && node --test tests/review_picker/*.test.js tests/rental_sync/*.test.js`
Expected: all pass.

```bash
git add tools/rental-sync/client-guide.md catalog/README.md CLAUDE.md
git commit -m "docs: rental sync app client guide, pipeline notes, roadmap status"
```

- [ ] **Step 5: Switch to production (developer, on explicit go-ahead)**

1. Install the custom app's current version on `p0wkgv-wy.myshopify.com` if the scope list changed in Task 9 Step 1, then re-run the Task 9 Step 1 script with `SHOPIFY_STORE` set to `p0wkgv-wy.myshopify.com`. Expect exactly one location — if production has more than one, stop and decide which one rentals live at before going further.
2. In Vercel, set `SHOPIFY_STORE=p0wkgv-wy.myshopify.com` for Production and redeploy.
3. Open the page: the header shows the production store; "No sync yet."
4. Run the first real sync with the client watching, check two of the created products in production admin against Task 9 Step 6, and give the client the page URL, the password and `client-guide.md`.
5. Run `python3 -m catalog audit` afterwards: the new products should produce no `new-flow-rental-*` findings.

---

## Out of scope (from the spec's "Later")

Auto-export through a GitHub Action, the Libib bulk-upload CSV template, pushing later Libib edits
to existing products, widening scope to legacy 8-digit rentals, removing legacy rentals from POS.
Also not in this plan: stopping `audit`/`picker push` from queuing description cards for new-flow
rentals — `apply` already refuses those changes (Task 11), so the worst case is a wasted card.
