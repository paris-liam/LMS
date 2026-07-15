"""Generate a manual-review picker page for TMDB fill review entries.

Re-queries TMDB for every product in a tmdb-needs-review.csv with no
confidence threshold, and writes a self-contained HTML page showing each
product's top candidates. Picks are exported from the page as
tmdb-picks.json and applied with apply_review_picks.py.

See docs/superpowers/specs/2026-07-15-tmdb-review-picker-design.md.
"""

import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

from tmdb_fill import (
    REQUEST_DELAY_SECONDS,
    clean_title_and_year,
    load_export,
    make_tmdb_fetcher,
    print_progress,
    search_tmdb,
)

MAX_CANDIDATES = 5
THUMB_BASE_URL = "https://image.tmdb.org/t/p/w185"


def fetch_candidates(fetch_fn, title: str, year: int | None) -> list[dict]:
    """Search TMDB and map the top results to picker candidates."""
    results = search_tmdb(fetch_fn, title, year)
    candidates = []
    for result in results[:MAX_CANDIDATES]:
        candidates.append({
            "id": result.get("id"),
            "title": result.get("title") or "",
            "year": (result.get("release_date") or "")[:4],
            "overview": result.get("overview") or "",
            "poster_path": result.get("poster_path") or "",
        })
    return candidates


def collect_products(
    review_rows: list[dict],
    fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, handle, message: None,
) -> list[dict]:
    """Dedupe review rows by handle and fetch each product's candidates."""
    merged: dict[str, dict] = {}
    for row in review_rows:
        handle = row["Handle"]
        if handle not in merged:
            merged[handle] = {"handle": handle, "title": row["Title"], "reasons": []}
        merged[handle]["reasons"].append(row["Reason"])

    products = []
    total = len(merged)
    for index, entry in enumerate(merged.values(), start=1):
        clean_title, year = clean_title_and_year(entry["title"])
        try:
            candidates = fetch_candidates(fetch_fn, clean_title, year)
            message = f"{len(candidates)} candidate(s)"
        except Exception as exc:
            candidates = []
            message = f"TMDB request failed: {exc}"
        sleep_fn(REQUEST_DELAY_SECONDS)
        products.append({
            "handle": entry["handle"],
            "title": entry["title"],
            "reason": "; ".join(entry["reasons"]),
            "candidates": candidates,
        })
        progress_fn(index, total, entry["handle"], message)

    return products


def build_picker_html(products: list[dict]) -> str:
    """Render the self-contained picker page with embedded candidate data."""
    # Escape "</" so overview text can't terminate the script tag.
    products_json = json.dumps(products).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TMDB review picker — {len(products)} products</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 1080px; padding: 0 1rem; background: #fafafa; color: #222; }}
  header {{ position: sticky; top: 0; background: #fafafa; padding: .75rem 0; border-bottom: 1px solid #ddd; z-index: 10; display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.1rem; margin: 0; flex: 1; }}
  #counter {{ color: #666; font-size: .9rem; }}
  #export {{ background: #973123; color: #fff; border: 0; border-radius: 6px; padding: .5rem 1rem; font-size: .9rem; cursor: pointer; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; margin: 1.5rem 0; }}
  .card.decided {{ border-color: #5f8d7a; background: #f4faf7; }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 .15rem; }}
  .card .meta {{ font-size: .8rem; color: #888; margin-bottom: .75rem; }}
  .card .meta a {{ color: #973123; }}
  .candidates {{ display: flex; flex-direction: column; gap: .5rem; }}
  label.option {{ display: flex; gap: .75rem; align-items: flex-start; border: 1px solid #eee; border-radius: 6px; padding: .5rem .75rem; cursor: pointer; }}
  label.option:hover {{ background: #f5f5f5; }}
  label.option input {{ margin-top: .3rem; }}
  label.option img {{ width: 60px; height: auto; border-radius: 3px; flex-shrink: 0; }}
  label.option .no-poster {{ width: 60px; height: 90px; background: #eee; color: #999; font-size: .65rem; display: flex; align-items: center; justify-content: center; border-radius: 3px; flex-shrink: 0; }}
  label.option .info {{ font-size: .85rem; line-height: 1.4; }}
  label.option .info strong {{ font-size: .9rem; }}
  label.option.special {{ background: #fdf6f5; }}
</style>
</head>
<body>
<header>
  <h1>TMDB review picker</h1>
  <span id="counter"></span>
  <button id="export">Export picks (tmdb-picks.json)</button>
</header>
<main id="cards"></main>
<script>
const PRODUCTS = {products_json};
const STORAGE_KEY = "tmdb-review-picks";

function loadPicks() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {{}}; }}
  catch (e) {{ return {{}}; }}
}}
let picks = loadPicks();

function savePicks() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(picks));
}}

function esc(text) {{
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}}

function optionHtml(handle, value, checked, extraClass, inner) {{
  return `<label class="option ${{extraClass}}">
    <input type="radio" name="pick-${{esc(handle)}}" value="${{value}}" ${{checked ? "checked" : ""}}>
    ${{inner}}
  </label>`;
}}

function render() {{
  const cards = document.getElementById("cards");
  cards.innerHTML = PRODUCTS.map(product => {{
    const current = picks[product.handle];
    const searchUrl = "https://www.themoviedb.org/search?query=" + encodeURIComponent(product.title);
    const googleUrl = "https://www.google.com/search?q=" + encodeURIComponent(product.title + " movie");
    const options = product.candidates.map((candidate, i) => {{
      const poster = candidate.poster_path
        ? `<img src="{THUMB_BASE_URL}${{esc(candidate.poster_path)}}" alt="" loading="lazy">`
        : '<div class="no-poster">no poster</div>';
      const overview = candidate.overview ? esc(candidate.overview) : "<em>(no overview)</em>";
      return optionHtml(product.handle, String(i), current === String(i), "",
        `${{poster}}<span class="info"><strong>${{esc(candidate.title)}}</strong> (${{esc(candidate.year) || "?"}})<br>${{overview}}</span>`);
    }}).join("");
    return `<section class="card ${{current !== undefined ? "decided" : ""}}" data-handle="${{esc(product.handle)}}">
      <h2>${{esc(product.title)}}</h2>
      <div class="meta"><code>${{esc(product.handle)}}</code> — ${{esc(product.reason)}}
        · <a href="${{searchUrl}}" target="_blank">TMDB search</a>
        · <a href="${{googleUrl}}" target="_blank">Google</a></div>
      <div class="candidates">
        ${{options}}
        ${{optionHtml(product.handle, "needs_data", current === "needs_data", "special",
          '<span class="info"><strong>Not filling this one</strong> — tag as "needs data"</span>')}}
        ${{optionHtml(product.handle, "undecided", current === undefined, "",
          '<span class="info">Decide later</span>')}}
      </div>
    </section>`;
  }}).join("");
  updateCounter();
}}

function updateCounter() {{
  const decided = Object.keys(picks).length;
  document.getElementById("counter").textContent = `${{decided}} / ${{PRODUCTS.length}} decided`;
}}

document.getElementById("cards").addEventListener("change", event => {{
  const input = event.target;
  if (input.type !== "radio") return;
  const handle = input.closest(".card").dataset.handle;
  if (input.value === "undecided") {{
    delete picks[handle];
  }} else {{
    picks[handle] = input.value;
  }}
  savePicks();
  input.closest(".card").classList.toggle("decided", picks[handle] !== undefined);
  updateCounter();
}});

document.getElementById("export").addEventListener("click", () => {{
  const out = [];
  for (const product of PRODUCTS) {{
    const pick = picks[product.handle];
    if (pick === undefined) continue;
    if (pick === "needs_data") {{
      out.push({{handle: product.handle, choice: "needs_data"}});
    }} else {{
      const candidate = product.candidates[Number(pick)];
      if (!candidate) continue;
      out.push({{
        handle: product.handle,
        choice: "tmdb",
        poster_path: candidate.poster_path,
        overview: candidate.overview,
      }});
    }}
  }}
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: "application/json"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "tmdb-picks.json";
  link.click();
  URL.revokeObjectURL(link.href);
}});

render();
</script>
</body>
</html>
"""


def run(review_path, outdir, api_key: str, fetch_fn=None, sleep_fn=time.sleep, progress_fn=None) -> dict:
    _, review_rows = load_export(review_path)

    if fetch_fn is None:
        fetch_fn = make_tmdb_fetcher(api_key)
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    products = collect_products(review_rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)

    outdir = Path(outdir)
    (outdir / "tmdb-review-picker.html").write_text(build_picker_html(products), encoding="utf-8")

    return {"products": len(products)}


def main():
    parser = argparse.ArgumentParser(
        description="Generate a manual-review picker page from a tmdb-needs-review.csv."
    )
    parser.add_argument("review_csv", help="Path to the tmdb-needs-review.csv from a tmdb_fill run")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Directory to write tmdb-review-picker.html (default: review file's directory)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print("Error: TMDB_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    review_path = Path(args.review_csv)
    outdir = Path(args.outdir) if args.outdir else review_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {review_path}...")
    counts = run(review_path, outdir, api_key, progress_fn=print_progress)
    print(f"Picker page for {counts['products']} products -> open {outdir / 'tmdb-review-picker.html'}")
    print("Pick per product, then Export picks and apply with apply_review_picks.py.")


if __name__ == "__main__":
    main()
