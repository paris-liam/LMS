"""TMDB lookup on its own: run the audit's matcher over the products carrying
one tag and report what TMDB would give each — whether or not the product
already has a poster. Read-only; nothing here writes to Shopify or the registry.
"""

from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.text import strip_html
from catalog.tmdb.match import match_product, poster_url

LOOKUP_COLUMNS = [
    "Handle", "Title", "Vendor", "Genre", "Has Poster", "Has Description",
    "Match", "TMDB Title", "TMDB Year", "TMDB ID", "Poster URL", "Overview", "Reason",
]


def has_tag(row: dict, tag: str) -> bool:
    wanted = tag.strip().lower()
    return any(t.strip().lower() == wanted for t in (row.get("Tags") or "").split(","))


def _yes(value) -> str:
    return "yes" if (value or "").strip() else "no"


def lookup(rows: list[dict], tag: str, fetch_fn) -> list[dict]:
    tagged = [r for r in rows if has_tag(r, tag)]
    out = []
    for index, row in enumerate(tagged, 1):
        result = match_product(row, fetch_fn)
        best = result.best if result.kind in ("confident", "ambiguous") else None
        out.append({
            "Handle": row.get("Handle", ""),
            "Title": row.get("Title", ""),
            "Vendor": row.get("Vendor", ""),
            "Genre": row.get(GENRE_METAFIELD, ""),
            "Has Poster": _yes(row.get("Image Src")),
            "Has Description": _yes(strip_html(row.get("Body (HTML)", ""))),
            "Match": result.kind,
            "TMDB Title": (best or {}).get("title", ""),
            "TMDB Year": ((best or {}).get("release_date") or "")[:4],
            "TMDB ID": str((best or {}).get("id", "")),
            "Poster URL": poster_url(best),
            "Overview": (best or {}).get("overview", ""),
            "Reason": result.reason,
        })
        log.progress(index, len(tagged), row.get("Handle", ""), result.reason)
    return out
