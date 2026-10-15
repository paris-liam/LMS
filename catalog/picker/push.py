"""Stage 2 core: which review.json products are new, and adding them to the
hosted picker's groups (rentals, untyped). Floor sale is never queued: it
carries no poster or description by design (2026-10-08); the floor-sale-NN
groups already in the picker stay as they are."""

from catalog.core import log
from catalog.core.registry import is_known
from catalog.picker.queues import append_to_queue
from catalog.tmdb.candidates import rental_or_floor_sale

RENTALS_GROUP = "rentals"
UNTYPED_GROUP = "untyped"


def _poster_only(entry: dict) -> bool:
    return entry.get("Missing") == ["Image Src"]


def new_entries_by_queue(review: list[dict], registry: dict) -> dict[str, list[dict]]:
    """review.json entries the registry doesn't know yet, grouped by the
    picker group they belong in: every rental in `rentals`, anything tagged
    neither Rental nor Floor Sale in `untyped`, floor sales left out. The type
    comes from the product's Tags, not from why it needs a person. The first
    entry for a handle wins. Within the push, cards missing only a poster go
    last: a rental with a description is already good for Libib. Entries with
    no `Missing` list (older review.json) count as blocking."""
    review = sorted(review, key=_poster_only)
    grouped: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for entry in review:
        handle = entry["Handle"]
        if handle in seen or is_known(registry, handle):
            continue
        seen.add(handle)
        kind = rental_or_floor_sale(entry.get("Tags", ""))
        if kind == "Floor Sale":
            continue
        group = RENTALS_GROUP if kind == "Rental" else UNTYPED_GROUP
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
