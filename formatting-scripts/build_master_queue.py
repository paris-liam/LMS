"""Build the two files still-ambiguous review needs once the per-batch
output folders are gone: a picker page and a base upload CSV, both
self-contained in the queue directory.

    python3 formatting-scripts/build_master_queue.py review-queue-8.31

Writes, into the queue directory:
  - review-picker.html   the picker page for every entry in ambiguous.json
                          (built straight from the candidates already
                          embedded there — no TMDB calls)
  - upload.csv            each entry's current base product row, pulled
                          from its source batch, so apply_picks.py has
                          something to apply picks to without needing the
                          batch directories anymore

Run this BEFORE deleting catalogue-batches/ (or wherever the batch
output folders live) — it's the last thing that needs them.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_common import write_csv
from extract_master_queue import collect_master_rows
from review_page import build_picker_html
from run_master_resolve import find_base_csv


def load_base_csvs(source_folders: set[str]) -> dict[str, tuple[list[str], list[dict]]]:
    from catalog_common import load_export

    return {folder: load_export(find_base_csv(folder)) for folder in source_folders}


def run(queue_dir: Path) -> dict:
    entries = json.loads((queue_dir / "ambiguous.json").read_text(encoding="utf-8"))
    source_folders = {e["source_folder"] for e in entries}

    rows_by_folder = load_base_csvs(source_folders)
    header, rows, missing = collect_master_rows(entries, rows_by_folder)
    write_csv(queue_dir / "upload.csv", header, rows)

    html = build_picker_html(entries, batch_id=queue_dir.name)
    (queue_dir / "review-picker.html").write_text(html, encoding="utf-8")

    if missing:
        missing_path = queue_dir / "missing-base-rows.json"
        missing_path.write_text(json.dumps(missing, indent=2), encoding="utf-8")

    return {
        "entries": len(entries),
        "upload_rows": len(rows),
        "missing": len(missing),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue_dir", help="Directory containing ambiguous.json (e.g. review-queue-8.31)")
    args = parser.parse_args()

    report = run(Path(args.queue_dir))
    for key, value in report.items():
        print(f"{key}: {value}")
    if report["missing"]:
        print(f"WARNING: {report['missing']} entries had no matching base row — see missing-base-rows.json")


if __name__ == "__main__":
    main()
