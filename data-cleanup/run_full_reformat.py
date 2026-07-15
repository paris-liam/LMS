"""Orchestrate the full movie-catalogue reformat pipeline: run both the
resale and CircaOS reformats against one export, merge their review reports,
and build a single combined upload file with review-flagged products tagged
and passed through unchanged.

See docs/superpowers/specs/2026-07-14-full-reformat-pipeline-design.md.
"""

import argparse
import csv
from pathlib import Path

import reformat_movies
import circaos_reformat
from reformat_movies import FORMAT_COLUMN, group_rows_by_handle

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


def load_export(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(input_path, outdir):
    fieldnames, rows = load_export(input_path)

    resale_fieldnames, resale_output_rows, resale_review_rows = reformat_movies.build_output(
        rows, fieldnames
    )
    circaos_fieldnames, circaos_output_rows, circaos_review_rows = circaos_reformat.build_output(
        rows, fieldnames
    )
    assert resale_fieldnames == circaos_fieldnames
    shared_fieldnames = resale_fieldnames

    groups = dict(group_rows_by_handle(rows))

    review_rows = merge_review_rows(resale_review_rows, circaos_review_rows)
    combined_rows = build_combined_upload(
        resale_output_rows, circaos_output_rows, resale_review_rows, circaos_review_rows, groups
    )

    outdir = Path(outdir)
    write_csv(outdir / "reformatted-resale.csv", shared_fieldnames, resale_output_rows)
    write_csv(outdir / "reformatted-circaos.csv", shared_fieldnames, circaos_output_rows)
    write_csv(outdir / "needs-review.csv", ["Handle", "Title", "Batch", "Reason"], review_rows)
    write_csv(outdir / "combined-upload.csv", shared_fieldnames, combined_rows)

    return {
        "resale_output": len(resale_output_rows),
        "circaos_output": len(circaos_output_rows),
        "review": len(review_rows),
        "combined": len(combined_rows),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run the full movie-catalogue reformat pipeline."
    )
    parser.add_argument("input_csv", help="Path to the full product export CSV")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write output files (default: input file's directory)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    outdir = Path(args.outdir) if args.outdir else input_path.parent

    counts = run(input_path, outdir)
    print(f"Reformatted resale: {counts['resale_output']} rows -> {outdir / 'reformatted-resale.csv'}")
    print(f"Reformatted circaos: {counts['circaos_output']} rows -> {outdir / 'reformatted-circaos.csv'}")
    print(f"Needs review: {counts['review']} rows -> {outdir / 'needs-review.csv'}")
    print(f"Combined upload: {counts['combined']} rows -> {outdir / 'combined-upload.csv'}")


if __name__ == "__main__":
    main()
