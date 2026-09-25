"""The snapshot: one normalized row per catalogue movie (SNAPSHOT_COLUMNS).

Both readers (API and export CSV) produce these rows; filter_catalogue then
drops everything that is not a live movie.
"""

import json
from pathlib import Path

from catalog.core.columns import SNAPSHOT_COLUMNS


def blank_row() -> dict:
    return {column: "" for column in SNAPSHOT_COLUMNS}


def exclusion_reason(row: dict) -> str | None:
    """Why this product is not audited, or None for a catalogue movie."""
    # Movies carry no template suffix (templates/product.json is the movie
    # layout); every non-movie product (retail, membership, …) carries one.
    suffix = (row.get("Template Suffix") or "").strip().lower()
    if suffix:
        return f"{suffix} template"
    if (row.get("Status") or "").strip().lower() == "archived":
        return "archived"
    # Export-path fallbacks: an export CSV carries no template suffix.
    if (row.get("Vendor") or "").strip() == "Supercycle":
        return "membership plan"
    tags = [t.strip().lower() for t in (row.get("Tags") or "").split(",")]
    if "online-store" in tags:
        return "online-store item"
    return None


def filter_catalogue(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    kept: list[dict] = []
    excluded: dict[str, int] = {}
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            kept.append(row)
    return kept, excluded


def write_snapshot(path, rows: list[dict]) -> None:
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")


def load_snapshot(path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
