"""Python mirror of the Libib rental upload sheet.

The sheet (template/libib-rental/) is the deliverable: the client lists new
rentals on `Add rentals`, a `Check` column flags rows that aren't ready, and
the `Libib import` tab turns every ready row into a row of Libib's Movie CSV
import. This module encodes the same rules so they can be tested and the
expected-output fixture regenerated.

The output is shaped for the rental sync app downstream: tags are one format
and the genre handles (catalog/rental_sync/transform.py's vocabulary), and
call_number stays blank so Libib's own `201…` copy barcodes are the join key.
"""

import re

from catalog.core.handles import slugify
from catalog.core.taxonomy import FORMATS, GENRES
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

LIBIB_RENTAL_FILL_COLUMNS = [
    "Title", "Format", "Genre 1", "Genre 2", "Genre 3", "Copies", "Description", "Extra tags",
]
GENRE_COLUMNS = ("Genre 1", "Genre 2", "Genre 3")
CHECK_OK = "OK"
_FORMAT_BY_KEY = {f.lower(): f for f in FORMATS}
_GENRE_HANDLE_BY_KEY = {name.lower(): handle for name, handle in GENRES.items()}
_WHOLE_NUMBER = re.compile(r"^[1-9]\d*$")


def _cell(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _collapse(text) -> str:
    return " ".join((text or "").split())


def is_blank(row: dict) -> bool:
    return not any(_cell(row, column) for column in LIBIB_RENTAL_FILL_COLUMNS)


def row_problems(row: dict) -> list[str]:
    """Why a filled-in row can't be imported yet, in the Check column's order."""
    problems = []
    if not _cell(row, "Title"):
        problems.append("no title")
    if _cell(row, "Format").lower() not in _FORMAT_BY_KEY:
        problems.append("pick a format")
    genres = [_cell(row, column) for column in GENRE_COLUMNS]
    if not any(genres):
        problems.append("pick a genre")
    for genre in genres:
        if genre and genre.lower() not in _GENRE_HANDLE_BY_KEY:
            problems.append(f"unknown genre '{genre}'")
    copies = _cell(row, "Copies")
    if copies and not _WHOLE_NUMBER.match(copies):
        problems.append("copies must be a whole number")
    return problems


def check_value(row: dict) -> str:
    """What the sheet's Check column shows: blank, OK, or the problems."""
    if is_blank(row):
        return ""
    return "; ".join(row_problems(row)) or CHECK_OK


def libib_tags(row: dict) -> str:
    """Format, genre handles, extra tags — lowercased (Libib lowercases on save),
    repeats dropped, in that order."""
    tags = [slugify(_cell(row, "Format"))]
    tags += [_GENRE_HANDLE_BY_KEY.get(_cell(row, c).lower(), "") for c in GENRE_COLUMNS]
    tags += [part.strip().lower() for part in (row.get("Extra tags") or "").split(",")]
    seen: list[str] = []
    for tag in tags:
        if tag and tag not in seen:
            seen.append(tag)
    return ", ".join(seen)


def fill_row_to_libib_row(row: dict) -> dict:
    out = {column: "" for column in LIBIB_MOVIE_COLUMNS}
    out.update({
        "title": _collapse(row.get("Title")),
        "description": _collapse(row.get("Description")),
        "tags": libib_tags(row),
        "copies": _cell(row, "Copies") or "1",
    })
    return out


def fill_rows_to_libib_rows(rows: list[dict]) -> list[dict]:
    """Every row whose Check is OK, in sheet order. Others are held back."""
    return [fill_row_to_libib_row(row) for row in rows if check_value(row) == CHECK_OK]
