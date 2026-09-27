"""TMDB matching: clean a title, search, and decide confident / ambiguous / none.

Moved from formatting-scripts/tmdb_fill.py. The matching rules are
unchanged; match_product replaces build_output's per-product logic.
"""

import difflib
import re
from dataclasses import dataclass

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.text import strip_html
from catalog.errors import CatalogError

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


# A word-overlap score this low is no more than noise (shared stopwords,
# common movie-description phrasing) — not a real signal that one candidate's
# plot matches our description better than another's.
OVERVIEW_TIEBREAK_MIN_SCORE = 0.15
# ...and the gap over the runner-up has to be this wide to trust it over a
# candidate that merely shares genre-typical vocabulary.
OVERVIEW_TIEBREAK_MARGIN = 0.10

_WORD_RE = re.compile(r"[a-z']+")


def overview_similarity(a: str, b: str) -> float:
    """Jaccard overlap of two texts' lowercased word sets. Cheap and order-
    insensitive — good enough to tell "photographer spies on neighbors,
    convinced of a murder" apart from an unrelated same-titled film's plot,
    which is all this is used for (a tiebreak, not a match on its own)."""
    a_words = set(_WORD_RE.findall((a or "").lower()))
    b_words = set(_WORD_RE.findall((b or "").lower()))
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def overview_tiebreak(candidates: list[dict], overview_hint: str) -> dict | None:
    """Return the candidate whose TMDB overview decisively out-overlaps the
    field against our own product description, or None if there's no hint,
    fewer than two candidates, or no decisive winner."""
    if not overview_hint or len(candidates) < 2:
        return None
    scored = sorted(
        ((overview_similarity(overview_hint, r.get("overview") or ""), r) for r in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top_score, top = scored[0]
    runner_score = scored[1][0]
    if top_score >= OVERVIEW_TIEBREAK_MIN_SCORE and (top_score - runner_score) >= OVERVIEW_TIEBREAK_MARGIN:
        return top
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
    overview_hint: str = "",
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
    title alone (e.g. three "Mandela" entries), three more signals get a
    shot at resolving it before giving up: a genre match that narrows the
    tie to exactly one candidate wins outright; failing that, our own
    product description decisively out-overlapping one candidate's TMDB
    overview over the rest (overview_hint, optional — pass our Body (HTML)
    text stripped of tags; a caller with no description text simply passes
    "" and this tier is skipped); and failing that too, a 10x+ popularity
    gap (POPULARITY_TIEBREAK_FACTOR) between the top two is treated as
    decisive. None of the three can resolve a tie the underlying data
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
        if len(year_matches) > 1:
            overview_winner = overview_tiebreak(year_matches, overview_hint)
            if overview_winner is not None:
                return overview_winner, "confident"
        return best, "ambiguous"

    if best_score < MATCH_THRESHOLD:
        return best, "ambiguous"

    tied = [r for s, r in scored if best_score - s < MATCH_MARGIN]
    if len(tied) == 1:
        return best, "confident"

    # Multiple strong, fully-populated candidates still tied on title alone:
    # try narrowing by genre, then description overlap, then a decisive
    # popularity gap, before giving up and sending this to the picker. A
    # candidate newer than the catalogue could ever carry is excluded from
    # this narrowing first — otherwise it can be the one candidate that
    # happens to carry the right genre tag (or the most popularity) and win
    # a tie it was never really in contention for. This mirrors
    # GLOBAL_YEAR_CUTOFF's build_output-level filter, but scoped to just the
    # tiebreak: `best` (and thus the ambiguous fallback) still reflects the
    # unfiltered field.
    plausible = filter_by_year_cutoff(tied, GLOBAL_YEAR_CUTOFF)
    if plausible:
        tied = plausible

    genre_filtered = [r for r in tied if genre_matches(genre, r)]
    if len(genre_filtered) == 1:
        return genre_filtered[0], "confident"
    if genre_filtered:
        tied = genre_filtered

    overview_winner = overview_tiebreak(tied, overview_hint)
    if overview_winner is not None:
        return overview_winner, "confident"

    pop_winner = popularity_tiebreak(tied)
    if pop_winner is not None:
        return pop_winner, "confident"

    return best, "ambiguous"



@dataclass(frozen=True)
class MatchResult:
    kind: str  # "confident" | "ambiguous" | "none" | "error"
    best: dict | None
    reason: str


def match_product(row: dict, fetch_fn) -> MatchResult:
    """Search TMDB for one snapshot row and classify the result: classify_match,
    then the format-aware year-cutoff retry when the title carried no year.
    The product's own description is the overview tiebreak hint."""
    title = (row.get("Title") or "").strip() or row.get("Handle", "")
    clean_title, year = clean_title_and_year(title)
    genre = row.get(GENRE_METAFIELD, "") or ""
    overview_hint = strip_html(row.get("Body (HTML)", ""))

    try:
        results = search_tmdb(fetch_fn, clean_title, year)
    except CatalogError:
        raise  # a bad key or similar: stop the whole run, don't mark every product failed
    except Exception as exc:  # network, HTTP or JSON failure: never cached, retried next audit
        return MatchResult("error", None, f"TMDB request failed: {exc}")

    best, kind = classify_match(clean_title, year, results, genre, overview_hint)
    if year is None and kind == "ambiguous":
        cutoff = VHS_YEAR_CUTOFF if is_vhs(row.get("Vendor", "")) else GLOBAL_YEAR_CUTOFF
        filtered = filter_by_year_cutoff(results, cutoff)
        if filtered and filtered != results:
            filtered_best, filtered_kind = classify_match(clean_title, year, filtered, genre, overview_hint)
            if filtered_kind == "confident":
                best, kind = filtered_best, filtered_kind

    if kind == "none":
        return MatchResult("none", None, "no TMDB match")
    if kind == "ambiguous":
        best_year = (best.get("release_date") or "")[:4] or "?"
        return MatchResult("ambiguous", best,
                           f"ambiguous match (best candidate: '{best.get('title', '?')}' ({best_year}))")
    return MatchResult("confident", best, "confident TMDB match")


def poster_url(best: dict | None) -> str:
    path = ((best or {}).get("poster_path") or "").strip()
    return f"{POSTER_BASE_URL}{path}" if path else ""


def alt_text_for(title: str, best: dict | None) -> str:
    clean_title, _ = clean_title_and_year(title)
    year = ((best or {}).get("release_date") or "")[:4]
    return f"{clean_title} ({year}) poster" if year else f"{clean_title} poster"
