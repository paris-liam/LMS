"""Shared helpers for the catalogue formatting scripts: CSV I/O, tag
manipulation, and handle grouping.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import csv


def load_export(path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_tags(tags_str: str | None) -> list[str]:
    return [t.strip() for t in (tags_str or "").split(",") if t.strip()]


def has_tag(tags_str: str | None, tag: str) -> bool:
    return tag in split_tags(tags_str)


def add_tags(tags_str: str | None, tags_to_add: list[str]) -> str:
    existing = split_tags(tags_str)
    for tag in tags_to_add:
        if tag not in existing:
            existing.append(tag)
    return ", ".join(existing)


def remove_tag(tags_str: str | None, tag: str) -> str:
    return ", ".join(t for t in split_tags(tags_str) if t != tag)


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
