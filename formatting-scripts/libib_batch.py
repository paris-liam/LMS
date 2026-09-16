"""Drives the rental catalogue through Libib in batches: pick the next N
un-sent products from a Shopify export, enrich them with a real UPC/EAN
(libib_pipeline.py), hand off for a manual CSV import into Libib (there is
no API for this -- see claudedocs/2026-09-14-libib-bulk-upload-plan.md),
then set each copy's physical barcode to match its call_number
(libib_barcode_update.py, since that field is UI-only too).

Progress is tracked by product Handle in libib-batches/_handle-index.json
(see libib_batch_state.py) so re-running `export` never re-sends a handle
that's already gone through, even across sessions.

Each batch's enriched rows are split by whether a real UPC/EAN was found:
Libib's CSV import silently drops any row without one unless Force Import
Mode is on, so rows without a UPC are held back rather than imported
title-only -- editing a UPC (or re-importing) after an item already
exists in Libib doesn't do anything useful, since import only creates
items and never updates them. Chase down UPCs for the held-back rows
separately, then export/import them once you have one.

Workflow:

    python3 formatting-scripts/libib_batch.py export products_9.14_rental.csv --size 100
        -> libib-batches/batch-0001/upload-with-upc.csv (ready to import)
           and upload-needs-upc.csv (held back, no UPC yet), plus
           .review.csv if anything needs a look. with-upc handles marked
           "exported", needs-upc handles marked "awaiting-upc"

    # manual step: Libib -> Add Items -> CSV -> upload batch-0001/upload-with-upc.csv

    python3 formatting-scripts/libib_batch.py mark-uploaded batch-0001
        -> "exported" handles (i.e. the with-upc ones) marked "uploaded"

    python3 formatting-scripts/libib_batch.py barcodes batch-0001
        -> runs libib_barcode_update.py against upload-with-upc.csv, handles
           marked "barcoded" (updated/skipped) or "needs-review" (error --
           see batch-0001/upload-with-upc.barcode-report.csv for why)

    python3 formatting-scripts/libib_batch.py status
        -> counts per state across every batch

`export` requires TMDB_API_KEY and UPCMDB_API_KEY in the environment (same
as libib_pipeline.py). `barcodes` requires the venv with playwright set up
for libib_barcode_update.py (see that script's docstring).
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from catalog_common import load_export, write_csv  # noqa: E402
from libib_export import LIBIB_MOVIE_COLUMNS  # noqa: E402
from libib_pipeline import enrich_rows  # noqa: E402
import libib_batch_state as state  # noqa: E402

DEFAULT_BATCHES_DIR = Path("libib-batches")
SCRIPT_DIR = Path(__file__).parent


def next_batch_id(batches_dir: Path) -> str:
    existing = [p.name for p in batches_dir.glob("batch-*") if p.is_dir()]
    numbers = [int(name.split("-")[1]) for name in existing if name.split("-")[1].isdigit()]
    return f"batch-{(max(numbers) + 1) if numbers else 1:04d}"


def cmd_export(args):
    batches_dir = Path(args.batches_dir)
    source_path = Path(args.source)
    registry = state.load_registry(batches_dir)

    _, rows = load_export(source_path)
    pending = state.filter_unexported(rows, registry)
    if not pending:
        print("Nothing left to export -- every handle in the source file has already been sent through.")
        return
    batch_rows = pending[: args.size]

    batch_id = next_batch_id(batches_dir)
    batch_dir = batches_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    print(f"== {batch_id}: {len(batch_rows)} handles ({len(pending)} were pending) ==")
    libib_rows, review_rows = enrich_rows(
        batch_rows, cache_dir=source_path.parent, no_cache=args.no_cache, skip_upcmdb=args.skip_upcmdb
    )

    with_upc_rows = [r for r in libib_rows if r["upc_isbn10"].strip()]
    needs_upc_rows = [r for r in libib_rows if not r["upc_isbn10"].strip()]

    with_upc_path = batch_dir / "upload-with-upc.csv"
    needs_upc_path = batch_dir / "upload-needs-upc.csv"
    write_csv(with_upc_path, LIBIB_MOVIE_COLUMNS, with_upc_rows)
    write_csv(needs_upc_path, LIBIB_MOVIE_COLUMNS, needs_upc_rows)
    print(f"wrote {len(with_upc_rows)} rows to {with_upc_path} (ready to import)")
    print(f"wrote {len(needs_upc_rows)} rows to {needs_upc_path} (held back, no UPC yet)")

    if review_rows:
        review_path = batch_dir / "upload.review.csv"
        write_csv(review_path, ["Handle", "Title", "Vendor", "Kind", "Reason"], review_rows)
        print(f"{len(review_rows)} rows need review -> {review_path}")

    # call_number (Variant Barcode) -> Handle, so `barcodes` can translate
    # libib_barcode_update.py's report rows back to handles for the registry.
    call_number_map = {row.get("Variant Barcode", "").strip(): row["Handle"] for row in batch_rows}
    (batch_dir / "call-numbers.json").write_text(json.dumps(call_number_map, indent=2), encoding="utf-8")

    libib_row_by_handle = dict(zip((r["Handle"] for r in batch_rows), libib_rows))
    with_upc_handles = [h for h, r in libib_row_by_handle.items() if r["upc_isbn10"].strip()]
    needs_upc_handles = [h for h, r in libib_row_by_handle.items() if not r["upc_isbn10"].strip()]
    state.mark(registry, with_upc_handles, batch_id, "exported")
    state.mark(registry, needs_upc_handles, batch_id, "awaiting-upc")
    state.save_registry(batches_dir, registry)

    print(
        f"\nNext: manually import {with_upc_path} into Libib "
        "(Add Items -> CSV), then run:\n"
        f"  python3 formatting-scripts/libib_batch.py mark-uploaded {batch_id}\n"
        f"({len(needs_upc_rows)} rows in {needs_upc_path} are held back until they have a UPC.)"
    )


def cmd_mark_uploaded(args):
    batches_dir = Path(args.batches_dir)
    registry = state.load_registry(batches_dir)
    handles = [h for h in state.handles_in_batch(registry, args.batch_id) if registry[h]["status"] == "exported"]
    if not handles:
        print(f"No handles in {args.batch_id} are waiting to be marked uploaded.")
        return
    state.mark(registry, handles, args.batch_id, "uploaded")
    state.save_registry(batches_dir, registry)
    print(f"{len(handles)} handles in {args.batch_id} marked uploaded.")
    print(f"Next: python3 formatting-scripts/libib_batch.py barcodes {args.batch_id}")


def cmd_barcodes(args):
    batches_dir = Path(args.batches_dir)
    batch_dir = batches_dir / args.batch_id
    upload_path = batch_dir / "upload-with-upc.csv"
    call_number_map_path = batch_dir / "call-numbers.json"
    if not upload_path.exists():
        sys.exit(f"{upload_path} does not exist -- run `export` first.")

    registry = state.load_registry(batches_dir)
    handles = state.handles_in_batch(registry, args.batch_id)
    not_uploaded = [h for h in handles if registry[h]["status"] == "exported"]
    if not_uploaded:
        print(
            f"Warning: {len(not_uploaded)} handles in {args.batch_id} are still marked 'exported', "
            "not 'uploaded' -- make sure you've imported the CSV into Libib first."
        )

    report_path = upload_path.with_suffix(".barcode-report.csv")
    cmd = [sys.executable, str(SCRIPT_DIR / "libib_barcode_update.py"), str(upload_path), "--report", str(report_path)]
    if args.headless:
        cmd.append("--headless")
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    subprocess.run(cmd, check=True)

    call_number_map = json.loads(call_number_map_path.read_text(encoding="utf-8"))
    with report_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    resolved_handles, review_handles = [], []
    for row in rows:
        handle = call_number_map.get(row["call_number"])
        if not handle:
            continue
        (resolved_handles if row["status"] in ("updated", "skipped") else review_handles).append(handle)

    state.mark(registry, resolved_handles, args.batch_id, "barcoded")
    state.mark(registry, review_handles, args.batch_id, "needs-review")
    state.save_registry(batches_dir, registry)
    print(f"\n{len(resolved_handles)} handles barcoded, {len(review_handles)} need manual review (see {report_path}).")


def cmd_status(args):
    batches_dir = Path(args.batches_dir)
    registry = state.load_registry(batches_dir)
    if not registry:
        print("No batches yet.")
        return
    counts = state.counts_by_status(registry)
    for status_name in ("awaiting-upc", "exported", "uploaded", "barcoded", "needs-review"):
        print(f"{status_name}: {counts.get(status_name, 0)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batches-dir", default=str(DEFAULT_BATCHES_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Enrich the next batch and write its Libib upload CSV")
    p_export.add_argument("source", help="Shopify rental-library export CSV")
    p_export.add_argument("--size", type=int, default=100)
    p_export.add_argument("--no-cache", action="store_true")
    p_export.add_argument("--skip-upcmdb", action="store_true")
    p_export.set_defaults(func=cmd_export)

    p_uploaded = sub.add_parser("mark-uploaded", help="Confirm a batch's CSV was manually imported into Libib")
    p_uploaded.add_argument("batch_id")
    p_uploaded.set_defaults(func=cmd_mark_uploaded)

    p_barcodes = sub.add_parser("barcodes", help="Run libib_barcode_update.py against a batch")
    p_barcodes.add_argument("batch_id")
    p_barcodes.add_argument("--headless", action="store_true")
    p_barcodes.add_argument("--limit", type=int, default=None)
    p_barcodes.set_defaults(func=cmd_barcodes)

    p_status = sub.add_parser("status", help="Show handle counts per state")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
