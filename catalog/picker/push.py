"""Stage 2 core: which review.json products are new, and adding them to the
hosted picker's evergreen queues."""

from catalog.core import log
from catalog.core.registry import is_known
from catalog.picker.queues import append_to_queue

QUEUE_FOR_KIND = {"ambiguous": "ambiguous-queue", "unmatched": "unmatched-queue"}


def new_entries_by_queue(review: list[dict], registry: dict) -> dict[str, list[dict]]:
    """review.json entries the registry doesn't know yet, grouped by queue.
    The first entry for a handle wins."""
    grouped: dict[str, list[dict]] = {queue: [] for queue in QUEUE_FOR_KIND.values()}
    seen: set[str] = set()
    for entry in review:
        handle = entry["Handle"]
        if handle in seen or is_known(registry, handle):
            continue
        seen.add(handle)
        grouped[QUEUE_FOR_KIND[entry["Kind"]]].append(entry)
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
