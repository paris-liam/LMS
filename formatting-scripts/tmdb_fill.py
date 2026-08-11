"""Fill missing product images/descriptions from TMDB (The Movie Database).

See docs/superpowers/specs/2026-07-14-tmdb-image-description-fill-design.md.
"""

import argparse
import difflib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from catalog_common import add_tags, group_rows_by_handle, has_tag, load_export, write_csv

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

MATCH_THRESHOLD = 0.9
SHORT_DESCRIPTION_LENGTH = 40
REQUEST_DELAY_SECONDS = 0.25
CIRCAOS_IMPORT_TAG = "CircaOS Import"
TMDB_FILLED_TAG = "TMDB Filled"
NEEDS_DATA_TAG = "needs data"

YEAR_PATTERN = re.compile(r"\(\s*(\d{4})\s*\)\s*$")

# Packaging/edition noise that isn't part of the movie's real title.
# Wrapped (bracketed/parenthesized) forms are listed before their bare form
# so both "(Remastered)" and a bare trailing "Remastered" get stripped.
NOISE_PATTERNS = [
    r"\[\s*Steelbook\s*\]",
    r"\(\s*Free Gift\s*\)",
    r"\(\s*Remastered\s*\)",
    r"\bRemastered\b",
    r"\(\s*Director'?s Cut\s*\)",
    r"\bDirector'?s Cut\b",
    r"\(\s*Special Edition\s*\)",
    r"\bSpecial Edition\b",
    r"\(\s*Collector'?s Edition\s*\)",
    r"\bCollector'?s Edition\b",
    r"\(\s*Anniversary Edition\s*\)",
    r"\bAnniversary Edition\b",
    r"\(\s*Extended Cut\s*\)",
    r"\bExtended Cut\b",
    r"\bWidescreen Set\b",
    r"\bFull Screen\b",
    r"\bUncut\b",
    r"\bUnrated\b",
]


def clean_title_and_year(title: str) -> tuple[str, int | None]:
    """Strip a trailing "(YYYY)" year and known packaging/edition noise from a title."""
    year = None
    match = YEAR_PATTERN.search(title)
    if match:
        year = int(match.group(1))
        title = title[: match.start()]

    for pattern in NOISE_PATTERNS:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)

    title = re.sub(r"\s+", " ", title).strip()
    return title, year


def normalize_title(title: str) -> str:
    """Lowercase and strip everything but letters/digits, for fuzzy comparison."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def search_tmdb(fetch_fn, title: str, year: int | None) -> list[dict]:
    """Search TMDB for a title, falling back to a year-less search if a
    year-filtered search returns nothing (old VHS/DVD release-year metadata
    is often off by a year from TMDB's theatrical date)."""
    data = fetch_fn(title, year)
    results = data.get("results", [])
    if not results and year is not None:
        data = fetch_fn(title, None)
        results = data.get("results", [])
    return results


def find_best_match(clean_title: str, results: list[dict]) -> tuple[dict | None, bool]:
    """Return (top_result_or_None, is_confident) for a TMDB search's results list."""
    if not results:
        return None, False
    best = results[0]
    score = title_similarity(clean_title, best.get("title", ""))
    return best, score >= MATCH_THRESHOLD


def strip_html(text: str | None) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def needs_image(group: list[dict]) -> bool:
    return not any(r.get("Image Src", "").strip() for r in group)


def needs_description(group: list[dict]) -> bool:
    text = strip_html(group[0].get("Body (HTML)", ""))
    return len(text) < SHORT_DESCRIPTION_LENGTH


def has_circaos_tag(group: list[dict]) -> bool:
    """CircaOS-imported products carry descriptions known to be wrong, so
    they get a TMDB description refresh even when one is present — but only
    until a fill lands (see TMDB_FILLED_TAG in build_output)."""
    return has_tag(group[0].get("Tags", ""), CIRCAOS_IMPORT_TAG)


def build_output(
    rows: list[dict],
    fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, handle, message: None,
) -> tuple[list[dict], list[dict]]:
    """Fill missing Image Src / Body (HTML) fields via TMDB, per product handle.

    Returns (output_rows, review_rows). output_rows preserves every input
    row's original order; only a primary row's Image Src/Body (HTML) are
    ever modified, and only for the field(s) it actually needed.

    progress_fn(index, total, handle, message) is called once per product
    handle (1-indexed, total = number of distinct handles), after that
    handle has been fully processed, with a short human-readable outcome.
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    groups = group_rows_by_handle(rows)
    total = len(groups)

    for index, (handle, group) in enumerate(groups, start=1):
        primary_tags = group[0].get("Tags", "")
        if has_tag(primary_tags, NEEDS_DATA_TAG):
            output_rows.extend(group)
            progress_fn(index, total, handle, "skipped (needs data)")
            continue

        force_refresh = has_circaos_tag(group) and not has_tag(primary_tags, TMDB_FILLED_TAG)
        need_img = needs_image(group)
        need_desc = needs_description(group) or force_refresh

        if not need_img and not need_desc:
            output_rows.extend(group)
            progress_fn(index, total, handle, "already complete, skipped")
            continue

        primary = dict(group[0])
        title = primary.get("Title", "").strip() or handle
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review_rows.append({
                "Handle": handle,
                "Title": title,
                "Reason": f"TMDB request failed: {exc}",
            })
            output_rows.extend(group)
            progress_fn(index, total, handle, f"review: TMDB request failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)

        if not results:
            review_rows.append({"Handle": handle, "Title": title, "Reason": "no TMDB match"})
            output_rows.extend(group)
            progress_fn(index, total, handle, "review: no TMDB match")
            continue

        best, confident = find_best_match(clean_title, results)
        if not confident:
            best_title = best.get("title", "?")
            best_year = (best.get("release_date") or "")[:4] or "?"
            review_rows.append({
                "Handle": handle,
                "Title": title,
                "Reason": f"ambiguous match (best candidate: '{best_title}' ({best_year}))",
            })
            output_rows.extend(group)
            progress_fn(index, total, handle, f"review: ambiguous match (best candidate: '{best_title}' ({best_year}))")
            continue

        filled = []
        flagged = []

        if need_img:
            poster_path = best.get("poster_path")
            if poster_path:
                primary["Image Src"] = f"{POSTER_BASE_URL}{poster_path}"
                filled.append("image")
            else:
                review_rows.append({
                    "Handle": handle,
                    "Title": title,
                    "Reason": "matched but no TMDB poster",
                })
                flagged.append("no poster")

        if need_desc:
            overview = (best.get("overview") or "").strip()
            if overview:
                primary["Body (HTML)"] = f"<p>{overview}</p>"
                filled.append("description")
            else:
                review_rows.append({
                    "Handle": handle,
                    "Title": title,
                    "Reason": "matched but no TMDB overview",
                })
                flagged.append("no overview")

        if filled:
            primary["Tags"] = add_tags(primary.get("Tags"), [TMDB_FILLED_TAG])

        output_rows.append(primary)
        output_rows.extend(group[1:])

        message_parts = []
        if filled:
            message_parts.append(f"filled {', '.join(filled)}")
        if flagged:
            message_parts.append(f"review: {', '.join(flagged)}")
        progress_fn(index, total, handle, "; ".join(message_parts) if message_parts else "matched")

    return output_rows, review_rows


def make_tmdb_fetcher(api_key: str):
    """Build a real, network-hitting fetch_fn(query, year) -> dict for TMDB search."""

    def fetch(query: str, year: int | None) -> dict:
        params = {"api_key": api_key, "query": query}
        if year is not None:
            params["primary_release_year"] = year
        url = f"{TMDB_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    return fetch


def build_changes_html(changed_pairs: list[tuple[dict, dict]]) -> str:
    """Render a self-contained before/after HTML report for changed rows.

    changed_pairs is a list of (before_row, after_row) dicts. Only Image Src
    and Body (HTML) ever change, so the report shows those side by side.
    """
    cards = []
    for before, after in changed_pairs:
        handle = html.escape(after.get("Handle", ""))
        title = html.escape(after.get("Title", "") or after.get("Handle", ""))

        def img_cell(row):
            src = (row.get("Image Src") or "").strip()
            if not src:
                return '<div class="no-image">no image</div>'
            return f'<img src="{html.escape(src, quote=True)}" alt="" loading="lazy">'

        def desc_cell(row):
            text = strip_html(row.get("Body (HTML)", ""))
            if not text:
                return '<p class="empty">(empty)</p>'
            return f"<p>{html.escape(text)}</p>"

        image_changed = (before.get("Image Src") or "") != (after.get("Image Src") or "")
        desc_changed = (before.get("Body (HTML)") or "") != (after.get("Body (HTML)") or "")
        badges = "".join(
            f'<span class="badge">{label}</span>'
            for label, changed in (("image", image_changed), ("description", desc_changed))
            if changed
        )

        cards.append(f"""
<section class="card">
  <h2>{title} <code>{handle}</code> {badges}</h2>
  <div class="compare">
    <div class="side">
      <h3>Before</h3>
      {img_cell(before)}
      {desc_cell(before)}
    </div>
    <div class="side">
      <h3>After</h3>
      {img_cell(after)}
      {desc_cell(after)}
    </div>
  </div>
</section>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TMDB fill — {len(changed_pairs)} changed product{"s" if len(changed_pairs) != 1 else ""}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 960px; padding: 0 1rem; background: #fafafa; color: #222; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1.5rem; }}
  .card h2 {{ font-size: 1.1rem; margin: 0 0 .75rem; }}
  .card h2 code {{ font-size: .8rem; color: #888; font-weight: normal; }}
  .badge {{ font-size: .7rem; background: #973123; color: #fff; border-radius: 4px; padding: 2px 6px; margin-left: 4px; vertical-align: middle; }}
  .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .side h3 {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: #888; margin: 0 0 .5rem; }}
  .side img {{ max-width: 150px; height: auto; border: 1px solid #ddd; border-radius: 4px; display: block; margin-bottom: .5rem; }}
  .no-image {{ width: 150px; height: 100px; display: flex; align-items: center; justify-content: center; background: #eee; color: #999; font-size: .8rem; border-radius: 4px; margin-bottom: .5rem; }}
  .side p {{ font-size: .9rem; line-height: 1.45; margin: 0; }}
  .side p.empty {{ color: #999; font-style: italic; }}
</style>
</head>
<body>
<h1>TMDB fill — {len(changed_pairs)} changed product{"s" if len(changed_pairs) != 1 else ""}</h1>
{"".join(cards)}
</body>
</html>
"""


def print_progress(index: int, total: int, handle: str, message: str) -> None:
    print(f"[{index}/{total}] {handle}: {message}", flush=True)


def run(input_path, outdir, api_key: str, fetch_fn=None, sleep_fn=time.sleep, progress_fn=None) -> dict:
    fieldnames, rows = load_export(input_path)

    if fetch_fn is None:
        fetch_fn = make_tmdb_fetcher(api_key)
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    output_rows, review_rows = build_output(rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)

    # build_output preserves row order and count, so pairing input to output
    # positionally identifies exactly the rows it modified.
    changed_pairs = [
        (before, after) for before, after in zip(rows, output_rows) if before != after
    ]

    outdir = Path(outdir)
    write_csv(outdir / "tmdb-filled.csv", fieldnames, output_rows)
    write_csv(outdir / "tmdb-needs-review.csv", ["Handle", "Title", "Reason"], review_rows)
    write_csv(outdir / "tmdb-changed.csv", fieldnames, [after for _, after in changed_pairs])
    write_csv(outdir / "tmdb-changed-before.csv", fieldnames, [before for before, _ in changed_pairs])
    (outdir / "tmdb-changes.html").write_text(build_changes_html(changed_pairs), encoding="utf-8")

    return {"filled": len(output_rows), "review": len(review_rows), "changed": len(changed_pairs)}


def main():
    parser = argparse.ArgumentParser(
        description="Fill missing product images/descriptions from TMDB."
    )
    parser.add_argument("input_csv", help="Path to a Shopify product export CSV")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write output files (default: input file's directory)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print("Error: TMDB_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input_csv)
    outdir = Path(args.outdir) if args.outdir else input_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {input_path}...")
    counts = run(input_path, outdir, api_key, progress_fn=print_progress)
    print(f"Output: {counts['filled']} total rows written -> {outdir / 'tmdb-filled.csv'}")
    print(f"Actually changed: {counts['changed']} rows -> {outdir / 'tmdb-changed.csv'} (originals in tmdb-changed-before.csv)")
    print(f"Needs review: {counts['review']} rows -> {outdir / 'tmdb-needs-review.csv'}")
    print(f"Visual diff: open {outdir / 'tmdb-changes.html'}")


if __name__ == "__main__":
    main()
