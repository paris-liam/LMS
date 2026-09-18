"""Per-handle state for the repeatable Shopify -> Libib sync pipeline
(libib_sync.py). One JSON file, libib-sync/_state.json:

    {"<handle>": {
        "status": "queued" | "imported" | "done" | "needs-review",
        "call_number": "...",
        "poster_confirmed": true/false,
        "note": "..."            # why it's needs-review, if applicable
     }, ...}

status moves forward through:
  (absent) -> queue -> "queued" -> prepare -> (still "queued", CSV built)
  -> manual force-import -> mark-imported -> "imported"
  -> sync (barcode/title/description/tags/poster fixed) -> still "imported"
  -> verify confirms it's really in Libib and correct -> "done"
  -> verify finds it's missing/wrong -> back to absent (re-enters the
     eligible pool next `queue` run) or "needs-review" for a real problem
     (barcode collision, sync error) that needs a human, not a retry.

poster_confirmed tracks whether our own script has successfully uploaded
a poster for this handle -- Libib's exports carry no image data, so this
is the only way to know "don't bother re-uploading" on a future audit.
"""

import json
from pathlib import Path

STATE_FILENAME = "_state.json"


def state_path(sync_dir: Path) -> Path:
    return Path(sync_dir) / STATE_FILENAME


def load_state(sync_dir: Path) -> dict:
    path = state_path(sync_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(sync_dir: Path, state: dict) -> None:
    path = state_path(sync_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def set_status(state: dict, handle: str, status: str, **fields) -> None:
    entry = state.setdefault(handle, {})
    entry["status"] = status
    entry.update(fields)


def counts_by_status(state: dict) -> dict:
    counts: dict = {}
    for info in state.values():
        counts[info["status"]] = counts.get(info["status"], 0) + 1
    return counts
