"""Tracks which product handles have ever been queued in the hosted review
picker, so re-processing overlapping catalogue data never creates a
duplicate card for a handle that's already sitting in a queue (or already
resolved).

One JSON file, tools_dir/data/_handle-index.json:

    {"<handle>": {"batch": "ambiguous-queue", "status": "queued"}, ...}

status is "queued" (added to a batch, no decision applied yet) or
"resolved" (a decided pick was applied to a CSV via apply_picks.py). Both
statuses block re-queuing — the point is "don't ask the client to review
this handle again," not "only skip it once."
"""

import json
from pathlib import Path

REGISTRY_FILENAME = "_handle-index.json"


def _registry_path(tools_dir) -> Path:
    return Path(tools_dir) / "data" / REGISTRY_FILENAME


def load_registry(tools_dir) -> dict:
    path = _registry_path(tools_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(tools_dir, registry: dict) -> None:
    path = _registry_path(tools_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def is_known(registry: dict, handle: str) -> bool:
    """True if this handle is already queued somewhere or already resolved."""
    return handle in registry


def filter_unknown(rows: list[dict], registry: dict) -> list[dict]:
    """Rows whose Handle isn't already queued or resolved."""
    return [row for row in rows if not is_known(registry, row["Handle"])]


def mark_queued(registry: dict, handles, batch_id: str) -> None:
    for handle in handles:
        registry[handle] = {"batch": batch_id, "status": "queued"}


def mark_resolved(registry: dict, handles) -> None:
    for handle in handles:
        entry = registry.get(handle, {})
        entry["status"] = "resolved"
        registry[handle] = entry
