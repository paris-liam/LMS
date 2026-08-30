"""Best-effort formatter for an issue-category CSV where exactly one field
is known to be unresolvable across the whole file (no media format, no
usable genre, or a rental with a stray price). Everything else is resolved
normally and the row still goes through TMDB fill, same as run.py — a row
only lands in leftover-issues.csv if it fails for a *different* reason than
the one this batch is known for.

    python3 formatting-scripts/format_issue_batch.py <input_csv> --skip format --tags Issue,Needs-Format
    python3 formatting-scripts/format_issue_batch.py <input_csv> --skip genre --tags Issue,Genre-needed
    python3 formatting-scripts/format_issue_batch.py <input_csv> --zero-price-rental

Writes to out-<inputname>/, same shape as run.py's output: upload.csv,
issues.csv (leftover), tmdb-unmatched.csv, review-picker.html, run-report.txt.
"""

import argparse
import sys
import time
from pathlib import Path

from catalog_common import group_rows_by_handle, load_export, write_csv
from columns import EXPORT_COLUMNS, FIXED_VALUES, FORMATTED_TAG, GENRE_METAFIELD, REASON_COLUMN
from detect import strip_reason
from normalize import _flag, _image_row, _is_variant_row, _blank_row
from resolve import extra_tags, resolve_format, resolve_genres, resolve_price, resolve_type, split_list
from taxonomy import genre_handle
import tmdb_fill
from review_page import write_picker
from tmdb_cache import TmdbCache

CACHE_FILENAME = ".tmdb-cache.json"


def resolve_partial(
    primary: dict, skip_fields: set[str], force_price_zero: bool
) -> tuple[dict | None, str | None]:
    """Resolve one row, skipping only the fields this batch is known to be
    missing. Any other resolution failure still returns a reason — this is
    a best-effort fill, not a bypass of every check.

    Price validation is fundamentally a function of type (Rental must be 0,
    Floor Sale must be > 0) — resolve_price(None, ...) would silently fall
    into its Floor-Sale branch and misvalidate every row, so skipping type
    always skips price validation too: the raw price passes through
    untouched rather than being checked against the wrong rule.
    """
    tags = split_list(primary.get("Tags", ""))
    option1_value = (primary.get("Option1 Value") or "").strip()

    product_type, type_reason = resolve_type(tags)
    type_known = type_reason is None
    if type_reason and "type" not in skip_fields:
        return None, type_reason

    media_format, format_reason = resolve_format(primary.get("Vendor", ""), option1_value, tags, "")
    format_known = format_reason is None
    if format_reason and "format" not in skip_fields:
        return None, format_reason

    genres, genre_reason = resolve_genres(option1_value, tags, [])
    if genre_reason and "genre" not in skip_fields:
        return None, genre_reason
    if genre_reason:
        genres = []

    if not type_known:
        # Can't validate a price against an unknown type — pass it through
        # exactly as found, for a person to set correctly once type is known.
        price = (primary.get("Variant Price") or "").strip()
    elif force_price_zero:
        price = "0"
    else:
        price, price_reason = resolve_price(product_type, primary.get("Variant Price", ""))
        if price_reason:
            return None, price_reason

    return {
        "type": product_type,
        "type_known": type_known,
        "format": media_format,
        "format_known": format_known,
        "raw_vendor": (primary.get("Vendor") or "").strip(),
        "genres": genres,
        "price": price,
        "extras": extra_tags(tags),
        # Only true if the row actually needed a fallback — a row that
        # resolves fine despite being in this batch (e.g. a typo fixed since
        # the batch was split out) shouldn't get tagged as still broken.
        # Forcing the price counts too: it means resolve_price was bypassed
        # rather than actually validated.
        "skip_triggered": bool(type_reason) or bool(format_reason) or bool(genre_reason) or force_price_zero,
    }, None


def build_row_partial(primary: dict, resolved: dict, handle: str, extra_issue_tags: list[str]) -> dict:
    out = _blank_row("export")
    out.update(FIXED_VALUES)

    title = (primary.get("Title") or "").strip()
    image_src = (primary.get("Image Src") or "").strip()
    alt_text = (primary.get("Image Alt Text") or "").strip()

    out["Handle"] = handle
    out["Title"] = title
    out["Body (HTML)"] = primary.get("Body (HTML)", "") or ""
    out["Vendor"] = resolved["format"] if resolved["format_known"] else resolved["raw_vendor"]

    tag_parts = []
    if resolved["type_known"]:
        tag_parts.append(resolved["type"])
    if resolved["format_known"]:
        tag_parts.append(resolved["format"])
    tag_parts += resolved["genres"] + resolved["extras"] + [FORMATTED_TAG]
    if resolved["skip_triggered"]:
        tag_parts += extra_issue_tags
    out["Tags"] = ", ".join(tag_parts)

    out["Option1 Value"] = resolved["genres"][0] if resolved["genres"] else ""
    out["Variant Price"] = resolved["price"]
    out["Image Src"] = image_src
    out["Image Alt Text"] = alt_text or (f"{title} poster" if image_src else "")
    out[GENRE_METAFIELD] = "; ".join(h for h in (genre_handle(g) for g in resolved["genres"]) if h)
    out["Variant Barcode"] = (primary.get("Variant Barcode") or "").strip()
    out["Image Position"] = (primary.get("Image Position") or "").strip()
    return out


def normalize_partial(
    rows: list[dict], skip_fields: set[str], force_price_zero: bool, extra_issue_tags: list[str]
) -> tuple[list[dict], list[dict]]:
    clean_rows: list[dict] = []
    issue_rows: list[dict] = []
    produced: dict[str, list[dict]] = {}

    for handle, group in group_rows_by_handle(rows):
        primary = group[0]

        variant_rows = [row for row in group if _is_variant_row(row)]
        if len(variant_rows) > 1:
            issue_rows.extend(_flag(group, f"product has {len(variant_rows)} variants"))
            continue

        resolved, reason = resolve_partial(primary, skip_fields, force_price_zero)
        if reason:
            issue_rows.extend(_flag(group, reason))
            continue

        product_rows = [build_row_partial(primary, resolved, handle, extra_issue_tags)]
        product_rows += [_image_row(row, "export") for row in group[1:]]
        produced.setdefault(handle, []).append({"group": group, "rows": product_rows})

    for out_handle, entries in produced.items():
        if len(entries) > 1:
            reason = f"duplicate handle {out_handle} — produced by {len(entries)} input products"
            for entry in entries:
                issue_rows.extend(_flag(entry["group"], reason))
        else:
            clean_rows.extend(entries[0]["rows"])

    return clean_rows, issue_rows


def run(
    input_path, skip_fields, force_price_zero, extra_issue_tags, outdir=None,
    api_key=None, fetch_fn=None, sleep_fn=time.sleep, log_fn=lambda m: None,
    progress_fn=None,
) -> dict:
    input_path = Path(input_path)
    outdir = Path(outdir) if outdir else input_path.parent / f"out-{input_path.stem}"
    outdir.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = load_export(input_path)
    fieldnames, rows = strip_reason(fieldnames, rows)

    clean_rows, issue_rows = normalize_partial(rows, skip_fields, force_price_zero, extra_issue_tags)
    log_fn(f"Stage 1: {len(clean_rows)} rows normalized, {len(issue_rows)} rows still broken")
    write_csv(outdir / "issues.csv", [REASON_COLUMN] + fieldnames, issue_rows)

    result = {"clean": len(clean_rows), "issues": len(issue_rows), "ambiguous": 0, "unmatched": 0, "outdir": str(outdir)}

    raw_fetch = fetch_fn or tmdb_fill.make_tmdb_fetcher(api_key)
    cache = TmdbCache(outdir / CACHE_FILENAME)
    cached_fetch = cache.wrap(raw_fetch)

    filled_rows, review_rows = tmdb_fill.build_output(
        clean_rows, cached_fetch, sleep_fn=sleep_fn,
        progress_fn=progress_fn or (lambda i, t, h, m: None),
    )
    cache.save()

    write_csv(outdir / "upload.csv", EXPORT_COLUMNS, filled_rows)

    by_handle = {}
    for row in filled_rows:
        by_handle.setdefault(row.get("Handle", ""), row)
    seen = set()
    unmatched_order = []
    for entry in review_rows:
        if entry["Kind"] != "unmatched" or entry["Handle"] not in by_handle or entry["Handle"] in seen:
            continue
        seen.add(entry["Handle"])
        unmatched_order.append(entry["Handle"])
    unmatched = [{c: by_handle[h].get(c, "") for c in EXPORT_COLUMNS} for h in unmatched_order]
    write_csv(outdir / "tmdb-unmatched.csv", EXPORT_COLUMNS, unmatched)

    ambiguous = [entry for entry in review_rows if entry["Kind"] == "ambiguous"]
    result["ambiguous"] = len({entry["Handle"] for entry in ambiguous})
    result["unmatched"] = len(unmatched)

    log_fn(f"Stage 2: {len(filled_rows)} rows written, {result['ambiguous']} ambiguous, {result['unmatched']} unmatched")

    if ambiguous:
        write_picker(ambiguous, outdir, cached_fetch, sleep_fn=sleep_fn,
                     progress_fn=progress_fn or (lambda i, t, h, m: None))
        cache.save()
        log_fn(f"Stage 3: picker page for {result['ambiguous']} products")

    lines = [
        f"input:      {input_path}",
        f"skip:       {', '.join(sorted(skip_fields)) or '(none)'}",
        f"force_price_zero: {force_price_zero}",
        f"tags added: {', '.join(extra_issue_tags) or '(none)'}",
        f"upload.csv: {result['clean']} rows written",
        f"issues.csv: {result['issues']} rows still broken",
        f"ambiguous:  {result['ambiguous']} products in review-picker.html",
        f"unmatched:  {result['unmatched']} products in tmdb-unmatched.csv",
    ]
    (outdir / "run-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_fn(f"  -> {outdir}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_csv")
    parser.add_argument("--skip", default="",
                         help="Comma-separated fields this batch is known to be missing "
                              "(type, format, genre) — filled with a placeholder/left blank "
                              "instead of blocking the row. Skipping type also skips price "
                              "validation (price can't be validated against an unknown type), "
                              "passing the raw price through untouched.")
    parser.add_argument("--zero-price-rental", action="store_true",
                         help="Force Variant Price to 0 instead of blocking on a Rental with a nonzero price")
    parser.add_argument("--tags", default="", help="Comma-separated extra tags to add, e.g. Issue,Needs-Format")
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()

    skip_fields = {f.strip() for f in args.skip.split(",") if f.strip()}
    unknown = skip_fields - {"type", "format", "genre"}
    if unknown:
        parser.error(f"--skip: unknown field(s) {', '.join(sorted(unknown))} (expected type, format, genre)")
    extra_tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    api_key = "259d3aaf7c2a60737d754042363eb5a6"

    result = run(
        Path(args.input_csv), skip_fields, args.zero_price_rental, extra_tags_list,
        outdir=args.outdir, api_key=api_key,
        log_fn=lambda m: print(m, flush=True),
        progress_fn=tmdb_fill.print_progress,
    )

    outdir = Path(result["outdir"])
    print()
    print(f"Import this:  {outdir / 'upload.csv'}")
    if result["issues"]:
        print(f"Still broken: {outdir / 'issues.csv'} ({result['issues']} rows)")
    if result["ambiguous"]:
        print(f"Pick posters: open {outdir / 'review-picker.html'}, export picks, then")
        print(f"  python3 formatting-scripts/apply_picks.py {outdir / 'tmdb-picks.json'} {outdir / 'upload.csv'}")
    if result["unmatched"]:
        print(f"Fill by hand: {outdir / 'tmdb-unmatched.csv'} ({result['unmatched']} products)")


if __name__ == "__main__":
    main()
