"""Group catalogue movies that are copies of the same movie + format.

Read-only analysis for "what if one product held several copies". Plan and
decisions: claudedocs/2026-10-02-duplicate-copies-lookup-plan.md.

A product is identified by (format, type, edition, box-set flag, title):
  * format  — Vendor; a DVD never groups with a VHS.
  * type    — Rental and Floor Sale copies stay separate products (decision 1).
  * edition — Extended / Director's Cut / … stay separate products
              (decision 2); same-title, different-edition pairs are listed for
              review instead (see edition_pairs).
  * box set — "A / B", "… Collection", "Trilogy" never group with a single
              film (decision 4).
Drafts are grouped like any other product (decision 3); the report lists them
separately.

Titles match in three tiers: exact (case-folded), normalized (punctuation,
& / and, leading article, format words), and fuzzy (about one typo apart, with
identical numbers). Evidence then sets each group's confidence.
"""

import re
import unicodedata
from collections import Counter, defaultdict

from catalog.core.taxonomy import FORMATS, canonical_format, canonical_type
from catalog.core.text import norm_ws, strip_html

CERTAIN, LIKELY, REVIEW = "certain", "likely", "review"
CONFIDENCES = (CERTAIN, LIKELY, REVIEW)

# Description texts shorter than this are too generic to count as evidence.
MIN_DESCRIPTION = 40
# A poster file used by more than this many different titles is a placeholder.
PLACEHOLDER_TITLES = 3
# Fuzzy tier: titles at least this long may differ by this many edits.
FUZZY_MIN_LENGTH = 8
FUZZY_MAX_EDITS = 2

EDITION_PATTERNS = {
    "extended": r"extended(?: edition| cut)?",
    "director's cut": r"director'?s'? cut",
    "collector's edition": r"collector'?s'? edition",
    "special edition": r"special edition",
    "unrated": r"unrated(?: edition| cut)?",
    "criterion": r"criterion(?: collection)?",
    "screener": r"screener",
    "anniversary edition": r"(?:\d+(?:th|st|nd|rd) )?anniversary edition",
    "theatrical": r"theatrical(?: cut| edition| version)?",
    "deluxe edition": r"deluxe edition",
    "limited edition": r"limited edition",
    "remastered": r"(?:digitally )?remastered",
}
_EDITION_RES = {label: re.compile(rf"\b{pattern}\b", re.I) for label, pattern in EDITION_PATTERNS.items()}
_SET_RE = re.compile(
    r"\s/\s|\b(?:collection|trilogy|quadrilogy|anthology|box ?set|double feature|triple feature"
    r"|\d+[- ]film|\d+[- ]movie|complete series|season \d+)\b", re.I)
_FORMAT_WORDS_RE = re.compile(r"[\(\[]?\b(?:dvd|vhs|blu-?ray|4k(?: uhd)?|uhd|laserdisc|betamax)\b[\)\]]?", re.I)
_YEAR_RE = re.compile(r"[\(\[]((?:19|20)\d\d)[\)\]]")
_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}
_UUID_SUFFIX_RE = re.compile(r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=\.)")


# --- per-product parsing -------------------------------------------------

def product_type(row: dict) -> str:
    types = {canonical_type(t) for t in (row.get("Tags") or "").split(",")} - {None}
    if len(types) == 1:
        return types.pop()
    return "Rental + Floor Sale" if types else "untyped"


def product_format(row: dict) -> str | None:
    return canonical_format(row.get("Vendor") or "")


def editions(title: str) -> tuple[str, ...]:
    return tuple(sorted(label for label, rx in _EDITION_RES.items() if rx.search(title)))


def is_box_set(title: str) -> bool:
    return bool(_SET_RE.search(title))


def title_year(title: str) -> str:
    match = _YEAR_RE.search(title)
    return match.group(1) if match else ""


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_title(title: str) -> str:
    """The title with everything that doesn't tell two films apart removed.

    Numbers and roman numerals are kept (they separate sequels); edition
    words, a bracketed year and format words are removed (editions and years
    are compared separately)."""
    text = _fold(title).lower()
    for rx in _EDITION_RES.values():
        text = rx.sub(" ", text)
    text = _YEAR_RE.sub(" ", text)
    text = _FORMAT_WORDS_RE.sub(" ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"['’`]", "", text)          # boyfriend's -> boyfriends
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^(?:the|a|an) ", "", text)
    return re.sub(r"\s+", " ", text).strip()


def number_tokens(normalized: str) -> tuple[str, ...]:
    """Digits and roman numerals, in order — two titles with different ones
    are different films (101 vs 102 Dalmatians, Rocky II vs Rocky III)."""
    return tuple(t for t in normalized.split() if t.isdigit() or t in _ROMAN)


def description_key(row: dict) -> str:
    text = norm_ws(strip_html(row.get("Body (HTML)") or "")).lower()
    return text if len(text) >= MIN_DESCRIPTION else ""


def poster_key(row: dict) -> str:
    """The image's file name without Shopify's `_<uuid>` re-upload suffix —
    for TMDB fills this is the TMDB poster path, shared by every copy."""
    url = (row.get("Image Src") or "").split("?", 1)[0]
    name = url.rsplit("/", 1)[-1].lower()
    return _UUID_SUFFIX_RE.sub("", name)


def quantity(row: dict) -> int | None:
    raw = (row.get("Variant Inventory Qty") or "").strip()
    try:
        return int(float(raw))
    except ValueError:
        return None


# --- grouping ---------------------------------------------------------------

def _edit_distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, giving up (returning limit + 1) past `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def fuzzy_match(a: str, b: str) -> bool:
    if a == b or min(len(a), len(b)) < FUZZY_MIN_LENGTH:
        return False
    if number_tokens(a) != number_tokens(b):
        return False
    return _edit_distance(a, b, FUZZY_MAX_EDITS) <= FUZZY_MAX_EDITS


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def placeholder_posters(rows: list[dict]) -> set[str]:
    titles_per_poster = defaultdict(set)
    for row in rows:
        key = poster_key(row)
        if key:
            titles_per_poster[key].add(normalize_title(row.get("Title") or ""))
    return {key for key, titles in titles_per_poster.items() if len(titles) > PLACEHOLDER_TITLES}


def partition_key(row: dict) -> tuple:
    title = row.get("Title") or ""
    return (product_format(row), product_type(row), editions(title), is_box_set(title))


def find_groups(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(groups, unclassifiable rows). Each group is a dict with members (2+),
    tier, confidence, reasons and its partition fields."""
    movies = [r for r in rows if product_format(r)]
    unclassifiable = [r for r in rows if not product_format(r)]
    placeholders = placeholder_posters(movies)

    partitions = defaultdict(list)
    for row in movies:
        partitions[partition_key(row)].append(row)

    groups = []
    for (fmt, ptype, edition, box_set), members in partitions.items():
        by_norm = defaultdict(list)
        for row in members:
            by_norm[normalize_title(row.get("Title") or "")].append(row)
        names = [n for n in by_norm if n]
        sets = _UnionFind(names)
        # Fuzzy links between normalized titles, blocked by first letter.
        by_initial = defaultdict(list)
        for name in names:
            by_initial[name[0]].append(name)
        for block in by_initial.values():
            block.sort(key=len)
            for i, a in enumerate(block):
                for b in block[i + 1:]:
                    if len(b) - len(a) > FUZZY_MAX_EDITS:
                        break
                    if fuzzy_match(a, b):
                        sets.union(a, b)
        clusters = defaultdict(list)
        for name in names:
            clusters[sets.find(name)].append(name)
        for cluster_names in clusters.values():
            group_rows = [row for name in cluster_names for row in by_norm[name]]
            if len(group_rows) < 2:
                continue
            groups.append(_describe(group_rows, cluster_names, fmt, ptype, edition, box_set, placeholders))

    groups.sort(key=lambda g: (CONFIDENCES.index(g["confidence"]), g["format"], g["type"],
                               normalize_title(g["members"][0].get("Title") or "")))
    for number, group in enumerate(groups, 1):
        group["id"] = f"G{number:04d}"
    return groups, unclassifiable


def _describe(rows, normalized_names, fmt, ptype, edition, box_set, placeholders) -> dict:
    exact_titles = {(r.get("Title") or "").strip().casefold() for r in rows}
    tier = 1 if len(exact_titles) == 1 else (2 if len(normalized_names) == 1 else 3)

    support, against = [], []
    descriptions = Counter(description_key(r) for r in rows if description_key(r))
    posters = Counter(k for k in (poster_key(r) for r in rows) if k and k not in placeholders)

    def corroborated(row):
        d, p = description_key(row), poster_key(row)
        return (d and descriptions[d] > 1) or (p and p not in placeholders and posters[p] > 1)

    if all(corroborated(r) for r in rows):
        kinds = []
        if any(c > 1 for c in descriptions.values()):
            kinds.append("same description")
        if any(c > 1 for c in posters.values()):
            kinds.append("same poster")
        support.append(" + ".join(kinds))
    years = {y for y in (title_year(r.get("Title") or "") for r in rows) if y}
    if len(years) > 1:
        against.append("different years: " + ", ".join(sorted(years)))
    if ptype == "Rental + Floor Sale" or ptype == "untyped":
        against.append(f"type is {ptype}")

    if against:
        confidence = REVIEW
    elif tier in (1, 2) and support:
        confidence = CERTAIN
    elif tier == 2 or (tier == 1 and not support) or (tier == 3 and support):
        confidence = LIKELY
    else:
        confidence = REVIEW

    reasons = [{1: "exact title", 2: "same title after clean-up", 3: "titles one typo apart"}[tier]]
    reasons += support or ["no description/poster match"]
    reasons += against
    return {
        "format": fmt, "type": ptype, "edition": ", ".join(edition), "box_set": box_set,
        "tier": tier, "confidence": confidence, "reasons": "; ".join(reasons),
        "members": sorted(rows, key=lambda r: (r.get("Created At") or "", r.get("Handle") or "")),
    }


def edition_pairs(rows: list[dict]) -> list[dict]:
    """Same format + type + normalized title, but different editions — kept
    as separate products (decision 2) and listed for a person to look at."""
    buckets = defaultdict(list)
    for row in rows:
        fmt = product_format(row)
        if not fmt:
            continue
        title = row.get("Title") or ""
        buckets[(fmt, product_type(row), is_box_set(title), normalize_title(title))].append(row)
    out = []
    for (fmt, ptype, _, name), members in buckets.items():
        if name and len({editions(r.get("Title") or "") for r in members}) > 1:
            out.append({"format": fmt, "type": ptype, "members": members})
    return out


__all__ = ["find_groups", "edition_pairs", "normalize_title", "fuzzy_match", "FORMATS",
           "CERTAIN", "LIKELY", "REVIEW", "CONFIDENCES", "quantity", "product_type"]
