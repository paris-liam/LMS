"""Apply picks exported from the TMDB review picker page to a product CSV.

Takes the tmdb-picks.json downloaded from review-picker.html and a base
product CSV (normally a run's upload.csv), and writes picks-applied.csv
with the chosen TMDB data filled in and skipped products left untouched.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import argparse
import json
from pathlib import Path

from catalog_common import group_rows_by_handle, load_export, write_csv
from tmdb_fill import POSTER_BASE_URL, needs_description, needs_image


def apply_picks(rows: list[dict], picks: list[dict]) -> tuple[list[dict], dict]:
    """Apply review picks to CSV rows, returning (output_rows, counts).

    A "tmdb" pick fills only fields the product actually needs (same rules
    as the auto-fill: image only when missing, description only when
    empty) and only when the pick carries data.
    A "manual" pick is a deliberate operator override: whichever of its
    image_src/overview fields are non-empty replace the current values
    unconditionally. A "skip" pick leaves the row untouched.

    A row with a Status column left blank fails Shopify's import outright
    ("Status isn't valid") — a blank cell in a present column is not the
    same as the column being absent, so a blank Status is filled with
    "active" regardless of pick choice.
    """
    picks_by_handle = {pick["handle"]: pick for pick in picks}
    groups = group_rows_by_handle(rows)
    known_handles = {handle for handle, _ in groups}

    counts = {
        "applied": 0,
        "skipped": 0,
        "unknown": sum(1 for handle in picks_by_handle if handle not in known_handles),
    }

    output_rows: list[dict] = []
    for handle, group in groups:
        pick = picks_by_handle.get(handle)
        if pick is None:
            output_rows.extend(group)
            continue

        primary = dict(group[0])
        title = (primary.get("Title") or "").strip()

        if pick["choice"] == "skip":
            counts["skipped"] += 1
        elif pick["choice"] == "manual":
            image_src = (pick.get("image_src") or "").strip()
            overview = (pick.get("overview") or "").strip()
            if image_src:
                primary["Image Src"] = image_src
                if not (primary.get("Image Alt Text") or "").strip():
                    primary["Image Alt Text"] = f"{title} poster"
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
            counts["applied"] += 1
        else:
            poster_path = (pick.get("poster_path") or "").strip()
            overview = (pick.get("overview") or "").strip()
            if needs_image(group) and poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
                if not (primary.get("Image Alt Text") or "").strip():
                    primary["Image Alt Text"] = f"{title} poster"
            if needs_description(group) and overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
            counts["applied"] += 1

        output_rows.append(primary)
        output_rows.extend(group[1:])

    for row in output_rows:
        if "Status" in row and not (row.get("Status") or "").strip():
            row["Status"] = "active"

    return output_rows, counts


def run(picks_path, base_path, outdir) -> dict:
    with open(picks_path, encoding="utf-8") as f:
        picks = json.load(f)

    fieldnames, rows = load_export(base_path)
    output_rows, counts = apply_picks(rows, picks)

    outdir = Path(outdir)
    write_csv(outdir / "picks-applied.csv", fieldnames, output_rows)
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Apply tmdb-picks.json from the review picker page to a product CSV."
    )
    parser.add_argument("picks_json", help="Path to tmdb-picks.json exported from the picker page")
    parser.add_argument("base_csv", help="Base product CSV to apply picks to (normally upload.csv)")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write picks-applied.csv (default: base CSV's directory)",
    )
    args = parser.parse_args()

    base_path = Path(args.base_csv)
    outdir = Path(args.outdir) if args.outdir else base_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    counts = run(Path(args.picks_json), base_path, outdir)
    print(f"Applied TMDB picks: {counts['applied']}")
    print(f"Skipped: {counts['skipped']}")
    if counts["unknown"]:
        print(f"Warning: {counts['unknown']} pick handle(s) not found in {base_path.name}")
    print(f"Output -> {outdir / 'picks-applied.csv'}")


if __name__ == "__main__":
    main()
