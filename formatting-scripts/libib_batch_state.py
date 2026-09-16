"""Tracks each product Handle's progress through the Libib batch pipeline,
so `libib_batch.py export` always means "the next handles not yet sent
through", not "the first N rows of the source file again".

One JSON file, <batches_dir>/_handle-index.json:

    {"<handle>": {"batch": "batch-0001", "status": "exported"}, ...}

status moves forward through: awaiting-upc (no UPC/EAN found yet, held
back from import) or exported -> uploaded -> barcoded (or needs-review,
if the barcode step couldn't resolve it -- see libib_barcode_update.py's
own report for why).
"""

import json
from pathlib import Path

REGISTRY_FILENAME = "_handle-index.json"


def registry_path(batches_dir: Path) -> Path:
    return Path(batches_dir) / REGISTRY_FILENAME


def load_registry(batches_dir: Path) -> dict:
    path = registry_path(batches_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(batches_dir: Path, registry: dict) -> None:
    path = registry_path(batches_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def filter_unexported(rows: list[dict], registry: dict) -> list[dict]:
    return [row for row in rows if row["Handle"] not in registry]


def mark(registry: dict, handles, batch_id: str, status: str) -> None:
    for handle in handles:
        registry[handle] = {"batch": batch_id, "status": status}


def handles_in_batch(registry: dict, batch_id: str) -> list:
    return [handle for handle, info in registry.items() if info["batch"] == batch_id]


def counts_by_status(registry: dict) -> dict:
    counts: dict = {}
    for info in registry.values():
        counts[info["status"]] = counts.get(info["status"], 0) + 1
    return counts
