"""Which handles the review picker already knows about.

One JSON file, <picker_dir>/data/_handle-index.json:

    {"<handle>": {"batch": "ambiguous-queue", "status": "queued"}, ...}

status: queued   — a card is in a picker queue, no decision applied yet
        applied  — apply wrote an import CSV; `run` and `values` record what
        resolved — a later audit saw those values in Shopify
        skipped  — the client chose "none of these match"
Every status blocks re-queuing. Files written by the old pipeline hold only
queued/resolved and load unchanged. Lives in core/ because audit, picker
push and apply all read it.
"""

import json
from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.text import norm_ws, strip_html

REGISTRY_FILENAME = "_handle-index.json"


def registry_path(picker_dir) -> Path:
    return Path(picker_dir) / "data" / REGISTRY_FILENAME


def load_registry(picker_dir) -> dict:
    path = registry_path(picker_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(picker_dir, registry: dict) -> None:
    path = registry_path(picker_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def is_known(registry: dict, handle: str) -> bool:
    return handle in registry


def filter_unknown(rows: list[dict], registry: dict) -> list[dict]:
    return [row for row in rows if not is_known(registry, row["Handle"])]


def mark_queued(registry: dict, handles, batch_id: str) -> None:
    for handle in handles:
        registry[handle] = {"batch": batch_id, "status": "queued"}


def mark_applied(registry: dict, handle: str, run_id: str, values: dict) -> None:
    entry = registry.setdefault(handle, {})
    entry.update({"status": "applied", "run": run_id, "values": dict(values)})


def mark_skipped(registry: dict, handle: str) -> None:
    registry.setdefault(handle, {})["status"] = "skipped"


def mark_resolved(registry: dict, handles) -> None:
    for handle in handles:
        registry.setdefault(handle, {})["status"] = "resolved"


def _tag_set(value: str) -> set[str]:
    return {t.strip().lower() for t in (value or "").split(",") if t.strip()}


def _handle_set(value: str) -> set[str]:
    return {h.strip() for h in (value or "").split(";") if h.strip()}


def _same_number(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return a.strip() == b.strip()


def fix_visible(row: dict, field: str, value: str) -> bool:
    """Does the snapshot row show a value we applied? Shopify normalises what
    it stores (re-hosts images, sorts tags, prints prices as "0.00"), so each
    field is compared the way Shopify can change it."""
    current = row.get(field) or ""
    value = value or ""
    if field == "Image Src":
        return bool(current.strip())
    if field == "Body (HTML)":
        return norm_ws(strip_html(current)) == norm_ws(strip_html(value))
    if field == "Tags":
        return _tag_set(current) == _tag_set(value)
    if field == GENRE_METAFIELD:
        return _handle_set(current) == _handle_set(value)
    if field == "Variant Price":
        return _same_number(current, value)
    return current.strip() == value.strip()


def promote_applied(registry: dict, rows_by_handle: dict) -> tuple[list[str], list[str]]:
    """applied -> resolved where every recorded value is visible. Handles not
    in the snapshot (deleted/archived products) are left untouched."""
    resolved, missing = [], []
    for handle, entry in registry.items():
        if entry.get("status") != "applied" or handle not in rows_by_handle:
            continue
        row = rows_by_handle[handle]
        if all(fix_visible(row, f, v) for f, v in (entry.get("values") or {}).items()):
            entry["status"] = "resolved"
            resolved.append(handle)
        else:
            missing.append(handle)
    return resolved, missing
