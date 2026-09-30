"""Stage 2 core: which review.json products are new, and adding them to the
hosted picker's groups (rentals, floor-sale-NN of 100, untyped)."""

import re
from pathlib import Path

from catalog.core import log
from catalog.core.registry import is_known
from catalog.picker.queues import append_to_queue, load_products
from catalog.tmdb.candidates import rental_or_floor_sale

RENTALS_GROUP = "rentals"
UNTYPED_GROUP = "untyped"
FLOOR_SALE_PREFIX = "floor-sale-"
FLOOR_SALE_GROUP_SIZE = 100
_FLOOR_SALE_ID = re.compile(rf"^{FLOOR_SALE_PREFIX}(\d+)$")


def floor_sale_group(number: int) -> str:
    return f"{FLOOR_SALE_PREFIX}{number:02d}"


def existing_floor_sale_groups(picker_dir) -> dict[int, int]:
    """{group number: cards already in it} for the floor-sale groups on disk."""
    found = {}
    data_dir = Path(picker_dir) / "data"
    for path in data_dir.glob(f"{FLOOR_SALE_PREFIX}*.products.json"):
        match = _FLOOR_SALE_ID.match(path.name[: -len(".products.json")])
        if match:
            found[int(match.group(1))] = len(load_products(picker_dir, path.name[: -len(".products.json")]))
    return found


def _poster_only(entry: dict) -> bool:
    return entry.get("Missing") == ["Image Src"]


def new_entries_by_queue(review: list[dict], registry: dict, picker_dir=None) -> dict[str, list[dict]]:
    """review.json entries the registry doesn't know yet, grouped by the
    picker group they belong in: every rental in `rentals`, floor sales into
    the newest floor-sale-NN until it holds 100 and then a new one, anything
    tagged neither in `untyped`. The type comes from the product's Tags, not
    from why it needs a person. The first entry for a handle wins. Within the
    push, cards missing only a poster go last: a rental with a description is
    already good for Libib. Entries with no `Missing` list (older review.json)
    count as blocking."""
    review = sorted(review, key=_poster_only)
    counts = existing_floor_sale_groups(picker_dir) if picker_dir is not None else {}
    number = max(counts, default=1)
    room = FLOOR_SALE_GROUP_SIZE - counts.get(number, 0)
    grouped: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for entry in review:
        handle = entry["Handle"]
        if handle in seen or is_known(registry, handle):
            continue
        seen.add(handle)
        kind = rental_or_floor_sale(entry.get("Tags", ""))
        if kind == "Rental":
            group = RENTALS_GROUP
        elif kind == "Floor Sale":
            if room <= 0:
                number, room = number + 1, FLOOR_SALE_GROUP_SIZE
            group = floor_sale_group(number)
            room -= 1
        else:
            group = UNTYPED_GROUP
        grouped.setdefault(group, []).append(entry)
    return grouped


def push(entries_by_queue: dict[str, list[dict]], picker_dir, registry: dict, fetch_fn) -> dict[str, dict]:
    """Append each queue's new entries (fetching their TMDB candidates).
    Mutates `registry`; the caller saves it."""
    results = {}
    for queue, entries in entries_by_queue.items():
        if entries:
            results[queue] = append_to_queue(entries, picker_dir, queue, fetch_fn, registry,
                                             sleep_fn=lambda seconds: None, progress_fn=log.progress)
    return results
