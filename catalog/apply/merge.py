"""Combine the audit's safe auto-fixes with the client's picks, checked
against the snapshot. Pure: data in, a MergeResult out.

Precedence: a pick beats an auto-fix on the same field. A tmdb pick only
fills empty fields. A manual pick overwrites when the handle is in the
current picker cycle (registry "queued"); a manual pick from an older batch
(not in the registry) only fills empty fields, so it can't undo a fix made
since. Handles already applied/resolved are left alone.
"""

import html
from dataclasses import dataclass, field

from catalog.core.picks import Pick
from catalog.core.text import strip_html
from catalog.tmdb.match import POSTER_BASE_URL

AUTO_FIX_SOURCE = "auto-fix"
CHANGE_COLUMNS = ["handle", "field", "before", "after", "source"]


@dataclass(frozen=True)
class Change:
    handle: str
    field: str
    before: str
    after: str
    source: str  # "auto-fix" or "pick:<batch>"


@dataclass
class MergeResult:
    changes: list[Change] = field(default_factory=list)
    applied: dict = field(default_factory=dict)    # handle -> {field: value}, pick-sourced only
    skipped: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)  # picks Shopify already satisfies
    ignored: list[tuple[str, str]] = field(default_factory=list)


def _pick_values(pick: Pick, row: dict, current_cycle: bool) -> dict | None:
    """Fields this pick would set; None for an empty manual pick."""
    title = (row.get("Title") or "").strip()
    has_image = bool((row.get("Image Src") or "").strip())
    has_alt = bool((row.get("Image Alt Text") or "").strip())
    has_body = bool(strip_html(row.get("Body (HTML)", "")))
    if pick.choice == "manual":
        if not pick.image_src and not pick.overview:
            return None
        image, body, overwrite = pick.image_src, pick.overview, current_cycle
    else:
        image = f"{POSTER_BASE_URL}{pick.poster_path}" if pick.poster_path else ""
        body, overwrite = pick.overview, False

    values: dict = {}
    if image and (overwrite or not has_image):
        values["Image Src"] = image
        if not has_alt:
            values["Image Alt Text"] = f"{title} poster"
    if body and (overwrite or not has_body):
        values["Body (HTML)"] = f"<p>{html.escape(body, quote=False)}</p>"
    return values


def merge(rows: list[dict], autofix: dict, picks: list[Pick], registry: dict, run_id: str | None = None) -> MergeResult:
    """`run_id`: picks already applied in this same run are re-emitted, so
    re-running apply on a run always rewrites the complete set of files."""
    by_handle = {r["Handle"]: r for r in rows}
    result = MergeResult()
    planned: dict[tuple[str, str], Change] = {}

    for handle, entry in autofix.items():
        row = by_handle.get(handle)
        if row is None:
            result.ignored.append((handle, "auto-fix for a product no longer in the snapshot"))
            continue
        for field_name, after in entry["changes"].items():
            before = row.get(field_name, "") or ""
            if before != after:
                planned[(handle, field_name)] = Change(handle, field_name, before, after, AUTO_FIX_SOURCE)

    if run_id is not None:
        for handle, entry in registry.items():
            if entry.get("status") != "applied" or entry.get("run") != run_id or handle not in by_handle:
                continue
            for field_name, after in (entry.get("values") or {}).items():
                before = by_handle[handle].get(field_name, "") or ""
                if before != after:
                    planned[(handle, field_name)] = Change(handle, field_name, before, after, f"applied:{run_id}")

    latest: dict[str, Pick] = {}
    for pick in picks:  # manifest order: a later batch wins
        latest[pick.handle] = pick

    for handle, pick in latest.items():
        entry = registry.get(handle) or {}
        status = entry.get("status")
        if status in ("applied", "resolved"):
            continue
        # A handle queued in a current queue belongs to that queue's card: a
        # pick from an older batch may fill gaps but never overwrite or skip it.
        current_cycle = status == "queued" and pick.batch == entry.get("batch")
        if pick.choice == "skip":
            if status == "queued" and not current_cycle:
                result.ignored.append((handle, f"skip in {pick.batch} superseded by the card in {entry.get('batch')}"))
            elif status != "skipped":
                result.skipped.append(handle)
            continue
        row = by_handle.get(handle)
        if row is None:
            result.ignored.append((handle, f"pick in {pick.batch} for a product not in the snapshot"))
            continue
        values = _pick_values(pick, row, current_cycle=current_cycle)
        if values is None:
            result.ignored.append((handle, f"empty manual pick in {pick.batch}"))
            continue
        if not values:
            result.resolved.append(handle)
            continue
        source = f"pick:{pick.batch}"
        for field_name, after in values.items():
            planned[(handle, field_name)] = Change(handle, field_name, row.get(field_name, "") or "", after, source)
        result.applied[handle] = values

    result.changes = sorted(planned.values(), key=lambda c: (c.handle, c.field))
    return result
