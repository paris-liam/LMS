"""Read Libib's two exports and join them. The item/barcode export has the copy
`barcode` but no `description`; the collection export has `description` but
no copy barcode — both are needed (see the 2026-09-18 notes)."""

import csv
from pathlib import Path

from catalog.errors import InputShapeError

DEFAULT_COLLECTION = "Rental Library"
BARCODE_REQUIRED = ("id", "title", "barcode", "call_number", "tags", "collection")
COLLECTION_REQUIRED = ("id", "description")


def _read(path, required: tuple[str, ...]) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise InputShapeError(f"Libib export not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise InputShapeError(f"{path.name} is missing column(s) {', '.join(missing)} — is it the right Libib export?")
        return list(reader)


def load_libib(barcode_export, collection_export, collection: str | None = DEFAULT_COLLECTION) -> list[dict]:
    items_rows = _read(barcode_export, BARCODE_REQUIRED)
    descriptions = {r["id"]: r.get("description") or "" for r in _read(collection_export, COLLECTION_REQUIRED)}
    items = []
    for r in items_rows:
        item_collection = (r.get("collection") or "").strip()
        if collection and item_collection != collection:
            continue
        items.append({
            "id": r["id"],
            "title": r.get("title") or "",
            "barcode": (r.get("barcode") or "").strip(),
            "call_number": (r.get("call_number") or "").strip(),
            "tags": r.get("tags") or "",
            "description": descriptions.get(r["id"], ""),
            "collection": item_collection,
        })
    return items
