"""One command: normalize a movie CSV, fill it from TMDB, and queue
everything that needs a human in the hosted review picker.

    python3 formatting-scripts/run.py <input.csv>

Writes to out-<inputname>/ beside the input, so re-running on that run's
issues.csv cannot clobber its upload.csv. Every output file is itself a
valid input file: fix the rows, run the same command on the fixed file,
import what comes out.

Ambiguous and unmatched products are no longer written locally
(review-picker.html / tmdb-unmatched.csv) — they're appended straight to
the two evergreen queues in tools/review-picker/ (ambiguous-queue,
unmatched-queue), skipping any handle already queued or resolved there.
The output dir only ever holds issues.csv, upload.csv, run-report.txt, and
the TMDB cache.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import argparse
import sys
import time
from pathlib import Path

import tmdb_fill
from catalog_common import load_export, write_csv
from columns import REASON_COLUMN
from detect import UnknownShapeError, detect_shape, strip_reason
from git_sync import sync_review_picker
from hosted_review_page import append_to_queue
from normalize import normalize_rows, output_columns
from review_registry import load_registry, save_registry
from tmdb_cache import TmdbCache

NO_LOG = lambda message: None

CACHE_FILENAME = ".tmdb-cache.json"
AMBIGUOUS_BATCH_ID = "ambiguous-queue"
UNMATCHED_BATCH_ID = "unmatched-queue"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOLS_DIR = REPO_ROOT / "tools" / "review-picker"


def output_dir_for(input_path) -> Path:
    input_path = Path(input_path)
    return input_path.parent / f"out-{input_path.stem}"


def run(
    input_path,
    outdir=None,
    skip_tmdb=False,
    api_key=None,
    fetch_fn=None,
    sleep_fn=time.sleep,
    log_fn=NO_LOG,
    progress_fn=None,
    no_cache=False,
    tools_dir=None,
) -> dict:
    """Library entry point — never touches git. `tools_dir` defaults to the
    real tools/review-picker, but tests must pass an isolated tmp dir so
    they never write into the actual repo's queue files."""
    input_path = Path(input_path)
    outdir = Path(outdir) if outdir else output_dir_for(input_path)
    outdir.mkdir(parents=True, exist_ok=True)
    tools_dir = Path(tools_dir) if tools_dir else DEFAULT_TOOLS_DIR

    fieldnames, rows = load_export(input_path)
    fieldnames, rows = strip_reason(fieldnames, rows)
    shape = detect_shape(fieldnames)
    log_fn(f"== {input_path.name}: {len(rows)} rows, detected shape: {shape} ==")

    clean_rows, issue_rows = normalize_rows(rows, shape)
    columns = output_columns(shape)

    write_csv(outdir / "issues.csv", [REASON_COLUMN] + fieldnames, issue_rows)
    log_fn(f"Stage 1: {len(clean_rows)} rows normalized, {len(issue_rows)} rows flagged")

    result = {
        "shape": shape,
        "clean": len(clean_rows),
        "issues": len(issue_rows),
        "ambiguous": 0,
        "unmatched": 0,
        "ambiguous_queued": 0,
        "unmatched_queued": 0,
        "outdir": str(outdir),
        "tools_dir": str(tools_dir),
    }

    if skip_tmdb or (fetch_fn is None and not api_key):
        reason = "--skip-tmdb" if skip_tmdb else "TMDB_API_KEY not set"
        log_fn(f"Stage 2: skipped ({reason})")
        write_csv(outdir / "upload.csv", columns, clean_rows)
        _write_report(outdir, input_path, result, log_fn)
        return result

    raw_fetch = fetch_fn or tmdb_fill.make_tmdb_fetcher(api_key)

    if no_cache:
        # Bypass the cache entirely: don't read the existing cache file, don't
        # write to it. The user's existing cache is left exactly as it was.
        cache = None
        cached_fetch = raw_fetch
        cache_status = "bypassed (--no-cache)"
        log_fn("Stage 2: TMDB cache bypassed (--no-cache) — re-fetching everything")
    else:
        cache = TmdbCache(outdir / CACHE_FILENAME)
        cached_fetch = cache.wrap(raw_fetch)
        cache_status = None  # filled in after the fetch below

    filled_rows, review_rows = tmdb_fill.build_output(
        clean_rows, cached_fetch, sleep_fn=sleep_fn,
        progress_fn=progress_fn or (lambda i, t, h, m: None),
    )
    if cache is not None:
        cache.save()
        cache_status = f"{cache.hits} hits, {cache.misses} fetches"

    write_csv(outdir / "upload.csv", columns, filled_rows)

    ambiguous_rows = [r for r in review_rows if r["Kind"] == "ambiguous"]
    unmatched_rows = [r for r in review_rows if r["Kind"] == "unmatched"]
    result["ambiguous"] = len({r["Handle"] for r in ambiguous_rows})
    result["unmatched"] = len({r["Handle"] for r in unmatched_rows})

    log_fn(
        f"Stage 2: {len(filled_rows)} rows written, "
        f"{result['ambiguous']} ambiguous, {result['unmatched']} unmatched "
        f"(cache: {cache_status})"
    )

    if ambiguous_rows or unmatched_rows:
        registry = load_registry(tools_dir)

        ambiguous_result = append_to_queue(
            ambiguous_rows, tools_dir, AMBIGUOUS_BATCH_ID, cached_fetch, registry,
            sleep_fn=sleep_fn, progress_fn=progress_fn or (lambda i, t, h, m: None),
        )
        unmatched_result = append_to_queue(
            unmatched_rows, tools_dir, UNMATCHED_BATCH_ID, cached_fetch, registry,
            sleep_fn=sleep_fn, progress_fn=progress_fn or (lambda i, t, h, m: None),
        )
        save_registry(tools_dir, registry)
        if cache is not None:
            cache.save()

        result["ambiguous_queued"] = ambiguous_result["added"]
        result["unmatched_queued"] = unmatched_result["added"]
        log_fn(
            f"Stage 3: {AMBIGUOUS_BATCH_ID} +{ambiguous_result['added']} "
            f"(total {ambiguous_result['batch_total']}), "
            f"{UNMATCHED_BATCH_ID} +{unmatched_result['added']} "
            f"(total {unmatched_result['batch_total']})"
        )

    _write_report(outdir, input_path, result, log_fn, cache_status=cache_status)
    return result


def _write_report(outdir: Path, input_path: Path, result: dict, log_fn, cache_status=None) -> None:
    lines = [
        f"input:      {input_path}",
        f"shape:      {result['shape']}",
        f"upload.csv: {result['clean']} rows written (products + extra-image rows)",
        f"issues.csv: {result['issues']} rows need a fix",
        f"ambiguous:  {result['ambiguous']} products seen this run, "
        f"{result['ambiguous_queued']} newly queued in {AMBIGUOUS_BATCH_ID}",
        f"unmatched:  {result['unmatched']} products seen this run, "
        f"{result['unmatched_queued']} newly queued in {UNMATCHED_BATCH_ID}",
    ]
    if cache_status is not None:
        lines.append(f"cache:      {cache_status}")
    (outdir / "run-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_fn(f"  -> {outdir}")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize and TMDB-fill a movie CSV for Shopify import."
    )
    parser.add_argument("input_csv", help="Upload-template batch, Shopify export, or a prior output")
    parser.add_argument("--outdir", default=None, help="Override the out-<inputname>/ directory")
    parser.add_argument("--skip-tmdb", action="store_true", help="Stop after normalization")
    parser.add_argument("--no-cache", action="store_true",
                         help="Bypass the TMDB query cache and re-fetch everything")
    parser.add_argument("--tools-dir", default=None,
                         help="Override the tools/review-picker directory (default: repo's own)")
    parser.add_argument("--no-git-sync", action="store_true",
                         help="Don't pull/commit/push tools/review-picker after queuing")
    args = parser.parse_args()

    api_key = "259d3aaf7c2a60737d754042363eb5a6"
    if not args.skip_tmdb and not api_key:
        print("Note: TMDB_API_KEY is not set — running normalization only.", file=sys.stderr)

    try:
        result = run(
            Path(args.input_csv),
            outdir=args.outdir,
            skip_tmdb=args.skip_tmdb,
            api_key=api_key,
            log_fn=lambda message: print(message, flush=True),
            progress_fn=tmdb_fill.print_progress,
            no_cache=args.no_cache,
            tools_dir=args.tools_dir,
        )
    except UnknownShapeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(result["outdir"])
    print()
    print(f"Import this:  {outdir / 'upload.csv'}")
    if result["issues"]:
        print(f"Fix and re-run: {outdir / 'issues.csv'} "
              f"({result['issues']} rows) — python3 formatting-scripts/run.py {outdir / 'issues.csv'}")
    if result["ambiguous_queued"]:
        print(f"Queued for review: {result['ambiguous_queued']} product(s) in {AMBIGUOUS_BATCH_ID}")
    if result["unmatched_queued"]:
        print(f"Queued for review: {result['unmatched_queued']} product(s) in {UNMATCHED_BATCH_ID}")
    print()
    print("After importing: run scripts/set-movie-template.sh so movies use the movie template.")

    newly_queued = result["ambiguous_queued"] + result["unmatched_queued"]
    if newly_queued and not args.no_git_sync:
        tools_dir = Path(result["tools_dir"]).resolve()
        try:
            tools_dir_rel = str(tools_dir.relative_to(REPO_ROOT))
        except ValueError:
            print(
                f"Note: {tools_dir} is outside the repo ({REPO_ROOT}) — skipping git sync.",
                file=sys.stderr,
            )
            return
        message = (
            f"review-picker: +{result['ambiguous_queued']} ambiguous, "
            f"+{result['unmatched_queued']} unmatched (from {Path(args.input_csv).name})"
        )
        sync_result = sync_review_picker(
            REPO_ROOT, tools_dir_rel, message,
            log_fn=lambda m: print(m, flush=True),
        )
        if not sync_result["synced"] and sync_result["reason"] not in ("nothing to commit",):
            print(
                f"Note: {tools_dir_rel} was updated locally but not pushed "
                f"({sync_result['reason']}) — commit and push it yourself when ready.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
