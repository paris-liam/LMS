"""Picker candidates: the top TMDB results for a product, ranked for a human.

Moved from formatting-scripts/review_page.py (the ranking half). Its local
page generator is gone — the hosted picker replaced it.
"""

import time

from catalog.tmdb.match import (
    GLOBAL_YEAR_CUTOFF,
    REQUEST_DELAY_SECONDS,
    clean_title_and_year,
    filter_by_year_cutoff,
    genre_matches,
    search_tmdb,
    title_similarity,
)

MAX_CANDIDATES = 5
THUMB_BASE_URL = "https://image.tmdb.org/t/p/w185"

# Same-score candidates are grouped to this many decimal places before
# popularity breaks the tie, so popularity only orders genuinely close
# calls rather than nudging ahead of a clearly better (or worse) title match.
SCORE_TIE_PRECISION = 3


def fetch_candidates(fetch_fn, title: str, year: int | None, genre: str = "") -> list[dict]:
    """Search TMDB and map the top results to picker candidates, ranked by
    title similarity first, genre match as a tiebreak, and popularity/vote
    count as a final tiebreak among candidates still tied after that — so a
    genre mismatch overrides popularity. This mirrors classify_match's own
    signals (title_similarity, genre_matches) but without candidate_score's
    1.0 cap, which would hide the genre tiebreak whenever two candidates
    already have a perfect title match.

    This ordering only affects what the human sees first in the picker —
    it never decides a match on its own (that stays classify_match's job).

    Candidates released in or after GLOBAL_YEAR_CUTOFF + 1 are dropped
    outright (unless the title itself carried an explicit year) — the
    catalogue doesn't carry anything that new, so a candidate from 2020 on
    isn't a real option worth showing the reviewer."""
    results = search_tmdb(fetch_fn, title, year)
    if year is None:
        results = filter_by_year_cutoff(results, GLOBAL_YEAR_CUTOFF)
    results = sorted(
        results,
        key=lambda r: (
            round(title_similarity(title, r.get("title", "")), SCORE_TIE_PRECISION),
            genre_matches(genre, r),
            r.get("popularity") or 0,
            r.get("vote_count") or 0,
        ),
        reverse=True,
    )
    candidates = []
    for result in results[:MAX_CANDIDATES]:
        candidates.append({
            "id": result.get("id"),
            "title": result.get("title") or "",
            "year": (result.get("release_date") or "")[:4],
            "overview": result.get("overview") or "",
            "poster_path": result.get("poster_path") or "",
        })
    return candidates


def collect_products(
    review_rows: list[dict],
    fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, title, message: None,
) -> list[dict]:
    """Dedupe review rows by handle and fetch each product's candidates."""
    merged: dict[str, dict] = {}
    for row in review_rows:
        handle = row["Handle"]
        if handle not in merged:
            merged[handle] = {
                "handle": handle, "title": row["Title"],
                "vendor": row.get("Vendor", ""), "genre": row.get("Genre", ""),
                "tag": rental_or_floor_sale(row.get("Tags", "")),
                "reasons": [],
            }
        merged[handle]["reasons"].append(row["Reason"])

    products = []
    total = len(merged)
    for index, entry in enumerate(merged.values(), start=1):
        clean_title, year = clean_title_and_year(entry["title"])
        try:
            candidates = fetch_candidates(fetch_fn, clean_title, year, genre=entry["genre"])
            message = f"{len(candidates)} candidate(s)"
        except Exception as exc:
            candidates = []
            message = f"TMDB request failed: {exc}"
        sleep_fn(REQUEST_DELAY_SECONDS)
        products.append({
            "handle": entry["handle"],
            "title": entry["title"],
            "vendor": entry["vendor"],
            "genre": entry["genre"],
            "tag": entry["tag"],
            "reason": "; ".join(entry["reasons"]),
            "candidates": candidates,
        })
        progress_fn(index, total, entry["title"], message)

    return products


def rental_or_floor_sale(tags: str) -> str:
    """Pull the catalogue-scoping tag ("Rental" or "Floor Sale") out of a
    raw Shopify Tags string, for the picker's Rental-only filter. Returns
    "" when neither is present (e.g. Tags wasn't carried through, or the
    row predates the Rental/Floor Sale scoping decision)."""
    tag_list = [t.strip() for t in tags.split(",")]
    if "Rental" in tag_list:
        return "Rental"
    if "Floor Sale" in tag_list:
        return "Floor Sale"
    return ""
