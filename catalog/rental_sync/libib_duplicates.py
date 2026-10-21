"""Which new Libib items are really another Libib item again.

A candidate is flagged when some other item (synced or not) has the same
format and the same title, so the person can add it as a copy of that item
instead of making a second product. Pure: nothing here reads or writes a file.
"""

import re

from catalog.duplicates.match import editions, fuzzy_match, is_box_set, normalize_title, title_year
from catalog.rental_sync.transform import transform

_TRAILING_ARTICLE = re.compile(r"^(.*),\s*(the|a|an)\s*$", re.IGNORECASE)


def _unsort(title: str) -> str:
    """Libib's sorted form 'Godfather, The' -> 'The Godfather'."""
    match = _TRAILING_ARTICLE.match(title.strip())
    return f"{match.group(2)} {match.group(1)}" if match else title


def same_title(a: str, b: str) -> bool:
    a, b = _unsort(a), _unsort(b)
    if editions(a) != editions(b) or is_box_set(a) != is_box_set(b):
        return False
    year_a, year_b = title_year(a), title_year(b)
    if year_a and year_b and year_a != year_b:
        return False
    name_a, name_b = normalize_title(a), normalize_title(b)
    return bool(name_a) and (name_a == name_b or fuzzy_match(name_a, name_b))


def _group_items(items: list[dict]) -> dict[str, dict]:
    """Rows sharing an id are one item; title/tags/format come from its first row."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["id"], []).append(item)
    out = {}
    for item_id, rows in groups.items():
        info = transform(rows[0])
        out[item_id] = {
            "item_id": item_id, "title": info["title"], "format": info["format"],
            "genres": [g["name"] for g in info["genres"]], "copies": len(rows),
            "created": min(r.get("created") or "" for r in rows),
            "set_aside": bool(info["set_aside"]),
        }
    return out


def find_libib_duplicates(items: list[dict], candidate_ids: set[str]) -> dict[str, dict]:
    """Candidate item id -> summary of the earliest other item it duplicates."""
    grouped = _group_items(items)
    found = {}
    for cid in candidate_ids:
        mine = grouped.get(cid)
        if not mine or mine["set_aside"] or not mine["format"]:
            continue
        matches = []
        for other in grouped.values():
            if other["item_id"] == cid or other["format"] != mine["format"]:
                continue
            if not same_title(mine["title"], other["title"]):
                continue
            if other["item_id"] in candidate_ids and (other["created"], other["item_id"]) > (mine["created"], cid):
                continue  # both are new: only the later one is flagged
            matches.append(other)
        if matches:
            best = min(matches, key=lambda o: (o["created"], o["item_id"]))
            found[cid] = {k: v for k, v in best.items() if k != "set_aside"}
    return found
