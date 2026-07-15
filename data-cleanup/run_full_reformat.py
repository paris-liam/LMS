"""Orchestrate the full movie-catalogue reformat pipeline: run both the
resale and CircaOS reformats against one export, merge their review reports,
and build a single combined upload file with review-flagged products tagged
and passed through unchanged.

See docs/superpowers/specs/2026-07-14-full-reformat-pipeline-design.md.
"""

from reformat_movies import FORMAT_COLUMN

NEEDS_REVIEW_TAG = "Needs Review"
CIRCAOS_IMPORT_TAG = "CircaOS Import"


def add_tags(existing_tags_str: str, tags_to_add: list[str]) -> str:
    existing = [t.strip() for t in existing_tags_str.split(",") if t.strip()]
    for t in tags_to_add:
        if t not in existing:
            existing.append(t)
    return ", ".join(existing)


def merge_review_rows(resale_review_rows: list[dict], circaos_review_rows: list[dict]) -> list[dict]:
    merged = []
    for r in resale_review_rows:
        merged.append({**r, "Batch": "resale"})
    for r in circaos_review_rows:
        merged.append({**r, "Batch": "circaos"})
    return merged


def build_passthrough_rows(handle: str, groups: dict, tags_to_add: list[str]) -> list[dict]:
    """Return this handle's original CSV rows, unchanged except Tags on the first row.

    Every other field is preserved at its real current value, since Shopify's
    CSV import clears any column present in the file when a row's cell for
    that column is blank — passthrough rows must never leave a column blank
    just because they don't need to change it.
    """
    group = groups[handle]
    out = []
    for i, r in enumerate(group):
        new_row = dict(r)
        if FORMAT_COLUMN not in new_row:
            new_row[FORMAT_COLUMN] = ""
        if i == 0:
            new_row["Tags"] = add_tags(r["Tags"], tags_to_add)
        out.append(new_row)
    return out


def build_combined_upload(
    resale_output_rows: list[dict],
    circaos_output_rows: list[dict],
    resale_review_rows: list[dict],
    circaos_review_rows: list[dict],
    groups: dict,
) -> list[dict]:
    combined = list(resale_output_rows) + list(circaos_output_rows)
    for r in resale_review_rows:
        combined.extend(build_passthrough_rows(r["Handle"], groups, [NEEDS_REVIEW_TAG]))
    for r in circaos_review_rows:
        combined.extend(
            build_passthrough_rows(r["Handle"], groups, [CIRCAOS_IMPORT_TAG, NEEDS_REVIEW_TAG])
        )
    return combined
