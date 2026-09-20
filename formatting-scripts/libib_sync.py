"""Repeatable Shopify -> Libib rental-catalogue sync.

Shopify is the source of truth. A product is eligible once title, poster,
barcode, description, genre, tags, and format are all filled in (see
libib_fields.py). Libib has no items API and no CSV update path (import
only creates), so getting an item in and keeping it correct is a
human-in-the-loop loop:

    1. (you)  Export the full Shopify rental catalogue, and Libib's two
              exports (Item/barcode export + Collection export -- both
              needed, see 2026-09-18 notes: barcode export has `barcode`
              but no `description`; collection export has `description`
              but no `barcode`).

    2. audit  Compare every item already in Libib against Shopify on
              title/description/tags/barcode. Pure CSV diffing, no
              browser -- cheap even at thousands of items. Flags real
              problems (barcode collisions, orphaned handles) that need
              you, not a script.

    3. queue  Pick the next --size (default 200) eligible, not-yet-queued
              handles from the full Shopify export. Tracked in
              libib-sync/_state.json so re-running never re-grabs a
              handle already in flight or done.

    4. prepare  Build the Libib import CSV + download each poster for the
              queued batch into libib-sync/batch-NNNN/.

    5. (you)  Add Items -> CSV -> upload libib-sync/batch-NNNN/import.csv
              with Force Import Mode on (no UPC needed).

    6. mark-imported + sync
              mark-imported confirms the manual import happened.
              sync runs libib_sync_fix.py (one script, one item-open,
              fixes barcode + title + description + tags + poster
              together) against the batch.

    7. (you)  Fresh Libib export (both files again).
       verify  Confirms each "imported" handle is really in Libib and
              correct; promotes it to "done", or drops it back into the
              eligible pool (or "needs-review" for a real problem) if not.

reverify-posters is a separate one-off track: "done" handles whose poster
was never actually confirmed by our own script (e.g. items that went
through Libib's old, unreliable UPC-based auto-lookup before this pipeline
existed) get a fresh ready.csv + freshly-downloaded poster and a `sync`
pass, same as any other batch -- it's already-live items, so there's no
import.csv/manual-import step, just prepare-equivalent + sync + verify.

Usage:
    python3 formatting-scripts/libib_sync.py audit --shopify <csv> --libib-barcode <csv> --libib-collection <csv>
    python3 formatting-scripts/libib_sync.py queue --shopify <csv> --size 200
    python3 formatting-scripts/libib_sync.py prepare
    python3 formatting-scripts/libib_sync.py mark-imported <batch>
    python3 formatting-scripts/libib_sync.py sync <batch> [--headless]
    python3 formatting-scripts/libib_sync.py verify --shopify <csv> --libib-barcode <csv> --libib-collection <csv>
    python3 formatting-scripts/libib_sync.py reverify-posters --shopify <csv>
    python3 formatting-scripts/libib_sync.py status
"""

import argparse
import csv
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from catalog_common import load_export, write_csv  # noqa: E402
from libib_export import LIBIB_MOVIE_COLUMNS  # noqa: E402
import libib_fields as fields  # noqa: E402
import libib_sync_state as state_mod  # noqa: E402

SYNC_DIR = Path("libib-sync")
SCRIPT_DIR = Path(__file__).parent


def load_shopify_by_handle(path: str) -> dict:
    _, rows = load_export(path)
    return {r["Handle"]: r for r in rows if r["Title"].strip()}


def next_batch_id(sync_dir: Path) -> str:
    existing = [p.name for p in sync_dir.glob("batch-*") if p.is_dir()]
    numbers = [int(name.split("-")[1]) for name in existing if name.split("-")[1].isdigit()]
    return f"batch-{(max(numbers) + 1) if numbers else 1:04d}"


# ---------------------------------------------------------------- audit ----


def cmd_audit(args):
    by_handle = load_shopify_by_handle(args.shopify)
    barcode_rows = list(csv.DictReader(open(args.libib_barcode, newline="", encoding="utf-8")))
    collection_by_id = {r["id"]: r for r in csv.DictReader(open(args.libib_collection, newline="", encoding="utf-8"))}

    state = state_mod.load_state(SYNC_DIR)
    handle_by_call_number = {
        info["call_number"]: handle for handle, info in state.items() if info.get("call_number")
    }

    clean, issues = 0, []
    for row in barcode_rows:
        cn = row["call_number"].strip()
        handle = handle_by_call_number.get(cn)
        srow = by_handle.get(handle) if handle else None
        if not srow:
            issues.append({"call_number": cn, "title": row["title"], "problem": "not tracked / no Shopify match"})
            continue

        coll = collection_by_id.get(row["id"], {})
        problems = []
        if fields.norm_ws(row["title"]) != fields.expected_title(srow):
            problems.append("title")
        if fields.norm_ws(coll.get("description", "")) != fields.expected_description(srow):
            problems.append("description")
        if fields.normalized_tag_set(row.get("tags", "")) != fields.normalized_tag_set(fields.expected_tags_string(srow)):
            problems.append("tags")
        if row["barcode"].strip() != cn:
            problems.append("barcode")

        if problems:
            issues.append({"call_number": cn, "title": row["title"], "problem": ", ".join(problems)})
        else:
            clean += 1
            if handle in state:
                state_mod.set_status(state, handle, "done", call_number=cn)

    state_mod.save_state(SYNC_DIR, state)

    print(f"{clean} clean / {len(barcode_rows)} total in Libib")
    if issues:
        print(f"{len(issues)} with issues:")
        for i in issues:
            print(f"  {i['call_number']} | {i['title']} | {i['problem']}")
        report_path = SYNC_DIR / "audit-issues.csv"
        write_csv(report_path, ["call_number", "title", "problem"], issues)
        print(f"Written to {report_path}")


# ---------------------------------------------------------------- queue ----


def cmd_queue(args):
    by_handle = load_shopify_by_handle(args.shopify)
    state = state_mod.load_state(SYNC_DIR)

    eligible = [h for h, r in by_handle.items() if fields.is_complete(r) and h not in state]
    picked = eligible[: args.size]

    if not picked:
        print("Nothing eligible to queue -- every complete handle is already tracked.")
        return

    for h in picked:
        state_mod.set_status(state, h, "queued")
    state_mod.save_state(SYNC_DIR, state)

    print(f"Queued {len(picked)} handles ({len(eligible)} were eligible).")
    print("Next: python3 formatting-scripts/libib_sync.py prepare")


# -------------------------------------------------------------- prepare ----


def cmd_prepare(args):
    by_handle = load_shopify_by_handle(args.shopify)
    state = state_mod.load_state(SYNC_DIR)

    queued = [h for h, info in state.items() if info["status"] == "queued" and "batch" not in info]
    if not queued:
        print("Nothing queued without a prepared batch yet.")
        return

    batch_id = next_batch_id(SYNC_DIR)
    batch_dir = SYNC_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    import_rows = []
    ready_rows = []
    total = len(queued)
    print(f"{batch_id}: preparing {total} handles...", flush=True)
    for i, h in enumerate(queued, 1):
        srow = by_handle[h]
        call_number = srow.get("Variant Barcode", "").strip()
        title = fields.expected_title(srow)
        description = fields.expected_description(srow)
        tags = fields.expected_tags_string(srow)

        import_rows.append(
            {
                "title": title,
                "creators": "",
                "description": description,
                "upc_isbn10": "",
                "ean_isbn13": "",
                "number_of_discs": "",
                "ensemble": "",
                "aspect_ratio": "",
                "tags": tags,
                "notes": "",
                "group": "",
                "price": srow.get("Variant Price", "").strip(),
                "added": "",
                "publisher": "",
                "publish_date": "",
                "length_of": "",
                "copies": "1",
                "call_number": call_number,
                "ddc": "",
                "lcc": "",
                "rating": "",
                "review": "",
                "review_created": "",
                "status": "",
                "began_date": "",
                "completed_date": "",
            }
        )

        img_url = srow.get("Image Src", "").strip()
        ext = img_url.split("?")[0].split(".")[-1]
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        image_path = batch_dir / f"{call_number}.{ext}"
        try:
            urllib.request.urlretrieve(img_url, image_path)
            print(f"  [{i}/{total}] {call_number} {title}: image ok", flush=True)
        except Exception as exc:
            print(f"  [{i}/{total}] {call_number} {title}: WARNING image download failed: {exc}", flush=True)
            image_path = ""

        ready_rows.append(
            {
                "call_number": call_number,
                "title": title,
                "description": description,
                "tags": tags,
                "image_path": str(image_path) if image_path else "",
            }
        )
        state_mod.set_status(state, h, "queued", batch=batch_id, call_number=call_number)

    write_csv(batch_dir / "import.csv", LIBIB_MOVIE_COLUMNS, import_rows)
    write_csv(batch_dir / "ready.csv", ["call_number", "title", "description", "tags", "image_path"], ready_rows)
    state_mod.save_state(SYNC_DIR, state)

    print(f"{batch_id}: {len(queued)} handles prepared.")
    print(f"  {batch_dir / 'import.csv'} -- upload via Add Items -> CSV, Force Import Mode on")
    print(f"  {batch_dir / 'ready.csv'} -- input for `sync` once imported")
    print(f"Next: manually import {batch_dir / 'import.csv'}, then:")
    print(f"  python3 formatting-scripts/libib_sync.py mark-imported {batch_id}")


# ------------------------------------------------------ reverify-posters --


def cmd_reverify_posters(args):
    by_handle = load_shopify_by_handle(args.shopify)
    state = state_mod.load_state(SYNC_DIR)

    targets = [
        h for h, info in state.items()
        if info["status"] == "done" and not info.get("poster_confirmed") and h in by_handle
    ]
    if not targets:
        print("Nothing to reverify -- every 'done' handle already has a confirmed poster.")
        return

    batch_id = next_batch_id(SYNC_DIR)
    batch_dir = SYNC_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    total = len(targets)
    print(f"{batch_id}: reverifying posters for {total} handles...", flush=True)

    ready_rows = []
    ok_count, fail_count = 0, 0
    for i, h in enumerate(targets, 1):
        srow = by_handle[h]
        call_number = srow.get("Variant Barcode", "").strip()
        title = fields.expected_title(srow)
        description = fields.expected_description(srow)
        tags = fields.expected_tags_string(srow)

        img_url = srow.get("Image Src", "").strip()
        ext = img_url.split("?")[0].split(".")[-1]
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        image_path = batch_dir / f"{call_number}.{ext}"
        try:
            urllib.request.urlretrieve(img_url, image_path)
            ok_count += 1
            print(f"  [{i}/{total}] {call_number} {title}: image ok", flush=True)
        except Exception as exc:
            fail_count += 1
            print(f"  [{i}/{total}] {call_number} {title}: WARNING image download failed: {exc}", flush=True)
            image_path = ""

        ready_rows.append(
            {
                "call_number": call_number,
                "title": title,
                "description": description,
                "tags": tags,
                "image_path": str(image_path) if image_path else "",
            }
        )
        state_mod.set_status(state, h, "done", batch=batch_id, call_number=call_number)

    write_csv(batch_dir / "ready.csv", ["call_number", "title", "description", "tags", "image_path"], ready_rows)
    state_mod.save_state(SYNC_DIR, state)

    print(f"\n{batch_id}: {ok_count} images downloaded, {fail_count} failed.")
    print(f"  {batch_dir / 'ready.csv'} -- input for `sync`")
    print(f"Next: python3 formatting-scripts/libib_sync.py sync {batch_id}")


# ---------------------------------------------------------- mark-imported --


def cmd_mark_imported(args):
    state = state_mod.load_state(SYNC_DIR)
    handles = [h for h, info in state.items() if info.get("batch") == args.batch_id and info["status"] == "queued"]
    if not handles:
        print(f"No handles in {args.batch_id} are waiting to be marked imported.")
        return
    for h in handles:
        state_mod.set_status(state, h, "imported", batch=args.batch_id, call_number=state[h]["call_number"])
    state_mod.save_state(SYNC_DIR, state)
    print(f"{len(handles)} handles in {args.batch_id} marked imported.")
    print(f"Next: python3 formatting-scripts/libib_sync.py sync {args.batch_id}")


# ----------------------------------------------------------------- sync ----


def cmd_sync(args):
    batch_dir = SYNC_DIR / args.batch_id
    ready_path = batch_dir / "ready.csv"
    if not ready_path.exists():
        sys.exit(f"{ready_path} does not exist -- run `prepare` first.")

    cmd = [sys.executable, str(SCRIPT_DIR / "libib_sync_fix.py"), str(ready_path)]
    if args.headless:
        cmd.append("--headless")
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    subprocess.run(cmd, check=True)

    report_path = ready_path.with_suffix(".sync-report.csv")
    state = state_mod.load_state(SYNC_DIR)
    call_to_handle = {info["call_number"]: h for h, info in state.items() if info.get("batch") == args.batch_id}

    resolved, review = [], []
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h = call_to_handle.get(row["call_number"])
            if not h:
                continue
            ok = row["barcode_status"] != "error" and row["content_status"] != "error"
            (resolved if ok else review).append(h)
            if ok and row["content_status"] == "updated" and "poster" in row.get("message", ""):
                state_mod.set_status(state, h, "imported", poster_confirmed=True)

    for h in resolved:
        state[h]["status"] = "imported"
    for h in review:
        state_mod.set_status(state, h, "needs-review", note="sync_fix reported an error, see sync-report.csv")

    state_mod.save_state(SYNC_DIR, state)
    print(f"\n{len(resolved)} handles synced ok, {len(review)} need review (see {report_path}).")
    print("Next: fresh Libib export, then:")
    print("  python3 formatting-scripts/libib_sync.py verify --shopify ... --libib-barcode ... --libib-collection ...")


# ---------------------------------------------------------------- verify ----


def cmd_verify(args):
    by_handle = load_shopify_by_handle(args.shopify)
    barcode_rows = {r["call_number"].strip(): r for r in csv.DictReader(open(args.libib_barcode, newline="", encoding="utf-8"))}
    collection_by_id = {r["id"]: r for r in csv.DictReader(open(args.libib_collection, newline="", encoding="utf-8"))}

    state = state_mod.load_state(SYNC_DIR)
    pending = [h for h, info in state.items() if info["status"] == "imported"]

    promoted, missing, retry = 0, 0, 0
    for h in pending:
        info = state[h]
        cn = info["call_number"]
        srow = by_handle.get(h)
        brow = barcode_rows.get(cn)

        if not brow or not srow:
            # Genuinely never landed in Libib at all (e.g. the CSV import
            # silently dropped this row) -- safe to fully re-queue for a
            # fresh import, since there's no existing item to duplicate.
            del state[h]
            missing += 1
            continue

        coll = collection_by_id.get(brow["id"], {})
        problems = []
        if fields.norm_ws(brow["title"]) != fields.expected_title(srow):
            problems.append("title")
        if fields.norm_ws(coll.get("description", "")) != fields.expected_description(srow):
            problems.append("description")
        if fields.normalized_tag_set(brow.get("tags", "")) != fields.normalized_tag_set(fields.expected_tags_string(srow)):
            problems.append("tags")
        if brow["barcode"].strip() != cn:
            problems.append("barcode")

        if not problems:
            state_mod.set_status(state, h, "done", call_number=cn, poster_confirmed=info.get("poster_confirmed", True))
            promoted += 1
        else:
            # It's already a real item in Libib -- re-importing would
            # create a duplicate, not fix it. Leave status "imported" (and
            # keep its `batch`) so a re-run of `sync <batch>` retries the
            # fix in place via search-and-edit, not a fresh CSV import.
            state_mod.set_status(state, h, "imported", call_number=cn, note=f"retry needed: {', '.join(problems)}")
            retry += 1

    state_mod.save_state(SYNC_DIR, state)
    print(f"{promoted} promoted to done, {missing} never landed (back in the eligible pool), {retry} present but wrong -- re-run `sync` on their batch to retry.")


# ---------------------------------------------------------------- status ----


def cmd_status(args):
    state = state_mod.load_state(SYNC_DIR)
    if not state:
        print("No handles tracked yet.")
        return
    for status_name, count in state_mod.counts_by_status(state).items():
        print(f"{status_name}: {count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Compare everything in Libib against Shopify")
    p_audit.add_argument("--shopify", required=True)
    p_audit.add_argument("--libib-barcode", required=True)
    p_audit.add_argument("--libib-collection", required=True)
    p_audit.set_defaults(func=cmd_audit)

    p_queue = sub.add_parser("queue", help="Pick the next batch of eligible handles")
    p_queue.add_argument("--shopify", required=True)
    p_queue.add_argument("--size", type=int, default=200)
    p_queue.set_defaults(func=cmd_queue)

    p_prepare = sub.add_parser("prepare", help="Build the import CSV + download posters for queued handles")
    p_prepare.add_argument("--shopify", required=True)
    p_prepare.set_defaults(func=cmd_prepare)

    p_marked = sub.add_parser("mark-imported", help="Confirm a batch's CSV was manually force-imported")
    p_marked.add_argument("batch_id")
    p_marked.set_defaults(func=cmd_mark_imported)

    p_sync = sub.add_parser("sync", help="Run libib_sync_fix.py against an imported batch")
    p_sync.add_argument("batch_id")
    p_sync.add_argument("--headless", action="store_true")
    p_sync.add_argument("--limit", type=int, default=None)
    p_sync.set_defaults(func=cmd_sync)

    p_verify = sub.add_parser("verify", help="Confirm imported handles are really in Libib and correct")
    p_verify.add_argument("--shopify", required=True)
    p_verify.add_argument("--libib-barcode", required=True)
    p_verify.add_argument("--libib-collection", required=True)
    p_verify.set_defaults(func=cmd_verify)

    p_reverify = sub.add_parser("reverify-posters", help="Re-download + re-sync posters for 'done' handles never confirmed by our own script")
    p_reverify.add_argument("--shopify", required=True)
    p_reverify.set_defaults(func=cmd_reverify_posters)

    p_status = sub.add_parser("status", help="Show handle counts per state")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
