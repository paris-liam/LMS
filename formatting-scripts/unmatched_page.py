"""Generate a manual-fill page for products TMDB couldn't match at all.

Unlike review_page.py's picker, there are no TMDB candidates to show here —
these rows have none. Each card just shows the title and genre, links out to
a Google search for them, and takes a manual image URL + description. The
exported JSON uses the same {handle, choice, image_src, overview} shape as
review-picker.html's manual entries, so it applies with the existing
apply_picks.py unchanged.
"""

import html
import json
import urllib.parse
from pathlib import Path

from taxonomy import GENRES

GENRE_LABELS = {handle: label for label, handle in GENRES.items()}


def genre_label(slug: str) -> str:
    """Map a shopify.genre metaobject handle back to its display label,
    falling back to the raw slug for anything unmapped."""
    slug = (slug or "").strip()
    if not slug:
        return ""
    first = slug.split(";")[0].strip()
    return GENRE_LABELS.get(first, first)


def google_search_url(title: str, genre: str) -> str:
    query = f"{title} {genre}".strip()
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def load_unmatched_products(rows: list[dict]) -> list[dict]:
    """Dedupe unmatched.csv rows by handle into the page's product shape."""
    seen = set()
    products = []
    for row in rows:
        handle = (row.get("Handle") or "").strip()
        if not handle or handle in seen:
            continue
        seen.add(handle)
        products.append({
            "handle": handle,
            "title": (row.get("Title") or "").strip(),
            "genre": genre_label(row.get("Genre (product.metafields.shopify.genre)", "")),
        })
    return products


def build_unmatched_html(products: list[dict], batch_id: str = "default") -> str:
    """Render the self-contained manual-fill page."""
    for p in products:
        p["search_url"] = google_search_url(p["title"], p["genre"])

    products_json = json.dumps(products).replace("</", "<\\/")
    batch_id_json = json.dumps(batch_id)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Unmatched fill-in — {len(products)} products</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; background: #fafafa; color: #222; }}
  header {{ position: sticky; top: 0; background: #fafafa; padding: .75rem 0; border-bottom: 1px solid #ddd; z-index: 10; display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.1rem; margin: 0; flex: 1; }}
  #counter {{ color: #666; font-size: .9rem; }}
  #export {{ background: #973123; color: #fff; border: 0; border-radius: 6px; padding: .5rem 1rem; font-size: .9rem; cursor: pointer; }}
  #hide-decided-label {{ font-size: .9rem; color: #444; display: flex; align-items: center; gap: .35rem; cursor: pointer; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; margin: 1.5rem 0; }}
  .card.decided {{ border-color: #5f8d7a; background: #f4faf7; }}
  body.hide-decided .card.decided {{ display: none; }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 .25rem; }}
  .card h2 a {{ color: #222; text-decoration: none; }}
  .card h2 a:hover {{ text-decoration: underline; color: #973123; }}
  .card .meta {{ font-size: .8rem; color: #888; margin-bottom: .75rem; }}
  .card .meta a {{ color: #973123; }}
  .fields {{ display: flex; flex-direction: column; gap: .4rem; }}
  .fields input, .fields textarea {{ font: inherit; font-size: .85rem; border: 1px solid #ccc; border-radius: 4px; padding: .5rem .6rem; width: 100%; box-sizing: border-box; }}
  .fields textarea {{ min-height: 4.5em; resize: vertical; }}
  .skip-row {{ margin-top: .5rem; font-size: .85rem; color: #666; display: flex; align-items: center; gap: .4rem; }}
</style>
</head>
<body>
<header>
  <h1>Unmatched fill-in</h1>
  <span id="counter"></span>
  <label id="hide-decided-label"><input type="checkbox" id="hide-decided"> Hide filled</label>
  <button id="export">Export picks (tmdb-picks.json)</button>
</header>
<main id="cards"></main>
<script>
const PRODUCTS = {products_json};
const BATCH_ID = {batch_id_json};
const STORAGE_KEY = "tmdb-review-manual::" + BATCH_ID;

function loadStored() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {{}}; }}
  catch (e) {{ return {{}}; }}
}}
let manualData = loadStored();

function saveManual() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(manualData));
}}

function esc(text) {{
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}}

function isFilled(handle) {{
  const d = manualData[handle];
  return !!(d && (d.image_src || d.overview));
}}

function updateCounter() {{
  const filled = PRODUCTS.filter(p => isFilled(p.handle)).length;
  document.getElementById("counter").textContent = `${{filled}} / ${{PRODUCTS.length}} filled`;
  document.querySelectorAll(".card").forEach(card => {{
    card.classList.toggle("decided", isFilled(card.dataset.handle));
  }});
}}

function render() {{
  const cards = document.getElementById("cards");
  cards.innerHTML = PRODUCTS.map(product => {{
    const current = manualData[product.handle] || {{}};
    return `<section class="card ${{isFilled(product.handle) ? "decided" : ""}}" data-handle="${{esc(product.handle)}}">
      <h2><a href="${{product.search_url}}" target="_blank">${{esc(product.title)}}</a></h2>
      <div class="meta"><code>${{esc(product.handle)}}</code>${{product.genre ? " — " + esc(product.genre) : ""}}
        · <a href="${{product.search_url}}" target="_blank">Google search</a></div>
      <div class="fields">
        <input type="url" class="image-input" placeholder="Image URL"
               value="${{esc(current.image_src || "")}}">
        <textarea class="overview-input" placeholder="Description">${{esc(current.overview || "")}}</textarea>
      </div>
    </section>`;
  }}).join("");

  cards.querySelectorAll(".card").forEach(card => {{
    const handle = card.dataset.handle;
    const imageInput = card.querySelector(".image-input");
    const overviewInput = card.querySelector(".overview-input");
    function save() {{
      manualData[handle] = {{ image_src: imageInput.value.trim(), overview: overviewInput.value.trim() }};
      saveManual();
      updateCounter();
    }}
    imageInput.addEventListener("input", save);
    overviewInput.addEventListener("input", save);
  }});

  updateCounter();
}}

document.getElementById("hide-decided").addEventListener("change", (e) => {{
  document.body.classList.toggle("hide-decided", e.target.checked);
}});

document.getElementById("export").addEventListener("click", () => {{
  const picks = PRODUCTS
    .filter(p => isFilled(p.handle))
    .map(p => ({{
      handle: p.handle,
      choice: "manual",
      image_src: (manualData[p.handle].image_src || ""),
      overview: (manualData[p.handle].overview || ""),
    }}));
  const blob = new Blob([JSON.stringify(picks, null, 2)], {{ type: "application/json" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tmdb-picks.json";
  a.click();
  URL.revokeObjectURL(url);
}});

render();
</script>
</body>
</html>
"""


def write_unmatched_page(rows: list[dict], outdir, batch_id: str | None = None) -> dict:
    products = load_unmatched_products(rows)
    outdir = Path(outdir)
    batch_id = batch_id or outdir.name
    outdir.joinpath("unmatched-fill-in.html").write_text(
        build_unmatched_html(products, batch_id=batch_id), encoding="utf-8"
    )
    return {"products": len(products)}
