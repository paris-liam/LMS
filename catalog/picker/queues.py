"""The hosted picker's evergreen queues: add products, keep the manifest and
launcher current. Moved from formatting-scripts/hosted_review_page.py (the
per-batch write_hosted_picker is gone — picker push only appends to the two
evergreen queues).
"""

import json
import re
import time
from pathlib import Path

from catalog.core.registry import filter_unknown, mark_queued
from catalog.picker.page import build_hosted_picker_html, build_launcher_html
from catalog.tmdb.candidates import collect_products

# KEEP IN SYNC with BATCH_ID_PATTERN in tools/review-picker/api/_github.js.
# The API routes reject any batch id outside this pattern with a 400; validating
# here means a bad id fails at generation time (for the operator) rather than
# later, on the client's deployed page.
BATCH_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_batch_id(batch_id) -> str:
    """Raise ValueError unless batch_id matches the API's accepted slug pattern."""
    if not isinstance(batch_id, str) or not BATCH_ID_PATTERN.match(batch_id):
        raise ValueError(
            f"invalid batch_id {batch_id!r}: must match {BATCH_ID_PATTERN.pattern} "
            "(lowercase letters, digits, '.', '_', '-'; must start with a letter or digit). "
            "The /api/save-pick and /api/get-picks routes reject anything else with a 400."
        )
    return batch_id

def _products_path(tools_dir, batch_id: str) -> Path:
    return Path(tools_dir) / "data" / f"{batch_id}.products.json"


def load_products(tools_dir, batch_id: str) -> list[dict]:
    """The full accumulated product list for an evergreen queue batch —
    the source of truth for what index.html embeds, kept separately from
    data/<batch_id>.json (which holds only decided picks)."""
    path = _products_path(tools_dir, batch_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_products(tools_dir, batch_id: str, products: list[dict]) -> None:
    path = _products_path(tools_dir, batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(products, indent=2), encoding="utf-8")


def append_to_queue(
    review_rows, tools_dir, batch_id, fetch_fn, registry: dict,
    sleep_fn=time.sleep, progress_fn=None,
) -> dict:
    """Add review rows to an evergreen queue batch, skipping any handle
    already in `registry` (queued in some batch, or already resolved) and
    merging genuinely new products into the batch's persisted product list
    rather than replacing it — so a card already shown to the client, and
    any candidates it holds, is never dropped by a later run.

    `registry` is mutated in place (new handles marked "queued") but not
    saved — the caller owns save_registry, so several batches can share
    one load/save around a run.
    """
    validate_batch_id(batch_id)
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    tools_dir = Path(tools_dir)

    new_rows = filter_unknown(review_rows, registry)
    if not new_rows:
        return {"added": 0, "batch_total": len(load_products(tools_dir, batch_id))}

    new_products = collect_products(new_rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)

    existing = load_products(tools_dir, batch_id)
    existing_handles = {p["handle"] for p in existing}
    added = [p for p in new_products if p["handle"] not in existing_handles]
    merged = existing + added
    save_products(tools_dir, batch_id, merged)

    batch_dir = tools_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "index.html").write_text(
        build_hosted_picker_html(merged, batch_id), encoding="utf-8"
    )

    data_dir = tools_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / f"{batch_id}.json"
    if not data_file.exists():
        data_file.write_text("[]", encoding="utf-8")

    mark_queued(registry, [p["handle"] for p in added], batch_id)

    update_manifest(tools_dir, batch_id, len(merged))
    write_launcher(tools_dir)

    return {"added": len(added), "batch_total": len(merged)}


def update_manifest(tools_dir, batch_id: str, total: int) -> list[dict]:
    """Add or update one batch's entry in tools_dir/batches.json, preserving order."""
    tools_dir = Path(tools_dir)
    manifest_path = tools_dir / "batches.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []

    for entry in manifest:
        if entry["batch_id"] == batch_id:
            entry["total"] = total
            break
    else:
        manifest.append({"batch_id": batch_id, "total": total})

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

def write_launcher(tools_dir) -> None:
    Path(tools_dir).joinpath("index.html").write_text(build_launcher_html(), encoding="utf-8")
