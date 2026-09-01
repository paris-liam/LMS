"""Fill missing product images/descriptions from TMDB (The Movie Database).

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import difflib
import json
import re
import time
import urllib.parse
import urllib.request

from catalog_common import group_rows_by_handle
from columns import GENRE_METAFIELD

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w1280"

MATCH_THRESHOLD = 0.9
MATCH_MARGIN = 0.05
REQUEST_DELAY_SECONDS = 0.25

# VHS stopped being a going format well before DVD/Blu-ray/4K did, so a VHS
# row with no title year is very unlikely to be a post-cutoff release — a
# same-titled remake showing up in TMDB's results is the main source of
# false ambiguity there. Only applied when the title itself has no year
# (an explicit title year always wins on conflict) and only for VHS — DVD/
# Blu-ray/4K legitimately carry both new releases and old catalog
# re-releases, so a date filter would wrongly exclude correct matches.
# Laserdisc and Betamax are comparably dead formats but have no cutoff of
# their own yet — is_vhs()/VHS_YEAR_CUTOFF would need generalizing to a
# per-format cutoff before they'd get the same treatment.
VHS_YEAR_CUTOFF = 2008

# The store's actual catalogue — VHS, DVD, Blu-ray, 4K, Laserdisc, and
# Betamax alike — doesn't carry anything released in or after 2020, so a
# candidate dated that late
# is essentially never the right match regardless of format. Looser than
# VHS_YEAR_CUTOFF; VHS rows still use the tighter of the two.
GLOBAL_YEAR_CUTOFF = 2019

# Our Genre metafield holds Shopify taxonomy slugs (one or more, joined with
# "; "). TMDB has no genre filter on /search/movie, but each result carries
# genre_ids from TMDB's own fixed movie-genre list — mapped here so a
# candidate whose genre overlaps ours can get a small score boost. Lossy for
# slugs with no clean TMDB counterpart ("foreign", "holiday" — left
# unmapped rather than guessed).
GENRE_TMDB_IDS: dict[str, set[int]] = {
    "action": {28},
    "adventure": {12},
    "animation": {16},
    "comedy": {35},
    "crime": {80},
    "documentary": {99},
    "drama": {18},
    "family": {10751},
    "kids-family": {10751},
    "fantasy": {14},
    "history": {36},
    "horror": {27},
    "music": {10402},
    "musical": {10402},
    "mystery": {9648},
    "romance": {10749},
    "romantic-comedy": {10749, 35},
    "sci-fi": {878},
    "science-fiction": {878},
    "thriller": {53},
    "tv-movie": {10770},
    "war": {10752},
    "western": {37},
}
GENRE_SCORE_BOOST = 0.05

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


def genre_matches(genre: str, result: dict) -> bool:
    """True if our (possibly "a; b") genre overlaps the TMDB result's genre_ids."""
    if not genre:
        return False
    result_ids = set(result.get("genre_ids") or [])
    if not result_ids:
        return False
    for slug in genre.split(";"):
        if GENRE_TMDB_IDS.get(slug.strip().lower(), set()) & result_ids:
            return True
    return False


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


def is_vhs(vendor: str) -> bool:
    return "vhs" in (vendor or "").lower()


def filter_by_year_cutoff(results: list[dict], cutoff: int) -> list[dict]:
    """Drop candidates released after `cutoff`. A candidate with no parseable
    release year is kept — there's nothing to filter it on. TMDB's search
    API has no date-range param, so this is applied client-side after the
    fetch rather than as a query filter."""
    kept = []
    for r in results:
        release_year = (r.get("release_date") or "")[:4]
        if not release_year or not release_year.isdigit() or int(release_year) <= cutoff:
            kept.append(r)
    return kept


def _is_populated(result: dict) -> bool:
    return bool((result.get("release_date") or "").strip()) and bool((result.get("poster_path") or "").strip())


def drop_incomplete_duplicates(results: list[dict]) -> list[dict]:
    """Within groups of candidates sharing the same normalized title, drop
    any missing year and/or poster if a fully-populated candidate exists in
    the same group — these are almost always TMDB's own sparse/duplicate
    entries, not real alternate releases, and left in they cause a false
    tie against the real match."""
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(normalize_title(r.get("title", "")), []).append(r)

    kept = []
    for group in groups.values():
        if len(group) > 1 and any(_is_populated(r) for r in group):
            kept.extend(r for r in group if _is_populated(r))
        else:
            kept.extend(group)
    return kept


# A gap this large between the top two candidates' popularity is treated as
# a soft-but-usable signal that the more popular one is the real match — a
# smaller gap isn't decisive enough to auto-accept on its own.
POPULARITY_TIEBREAK_FACTOR = 10


def popularity_tiebreak(candidates: list[dict]) -> dict | None:
    """Return the candidate with a decisive popularity lead over the
    runner-up, or None if the gap isn't large enough (or there's nothing to
    compare)."""
    if len(candidates) < 2:
        return None
    ranked = sorted(candidates, key=lambda r: r.get("popularity") or 0, reverse=True)
    top_pop = ranked[0].get("popularity") or 0
    runner_pop = ranked[1].get("popularity") or 0
    if top_pop <= 0:
        return None
    if runner_pop <= 0 or top_pop / runner_pop >= POPULARITY_TIEBREAK_FACTOR:
        return ranked[0]
    return None


def candidate_score(clean_title: str, genre: str, result: dict) -> float:
    """Title similarity, nudged up by a genre-overlap boost, capped at 1.0.
    Used by classify_match to rank and threshold auto-match candidates.

    Not used for the review picker's candidate ordering — the 1.0 cap makes
    the genre boost a no-op whenever two candidates already have a perfect
    title match, which is exactly the case the picker needs genre to break
    ties on. review_page.py ranks with title_similarity/genre_matches as
    separate, uncapped sort keys instead."""
    base = title_similarity(clean_title, result.get("title", ""))
    if genre_matches(genre, result):
        base = min(base + GENRE_SCORE_BOOST, 1.0)
    return base


def classify_match(
    clean_title: str, year: int | None, results: list[dict], genre: str = "",
) -> tuple[dict | None, str]:
    """Return (candidate_or_None, "confident" | "ambiguous" | "none").

    Confident needs all three: a strong title score, no runner-up close
    behind it, and — when the input told us a year — a candidate released
    in that year. A lone weak match is ambiguous, not an answer: across
    thousands of rows that difference is hundreds of wrong posters.

    When our Genre metafield is known, a candidate whose TMDB genres overlap
    it gets a small score boost (GENRE_SCORE_BOOST) before ranking — nudging
    a genre-matching candidate ahead of a same-titled one in the wrong genre,
    or tipping a close call over MATCH_THRESHOLD/MATCH_MARGIN. It cannot
    manufacture a match on its own: title similarity still has to be in the
    right neighborhood first.

    Sparse/duplicate TMDB entries (same title, missing year and/or poster)
    are dropped before scoring — see drop_incomplete_duplicates — so they
    can't manufacture a false tie against the real candidate.

    When several fully-populated candidates are still genuinely tied on
    title alone (e.g. three "Mandela" entries), two more signals get a shot
    at resolving it before giving up: a genre match that narrows the tie to
    exactly one candidate wins outright, and failing that, a 10x+
    popularity gap (POPULARITY_TIEBREAK_FACTOR) between the top two is
    treated as decisive. Neither can resolve a tie the title/genre data
    genuinely doesn't support — that's still routed to the picker.
    """
    if not results:
        return None, "none"

    results = drop_incomplete_duplicates(results)

    def score(r: dict) -> float:
        return candidate_score(clean_title, genre, r)

    scored = sorted(
        ((score(r), r) for r in results),
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

    tied = [r for s, r in scored if best_score - s < MATCH_MARGIN]
    if len(tied) == 1:
        return best, "confident"

    # Multiple strong, fully-populated candidates still tied on title alone:
    # try narrowing by genre, then by a decisive popularity gap, before
    # giving up and sending this to the picker. A candidate newer than the
    # catalogue could ever carry is excluded from this narrowing first —
    # otherwise it can be the one candidate that happens to carry the right
    # genre tag (or the most popularity) and win a tie it was never really
    # in contention for. This mirrors GLOBAL_YEAR_CUTOFF's build_output-level
    # filter, but scoped to just the tiebreak: `best` (and thus the
    # ambiguous fallback) still reflects the unfiltered field.
    plausible = filter_by_year_cutoff(tied, GLOBAL_YEAR_CUTOFF)
    if plausible:
        tied = plausible

    genre_filtered = [r for r in tied if genre_matches(genre, r)]
    if len(genre_filtered) == 1:
        return genre_filtered[0], "confident"
    if genre_filtered:
        tied = genre_filtered

    pop_winner = popularity_tiebreak(tied)
    if pop_winner is not None:
        return pop_winner, "confident"

    return best, "ambiguous"


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
    progress_fn=lambda index, total, title, message: None,
) -> tuple[list[dict], list[dict]]:
    """Fill empty Image Src / Body (HTML) / Image Alt Text via TMDB.

    Returns (output_rows, review_rows). Row order and count are preserved.
    Review rows are {"Handle", "Title", "Vendor", "Genre", "Kind", "Reason"}
    where Kind is "ambiguous" (send to the picker) or "unmatched" (send to
    the CSV). Vendor/Genre are carried through so the picker and the
    unmatched CSV can show them without looking the row back up — Vendor
    holds the physical format (VHS/DVD/Blu-Ray/4K/Laserdisc/Betamax), not a
    real vendor.
    Nothing is ever written to Tags.
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    groups = group_rows_by_handle(rows)
    total = len(groups)

    def review(handle, title, vendor, genre, kind, reason):
        review_rows.append({
            "Handle": handle, "Title": title, "Vendor": vendor, "Genre": genre,
            "Kind": kind, "Reason": reason,
        })

    for index, (handle, group) in enumerate(groups, start=1):
        title = group[0].get("Title", "").strip() or handle
        need_img = needs_image(group)
        need_desc = needs_description(group)

        if not need_img and not need_desc:
            output_rows.extend(group)
            progress_fn(index, total, title, "already complete, skipped")
            continue

        primary = dict(group[0])
        vendor = primary.get("Vendor", "")
        genre = primary.get(GENRE_METAFIELD, "")
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, vendor, genre, "unmatched", f"TMDB request failed: {exc}")
            output_rows.extend(group)
            progress_fn(index, total, title, f"unmatched: request failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)

        best, kind = classify_match(clean_title, year, results, genre)

        # The year cutoff is a disambiguation aid, not a pre-filter: it only
        # gets a say when the unfiltered result was already ambiguous. Never
        # apply it ahead of classify_match — doing so can strip out the
        # correct candidate (e.g. one TMDB has no poster for) and leave a
        # same-titled but wrong film as the last one standing, turning a
        # safe "needs a human" case into a confidently wrong auto-match.
        # VHS gets the tighter VHS_YEAR_CUTOFF; every other format still
        # gets the looser GLOBAL_YEAR_CUTOFF — the catalogue carries nothing
        # from 2020 on regardless of format.
        if year is None and kind == "ambiguous":
            cutoff = VHS_YEAR_CUTOFF if is_vhs(vendor) else GLOBAL_YEAR_CUTOFF
            filtered = filter_by_year_cutoff(results, cutoff)
            if filtered and filtered != results:
                filtered_best, filtered_kind = classify_match(clean_title, year, filtered, genre)
                if filtered_kind == "confident":
                    best, kind = filtered_best, filtered_kind

        if kind == "none":
            review(handle, title, vendor, genre, "unmatched", "no TMDB match")
            output_rows.extend(group)
            progress_fn(index, total, title, "unmatched: no TMDB match")
            continue

        if kind == "ambiguous":
            best_title = best.get("title", "?")
            best_year = (best.get("release_date") or "")[:4] or "?"
            review(handle, title, vendor, genre, "ambiguous",
                   f"ambiguous match (best candidate: '{best_title}' ({best_year}))")
            output_rows.extend(group)
            progress_fn(index, total, title, f"ambiguous: '{best_title}' ({best_year})")
            continue

        match_year = (best.get("release_date") or "")[:4]
        filled = []

        if need_img:
            poster_path = best.get("poster_path")
            if poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
                if not (primary.get("Image Alt Text") or "").strip():
                    suffix = f" ({match_year})" if match_year else ""
                    primary["Image Alt Text"] = f"{clean_title}{suffix} poster"
                filled.append("image")
            else:
                review(handle, title, vendor, genre, "unmatched", "matched but TMDB has no poster")

        if need_desc:
            overview = (best.get("overview") or "").strip()
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
                filled.append("description")
            else:
                review(handle, title, vendor, genre, "unmatched", "matched but TMDB has no overview")

        output_rows.append(primary)
        output_rows.extend(group[1:])
        progress_fn(index, total, title, f"filled {', '.join(filled)}" if filled else "matched")

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


def print_progress(index: int, total: int, title: str, message: str) -> None:
    print(f"[{index}/{total}] {title}: {message}", flush=True)
