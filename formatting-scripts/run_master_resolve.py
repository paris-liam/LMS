"""Run master_resolve against the consolidated review queue, using each
batch's on-disk TMDB cache (no network calls).

    python3 formatting-scripts/run_master_resolve.py review-queue-8.31

Writes, into the queue directory:
  - ambiguous.json       overwritten with only the entries still needing
                          a human (the resolved ones are removed)
  - image-fills.csv      Handle, Image Src, Image Alt Text
  - description-fills.csv  Handle, Body (HTML)
  - resolve-report.txt   counts

Each fill CSV only exists if it has at least one row. Import each
separately in Shopify admin — keeping them narrow (rather than one CSV
with both columns) means a product missing only one of the two fields
never has its other, already-populated field blanked by an empty cell in
a present column.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_common import load_export, write_csv
from master_resolve import (
    DESCRIPTION_FILL_COLUMNS,
    IMAGE_FILL_COLUMNS,
    build_fill_rows,
    resolve_queue,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOTS = ["catalogue-batches", "done/catalogue-batches", "done/catalogue-batches-done"]


def find_batch_file(source_folder: str, filenames: tuple[str, ...]) -> Path:
    """Search every known batch root independently for the first of
    `filenames` that exists under source_folder. The cache file and the
    base CSV for the same batch are not guaranteed to live in the same
    root — some batches have upload.csv under catalogue-batches/ but their
    .tmdb-cache.json only survives under done/catalogue-batches/ — so this
    must not assume one shared directory for both."""
    for root in BATCH_ROOTS:
        batch_dir = REPO_ROOT / root / source_folder
        for name in filenames:
            candidate = batch_dir / name
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        f"None of {filenames} found for {source_folder!r} under {BATCH_ROOTS}"
    )


def find_cache_file(source_folder: str) -> Path:
    return find_batch_file(source_folder, (".tmdb-cache.json",))


def find_base_csv(source_folder: str) -> Path:
    return find_batch_file(source_folder, ("upload.csv", "circa-refilled.csv"))


def cache_key(query: str, year: int | None) -> str:
    return f"{(query or '').strip().lower()}|{year if year is not None else ''}"


def load_caches(source_folders: set[str]) -> dict[str, dict]:
    caches = {}
    for folder in source_folders:
        cache_path = find_cache_file(folder)
        caches[folder] = json.loads(cache_path.read_text(encoding="utf-8"))
    return caches


def load_base_rows(source_folders: set[str]) -> dict[str, dict[str, dict]]:
    """{source_folder: {handle: row}} — first row per handle only, which
    is all build_fill_rows needs (image/description live on that row)."""
    base_rows = {}
    for folder in source_folders:
        _, rows = load_export(find_base_csv(folder))
        by_handle = {}
        for row in rows:
            by_handle.setdefault(row["Handle"], row)
        base_rows[folder] = by_handle
    return base_rows


def make_results_lookup(caches, clean_title_and_year_fn):
    def lookup(entry):
        cache = caches.get(entry["source_folder"], {})
        clean_title, year = clean_title_and_year_fn(entry["title"])
        key = cache_key(clean_title, year)
        if key in cache:
            results = cache[key].get("results", [])
            if results or year is None:
                return results
        if year is not None:
            fallback = cache.get(cache_key(clean_title, None))
            if fallback is not None:
                return fallback.get("results", [])
        return None

    return lookup


def collect_rows_by_handle(base_rows) -> dict[str, list[dict]]:
    """A handle can legitimately appear in more than one batch's base CSV
    (the same product got queued for review from two different source
    batches) — collect every copy rather than picking one arbitrarily, so
    make_needs_lookup and make_product_fields_lookup can both reason about the full
    set instead of one non-deterministically chosen row."""
    rows_by_handle: dict[str, list[dict]] = {}
    for rows in base_rows.values():
        for handle, row in rows.items():
            rows_by_handle.setdefault(handle, []).append(row)
    return rows_by_handle


def make_needs_lookup(rows_by_handle):
    """A field only counts as blank when every known copy of that handle
    is blank for it — if even one copy already has data, the field is
    treated as filled, the conservative (never-overwrite) choice. Picking
    one copy via dict-update order would be non-deterministic (Python's
    set iteration order is hash-randomized per process) and could pick a
    stale copy."""

    def lookup(handle):
        rows = rows_by_handle.get(handle, [])
        image_blank = bool(rows) and all(not (r.get("Image Src") or "").strip() for r in rows)
        description_blank = bool(rows) and all(not (r.get("Body (HTML)") or "").strip() for r in rows)
        return image_blank, description_blank

    return lookup


PRODUCT_FIELD_COLUMNS = ("Title", "Option1 Name", "Option1 Value")


def make_product_fields_lookup(rows_by_handle):
    """The Title/Option1 Name/Option1 Value from the first of a handle's
    known copies that has all three non-blank — copies of the same
    product should already agree on these, so this is a deterministic
    pick, not a merge decision like the blank-field checks in
    make_needs_lookup. Returns None if no copy has all three."""

    def lookup(handle):
        for row in rows_by_handle.get(handle, []):
            values = {col: (row.get(col) or "").strip() for col in PRODUCT_FIELD_COLUMNS}
            if all(values.values()):
                return values
        return None

    return lookup


def run(queue_dir: Path) -> dict:
    from tmdb_fill import clean_title_and_year

    entries = json.loads((queue_dir / "ambiguous.json").read_text(encoding="utf-8"))
    source_folders = {e["source_folder"] for e in entries}

    caches = load_caches(source_folders)
    base_rows = load_base_rows(source_folders)

    results_lookup = make_results_lookup(caches, clean_title_and_year)
    resolved, still_ambiguous = resolve_queue(entries, results_lookup)

    rows_by_handle = collect_rows_by_handle(base_rows)
    needs_lookup = make_needs_lookup(rows_by_handle)
    product_fields_lookup = make_product_fields_lookup(rows_by_handle)
    image_rows, description_rows = build_fill_rows(resolved, needs_lookup, product_fields_lookup)

    (queue_dir / "ambiguous.json").write_text(
        json.dumps(still_ambiguous, indent=2), encoding="utf-8"
    )

    if image_rows:
        write_csv(queue_dir / "image-fills.csv", IMAGE_FILL_COLUMNS, image_rows)
    if description_rows:
        write_csv(queue_dir / "description-fills.csv", DESCRIPTION_FILL_COLUMNS, description_rows)

    report = {
        "total_entries": len(entries),
        "resolved": len(resolved),
        "still_ambiguous": len(still_ambiguous),
        "image_fills": len(image_rows),
        "description_fills": len(description_rows),
    }
    lines = [
        f"input entries:        {report['total_entries']}",
        f"resolved (confident): {report['resolved']}",
        f"still ambiguous:      {report['still_ambiguous']}",
        f"image-fills.csv:      {report['image_fills']} rows",
        f"description-fills.csv:{report['description_fills']} rows",
    ]
    (queue_dir / "resolve-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue_dir", help="Directory containing ambiguous.json (e.g. review-queue-8.31)")
    args = parser.parse_args()

    report = run(Path(args.queue_dir))
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
