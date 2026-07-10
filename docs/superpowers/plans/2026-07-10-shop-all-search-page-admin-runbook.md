# Shop-all catalog page — remaining admin/browser runbook

All code (Tasks 2–5 of the implementation plan) is committed on branch `worktree-shop-all-search-page` and has been pushed to the live theme (`140918915134`) on `lms-sandbox-lutsfahz.myshopify.com`. What's left is Shopify Admin / theme-editor / browser work only — no code changes. Work through this in order; each step notes what to check before moving on.

Reference: full implementation plan at `docs/superpowers/plans/2026-07-10-shop-all-search-page.md` (Tasks 1, 6, 7, 8). Design rationale at `docs/superpowers/specs/2026-07-10-shop-all-search-page-design.md`.

---

## Step 1 — Product metafields and tags

**Admin → Settings → Custom data → Products → Add definition**

1. Add definition:
   - Name: `Genre`
   - Namespace and key: `custom.genre`
   - Type: **List of single line text**
   - Enable "Filter on the product list" (the storefront-filtering toggle)
   - Save

2. Add definition:
   - Name: `Boutique label`
   - Namespace and key: `custom.label`
   - Type: **Single line text**
   - Enable "Filter on the product list"
   - Save

3. Find the existing `custom.format` and `custom.condition` definitions (already used by product cards) → edit each → enable "Filter on the product list" if not already on → Save.

4. On **at least 5 products**, set real values so there's something to filter against later:
   - `custom.genre`: 1–2 values each, e.g. `Drama`, `Horror`, `Sci-Fi`
   - `custom.label`: e.g. `Criterion`, `Arrow Video`
   - Tag **at least 2** of them with the tag `new-arrival` (Product → Organization → Tags)

---

## Step 2 — Search & Discovery filter sources

**Admin → Apps → Search & Discovery → Filters → Add filter**

Add each of these as a separate filter source, saving after each:

1. Source: **Format** (`custom.format`)
2. Source: **Genre** (`custom.genre`)
3. Source: **Boutique label** (`custom.label`)
4. Source: **Product tag** — if the app lets you scope a tag filter to a specific tag value, restrict it to just `new-arrival`. If it doesn't offer scoping, add it unscoped (it'll show all tags in the store, not just `new-arrival`) — **note which case applies**, since it determines a CSS-targeting detail in Step 5 below.

Save all changes before leaving the app.

**Verify:** open any existing collection page in the theme editor preview (default template) and confirm the horizontal filter bar now offers Format, Genre, Boutique label, and a tag filter as options. This just confirms the filter sources are live — the vertical sidebar version comes from the template assignment in Step 3.

---

## Step 3 — Assign the shop-all template

1. Confirm/create the **All products** collection (a smart collection with no conditions is fine if one doesn't already exist).
2. Open that collection in Admin → **Theme template** dropdown → select **`collection.shop-all`** → Save.
3. Open the collection in the theme customizer preview (Online Store → Customize) and confirm:
   - Filters render as a **left sidebar**, not a horizontal bar.
   - A **search input** appears above the filter list.
   - Products render as **2:3 poster cards** (title, director, price, format/condition badges) — not the native card layout.
   - Scrolling to the bottom of the grid **auto-loads** more products (no "Load more" button).
   - The sort dropdown **defaults to "Date, new to old."**

---

## Step 4 — Supercycle Methods filter block

Supercycle is already installed on this dev store.

1. Confirm Shopify Search & Discovery is installed (it should already be, from Step 2).
2. **Admin → Settings → Custom data → Products → View unstructured metafields** → find `supercycle.methods` → **Add definition**. Type: **List of single line text**. Enable **"Filter on the product list and in the Admin API"** and **"Use as a condition in smart collections."** Save.
   - This is the one Supercycle-defined metafield you're allowed to touch — you're only enabling filtering on it, not creating data under it. Do **not** create anything else under the `supercycle` namespace.
3. **Apps → Search & Discovery → Filters → Add filter** → source **Rental availability** → Save. Add filter again → source **Supercycle Methods** → Save.
4. **Find the section ID:** Online Store → Customize → open the shop-all collection page → open browser DevTools → Network tab → clear the log → toggle any existing filter (e.g. Format) on the live preview → find the resulting filter request → read its `section_id` value from the query string/payload → copy it.
5. **Add the app block:** still in the theme customizer, on the shop-all collection page sidebar → Add block → Apps → **Methods filter**. Paste the section ID from Step 4 into its settings. Set which filter types to expose (Membership, Calendar, or all) — check with the client/your own notes on which Supercycle method types LMS actually has live if you're unsure. Save.
6. **Find the native filter's DOM id:** with the Methods filter block now visible alongside the native "Rental availability" checkbox filter, open DevTools → Elements → search the DOM for `Facet-Details-` → find the one for the Rental availability filter → note the `filter.param_name` portion of its `id` attribute (the part after the section ID).
7. **Report back to me** with that param-name fragment — I'll add one scoped CSS rule (`.facets--vertical [id*='Facet-Details-'][id*='<your value>'] { display: none; }`) to `blocks/filters.liquid` to hide the native checkbox, so the Methods filter block becomes the only availability UI. This is the one remaining code change and it needs your live value to write correctly — I can't guess it.
8. Once that CSS lands and is pushed, confirm in the preview: the native "Rental availability" checkbox is gone, and the Methods filter block is the only availability UI, sitting above Format in the sidebar.

---

## Step 5 — Manual QA pass

Once Steps 1–4 are done, walk through this checklist on the shop-all collection page:

1. **Desktop filters:** Format/Genre/Boutique label checkboxes each filter the grid and show a count per value. New-arrivals toggle reads as a pill switch and filters to only `new-arrival`-tagged products. Combining two filters (e.g. Format + Genre) narrows correctly (AND across groups). Sort dropdown defaults to "Date, new to old."
2. **Search handoff + filter carryover:** with Format = "Blu-ray" active, search something in the sidebar box. Confirm the URL becomes `/search?q=<query>&filter...=Blu-ray` (or equivalent) and the search-results page's sidebar still shows Format active.
3. **Zero-result state:** combine filters to a combination with no matches. Confirm a real "no products found" message appears (this now comes from the existing `product-grid.liquid` empty state, not a separate block).
4. **Infinite scroll:** with more than one page of results, scroll to the bottom and confirm the next page auto-loads.
5. **Mobile:** at a mobile viewport, confirm filters collapse into the drawer (tap "Show filters" opens Format/Genre/Label/New-arrivals/Availability plus "See results"/"Clear all"), and check whether the search input is reachable on mobile too — flag to me if it's missing there, since it may need a follow-up fix.
6. **Other collections unaffected:** visit a different collection still on the default template. Confirm it still shows the horizontal filter bar, native product cards, and no sidebar search box.

---

## When you're done

Come back and tell me the results of Steps 1–5 (especially: did the tag filter scope to just `new-arrival`, and what's the param-name fragment from Step 4.6). I'll finish the last CSS change for Step 4.7, push it, and we'll close out the plan.
