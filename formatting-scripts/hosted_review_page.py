"""Generate the hosted (Vercel-served) TMDB review-picker page.

Unlike formatting-scripts/review_page.py's build_picker_html, this page has
no "Export picks" button: every pick is POSTed to /api/save-pick immediately,
and the page hydrates its already-decided state from /api/get-picks on load
instead of relying solely on localStorage. localStorage is kept only as a
same-device fallback cache if a save request fails.

See docs/superpowers/specs/2026-08-30-hosted-review-picker-design.md.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from review_page import MAX_CANDIDATES, THUMB_BASE_URL, collect_products

__all__ = [
    "build_hosted_picker_html", "write_hosted_picker", "validate_batch_id",
    "update_manifest", "build_launcher_html", "write_launcher",
]

# KEEP IN SYNC with BATCH_ID_PATTERN in tools/review-picker/api/_github.js.
# The API routes reject any batch id outside this pattern with a 400; validating
# here means a bad id fails at generation time (for the operator) rather than
# later, on the client's deployed page.
BATCH_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_batch_id(batch_id) -> str:
    """Raise ValueError unless batch_id matches the API's accepted slug pattern."""
    if not isinstance(batch_id, str) or not BATCH_ID_PATTERN.match(batch_id):
        raise ValueError(
            f"invalid batch_id {batch_id!r}: must match {BATCH_ID_PATTERN.pattern} "
            "(lowercase letters, digits, '.', '_', '-'; must start with a letter or digit). "
            "The /api/save-pick and /api/get-picks routes reject anything else with a 400."
        )
    return batch_id


def build_hosted_picker_html(products: list[dict], batch_id: str) -> str:
    """Render the hosted picker page with embedded candidate data."""
    products_json = json.dumps(products).replace("</", "<\\/")
    batch_id_json = json.dumps(batch_id)
    batch_id_url = quote(batch_id, safe="")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Movie review picker — {len(products)} products</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 1080px; padding: 0 1rem; background: #fafafa; color: #222; }}
  header {{ position: sticky; top: 0; background: #fafafa; padding: .75rem 0; border-bottom: 1px solid #ddd; z-index: 10; }}
  header h1 {{ font-size: 1.2rem; margin: 0 0 .25rem; }}
  header p.instructions {{ margin: 0; color: #555; font-size: .95rem; }}
  header .status-row {{ display: flex; align-items: center; gap: 1rem; margin-top: .5rem; }}
  #counter {{ color: #666; font-size: .9rem; }}
  #hide-decided-label {{ font-size: .9rem; color: #444; display: flex; align-items: center; gap: .35rem; cursor: pointer; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1.25rem 1.5rem; margin: 1.5rem 0; }}
  .card.decided {{ border-color: #5f8d7a; background: #f4faf7; }}
  body.hide-decided .card.decided {{ display: none; }}
  .card h2 {{ font-size: 1.15rem; margin: 0 0 .15rem; display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }}
  .save-state {{ font-size: .8rem; font-weight: 500; }}
  .save-state.saved {{ color: #5f8d7a; }}
  .save-state.saving {{ color: #888; }}
  .save-state.error {{ color: #973123; }}
  .save-state.failed {{ color: #973123; font-weight: 700; }}
  .tags {{ display: inline-flex; gap: .3rem; }}
  .tag {{ font-size: .7rem; font-weight: 500; text-transform: uppercase; letter-spacing: .02em; color: #5f8d7a; background: #eef5f1; border-radius: 3px; padding: .1rem .4rem; }}
  .card .meta {{ font-size: .8rem; color: #888; margin-bottom: .75rem; }}
  .card .meta a {{ color: #973123; }}
  .candidates {{ display: flex; flex-direction: column; gap: .6rem; }}
  label.option {{ display: flex; gap: .85rem; align-items: flex-start; border: 1px solid #eee; border-radius: 6px; padding: .75rem 1rem; cursor: pointer; }}
  label.option:hover {{ background: #f5f5f5; }}
  label.option input {{ margin-top: .3rem; width: 1.15rem; height: 1.15rem; }}
  label.option img {{ width: 70px; height: auto; border-radius: 3px; flex-shrink: 0; }}
  label.option .no-poster {{ width: 70px; height: 105px; background: #eee; color: #999; font-size: .65rem; display: flex; align-items: center; justify-content: center; border-radius: 3px; flex-shrink: 0; }}
  label.option .info {{ font-size: .9rem; line-height: 1.45; flex: 1; min-width: 0; }}
  label.option .info strong {{ font-size: .95rem; }}
  .secondary-options {{ display: flex; flex-direction: column; gap: .6rem; margin-top: .25rem; font-size: .85rem; }}
  .secondary-options label.option {{ padding: .4rem .6rem; background: #fdf6f5; }}
  .manual-fields {{ display: flex; flex-direction: column; gap: .4rem; margin: .25rem 0 0 2rem; }}
  .manual-fields input, .manual-fields textarea {{ font: inherit; font-size: .85rem; border: 1px solid #ccc; border-radius: 4px; padding: .4rem .5rem; width: 100%; box-sizing: border-box; }}
  .manual-fields textarea {{ min-height: 4.5em; resize: vertical; }}
</style>
</head>
<body>
<header>
  <h1>Pick the right movie</h1>
  <p class="instructions">For each title below, choose the correct poster and description. Your choices save automatically as you go — no need to submit anything when you're done.</p>
  <div class="status-row">
    <span id="counter"></span>
    <label id="hide-decided-label"><input type="checkbox" id="hide-decided"> Hide decided</label>
  </div>
</header>
<main id="cards"></main>
<script>
const PRODUCTS = {products_json};
const BATCH_ID = {batch_id_json};
const STORAGE_KEY = "tmdb-review-picks::" + BATCH_ID;
const MANUAL_KEY = "tmdb-review-manual::" + BATCH_ID;
const HIDE_DECIDED_KEY = "tmdb-review-hide-decided::" + BATCH_ID;
const PENDING_KEY = "tmdb-review-pending::" + BATCH_ID;

const MANUAL_DEBOUNCE_MS = 1500;
const MAX_SAVE_ATTEMPTS = 5;
const RETRY_BASE_MS = 3000;

function loadCache(key) {{
  try {{ return JSON.parse(localStorage.getItem(key)) || {{}}; }}
  catch (e) {{ return {{}}; }}
}}
function saveCache() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(picks));
  localStorage.setItem(MANUAL_KEY, JSON.stringify(manualData));
}}

let picks = loadCache(STORAGE_KEY);
let manualData = loadCache(MANUAL_KEY);
let saveState = {{}};
const debounceTimers = {{}};

// Handles whose save has been started but not confirmed by the server. Persisted
// so a reload mid-failure does not silently drop the pick: on load we re-POST
// anything still pending that the server does not already have.
function loadPending() {{
  try {{
    const raw = JSON.parse(localStorage.getItem(PENDING_KEY));
    return Array.isArray(raw) ? raw : [];
  }} catch (e) {{ return []; }}
}}
let pending = loadPending();
function persistPending() {{
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}}
function markPending(handle) {{
  if (pending.indexOf(handle) === -1) {{ pending.push(handle); persistPending(); }}
}}
function clearPending(handle) {{
  const i = pending.indexOf(handle);
  if (i !== -1) {{ pending.splice(i, 1); persistPending(); }}
}}

// Returns the candidate index (as a string), "manual", "skip", or null when a
// stored "tmdb" pick matches none of this page-load's candidates. null means
// "leave undecided" -- never silently downgrade a good tmdb pick to a blank
// manual one, which the client could then overwrite with nothing.
function pickChoiceIndex(product, remotePick) {{
  if (remotePick.choice === "manual") return "manual";
  if (remotePick.choice === "skip") return "skip";
  let idx = product.candidates.findIndex(
    c => c.poster_path === remotePick.poster_path && c.overview === remotePick.overview);
  if (idx === -1) {{
    // poster_path is the stable identifier; overview text drifts between TMDB fetches.
    idx = product.candidates.findIndex(
      c => c.poster_path && c.poster_path === remotePick.poster_path);
  }}
  return idx === -1 ? null : String(idx);
}}

function matchesRemote(handle, value, remotePick) {{
  if (!remotePick) return false;
  const payload = buildPayload(handle, value);
  if (remotePick.choice !== payload.choice) return false;
  if (payload.choice === "tmdb") return (remotePick.poster_path || "") === (payload.poster_path || "");
  if (payload.choice === "manual") {{
    return (remotePick.image_src || "") === payload.image_src
      && (remotePick.overview || "") === payload.overview;
  }}
  return true;
}}

function resendPending(remotePicks) {{
  const byHandle = {{}};
  for (const remotePick of remotePicks) byHandle[remotePick.handle] = remotePick;
  for (const handle of pending.slice()) {{
    const value = picks[handle];
    if (value === undefined) {{ clearPending(handle); continue; }}
    // A debounced save for this handle is already queued -- don't double-POST.
    if (debounceTimers[handle]) continue;
    if (matchesRemote(handle, value, byHandle[handle])) {{
      clearPending(handle);
      setSaveState(handle, "saved");
      continue;
    }}
    savePick(handle, value);
  }}
}}

async function hydrateFromServer() {{
  let remotePicks = [];
  try {{
    const response = await fetch("/api/get-picks?batch={batch_id_url}");
    if (!response.ok) return;
    remotePicks = await response.json();
    if (!Array.isArray(remotePicks)) return;
    for (const remotePick of remotePicks) {{
      const product = PRODUCTS.find(p => p.handle === remotePick.handle);
      if (!product) continue;
      // A locally pending handle holds a newer, unconfirmed value -- don't clobber it.
      if (pending.indexOf(remotePick.handle) !== -1) continue;
      const choice = pickChoiceIndex(product, remotePick);
      if (choice === null) {{
        delete picks[remotePick.handle];
        continue;
      }}
      picks[remotePick.handle] = choice;
      if (remotePick.choice === "manual") {{
        manualData[remotePick.handle] = {{ image_src: remotePick.image_src || "", overview: remotePick.overview || "" }};
      }}
    }}
    saveCache();
    render();
  }} catch (e) {{ /* offline or first load with nothing saved yet -- localStorage cache still applies */ }}
  resendPending(remotePicks);
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

function saveStateLabel(state) {{
  if (state === "saving") return "Saving…";
  if (state === "saved") return "Saved ✓";
  if (state === "failed") return "Not saved — save failed";
  if (state === "error") return "Not saved — retrying";
  return "";
}}

function saveStateHtml(handle) {{
  const state = saveState[handle] || "";
  return `<span class="save-state ${{state}}">${{saveStateLabel(state)}}</span>`;
}}

function cardFor(handle) {{
  const cards = document.getElementById("cards").children;
  for (const card of cards) {{
    if (card.dataset.handle === handle) return card;
  }}
  return null;
}}

// Update only this card's save-state indicator. Never re-render: a full render()
// destroys the DOM (and focus/caret) of any manual field being typed into.
function setSaveState(handle, state) {{
  saveState[handle] = state;
  const card = cardFor(handle);
  if (!card) return;
  const span = card.querySelector(".save-state");
  if (!span) return;
  span.className = "save-state " + state;
  span.textContent = saveStateLabel(state);
}}

function markDecided(handle) {{
  const card = cardFor(handle);
  if (card) card.classList.add("decided");
  updateCounter();
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
      <h2>${{esc(product.title)}} ${{tagsHtml}} ${{saveStateHtml(product.handle)}}</h2>
      <div class="meta"><code>${{esc(product.handle)}}</code> — ${{esc(product.reason)}}
        · <a href="${{searchUrl}}" target="_blank">TMDB search</a>
        · <a href="${{googleUrl}}" target="_blank">Google</a></div>
      <div class="candidates">
        ${{options}}
        <div class="secondary-options">
          ${{optionHtml(product.handle, "manual", current === "manual", "special",
            `<span class="info"><strong>Type it in myself</strong>
              <span class="manual-fields">
                <input type="url" class="manual-image" placeholder="Image URL (leave blank to keep current)"
                       value="${{esc((manualData[product.handle] || {{}}).image_src || "")}}">
                <textarea class="manual-overview" placeholder="Description (leave blank to keep current)">${{esc((manualData[product.handle] || {{}}).overview || "")}}</textarea>
              </span>
            </span>`)}}
          ${{optionHtml(product.handle, "skip", current === "skip", "special",
            '<span class="info"><strong>None of these match — skip</strong></span>')}}
        </div>
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

function buildPayload(handle, value) {{
  if (value === "skip") return {{ batch: BATCH_ID, handle, choice: "skip" }};
  if (value === "manual") {{
    const fields = manualData[handle] || {{}};
    return {{ batch: BATCH_ID, handle, choice: "manual", image_src: fields.image_src || "", overview: fields.overview || "" }};
  }}
  const product = PRODUCTS.find(p => p.handle === handle);
  const candidate = product.candidates[Number(value)];
  return {{ batch: BATCH_ID, handle, choice: "tmdb", poster_path: candidate.poster_path, overview: candidate.overview }};
}}

async function savePick(handle, value, attempt) {{
  attempt = attempt || 0;
  markPending(handle);
  setSaveState(handle, "saving");
  try {{
    const response = await fetch("/api/save-pick", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(buildPayload(handle, value)),
    }});
    if (!response.ok) throw new Error("save failed");
    setSaveState(handle, "saved");
    clearPending(handle);
  }} catch (e) {{
    if (attempt + 1 >= MAX_SAVE_ATTEMPTS) {{
      // Out of retries: leave a persistent error state rather than looping forever.
      // The handle stays in `pending`, so a reload re-attempts it.
      setSaveState(handle, "failed");
      return;
    }}
    setSaveState(handle, "error");
    setTimeout(() => {{
      // Abandon this retry if a newer save has superseded it -- otherwise a stale
      // queued retry can clobber the client's correction with the old value.
      if (picks[handle] !== value) return;
      if (debounceTimers[handle]) return;
      savePick(handle, value, attempt + 1);
    }}, RETRY_BASE_MS * Math.pow(2, attempt));
  }}
}}

// Manual free-text saves are debounced: each save is a git commit, so saving on
// every keystroke would produce one commit (and one Pages deploy) per character.
function queueManualSave(handle) {{
  markPending(handle);
  clearTimeout(debounceTimers[handle]);
  debounceTimers[handle] = setTimeout(() => {{
    delete debounceTimers[handle];
    savePick(handle, "manual");
  }}, MANUAL_DEBOUNCE_MS);
}}

document.getElementById("cards").addEventListener("change", event => {{
  const input = event.target;
  if (input.type !== "radio") return;
  const handle = input.closest(".card").dataset.handle;
  picks[handle] = input.value;
  saveCache();
  markDecided(handle);
  savePick(handle, input.value);
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
  if (picks[handle] !== "manual") {{
    picks[handle] = "manual";
    const radio = card.querySelector('input[type="radio"][value="manual"]');
    if (radio) radio.checked = true;
  }}
  saveCache();
  markDecided(handle);
  queueManualSave(handle);
}});

render();
hydrateFromServer();
</script>
</body>
</html>
"""


def write_hosted_picker(
    review_rows, tools_dir, batch_id, fetch_fn, sleep_fn=time.sleep, progress_fn=None,
) -> dict:
    """Write tools_dir/<batch_id>/index.html and, if absent, an empty
    tools_dir/data/<batch_id>.json for a new batch."""
    validate_batch_id(batch_id)
    if progress_fn is None:
        progress_fn = lambda index, total, handle, message: None

    tools_dir = Path(tools_dir)
    products = collect_products(review_rows, fetch_fn, sleep_fn=sleep_fn, progress_fn=progress_fn)

    batch_dir = tools_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "index.html").write_text(
        build_hosted_picker_html(products, batch_id), encoding="utf-8"
    )

    data_dir = tools_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / f"{batch_id}.json"
    if not data_file.exists():
        data_file.write_text("[]", encoding="utf-8")

    update_manifest(tools_dir, batch_id, len(products))
    write_launcher(tools_dir)

    return {"products": len(products)}


def update_manifest(tools_dir, batch_id: str, total: int) -> list[dict]:
    """Add or update one batch's entry in tools_dir/batches.json, preserving order."""
    tools_dir = Path(tools_dir)
    manifest_path = tools_dir / "batches.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []

    for entry in manifest:
        if entry["batch_id"] == batch_id:
            entry["total"] = total
            break
    else:
        manifest.append({"batch_id": batch_id, "total": total})

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_launcher_html() -> str:
    """Static launcher shell: fetches batches.json and each batch's live
    progress from /api/get-picks client-side, so it never needs regenerating
    just because a batch's decided-count changed."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Review pickers</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 820px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.4rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd; vertical-align: middle; }
  th { background: #f5f5f5; }
  a.open { display: inline-block; padding: 0.35rem 0.8rem; background: #973123; color: #fff; border-radius: 4px; text-decoration: none; font-size: 0.9rem; }
  .progress-cell { min-width: 160px; }
  .progress-track { background: #eee; border-radius: 4px; height: 8px; overflow: hidden; margin-bottom: .25rem; }
  .progress-fill { background: #5f8d7a; height: 100%; }
  .progress-fill.complete { background: #2b6cb0; }
  .progress-text { font-size: .8rem; color: #555; }
</style>
</head>
<body>
  <h1>Review pickers</h1>
  <table>
    <thead><tr><th>Batch</th><th class="progress-cell">Progress</th><th></th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
<script>
async function loadBatches() {
  const manifestResponse = await fetch("batches.json");
  if (!manifestResponse.ok) throw new Error("batches.json unavailable");
  const batches = await manifestResponse.json();
  const rows = document.getElementById("rows");
  for (const batch of batches) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${batch.batch_id}</td>
      <td class="progress-cell">
        <div class="progress-track"><div class="progress-fill" id="fill-${batch.batch_id}"></div></div>
        <div class="progress-text" id="text-${batch.batch_id}">loading…</div>
      </td>
      <td><a class="open" href="${batch.batch_id}/" target="_blank">Open</a></td>`;
    rows.appendChild(tr);

    try {
      const response = await fetch(`/api/get-picks?batch=${encodeURIComponent(batch.batch_id)}`);
      if (!response.ok) throw new Error(`get-picks failed (${response.status})`);
      const picks = await response.json();
      if (!Array.isArray(picks)) throw new Error("get-picks returned a non-array");
      const decided = picks.length;
      const pct = batch.total ? Math.round((decided / batch.total) * 100) : 0;
      document.getElementById(`fill-${batch.batch_id}`).style.width = `${pct}%`;
      const text = document.getElementById(`text-${batch.batch_id}`);
      text.textContent = `${decided} / ${batch.total} decided`;
      if (decided >= batch.total) {
        document.getElementById(`fill-${batch.batch_id}`).classList.add("complete");
      }
    } catch (e) {
      document.getElementById(`text-${batch.batch_id}`).textContent = "progress unavailable";
    }
  }
}
loadBatches().catch(() => {
  document.getElementById("rows").innerHTML =
    '<tr><td colspan="3">Could not load the batch list.</td></tr>';
});
</script>
</body>
</html>
"""


def write_launcher(tools_dir) -> None:
    Path(tools_dir).joinpath("index.html").write_text(build_launcher_html(), encoding="utf-8")
