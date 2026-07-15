# TMDB Image/Description Auto-Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `data-cleanup/tmdb_fill.py`, a script that fills missing `Image Src`/`Body (HTML)` fields in a Shopify product CSV by matching titles against The Movie Database (TMDB) API, leaving anything ambiguous or unmatched in a review file instead of guessing.

**Architecture:** A single stdlib-only module following the existing `data-cleanup/*.py` pattern: pure, testable core functions (title cleaning, TMDB search/match, field-need detection, `build_output`) plus a thin `run()`/`main()` CLI wrapper mirroring `run_full_reformat.py`. All network I/O goes through an injectable `fetch_fn`, so every test runs against canned responses with zero real HTTP calls.

**Tech Stack:** Python 3.13 stdlib only (`csv`, `re`, `difflib`, `urllib.request`, `urllib.parse`, `json`, `argparse`, `time`, `os`) — no `requests`, no third-party dependencies. Tests use `unittest` (no `pytest` installed), run via `python3 -m unittest`.

## Global Constraints

- No third-party dependencies (`requests` is not installed; use `urllib.request`).
- TMDB API key read from the `TMDB_API_KEY` environment variable only — never written to or read from a file.
- Image field gets TMDB's own CDN URL (`https://image.tmdb.org/t/p/w500{poster_path}`) directly — no downloading/re-hosting.
- Description field gets `<p>{overview}</p>` — TMDB's `overview` text wrapped in a single paragraph tag, matching the existing `Body (HTML)` format in the CSVs.
- A product needing only one of image/description must never have its other, already-good field touched.
- A single failed/errored TMDB request must not abort the batch — route that one product to review and continue.
- Match confidence threshold: title-similarity ratio ≥ 0.9 (via `difflib.SequenceMatcher` on normalized titles) counts as confident; below that is "ambiguous" and goes to review.
- Description-needs-fill threshold: HTML-stripped `Body (HTML)` under 40 characters (including empty) counts as needing a fill.
- Follow the existing codebase style: plain module-level functions, `dict`-based rows, `csv.DictReader`/`DictWriter`, no classes, no external framework.

---

## File Structure

- **Create:** `data-cleanup/tmdb_fill.py` — the whole script: constants, `clean_title_and_year`, `normalize_title`, `title_similarity`, `make_tmdb_fetcher`, `search_tmdb`, `find_best_match`, `strip_html`, `needs_image`, `needs_description`, `build_output`, `load_export`, `write_csv`, `run`, `main`.
- **Create:** `tests/data_cleanup/test_tmdb_fill.py` — all unit tests, following the `sys.path.insert` import pattern used by `tests/data_cleanup/test_reformat_movies.py`.
- **Create:** `tests/data_cleanup/fixtures/tmdb_sample_export.csv` — a small fixture CSV for the `run()`/CLI-level test.
- **Modify:** none — this module imports `group_rows_by_handle` from the existing `reformat_movies.py` rather than duplicating it.

---

### Task 1: Title cleaning (year extraction + noise-pattern stripping)

**Files:**
- Create: `data-cleanup/tmdb_fill.py`
- Test: `tests/data_cleanup/test_tmdb_fill.py`

**Interfaces:**
- Produces: `clean_title_and_year(title: str) -> tuple[str, int | None]` — later tasks call this to turn a raw product title into a search-ready title and an optional year.

- [ ] **Step 1: Write the failing tests**

Create `tests/data_cleanup/test_tmdb_fill.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-cleanup"))

from tmdb_fill import clean_title_and_year


class TestCleanTitleAndYear(unittest.TestCase):
    def test_extracts_trailing_year(self):
        title, year = clean_title_and_year("Warriors (1994)")
        self.assertEqual(title, "Warriors")
        self.assertEqual(year, 1994)

    def test_no_year_present(self):
        title, year = clean_title_and_year("Bambi")
        self.assertEqual(title, "Bambi")
        self.assertIsNone(year)

    def test_strips_steelbook_noise(self):
        title, year = clean_title_and_year("Trick 'r Treat [Steelbook]")
        self.assertEqual(title, "Trick 'r Treat")
        self.assertIsNone(year)

    def test_strips_free_gift_noise(self):
        title, year = clean_title_and_year("Harriet the Spy (Free Gift)")
        self.assertEqual(title, "Harriet the Spy")
        self.assertIsNone(year)

    def test_strips_widescreen_set_noise(self):
        title, year = clean_title_and_year("Indiana Jones Widescreen Set")
        self.assertEqual(title, "Indiana Jones")
        self.assertIsNone(year)

    def test_strips_parenthesized_noise_and_extracts_year_together(self):
        title, year = clean_title_and_year("Phantasm (Remastered) (1979)")
        self.assertEqual(title, "Phantasm")
        self.assertEqual(year, 1979)

    def test_unrelated_parenthetical_is_not_mistaken_for_year(self):
        # "Free Gift" isn't 4 digits, so it must not be parsed as a year.
        title, year = clean_title_and_year("A Pig's Tale (Free Gift)")
        self.assertEqual(title, "A Pig's Tale")
        self.assertIsNone(year)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: `ModuleNotFoundError: No module named 'tmdb_fill'` (the file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `data-cleanup/tmdb_fill.py`:

```python
"""Fill missing product images/descriptions from TMDB (The Movie Database).

See docs/superpowers/specs/2026-07-14-tmdb-image-description-fill-design.md.
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from reformat_movies import group_rows_by_handle

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

MATCH_THRESHOLD = 0.9
SHORT_DESCRIPTION_LENGTH = 40
REQUEST_DELAY_SECONDS = 0.25

YEAR_PATTERN = re.compile(r"\(\s*(\d{4})\s*\)\s*$")

# Packaging/edition noise that isn't part of the movie's real title.
# Wrapped (bracketed/parenthesized) forms are listed before their bare form
# so both "(Remastered)" and a bare trailing "Remastered" get stripped.
NOISE_PATTERNS = [
    r"\[\s*Steelbook\s*\]",
    r"\(\s*Free Gift\s*\)",
    r"\(\s*Remastered\s*\)",
    r"\bRemastered\b",
    r"\(\s*Director'?s Cut\s*\)",
    r"\bDirector'?s Cut\b",
    r"\(\s*Special Edition\s*\)",
    r"\bSpecial Edition\b",
    r"\(\s*Collector'?s Edition\s*\)",
    r"\bCollector'?s Edition\b",
    r"\(\s*Anniversary Edition\s*\)",
    r"\bAnniversary Edition\b",
    r"\(\s*Extended Cut\s*\)",
    r"\bExtended Cut\b",
    r"\bWidescreen Set\b",
    r"\bFull Screen\b",
    r"\bUncut\b",
    r"\bUnrated\b",
]


def clean_title_and_year(title: str) -> tuple[str, int | None]:
    """Strip a trailing "(YYYY)" year and known packaging/edition noise from a title."""
    year = None
    match = YEAR_PATTERN.search(title)
    if match:
        year = int(match.group(1))
        title = title[: match.start()]

    for pattern in NOISE_PATTERNS:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)

    title = re.sub(r"\s+", " ", title).strip()
    return title, year
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: all 7 tests in `TestCleanTitleAndYear` PASS.

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/tmdb_fill.py tests/data_cleanup/test_tmdb_fill.py
git commit -m "Add TMDB title cleaning (year extraction + noise stripping)"
```

---

### Task 2: TMDB search + confidence matching

**Files:**
- Modify: `data-cleanup/tmdb_fill.py`
- Test: `tests/data_cleanup/test_tmdb_fill.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (this task's functions take already-cleaned titles).
- Produces:
  - `normalize_title(title: str) -> str`
  - `title_similarity(a: str, b: str) -> float`
  - `search_tmdb(fetch_fn, title: str, year: int | None) -> list[dict]` — `fetch_fn` has signature `(query: str, year: int | None) -> dict` (a parsed TMDB JSON response, i.e. a dict with a `"results"` key).
  - `find_best_match(clean_title: str, results: list[dict]) -> tuple[dict | None, bool]` — returns `(top_result_or_None, is_confident)`.
- Later tasks (`build_output`) call `search_tmdb` and `find_best_match` together, and construct a real `fetch_fn` via `make_tmdb_fetcher` (Task 5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/data_cleanup/test_tmdb_fill.py`:

```python
from tmdb_fill import (
    clean_title_and_year,
    normalize_title,
    title_similarity,
    search_tmdb,
    find_best_match,
)


def make_result(title, year=None, overview="An overview.", poster_path="/poster.jpg"):
    return {
        "title": title,
        "release_date": f"{year}-01-01" if year else "",
        "overview": overview,
        "poster_path": poster_path,
    }


class TestNormalizeAndSimilarity(unittest.TestCase):
    def test_normalize_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize_title("The Lion King!"), "the lion king")

    def test_identical_titles_score_one(self):
        self.assertEqual(title_similarity("Warriors", "Warriors"), 1.0)

    def test_dissimilar_titles_score_low(self):
        self.assertLess(title_similarity("Warriors", "The Parent Trap"), 0.5)


class TestSearchTmdb(unittest.TestCase):
    def test_uses_year_filtered_results_when_present(self):
        def fetch(query, year):
            self.assertEqual(query, "Warriors")
            self.assertEqual(year, 1994)
            return {"results": [make_result("Warriors", 1994)]}

        results = search_tmdb(fetch, "Warriors", 1994)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Warriors")

    def test_falls_back_to_no_year_search_when_year_filtered_is_empty(self):
        calls = []

        def fetch(query, year):
            calls.append(year)
            if year is not None:
                return {"results": []}
            return {"results": [make_result("Warriors", 1995)]}

        results = search_tmdb(fetch, "Warriors", 1994)
        self.assertEqual(calls, [1994, None])
        self.assertEqual(len(results), 1)

    def test_returns_empty_when_no_year_given_and_no_results(self):
        results = search_tmdb(lambda q, y: {"results": []}, "Nonexistent Movie", None)
        self.assertEqual(results, [])

    def test_does_not_retry_when_no_year_was_given(self):
        calls = []

        def fetch(query, year):
            calls.append(year)
            return {"results": []}

        search_tmdb(fetch, "Nonexistent Movie", None)
        self.assertEqual(calls, [None])


class TestFindBestMatch(unittest.TestCase):
    def test_confident_on_exact_normalized_match(self):
        results = [make_result("Warriors")]
        best, confident = find_best_match("Warriors", results)
        self.assertEqual(best["title"], "Warriors")
        self.assertTrue(confident)

    def test_not_confident_on_dissimilar_top_result(self):
        results = [make_result("The Parent Trap")]
        best, confident = find_best_match("Warriors", results)
        self.assertEqual(best["title"], "The Parent Trap")
        self.assertFalse(confident)

    def test_no_results_returns_none_and_not_confident(self):
        best, confident = find_best_match("Warriors", [])
        self.assertIsNone(best)
        self.assertFalse(confident)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: `ImportError: cannot import name 'normalize_title'` (and the other new names).

- [ ] **Step 3: Write the implementation**

Append to `data-cleanup/tmdb_fill.py` (after `clean_title_and_year`):

```python
def normalize_title(title: str) -> str:
    """Lowercase and strip everything but letters/digits, for fuzzy comparison."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def search_tmdb(fetch_fn, title: str, year: int | None) -> list[dict]:
    """Search TMDB for a title, falling back to a year-less search if a
    year-filtered search returns nothing (old VHS/DVD release-year metadata
    is often off by a year from TMDB's theatrical date)."""
    data = fetch_fn(title, year)
    results = data.get("results", [])
    if not results and year is not None:
        data = fetch_fn(title, None)
        results = data.get("results", [])
    return results


def find_best_match(clean_title: str, results: list[dict]) -> tuple[dict | None, bool]:
    """Return (top_result_or_None, is_confident) for a TMDB search's results list."""
    if not results:
        return None, False
    best = results[0]
    score = title_similarity(clean_title, best.get("title", ""))
    return best, score >= MATCH_THRESHOLD
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: all tests, including the new `TestNormalizeAndSimilarity`, `TestSearchTmdb`, and `TestFindBestMatch` classes, PASS.

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/tmdb_fill.py tests/data_cleanup/test_tmdb_fill.py
git commit -m "Add TMDB search and confidence-matching logic"
```

---

### Task 3: Field-need detection

**Files:**
- Modify: `data-cleanup/tmdb_fill.py`
- Test: `tests/data_cleanup/test_tmdb_fill.py`

**Interfaces:**
- Produces:
  - `strip_html(text: str) -> str`
  - `needs_image(group: list[dict]) -> bool` — `group` is every CSV row sharing one `Handle`, in original order (primary row first).
  - `needs_description(group: list[dict]) -> bool`
- `build_output` (Task 4) calls these per handle-group before deciding whether to search TMDB at all.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data_cleanup/test_tmdb_fill.py`:

```python
from tmdb_fill import strip_html, needs_image, needs_description


def make_row(**overrides):
    row = {
        "Handle": "some-movie",
        "Title": "Some Movie",
        "Body (HTML)": "",
        "Image Src": "",
    }
    row.update(overrides)
    return row


class TestStripHtml(unittest.TestCase):
    def test_removes_tags(self):
        self.assertEqual(strip_html("<p>Hello <b>world</b></p>"), "Hello world")

    def test_handles_empty_string(self):
        self.assertEqual(strip_html(""), "")

    def test_handles_none(self):
        self.assertEqual(strip_html(None), "")


class TestNeedsImage(unittest.TestCase):
    def test_true_when_no_row_has_image(self):
        group = [make_row(), make_row()]
        self.assertTrue(needs_image(group))

    def test_false_when_primary_row_has_image(self):
        group = [make_row(**{"Image Src": "https://img/1.jpg"})]
        self.assertFalse(needs_image(group))

    def test_false_when_a_bonus_image_row_has_image(self):
        group = [make_row(), make_row(**{"Image Src": "https://img/2.jpg", "Title": ""})]
        self.assertFalse(needs_image(group))


class TestNeedsDescription(unittest.TestCase):
    def test_true_when_body_is_empty(self):
        self.assertTrue(needs_description([make_row(**{"Body (HTML)": ""})]))

    def test_true_when_body_is_short(self):
        self.assertTrue(needs_description([make_row(**{"Body (HTML)": "<p>Too short</p>"})]))

    def test_false_when_body_is_long_enough(self):
        long_body = "<p>" + ("A" * 50) + "</p>"
        self.assertFalse(needs_description([make_row(**{"Body (HTML)": long_body})]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: `ImportError: cannot import name 'strip_html'`.

- [ ] **Step 3: Write the implementation**

Append to `data-cleanup/tmdb_fill.py`:

```python
def strip_html(text: str | None) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def needs_image(group: list[dict]) -> bool:
    return not any(r.get("Image Src", "").strip() for r in group)


def needs_description(group: list[dict]) -> bool:
    text = strip_html(group[0].get("Body (HTML)", ""))
    return len(text) < SHORT_DESCRIPTION_LENGTH
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: all tests, including the new `TestStripHtml`, `TestNeedsImage`, `TestNeedsDescription` classes, PASS.

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/tmdb_fill.py tests/data_cleanup/test_tmdb_fill.py
git commit -m "Add field-need detection for image/description gaps"
```

---

### Task 4: `build_output` — the core fill/review pipeline

**Files:**
- Modify: `data-cleanup/tmdb_fill.py`
- Test: `tests/data_cleanup/test_tmdb_fill.py`

**Interfaces:**
- Consumes: `clean_title_and_year`, `search_tmdb`, `find_best_match`, `needs_image`, `needs_description`, `group_rows_by_handle` (imported from `reformat_movies`).
- Produces: `build_output(rows: list[dict], fetch_fn, sleep_fn=lambda seconds: None) -> tuple[list[dict], list[dict]]` — returns `(output_rows, review_rows)`. `output_rows` is every input row, in original order, with `Image Src`/`Body (HTML)` filled in on primary rows wherever a confident match supplied them. `review_rows` is a list of `{"Handle", "Title", "Reason"}` dicts. `Task 5`'s `run()` calls this directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data_cleanup/test_tmdb_fill.py`:

```python
from tmdb_fill import build_output


NO_SLEEP = lambda seconds: None


class TestBuildOutput(unittest.TestCase):
    def test_untouched_when_both_fields_already_present(self):
        rows = [make_row(**{
            "Handle": "good-movie",
            "Image Src": "https://img/1.jpg",
            "Body (HTML)": "<p>" + ("A" * 50) + "</p>",
        })]

        def fetch_fn(query, year):
            raise AssertionError("should not be called")

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(review_rows, [])

    def test_fills_image_only_leaves_existing_description_untouched(self):
        original_body = "<p>" + ("A" * 50) + "</p>"
        rows = [make_row(**{
            "Handle": "needs-image",
            "Title": "Warriors (1994)",
            "Image Src": "",
            "Body (HTML)": original_body,
        })]

        def fetch_fn(query, year):
            self.assertEqual(query, "Warriors")
            self.assertEqual(year, 1994)
            return {"results": [make_result("Warriors", 1994, overview="Ignored overview.")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/poster.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], original_body)
        self.assertEqual(review_rows, [])

    def test_fills_description_only_leaves_existing_image_untouched(self):
        rows = [make_row(**{
            "Handle": "needs-description",
            "Title": "Bambi",
            "Image Src": "https://img/existing.jpg",
            "Body (HTML)": "",
        })]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], "https://img/existing.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(review_rows, [])

    def test_fills_both_fields_on_confident_match(self):
        rows = [make_row(**{"Handle": "needs-both", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(review_rows, [])

    def test_no_results_routes_to_review_and_leaves_row_unchanged(self):
        rows = [make_row(**{"Handle": "no-match", "Title": "Totally Fictional Movie XYZ"})]

        def fetch_fn(query, year):
            return {"results": []}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Handle"], "no-match")
        self.assertEqual(review_rows[0]["Reason"], "no TMDB match")

    def test_ambiguous_match_routes_to_review_and_leaves_row_unchanged(self):
        rows = [make_row(**{"Handle": "ambiguous", "Title": "Warriors"})]

        def fetch_fn(query, year):
            return {"results": [make_result("The Parent Trap", 1998)]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows, rows)
        self.assertEqual(len(review_rows), 1)
        self.assertIn("ambiguous match", review_rows[0]["Reason"])
        self.assertIn("The Parent Trap", review_rows[0]["Reason"])

    def test_confident_match_missing_poster_fills_description_and_flags_review(self):
        rows = [make_row(**{"Handle": "no-poster", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path=None)]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], "")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Reason"], "matched but no TMDB poster")

    def test_confident_match_missing_overview_fills_image_and_flags_review(self):
        rows = [make_row(**{"Handle": "no-overview", "Title": "Bambi"})]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "")
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Reason"], "matched but no TMDB overview")

    def test_failed_fetch_routes_to_review_without_aborting_batch(self):
        rows = [
            make_row(**{"Handle": "broken", "Title": "Bambi"}),
            make_row(**{"Handle": "fine", "Title": "Bambi"}),
        ]
        calls = []

        def fetch_fn(query, year):
            calls.append(query)
            if len(calls) == 1:
                raise RuntimeError("connection reset")
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Handle"], "broken")
        self.assertIn("TMDB request failed", review_rows[0]["Reason"])
        self.assertIn("connection reset", review_rows[0]["Reason"])
        # the second row still got filled despite the first one erroring
        self.assertEqual(output_rows[1]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")

    def test_multi_row_handle_only_fills_primary_row(self):
        rows = [
            make_row(**{"Handle": "multi", "Title": "Bambi", "Image Position": "1"}),
            make_row(**{"Handle": "multi", "Title": "", "Image Src": "", "Image Position": "2"}),
        ]

        def fetch_fn(query, year):
            return {"results": [make_result("Bambi", overview="A deer grows up.", poster_path="/bambi.jpg")]}

        output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=NO_SLEEP)
        self.assertEqual(output_rows[0]["Image Src"], f"{POSTER_BASE_URL_FOR_TEST}/bambi.jpg")
        self.assertEqual(output_rows[0]["Body (HTML)"], "<p>A deer grows up.</p>")
        # bonus row is untouched
        self.assertEqual(output_rows[1]["Image Src"], "")
        self.assertEqual(output_rows[1]["Body (HTML)"], "")


if __name__ == "__main__":
    unittest.main()
```

Add this constant near the top of the test file (right after the `sys.path.insert` line), since tests reference the poster base URL without hardcoding it twice:

```python
from tmdb_fill import POSTER_BASE_URL as POSTER_BASE_URL_FOR_TEST
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: `ImportError: cannot import name 'build_output'`.

- [ ] **Step 3: Write the implementation**

Append to `data-cleanup/tmdb_fill.py`:

```python
def build_output(rows: list[dict], fetch_fn, sleep_fn=time.sleep) -> tuple[list[dict], list[dict]]:
    """Fill missing Image Src / Body (HTML) fields via TMDB, per product handle.

    Returns (output_rows, review_rows). output_rows preserves every input
    row's original order; only a primary row's Image Src/Body (HTML) are
    ever modified, and only for the field(s) it actually needed.
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    for handle, group in group_rows_by_handle(rows):
        need_img = needs_image(group)
        need_desc = needs_description(group)

        if not need_img and not need_desc:
            output_rows.extend(group)
            continue

        primary = dict(group[0])
        title = primary.get("Title", "").strip() or handle
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review_rows.append({
                "Handle": handle,
                "Title": title,
                "Reason": f"TMDB request failed: {exc}",
            })
            output_rows.extend(group)
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)

        if not results:
            review_rows.append({"Handle": handle, "Title": title, "Reason": "no TMDB match"})
            output_rows.extend(group)
            continue

        best, confident = find_best_match(clean_title, results)
        if not confident:
            best_title = best.get("title", "?")
            best_year = (best.get("release_date") or "")[:4] or "?"
            review_rows.append({
                "Handle": handle,
                "Title": title,
                "Reason": f"ambiguous match (best candidate: '{best_title}' ({best_year}))",
            })
            output_rows.extend(group)
            continue

        if need_img:
            poster_path = best.get("poster_path")
            if poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
            else:
                review_rows.append({
                    "Handle": handle,
                    "Title": title,
                    "Reason": "matched but no TMDB poster",
                })

        if need_desc:
            overview = (best.get("overview") or "").strip()
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
            else:
                review_rows.append({
                    "Handle": handle,
                    "Title": title,
                    "Reason": "matched but no TMDB overview",
                })

        output_rows.append(primary)
        output_rows.extend(group[1:])

    return output_rows, review_rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: all tests, including the new `TestBuildOutput` class (10 tests), PASS.

- [ ] **Step 5: Commit**

```bash
git add data-cleanup/tmdb_fill.py tests/data_cleanup/test_tmdb_fill.py
git commit -m "Add build_output: TMDB-driven image/description fill pipeline"
```

---

### Task 5: Real TMDB fetcher + CLI (`run`/`main`)

**Files:**
- Modify: `data-cleanup/tmdb_fill.py`
- Create: `tests/data_cleanup/fixtures/tmdb_sample_export.csv`
- Test: `tests/data_cleanup/test_tmdb_fill.py`

**Interfaces:**
- Produces:
  - `make_tmdb_fetcher(api_key: str) -> Callable[[str, int | None], dict]` — the real, network-hitting `fetch_fn` implementation used outside tests.
  - `load_export(path) -> tuple[list[str], list[dict]]`
  - `write_csv(path, fieldnames: list[str], rows: list[dict]) -> None`
  - `run(input_path, outdir, api_key: str, fetch_fn=None, sleep_fn=time.sleep) -> dict` — returns `{"filled": int, "review": int}`. When `fetch_fn` is `None`, `run` builds one via `make_tmdb_fetcher(api_key)`; tests always pass an explicit fake `fetch_fn` so no test touches the network.
  - `main()` — argparse CLI entry point, reads `TMDB_API_KEY` from the environment, calls `run`.
- Consumes: `build_output` (Task 4).

- [ ] **Step 1: Create the fixture CSV**

Create `tests/data_cleanup/fixtures/tmdb_sample_export.csv`:

```csv
Handle,Title,Body (HTML),Image Src,Image Position
good-movie,Good Movie,"<p>A perfectly fine, already-complete fifty-plus character description.</p>",https://img/good.jpg,1
needs-both-movie,Needs Both,,,
no-match-movie,Totally Fictional Movie XYZ,,,
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/data_cleanup/test_tmdb_fill.py`:

```python
import tempfile
from unittest.mock import patch

from tmdb_fill import load_export, write_csv, run, make_tmdb_fetcher

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "tmdb_sample_export.csv"


class TestLoadExportAndWriteCsv(unittest.TestCase):
    def test_round_trips_fixture(self):
        fieldnames, rows = load_export(FIXTURE_PATH)
        self.assertIn("Handle", fieldnames)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Handle"], "good-movie")

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.csv"
            write_csv(out_path, fieldnames, rows)
            reloaded_fieldnames, reloaded_rows = load_export(out_path)
            self.assertEqual(reloaded_fieldnames, fieldnames)
            self.assertEqual(reloaded_rows, rows)


class TestMakeTmdbFetcher(unittest.TestCase):
    def test_builds_expected_url_and_parses_json_response(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"results": [{"title": "Bambi"}]}).encode("utf-8")

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("tmdb_fill.urllib.request.urlopen", fake_urlopen):
            fetch = make_tmdb_fetcher("test-api-key")
            data = fetch("Bambi", 1942)

        self.assertEqual(data, {"results": [{"title": "Bambi"}]})
        self.assertIn("api_key=test-api-key", captured["url"])
        self.assertIn("query=Bambi", captured["url"])
        self.assertIn("primary_release_year=1942", captured["url"])

    def test_omits_year_param_when_year_is_none(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"results": []}).encode("utf-8")

        captured = {}

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            return FakeResponse()

        with patch("tmdb_fill.urllib.request.urlopen", fake_urlopen):
            fetch = make_tmdb_fetcher("test-api-key")
            fetch("Bambi", None)

        self.assertNotIn("primary_release_year", captured["url"])


class TestRun(unittest.TestCase):
    def test_writes_filled_and_review_files(self):
        def fetch_fn(query, year):
            if query == "Needs Both":
                return {"results": [make_result("Needs Both", overview="Filled overview.", poster_path="/needs-both.jpg")]}
            return {"results": []}

        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            counts = run(FIXTURE_PATH, outdir, api_key="unused", fetch_fn=fetch_fn, sleep_fn=NO_SLEEP)

            self.assertEqual(counts, {"filled": 3, "review": 1})

            filled_fieldnames, filled_rows = load_export(outdir / "tmdb-filled.csv")
            by_handle = {r["Handle"]: r for r in filled_rows}
            self.assertEqual(by_handle["good-movie"]["Image Src"], "https://img/good.jpg")
            self.assertEqual(
                by_handle["needs-both-movie"]["Image Src"],
                f"{POSTER_BASE_URL_FOR_TEST}/needs-both.jpg",
            )
            self.assertEqual(by_handle["needs-both-movie"]["Body (HTML)"], "<p>Filled overview.</p>")
            self.assertEqual(by_handle["no-match-movie"]["Image Src"], "")

            review_fieldnames, review_rows = load_export(outdir / "tmdb-needs-review.csv")
            self.assertEqual(review_fieldnames, ["Handle", "Title", "Reason"])
            self.assertEqual(len(review_rows), 1)
            self.assertEqual(review_rows[0]["Handle"], "no-match-movie")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: `ImportError: cannot import name 'load_export'`.

- [ ] **Step 4: Write the implementation**

Append to `data-cleanup/tmdb_fill.py`:

```python
def make_tmdb_fetcher(api_key: str):
    """Build a real, network-hitting fetch_fn(query, year) -> dict for TMDB search."""

    def fetch(query: str, year: int | None) -> dict:
        params = {"api_key": api_key, "query": query}
        if year is not None:
            params["primary_release_year"] = year
        url = f"{TMDB_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    return fetch


def load_export(path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(input_path, outdir, api_key: str, fetch_fn=None, sleep_fn=time.sleep) -> dict:
    fieldnames, rows = load_export(input_path)

    if fetch_fn is None:
        fetch_fn = make_tmdb_fetcher(api_key)

    output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=sleep_fn)

    outdir = Path(outdir)
    write_csv(outdir / "tmdb-filled.csv", fieldnames, output_rows)
    write_csv(outdir / "tmdb-needs-review.csv", ["Handle", "Title", "Reason"], review_rows)

    return {"filled": len(output_rows), "review": len(review_rows)}


def main():
    parser = argparse.ArgumentParser(
        description="Fill missing product images/descriptions from TMDB."
    )
    parser.add_argument("input_csv", help="Path to a Shopify product export CSV")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write output files (default: input file's directory)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print("Error: TMDB_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input_csv)
    outdir = Path(args.outdir) if args.outdir else input_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    counts = run(input_path, outdir, api_key)
    print(f"Filled: {counts['filled']} rows -> {outdir / 'tmdb-filled.csv'}")
    print(f"Needs review: {counts['review']} rows -> {outdir / 'tmdb-needs-review.csv'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.data_cleanup.test_tmdb_fill -v`
Expected: every test in the file PASSES (35+ tests across all five tasks).

- [ ] **Step 6: Commit**

```bash
git add data-cleanup/tmdb_fill.py tests/data_cleanup/test_tmdb_fill.py tests/data_cleanup/fixtures/tmdb_sample_export.csv
git commit -m "Add real TMDB fetcher and run()/main() CLI for tmdb_fill.py"
```

---

## Manual smoke test (not automated — requires a real TMDB API key)

After Task 5 is committed, verify against the real API once by hand:

```bash
export TMDB_API_KEY=<your key>
python3 data-cleanup/tmdb_fill.py data-cleanup/movies-reformatted.csv --outdir /tmp/tmdb-smoke-test
```

Check:
1. It completes without a Python traceback.
2. `/tmp/tmdb-smoke-test/tmdb-filled.csv` has the same row count as the input, and a sample of previously-empty `Image Src`/`Body (HTML)` cells for well-known titles (e.g. search the file for `Bambi` or `Hocus Pocus`) are now filled with a plausible `image.tmdb.org` URL and a `<p>...</p>` description.
3. `/tmp/tmdb-smoke-test/tmdb-needs-review.csv` is non-empty and its `Reason` values look sensible (spot-check a few — obscure/retitled VHS-only releases are expected to show up here).
4. Row counts: `filled` count from the printed summary equals the input's row count; `review` count is a small fraction of the ~1,458 flagged products, not most of them (if it's most of them, the matching threshold or noise-pattern list likely needs tuning against the real data — that's expected first-pass tuning, not a bug).

This step is manual because it requires network access and a real API key that must never be committed or hardcoded — it can't run in the automated test suite.
