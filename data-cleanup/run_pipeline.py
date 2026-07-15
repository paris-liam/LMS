"""One-command, idempotent movie-catalogue pipeline: reformat, then TMDB
fill + review picker, safe to re-run on its own output.

Stage 1 classifies every product by CONTENT (is the genre metafield filled?)
rather than row shape, so already-reformatted products pass through untouched,
raw resale ("Genre" option) and CircaOS ("Condition" option) products get the
existing transforms, and reformatted products with an empty genre metafield
get a recovery attempt from their Tags before being flagged for review.

Stage 2 runs the TMDB fill and review-picker generation in-process on
stage 1's output (skipped with --skip-tmdb or when TMDB_API_KEY is unset).

See docs/superpowers/specs/2026-07-15-idempotent-pipeline-design.md.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import tmdb_fill
import tmdb_review_page
from catalog_common import add_tags, group_rows_by_handle, has_tag, load_export, remove_tag, write_csv
from circaos_reformat import extract_genre_from_tags, resolve_circaos_format, transform_circaos_group
from reformat_movies import (
    FIXED_CATEGORY,
    FIXED_VENDOR,
    FORMAT_COLUMN,
    GENRE_COLUMN,
    transform_group,
)

NEEDS_REVIEW_TAG = "Needs Review"

NO_LOG = lambda message: None


def _review_passthrough(handle, group, reason, log_fn):
    """Pass a product through unchanged apart from ensuring the Needs Review
    tag, and report whether the flag is new or pre-existing."""
    first = group[0]
    already_flagged = has_tag(first.get("Tags", ""), NEEDS_REVIEW_TAG)

    out_rows = []
    for i, row in enumerate(group):
        new_row = dict(row)
        if i == 0 and not already_flagged:
            new_row["Tags"] = add_tags(row.get("Tags", ""), [NEEDS_REVIEW_TAG])
        out_rows.append(new_row)

    status = "still-flagged" if already_flagged else "new"
    bucket = "flagged-still" if already_flagged else "flagged-new"
    if already_flagged:
        log_fn(f"[{handle}] still flagged: {reason}")
    else:
        log_fn(f"[{handle}] flagged: {reason}")
    review_entry = {
        "Handle": handle,
        "Title": first.get("Title", ""),
        "Reason": reason,
        "Status": status,
    }
    return out_rows, review_entry, bucket


def process_group(handle, group, log_fn=NO_LOG):
    """Classify + transform one product's rows.

    Returns (bucket, out_rows, review_entry_or_None) where bucket is one of:
    "plan", "resale", "circaos", "done", "resolved", "recovered",
    "flagged-new", "flagged-still".
    """
    first = group[0]
    option1_name = first.get("Option1 Name", "").strip()

    if first.get("Type", "").strip() == "Supercycle Plan":
        return "plan", [dict(r) for r in group], None

    if option1_name == "Genre":
        status, transformed, reason = transform_group(group)
        if status == "in_scope":
            transformed[0]["Tags"] = remove_tag(transformed[0].get("Tags", ""), NEEDS_REVIEW_TAG)
            log_fn(f"[{handle}] reformatted (resale)")
            return "resale", transformed, None
        out_rows, entry, bucket = _review_passthrough(handle, group, reason, log_fn)
        return bucket, out_rows, entry

    if option1_name == "Condition":
        status, products, reason = transform_circaos_group(group)
        if status == "in_scope":
            for product_rows in products:
                product_rows[0]["Tags"] = remove_tag(product_rows[0].get("Tags", ""), NEEDS_REVIEW_TAG)
            out_rows = [row for product_rows in products for row in product_rows]
            copies = f", {len(products)} copies" if len(products) > 1 else ""
            log_fn(f"[{handle}] reformatted (circaos{copies})")
            return "circaos", out_rows, None
        out_rows, entry, bucket = _review_passthrough(handle, group, reason, log_fn)
        return bucket, out_rows, entry

    # Reformatted ("Title") shape — classify by content.
    genre = first.get(GENRE_COLUMN, "").strip()
    tags_str = first.get("Tags", "")

    if genre:
        if has_tag(tags_str, NEEDS_REVIEW_TAG):
            out_rows = [dict(r) for r in group]
            out_rows[0]["Tags"] = remove_tag(tags_str, NEEDS_REVIEW_TAG)
            log_fn(f"[{handle}] resolved: genre is filled, removed '{NEEDS_REVIEW_TAG}' tag")
            return "resolved", out_rows, None
        return "done", [dict(r) for r in group], None

    recovered_genre = extract_genre_from_tags(tags_str)
    if recovered_genre is not None:
        out_rows = [dict(r) for r in group]
        primary = out_rows[0]
        primary[GENRE_COLUMN] = recovered_genre
        if not primary.get(FORMAT_COLUMN, "").strip():
            fmt = resolve_circaos_format(
                first.get("Vendor", "").strip(),
                tags_str,
                first.get("Variant Barcode", "").strip(),
            )
            primary[FORMAT_COLUMN] = fmt or ""
        primary["Vendor"] = FIXED_VENDOR
        primary["Product Category"] = FIXED_CATEGORY
        primary["Tags"] = remove_tag(tags_str, NEEDS_REVIEW_TAG)
        log_fn(f"[{handle}] recovered genre '{recovered_genre}' from tags")
        return "recovered", out_rows, None

    out_rows, entry, bucket = _review_passthrough(
        handle, group, "no genre metafield and no genre-like tag", log_fn
    )
    return bucket, out_rows, entry


def reformat_rows(rows, fieldnames, log_fn=NO_LOG):
    """Stage 1 over the full export. Returns
    (new_fieldnames, output_rows, review_report_rows, counts)."""
    new_fieldnames = list(fieldnames)
    if FORMAT_COLUMN not in new_fieldnames:
        genre_index = new_fieldnames.index(GENRE_COLUMN)
        new_fieldnames.insert(genre_index + 1, FORMAT_COLUMN)

    counts = {
        "plan": 0,
        "resale": 0,
        "circaos": 0,
        "done": 0,
        "resolved": 0,
        "recovered": 0,
        "flagged-new": 0,
        "flagged-still": 0,
    }
    output_rows = []
    review_report_rows = []
    handle_producers: dict[str, list[str]] = {}
    handle_titles: dict[str, str] = {}

    for handle, group in group_rows_by_handle(rows):
        bucket, out_rows, review_entry = process_group(handle, group, log_fn=log_fn)
        counts[bucket] += 1
        output_rows.extend(out_rows)
        if review_entry is not None:
            review_report_rows.append(review_entry)
        for out_handle in dict.fromkeys(r["Handle"] for r in out_rows):
            handle_producers.setdefault(out_handle, []).append(handle)
            handle_titles.setdefault(out_handle, out_rows[0].get("Title", ""))

    # Two different input products landing on the same output handle would
    # silently merge on Shopify import — flag them instead of hiding it.
    for out_handle, producers in handle_producers.items():
        if len(producers) > 1:
            reason = f"duplicate handle: produced by input products {', '.join(producers)}"
            log_fn(f"[{out_handle}] WARNING {reason}")
            review_report_rows.append({
                "Handle": out_handle,
                "Title": handle_titles.get(out_handle, ""),
                "Reason": reason,
                "Status": "duplicate",
            })
            counts["duplicate-handle"] = counts.get("duplicate-handle", 0) + 1

    return new_fieldnames, output_rows, review_report_rows, counts


def run(
    input_path,
    outdir,
    skip_tmdb=False,
    api_key=None,
    fetch_fn=None,
    sleep_fn=time.sleep,
    log_fn=NO_LOG,
    progress_fn=None,
) -> dict:
    outdir = Path(outdir)

    log_fn(f"== Stage 1: reformat == ({input_path})")
    fieldnames, rows = load_export(input_path)
    new_fieldnames, output_rows, review_report_rows, counts = reformat_rows(
        rows, fieldnames, log_fn=log_fn
    )

    reformatted_path = outdir / "reformatted.csv"
    write_csv(reformatted_path, new_fieldnames, output_rows)
    write_csv(
        outdir / "reformat-review.csv",
        ["Handle", "Title", "Reason", "Status"],
        review_report_rows,
    )
    log_fn(
        f"Stage 1 done: {counts['resale']} resale + {counts['circaos']} circaos reformatted, "
        f"{counts['recovered']} recovered, {counts['resolved']} resolved, "
        f"{counts['flagged-new']} newly flagged, {counts['flagged-still']} still flagged, "
        f"{counts['done']} already done, {counts['plan']} plan(s) passed through"
    )
    if counts.get("duplicate-handle"):
        log_fn(
            f"WARNING: {counts['duplicate-handle']} duplicate output handle(s) — "
            "these would merge on Shopify import; see reformat-review.csv (Status: duplicate)"
        )
    log_fn(f"  -> {reformatted_path}")
    log_fn(f"  -> {outdir / 'reformat-review.csv'}")

    result = {"reformat": counts, "tmdb": None, "picker": None}

    if skip_tmdb:
        log_fn("== Stage 2: TMDB fill == skipped (--skip-tmdb); upload file is reformatted.csv")
        return result
    if fetch_fn is None and not api_key:
        log_fn("== Stage 2: TMDB fill == skipped (TMDB_API_KEY not set); upload file is reformatted.csv")
        return result

    log_fn(f"== Stage 2: TMDB fill == ({reformatted_path})")
    tmdb_counts = tmdb_fill.run(
        reformatted_path, outdir, api_key,
        fetch_fn=fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn,
    )
    result["tmdb"] = tmdb_counts
    log_fn(
        f"Stage 2 done: {tmdb_counts['filled']} rows written, "
        f"{tmdb_counts['changed']} changed, {tmdb_counts['review']} for review"
    )
    log_fn(f"  -> {outdir / 'tmdb-filled.csv'} (upload file)")

    if tmdb_counts["review"]:
        log_fn(f"== Stage 3: review picker == ({tmdb_counts['review']} products)")
        picker_counts = tmdb_review_page.run(
            outdir / "tmdb-needs-review.csv", outdir, api_key,
            fetch_fn=fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn,
        )
        result["picker"] = picker_counts
        log_fn(f"  -> {outdir / 'tmdb-review-picker.html'}")
    else:
        log_fn("== Stage 3: review picker == skipped (nothing needs review)")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run the idempotent catalogue pipeline: reformat, TMDB fill, review picker."
    )
    parser.add_argument("input_csv", help="Path to a Shopify product export CSV")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write output files (default: input file's directory)",
    )
    parser.add_argument(
        "--skip-tmdb",
        action="store_true",
        help="Stop after the reformat stage (no TMDB API calls)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not args.skip_tmdb and not api_key:
        print(
            "Note: TMDB_API_KEY is not set — running the reformat stage only.\n"
            "Set it (or pass --skip-tmdb to silence this note) to include the TMDB fill.",
            file=sys.stderr,
        )

    input_path = Path(args.input_csv)
    outdir = Path(args.outdir) if args.outdir else input_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    result = run(
        input_path, outdir,
        skip_tmdb=args.skip_tmdb,
        api_key=api_key,
        log_fn=lambda message: print(message, flush=True),
        progress_fn=tmdb_fill.print_progress,
    )

    print()
    if result["tmdb"] is None:
        print(f"Upload file: {outdir / 'reformatted.csv'}")
        print(f"Review report: {outdir / 'reformat-review.csv'}")
    else:
        print(f"Upload file: {outdir / 'tmdb-filled.csv'}")
        print(f"Review report: {outdir / 'reformat-review.csv'}")
        if result["picker"] is not None:
            print("Next steps:")
            print(f"  1. Open {outdir / 'tmdb-review-picker.html'} and pick per product")
            print("  2. Export picks (tmdb-picks.json)")
            print(
                f"  3. python3 data-cleanup/apply_review_picks.py tmdb-picks.json "
                f"{outdir / 'tmdb-filled.csv'}"
            )


if __name__ == "__main__":
    main()
