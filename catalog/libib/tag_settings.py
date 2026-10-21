"""The adjustable numbers behind `libib tags`, read from tag_settings.json
(next to this file) so they change with a one-line commit, no code:

- new_arrivals.count         how many titles are new arrivals at once
- new_arrivals.max_age_days  null = off; else a title stops being new this
                             many days after it arrived, even inside `count`
- max_changes                the unattended run's change limit; keep it at
                             about 2 × count (a full rotation) + Community Picks
"""

import json
from dataclasses import dataclass
from pathlib import Path

from catalog.errors import InputShapeError

SETTINGS_PATH = Path(__file__).with_name("tag_settings.json")


@dataclass(frozen=True)
class TagSettings:
    new_arrivals_count: int
    new_arrivals_max_age_days: int | None
    max_changes: int


def _int(path: Path, data: dict, key: str, dotted: str, minimum: int, optional: bool = False):
    if key not in data:
        raise InputShapeError(f"{path.name}: missing {dotted}")
    value = data[key]
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        allowed = f"a whole number ≥ {minimum}" + (" or null" if optional else "")
        raise InputShapeError(f"{path.name}: {dotted} must be {allowed}, not {value!r}")
    return value


def load_settings(path=SETTINGS_PATH) -> TagSettings:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise InputShapeError(f"{path.name} not found at {path}") from None
    except json.JSONDecodeError as exc:
        raise InputShapeError(f"{path.name} is not valid JSON: {exc}") from None
    arrivals = data.get("new_arrivals")
    if not isinstance(arrivals, dict):
        raise InputShapeError(f"{path.name}: missing new_arrivals")
    return TagSettings(
        new_arrivals_count=_int(path, arrivals, "count", "new_arrivals.count", 1),
        new_arrivals_max_age_days=_int(path, arrivals, "max_age_days", "new_arrivals.max_age_days", 1, optional=True),
        max_changes=_int(path, data, "max_changes", "max_changes", 1),
    )
