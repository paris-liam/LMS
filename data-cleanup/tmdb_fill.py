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


def strip_html(text: str | None) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def needs_image(group: list[dict]) -> bool:
    return not any(r.get("Image Src", "").strip() for r in group)


def needs_description(group: list[dict]) -> bool:
    text = strip_html(group[0].get("Body (HTML)", ""))
    return len(text) < SHORT_DESCRIPTION_LENGTH


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
