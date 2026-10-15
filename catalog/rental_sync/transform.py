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
