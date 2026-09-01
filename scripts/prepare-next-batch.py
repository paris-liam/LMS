#!/usr/bin/env python3
"""Slice the next N un-uploaded products off the master catalogue CSV into a
new batch, ready to import into production.

Also captures a "before" snapshot for any handle in the batch that already
exists in the static production export (original/products_export_1-prod.csv)
— that's the ground truth for "what did production have before this batch
overwrote it", used later by verify-batch-import.py. Brand new handles (not
in that export) get no snapshot; there's nothing to lose for those.

Usage:
  python3 scripts/prepare-next-batch.py --count 150
  python3 scripts/prepare-next-batch.py --count 150 \
      --master 9.1-products/dev_minus_ambigeous_master.csv \
      --prod-export 9.1-products/original/products_export_1-prod.csv \
      --batches-dir 9.1-products/batches

Each run:
  1. Reads the master CSV.
  2. Takes the next --count *handles* worth of rows (in file order — a
     multi-row/multi-variant product's rows stay together rather than
     splitting across a batch boundary).
  3. Writes them to <batches-dir>/batch-NNN/upload.csv — this is the file
     you import into Shopify Admin.
  4. Writes <batches-dir>/batch-NNN/before-snapshot.csv for any of those
     handles found in the production export.
  5. Removes the consumed rows from the master CSV in place.
"""

import argparse
import csv
import os
import re
import sys


def next_batch_number(batches_dir):
    if not os.path.isdir(batches_dir):
        return 1
    existing = [
        int(m.group(1))
        for name in os.listdir(batches_dir)
        if (m := re.fullmatch(r"batch-(\d+)", name))
    ]
    return max(existing, default=0) + 1


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return r.fieldnames, list(r)


def write_rows(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", default="9.1-products/dev_minus_ambigeous_master.csv")
    ap.add_argument("--prod-export", default="9.1-products/original/products_export_1-prod.csv")
    ap.add_argument("--batches-dir", default="9.1-products/batches")
    ap.add_argument("--count", type=int, default=150, help="number of handles per batch")
    args = ap.parse_args()

    master_fields, master_rows = read_rows(args.master)

    # Group master rows by handle, preserving first-seen order.
    handles_in_order = []
    seen = set()
    for row in master_rows:
        h = row["Handle"].strip()
        if h and h not in seen:
            seen.add(h)
            handles_in_order.append(h)

    batch_handles = set(handles_in_order[: args.count])
    if not batch_handles:
        print("Master CSV has no rows left — nothing to batch.")
        sys.exit(0)

    batch_rows = [r for r in master_rows if r["Handle"].strip() in batch_handles]
    remaining_rows = [r for r in master_rows if r["Handle"].strip() not in batch_handles]

    n = next_batch_number(args.batches_dir)
    batch_dir = os.path.join(args.batches_dir, f"batch-{n:03d}")
    os.makedirs(batch_dir, exist_ok=True)

    upload_path = os.path.join(batch_dir, "upload.csv")
    write_rows(upload_path, master_fields, batch_rows)

    # Before-snapshot: whatever of these handles already exist in the
    # static production export.
    prod_fields, prod_rows = read_rows(args.prod_export)
    before_rows = [r for r in prod_rows if r["Handle"].strip() in batch_handles]
    snapshot_path = None
    if before_rows:
        snapshot_path = os.path.join(batch_dir, "before-snapshot.csv")
        write_rows(snapshot_path, prod_fields, before_rows)

    # Consume from the master file.
    write_rows(args.master, master_fields, remaining_rows)

    existing_handles = {r["Handle"].strip() for r in before_rows}
    new_count = len(batch_handles) - len(existing_handles)

    print(f"Batch {n:03d}: {len(batch_handles)} handles ({len(batch_rows)} rows)")
    print(f"  upload:   {upload_path}")
    if snapshot_path:
        print(f"  snapshot: {snapshot_path} ({len(existing_handles)} pre-existing on production)")
    else:
        print("  snapshot: none — all handles are new to production")
    print(f"  new products (no prior production data): {new_count}")
    print(f"  master CSV: {len(remaining_rows)} rows left")
    print()
    print("Next: import upload.csv into Shopify Admin, then run:")
    print(f"  python3 scripts/verify-batch-import.py {batch_dir}")


if __name__ == "__main__":
    main()
