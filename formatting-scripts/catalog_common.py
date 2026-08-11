"""Shared helpers for the catalogue formatting scripts: CSV I/O and
handle grouping.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import csv


def load_export(path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames: list[str], rows: list[dict]) -> None:
    for row in rows:
        if None in row:
            handle = row.get("Handle", "(unknown handle)")
            raise ValueError(
                f"Row for Handle {handle!r} has more fields than the CSV header — "
                f"extra value(s) {row[None]!r} were read into an unnamed column. "
                "This usually means a stray comma or an unescaped quote somewhere "
                "in that row of the source file. Fix the row in the source CSV and "
                "re-run."
            )
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def group_rows_by_handle(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group CSV rows by Handle, preserving first-seen order."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        handle = row["Handle"]
        if handle not in groups:
            groups[handle] = []
            order.append(handle)
        groups[handle].append(row)
    return [(handle, groups[handle]) for handle in order]
