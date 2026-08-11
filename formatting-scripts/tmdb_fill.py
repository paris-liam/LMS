"""Fill missing product images/descriptions from TMDB (The Movie Database).

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import difflib
import json
import re
import time
import urllib.parse
import urllib.request

from catalog_common import group_rows_by_handle, load_export, write_csv

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w1280"

MATCH_THRESHOLD = 0.9
MATCH_MARGIN = 0.05
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


def classify_match(clean_title: str, year: int | None, results: list[dict]) -> tuple[dict | None, str]:
    """Return (candidate_or_None, "confident" | "ambiguous" | "none").

    Confident needs all three: a strong title score, no runner-up close
    behind it, and — when the input told us a year — a candidate released
    in that year. A lone weak match is ambiguous, not an answer: across
    thousands of rows that difference is hundreds of wrong posters.
    """
    if not results:
        return None, "none"

    scored = sorted(
        ((title_similarity(clean_title, r.get("title", "")), r) for r in results),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]

    if year is not None:
        year_matches = [r for score, r in scored
                        if score >= MATCH_THRESHOLD and (r.get("release_date") or "")[:4] == str(year)]
        if len(year_matches) == 1:
            return year_matches[0], "confident"
        return best, "ambiguous"

    if best_score < MATCH_THRESHOLD:
        return best, "ambiguous"
    if len(scored) > 1 and best_score - scored[1][0] < MATCH_MARGIN:
        return best, "ambiguous"
    return best, "confident"


def strip_html(text: str | None) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def needs_image(group: list[dict]) -> bool:
    return not any(r.get("Image Src", "").strip() for r in group)


def needs_description(group: list[dict]) -> bool:
    return not strip_html(group[0].get("Body (HTML)", ""))


def build_output(
    rows: list[dict],
    fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, handle, message: None,
) -> tuple[list[dict], list[dict]]:
    """Fill empty Image Src / Body (HTML) / Image Alt Text via TMDB.

    Returns (output_rows, review_rows). Row order and count are preserved.
    Review rows are {"Handle", "Title", "Kind", "Reason"} where Kind is
    "ambiguous" (send to the picker) or "unmatched" (send to the CSV).
    Nothing is ever written to Tags.
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    groups = group_rows_by_handle(rows)
    total = len(groups)

    def review(handle, title, kind, reason):
        review_rows.append({"Handle": handle, "Title": title, "Kind": kind, "Reason": reason})

    for index, (handle, group) in enumerate(groups, start=1):
        need_img = needs_image(group)
        need_desc = needs_description(group)

        if not need_img and not need_desc:
            output_rows.extend(group)
            progress_fn(index, total, handle, "already complete, skipped")
            continue

        primary = dict(group[0])
        title = primary.get("Title", "").strip() or handle
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, "unmatched", f"TMDB request failed: {exc}")
            output_rows.extend(group)
            progress_fn(index, total, handle, f"unmatched: request failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)

        best, kind = classify_match(clean_title, year, results)

        if kind == "none":
            review(handle, title, "unmatched", "no TMDB match")
            output_rows.extend(group)
            progress_fn(index, total, handle, "unmatched: no TMDB match")
            continue

        if kind == "ambiguous":
            best_title = best.get("title", "?")
            best_year = (best.get("release_date") or "")[:4] or "?"
            review(handle, title, "ambiguous",
                   f"ambiguous match (best candidate: '{best_title}' ({best_year}))")
            output_rows.extend(group)
            progress_fn(index, total, handle, f"ambiguous: '{best_title}' ({best_year})")
            continue

        match_year = (best.get("release_date") or "")[:4]
        filled = []

        if need_img:
            poster_path = best.get("poster_path")
            if poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
                if not (primary.get("Image Alt Text") or "").strip():
                    suffix = f" ({match_year})" if match_year else ""
                    primary["Image Alt Text"] = f"{title}{suffix} poster"
                filled.append("image")
            else:
                review(handle, title, "unmatched", "matched but TMDB has no poster")

        if need_desc:
            overview = (best.get("overview") or "").strip()
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
                filled.append("description")
            else:
                review(handle, title, "unmatched", "matched but TMDB has no overview")

        output_rows.append(primary)
        output_rows.extend(group[1:])
        progress_fn(index, total, handle, f"filled {', '.join(filled)}" if filled else "matched")

    return output_rows, review_rows


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


def print_progress(index: int, total: int, handle: str, message: str) -> None:
    print(f"[{index}/{total}] {handle}: {message}", flush=True)
