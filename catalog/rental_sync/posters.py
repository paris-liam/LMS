"""TMDB poster for one copy, through the audit's matcher. Only a confident
match is pre-filled in the app; an ambiguous one is offered as "Not sure —
check this" and stays blank until the client accepts it."""

from catalog.core.columns import GENRE_METAFIELD
from catalog.tmdb.match import alt_text_for, match_product, poster_url

KINDS = {"confident": "confident", "ambiguous": "unsure", "none": "none", "error": "error"}


def lookup_poster(copy: dict, fetch_fn) -> dict:
    row = {"Title": copy["title"], "Body (HTML)": copy["description"], "Vendor": copy["format"],
           GENRE_METAFIELD: "; ".join(g["handle"] for g in copy["genres"])}
    result = match_product(row, fetch_fn)
    out = {"barcode": copy["barcode"], "kind": KINDS[result.kind], "url": "", "alt": "", "candidate": None,
           "reason": result.reason}
    if out["kind"] in ("confident", "unsure"):
        url = poster_url(result.best)
        if not url:
            return {**out, "kind": "none", "reason": "TMDB has no poster for this film"}
        best = result.best
        out.update(url=url, alt=alt_text_for(copy["title"], best),
                   candidate={"title": best.get("title", ""), "year": (best.get("release_date") or "")[:4]})
    return out
