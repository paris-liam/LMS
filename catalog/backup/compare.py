"""Compare a backup products.csv with a Shopify admin export, cell for cell.

LOCAL USE ONLY: this prints cell values (titles, barcodes, prices) so the
developer can see what differs. Run it by hand on files you own; never run it
in GitHub Actions, where logs are not private.

Files are read raw with csv.DictReader, not catalog.core.csv_io.load_export,
which renames "Variant Barcodes" and would hide a real header difference."""

import csv
from pathlib import Path

MAX_LINES = 200


def _read(path: Path) -> tuple[list[str], dict[str, list[dict]]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        groups: dict[str, list[dict]] = {}
        for row in reader:
            groups.setdefault(row.get("Handle") or "", []).append(row)
    return header, groups


def compare_exports(ours: Path, theirs: Path, ignore_columns: set[str]) -> list[str]:
    our_header, our_rows = _read(Path(ours))
    their_header, their_rows = _read(Path(theirs))
    our_cols = [c for c in our_header if c not in ignore_columns]
    their_cols = [c for c in their_header if c not in ignore_columns]
    diffs: list[str] = []

    only_ours = [c for c in our_cols if c not in their_cols]
    only_theirs = [c for c in their_cols if c not in our_cols]
    if only_ours:
        diffs.append(f"header: only in ours: {only_ours}")
    if only_theirs:
        diffs.append(f"header: only in theirs: {only_theirs}")
    common = [c for c in our_cols if c in their_cols]
    if common != [c for c in their_cols if c in common]:
        diffs.append("header: shared columns are in a different order")

    for handle, rows in our_rows.items():
        if handle not in their_rows:
            diffs.append(f"{handle}: missing from theirs ({len(rows)} rows in ours)")
            continue
        other = their_rows[handle]
        for n in range(max(len(rows), len(other))):
            if n >= len(rows):
                diffs.append(f"{handle} row {n + 1}: missing from ours")
            elif n >= len(other):
                diffs.append(f"{handle} row {n + 1}: missing from theirs")
            else:
                for col in common:
                    a, b = rows[n].get(col) or "", other[n].get(col) or ""
                    if a != b:
                        diffs.append(f"{handle} row {n + 1} {col}: ours={a} theirs={b}")
    for handle, rows in their_rows.items():
        if handle not in our_rows:
            diffs.append(f"{handle}: missing from ours ({len(rows)} rows in theirs)")

    if len(diffs) > MAX_LINES:
        return diffs[:MAX_LINES] + [f"... {len(diffs) - MAX_LINES} more differences ({len(diffs)} total)"]
    return diffs
