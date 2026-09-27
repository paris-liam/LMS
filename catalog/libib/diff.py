"""Compare the snapshot's rentals with Libib's exports. Pure, except that
in-sync handles still marked queued/imported/needs-review are promoted to
done in `state` (the caller saves it).

Join key: Shopify Variant Barcode == Libib call_number. An item with no
call_number is matched on its copy barcode instead, so an item imported
before call numbers existed is never mistaken for missing and re-imported.
"""

from dataclasses import dataclass, field

from catalog.core.barcodes import barcode_owners, is_rental_barcode
from catalog.core.text import norm_ws
from catalog.libib.fields import (
    expected_description, expected_tags_string, expected_title, is_complete, is_rental, normalized_tag_set,
)
from catalog.libib.state import IN_FLIGHT

DRIFT_COLUMNS = ["handle", "call_number", "field", "shopify", "libib"]
ORPHAN_COLUMNS = ["id", "title", "call_number", "barcode", "reason"]
BLOCKED_COLUMNS = ["handle", "barcode", "reason"]
ELIGIBLE_COLUMNS = ["handle", "call_number", "title"]
HELD_COLUMNS = ["handle", "call_number", "note"]
FIXABLE_FIELDS = ("title", "description", "tags", "barcode", "poster")
_PROMOTABLE = ("queued", "imported", "needs-review")


@dataclass
class DiffResult:
    in_sync: list = field(default_factory=list)
    drift: list = field(default_factory=list)
    eligible: list = field(default_factory=list)
    incomplete: list = field(default_factory=list)
    held: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    orphans: list = field(default_factory=list)
    promoted: list = field(default_factory=list)


def _orphan(item: dict, reason: str) -> dict:
    return {"id": item["id"], "title": item["title"], "call_number": item["call_number"],
            "barcode": item["barcode"], "reason": reason}


def _drift(row: dict, item: dict, entry: dict | None) -> list[dict]:
    call = row["Variant Barcode"].strip()
    out: list[dict] = []

    def add(name, shopify, libib):
        out.append({"handle": row["Handle"], "call_number": call, "field": name, "shopify": shopify, "libib": libib})

    if item["call_number"] != call:
        # Matched on the copy barcode or an old call number: the fixer finds
        # items by call number, so this one needs a manual fix.
        add("call_number", call, item["call_number"])
    if norm_ws(item["title"]) != expected_title(row):
        add("title", expected_title(row), norm_ws(item["title"]))
    if norm_ws(item["description"]) != expected_description(row):
        add("description", expected_description(row), norm_ws(item["description"]))
    if normalized_tag_set(item["tags"]) != normalized_tag_set(expected_tags_string(row)):
        add("tags", expected_tags_string(row), item["tags"])
    if item["barcode"] != call:
        add("barcode", call, item["barcode"])
    image = (row.get("Image Src") or "").strip()
    if image and entry is not None:
        # A tracked rental whose poster our fixer never confirmed (a failed
        # download, or synced before posters were tracked) needs one uploaded.
        poster_src = entry.get("poster_src")
        if not poster_src:
            add("poster", image, "unconfirmed")
        elif poster_src != image:
            add("poster", image, poster_src)
    return out


def diff(rows: list[dict], items: list[dict], state: dict) -> DiffResult:
    result = DiffResult()
    owners = barcode_owners(rows)
    by_call: dict[str, list[dict]] = {}
    by_barcode: dict[str, list[dict]] = {}
    for item in items:
        if item["call_number"]:
            by_call.setdefault(item["call_number"], []).append(item)
        elif item["barcode"]:
            by_barcode.setdefault(item["barcode"], []).append(item)
    matched: set[str] = set()

    for row in rows:
        if not is_rental(row):
            continue
        handle = row["Handle"]
        call = (row.get("Variant Barcode") or "").strip()
        if not is_rental_barcode(call):
            reason = "barcode missing" if not call else "barcode is not 8 digits"
            result.blocked.append({"handle": handle, "barcode": call, "reason": reason})
            continue
        others = [h for h in owners.get(call, []) if h != handle]
        if others:
            result.blocked.append({"handle": handle, "barcode": call, "reason": "barcode also on " + ", ".join(others)})
            continue

        entry = state.get(handle)
        found = by_call.get(call) or by_barcode.get(call) or []
        old_call = ((entry or {}).get("call_number") or "").strip()
        if not found and old_call and old_call != call and len(by_call.get(old_call) or []) == 1:
            found = by_call[old_call]  # still in Libib under its pre-reprint call number
        if len(found) > 1:
            for dup in found:
                matched.add(dup["id"])
                result.orphans.append(_orphan(dup, f"duplicate: {len(found)} Libib items share {call}"))
            continue

        if not found:
            status = (entry or {}).get("status")
            if status in IN_FLIGHT:
                continue
            if status == "needs-review":
                result.held.append({"handle": handle, "call_number": call, "note": (entry or {}).get("note", "")})
                continue
            if is_complete(row):
                result.eligible.append({"handle": handle, "call_number": call, "title": expected_title(row)})
            else:
                result.incomplete.append(handle)
            continue

        libib_item = found[0]
        matched.add(libib_item["id"])
        drift = _drift(row, libib_item, entry)
        if drift:
            result.drift.extend(drift)
            continue
        result.in_sync.append(handle)
        if entry and entry.get("status") in _PROMOTABLE:
            entry["status"] = "done"
            result.promoted.append(handle)

    for libib_item in items:
        if libib_item["id"] not in matched:
            reason = (f"no Shopify rental with call number {libib_item['call_number']}"
                      if libib_item["call_number"] else "no call number")
            result.orphans.append(_orphan(libib_item, reason))
    return result
