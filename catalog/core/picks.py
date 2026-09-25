"""The client's picks, as saved by the hosted picker's /api/save-pick into
tools/review-picker/data/<batch>.json:

    {handle, choice: "tmdb" | "manual" | "skip", poster_path?, overview?, image_src?}

`fields` is reserved for future genre/type/format/price picks. Until apply
supports it, a pick carrying it is rejected — never silently ignored.
Note: /api/save-pick rebuilds each pick from an allowlist of keys, so the
future picker-fields feature must extend that allowlist too.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from catalog.core.git_sync import show_file
from catalog.errors import CatalogError

CHOICES = ("tmdb", "manual", "skip")


class PickError(CatalogError):
    """A saved pick this version of apply cannot safely interpret."""


@dataclass(frozen=True)
class Pick:
    batch: str
    handle: str
    choice: str
    poster_path: str = ""
    overview: str = ""
    image_src: str = ""


def _text(raw: dict, key: str) -> str:
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def parse_pick(raw, batch: str) -> Pick:
    if not isinstance(raw, dict) or not isinstance(raw.get("handle"), str) or not raw["handle"].strip():
        raise PickError(f"a pick in {batch} has no handle: {str(raw)[:200]}")
    handle = raw["handle"].strip()
    if "fields" in raw:
        raise PickError(f"{batch}/{handle}: this pick carries 'fields' (genre/type/format/price), "
                        "which apply does not support yet")
    if raw.get("choice") not in CHOICES:
        raise PickError(f"{batch}/{handle}: unknown choice {raw.get('choice')!r}")
    return Pick(batch, handle, raw["choice"], _text(raw, "poster_path"), _text(raw, "overview"),
                _text(raw, "image_src"))


def load_picks(read_text) -> list[Pick]:
    """Every pick from every batch listed in batches.json, in manifest order.
    read_text(path relative to the picker dir) -> str | None."""
    manifest = read_text("batches.json")
    if manifest is None:
        return []
    picks: list[Pick] = []
    for entry in json.loads(manifest):
        batch = entry["batch_id"]
        data = read_text(f"data/{batch}.json")
        if data is None:
            continue
        picks.extend(parse_pick(raw, batch) for raw in json.loads(data))
    return picks


def local_reader(picker_dir):
    picker_dir = Path(picker_dir)

    def read(rel: str) -> str | None:
        path = picker_dir / rel
        return path.read_text(encoding="utf-8") if path.exists() else None

    return read


def remote_reader(repo_root, ref: str, picker_rel: str):
    def read(rel: str) -> str | None:
        return show_file(repo_root, ref, f"{picker_rel}/{rel}")

    return read
