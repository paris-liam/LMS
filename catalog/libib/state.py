"""What only we know about each rental's Libib sync — libib-sync/_state.json:

    {"<handle>": {"status": "queued" | "imported" | "done" | "needs-review",
                  "batch": "batch-0007", "call_number": "...",
                  "poster_src": "<Shopify Image Src last uploaded as the poster>",
                  "note": "..."}}

Libib's exports carry no image data, so poster_src is the only way to see
poster drift. Entries written by the old pipeline carry `poster_confirmed`
instead; migrate_poster_src converts them once, from the snapshot.
"""

import json
from pathlib import Path

from catalog.errors import InputShapeError

STATE_FILENAME = "_state.json"
IN_FLIGHT = ("queued", "imported")
# Never offered for import again: in flight, or waiting on a person.
HELD = IN_FLIGHT + ("needs-review",)


def state_path(sync_dir) -> Path:
    return Path(sync_dir) / STATE_FILENAME


def load_state(sync_dir) -> dict:
    path = state_path(sync_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputShapeError(f"{path} is not valid JSON ({exc})") from None


def save_state(sync_dir, state: dict) -> None:
    path = state_path(sync_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def set_status(state: dict, handle: str, status: str, **fields) -> None:
    entry = state.setdefault(handle, {})
    entry["status"] = status
    entry.update(fields)


def counts_by_status(state: dict) -> dict:
    counts: dict = {}
    for entry in state.values():
        counts[entry.get("status", "?")] = counts.get(entry.get("status", "?"), 0) + 1
    return counts


def migrate_poster_src(state: dict, rows_by_handle: dict) -> int:
    migrated = 0
    for handle, entry in state.items():
        if entry.get("poster_confirmed") and not entry.get("poster_src"):
            src = ((rows_by_handle.get(handle) or {}).get("Image Src") or "").strip()
            if src:
                entry["poster_src"] = src
                migrated += 1
    return migrated
