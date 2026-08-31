"""Generate a manual-review picker page for TMDB fill review entries.

Re-queries TMDB for every ambiguous review row produced by
tmdb_fill.build_output (unmatched rows go to tmdb-unmatched.csv instead —
run.py only passes ambiguous rows here), and writes a self-contained HTML
page showing each product's top candidates. Picks are exported from the
page as a JSON file and applied with apply_picks.py.

See docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md.
"""

import html
import json
import time
from pathlib import Path

from tmdb_fill import (
    GLOBAL_YEAR_CUTOFF,
    REQUEST_DELAY_SECONDS,
    clean_title_and_year,
    filter_by_year_cutoff,
    genre_matches,
    search_tmdb,
    title_similarity,
)

MAX_CANDIDATES = 5
THUMB_BASE_URL = "https://image.tmdb.org/t/p/w185"

# Same-score candidates are grouped to this many decimal places before
# popularity breaks the tie, so popularity only orders genuinely close
# calls rather than nudging ahead of a clearly better (or worse) title match.
SCORE_TIE_PRECISION = 3


def fetch_candidates(fetch_fn, title: str, year: int | None, genre: str = "") -> list[dict]:
    """Search TMDB and map the top results to picker candidates, ranked by
    title similarity first, genre match as a tiebreak, and popularity/vote
    count as a final tiebreak among candidates still tied after that — so a
    genre mismatch overrides popularity. This mirrors classify_match's own
    signals (title_similarity, genre_matches) but without candidate_score's
    1.0 cap, which would hide the genre tiebreak whenever two candidates
    already have a perfect title match.

    This ordering only affects what the human sees first in the picker —
    it never decides a match on its own (that stays classify_match's job).

    Candidates released in or after GLOBAL_YEAR_CUTOFF + 1 are dropped
    outright (unless the title itself carried an explicit year) — the
    catalogue doesn't carry anything that new, so a candidate from 2020 on
    isn't a real option worth showing the reviewer."""
    results = search_tmdb(fetch_fn, title, year)
    if year is None:
        results = filter_by_year_cutoff(results, GLOBAL_YEAR_CUTOFF)
    results = sorted(
        results,
        key=lambda r: (
            round(title_similarity(title, r.get("title", "")), SCORE_TIE_PRECISION),
            genre_matches(genre, r),
            r.get("popularity") or 0,
            r.get("vote_count") or 0,
        ),
        reverse=True,
    )
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
    progress_fn=lambda index, total, title, message: None,
) -> list[dict]:
    """Dedupe review rows by handle and fetch each product's candidates."""
    merged: dict[str, dict] = {}
    for row in review_rows:
        handle = row["Handle"]
        if handle not in merged:
            merged[handle] = {
                "handle": handle, "title": row["Title"],
                "vendor": row.get("Vendor", ""), "genre": row.get("Genre", ""),
                "reasons": [],
            }
        merged[handle]["reasons"].append(row["Reason"])

    products = []
    total = len(merged)
    for index, entry in enumerate(merged.values(), start=1):
        clean_title, year = clean_title_and_year(entry["title"])
        try:
            candidates = fetch_candidates(fetch_fn, clean_title, year, genre=entry["genre"])
            message = f"{len(candidates)} candidate(s)"
        except Exception as exc:
            candidates = []
            message = f"TMDB request failed: {exc}"
        sleep_fn(REQUEST_DELAY_SECONDS)
        products.append({
            "handle": entry["handle"],
            "title": entry["title"],
            "vendor": entry["vendor"],
            "genre": entry["genre"],
            "reason": "; ".join(entry["reasons"]),
            "candidates": candidates,
        })
        progress_fn(index, total, entry["title"], message)

    return products


def build_picker_html(products: list[dict], batch_id: str = "default") -> str:
    """Render the self-contained picker page with embedded candidate data.

    batch_id namespaces this page's localStorage keys. Pages are commonly
    served from one static-file origin (e.g. a local dev server), where
    localStorage is shared by *origin*, not by file path — without a
    per-batch namespace, every picker page reads and writes the same
    picks object and the "N / total decided" counter on any one page
    would count every other batch's decisions too.
    """
    # Escape "</" so overview text can't terminate the script tag.
    products_json = json.dumps(products).replace("</", "<\\/")
    batch_id_json = json.dumps(batch_id)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Movie review picker — {len(products)} products</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 1080px; padding: 0 1rem; background: #fafafa; color: #222; }}
  header {{ position: sticky; top: 0; background: #fafafa; padding: .75rem 0; border-bottom: 1px solid #ddd; z-index: 10; display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.1rem; margin: 0; flex: 1; }}
  #counter {{ color: #666; font-size: .9rem; }}
  #export {{ background: #973123; color: #fff; border: 0; border-radius: 6px; padding: .5rem 1rem; font-size: .9rem; cursor: pointer; }}
  #hide-decided-label {{ font-size: .9rem; color: #444; display: flex; align-items: center; gap: .35rem; cursor: pointer; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; margin: 1.5rem 0; }}
  .card.decided {{ border-color: #5f8d7a; background: #f4faf7; }}
  body.hide-decided .card.decided {{ display: none; }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 .15rem; display: flex; align-items: center; gap: .4rem; flex-wrap: wrap; }}
  .tags {{ display: inline-flex; gap: .3rem; }}
  .tag {{ font-size: .7rem; font-weight: 500; text-transform: uppercase; letter-spacing: .02em; color: #5f8d7a; background: #eef5f1; border-radius: 3px; padding: .1rem .4rem; }}
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
  .manual-fields {{ display: flex; flex-direction: column; gap: .4rem; margin: .25rem 0 0 2rem; }}
  .manual-fields input, .manual-fields textarea {{ font: inherit; font-size: .85rem; border: 1px solid #ccc; border-radius: 4px; padding: .4rem .5rem; width: 100%; box-sizing: border-box; }}
  .manual-fields textarea {{ min-height: 4.5em; resize: vertical; }}
</style>
</head>
<body>
<header>
  <h1>Movie review picker</h1>
  <span id="counter"></span>
  <label id="hide-decided-label"><input type="checkbox" id="hide-decided"> Hide decided</label>
  <button id="export">Export picks (tmdb-picks.json)</button>
</header>
<main id="cards"></main>
<script>
const PRODUCTS = {products_json};
const BATCH_ID = {batch_id_json};
const STORAGE_KEY = "tmdb-review-picks::" + BATCH_ID;
const MANUAL_KEY = "tmdb-review-manual::" + BATCH_ID;
const HIDE_DECIDED_KEY = "tmdb-review-hide-decided::" + BATCH_ID;
// Pre-namespacing pages all wrote to this one shared key. Migrate any
// entries for this batch's own handles into the namespaced key below,
// so picks made before this page was regenerated aren't lost.
const LEGACY_STORAGE_KEY = "tmdb-review-picks";
const LEGACY_MANUAL_KEY = "tmdb-review-manual";

function loadStored(key) {{
  try {{ return JSON.parse(localStorage.getItem(key)) || {{}}; }}
  catch (e) {{ return {{}}; }}
}}
let picks = loadStored(STORAGE_KEY);
let manualData = loadStored(MANUAL_KEY);

// One-time migration: pull this batch's own handles out of the old shared
// key, so picks made before namespacing existed aren't lost or, worse,
// don't leak other batches' decided counts into this page's counter.
(function migrateLegacyPicks() {{
  const handles = new Set(PRODUCTS.map(p => p.handle));
  const legacyPicks = loadStored(LEGACY_STORAGE_KEY);
  const legacyManual = loadStored(LEGACY_MANUAL_KEY);
  let changed = false;
  for (const handle of Object.keys(legacyPicks)) {{
    if (handles.has(handle) && !(handle in picks)) {{
      picks[handle] = legacyPicks[handle];
      changed = true;
    }}
  }}
  for (const handle of Object.keys(legacyManual)) {{
    if (handles.has(handle) && !(handle in manualData)) {{
      manualData[handle] = legacyManual[handle];
      changed = true;
    }}
  }}
  if (changed) savePicks();
}})();

function savePicks() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(picks));
  localStorage.setItem(MANUAL_KEY, JSON.stringify(manualData));
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
    const tags = [product.vendor, product.genre].filter(Boolean);
    const tagsHtml = tags.length
      ? `<span class="tags">${{tags.map(t => `<span class="tag">${{esc(t)}}</span>`).join("")}}</span>`
      : "";
    return `<section class="card ${{current !== undefined ? "decided" : ""}}" data-handle="${{esc(product.handle)}}">
      <h2>${{esc(product.title)}} ${{tagsHtml}}</h2>
      <div class="meta"><code>${{esc(product.handle)}}</code> — ${{esc(product.reason)}}
        · <a href="${{searchUrl}}" target="_blank">TMDB search</a>
        · <a href="${{googleUrl}}" target="_blank">Google</a></div>
      <div class="candidates">
        ${{options}}
        ${{optionHtml(product.handle, "manual", current === "manual", "special",
          `<span class="info" style="flex:1"><strong>Manual entry</strong> — fill in what you found
            <span class="manual-fields">
              <input type="url" class="manual-image" placeholder="Image URL (leave blank to keep current)"
                     value="${{esc((manualData[product.handle] || {{}}).image_src || "")}}">
              <textarea class="manual-overview" placeholder="Description (leave blank to keep current)">${{esc((manualData[product.handle] || {{}}).overview || "")}}</textarea>
            </span>
          </span>`)}}
        ${{optionHtml(product.handle, "skip", current === "skip", "special",
          '<span class="info"><strong>Skip this one</strong> — leave it for a later pass</span>')}}
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

const hideDecidedBox = document.getElementById("hide-decided");
hideDecidedBox.checked = localStorage.getItem(HIDE_DECIDED_KEY) === "1";
document.body.classList.toggle("hide-decided", hideDecidedBox.checked);
hideDecidedBox.addEventListener("change", () => {{
  document.body.classList.toggle("hide-decided", hideDecidedBox.checked);
  localStorage.setItem(HIDE_DECIDED_KEY, hideDecidedBox.checked ? "1" : "0");
}});

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

document.getElementById("cards").addEventListener("input", event => {{
  const input = event.target;
  if (!input.classList.contains("manual-image") && !input.classList.contains("manual-overview")) return;
  const card = input.closest(".card");
  const handle = card.dataset.handle;
  const fields = manualData[handle] || {{}};
  if (input.classList.contains("manual-image")) fields.image_src = input.value;
  else fields.overview = input.value;
  manualData[handle] = fields;
  // Typing in a manual field selects that card's Manual option.
  if (picks[handle] !== "manual") {{
    picks[handle] = "manual";
    const radio = card.querySelector('input[type="radio"][value="manual"]');
    if (radio) radio.checked = true;
    card.classList.add("decided");
    updateCounter();
  }}
  savePicks();
}});

document.getElementById("export").addEventListener("click", () => {{
  const out = [];
  for (const product of PRODUCTS) {{
    const pick = picks[product.handle];
    if (pick === undefined) continue;
    if (pick === "skip") {{
      out.push({{handle: product.handle, choice: "skip"}});
    }} else if (pick === "manual") {{
      const fields = manualData[product.handle] || {{}};
      const image_src = (fields.image_src || "").trim();
      const overview = (fields.overview || "").trim();
      if (!image_src && !overview) continue; // nothing typed — skip
      out.push({{handle: product.handle, choice: "manual", image_src, overview}});
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


def write_picker(review_rows, outdir, fetch_fn, sleep_fn=time.sleep, progress_fn=None) -> dict:
    """Build review-picker.html for the given review rows."""
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    products = collect_products(review_rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)
    batch_id = Path(outdir).name
    Path(outdir).joinpath("review-picker.html").write_text(
        build_picker_html(products, batch_id=batch_id), encoding="utf-8"
    )
    return {"products": len(products)}
