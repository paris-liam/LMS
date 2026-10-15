# Libib → Shopify rental sync app (design, 2026-10-15)

**Status: spec, not built.** Decisions confirmed with the developer
2026-10-15 in a brainstorming session, starting from the loose flow in
`Proposal for Libib to Shopify Sync App.md` (repo root).

**Supersedes** `claudedocs/2026-10-15-rental-libib-to-shopify-action.md` (the
daily GitHub Action, never built). Carried over from it: the Libib
conventions for the client, the transform rules, the product field mapping,
the handle rule and the pipeline changes. Dropped: the schedule, GitHub-issue
reporting, Actions secrets, and its decision 2 ("creates without approval").
The floor-sale sheet (`claudedocs/2026-10-08-floor-sale-upload-sheet.md`) is
unaffected.

## Goal

The client adds rentals **in Libib only** (UPC lookup or typed in), then —
whenever he chooses — opens a password-protected webpage, uploads two Libib
CSV exports, reviews what the app found, fixes posters, and creates the
Shopify products himself. Afterwards he prints and applies barcode labels from
Shopify admin. The developer is not needed for a normal run.

**Libib is the source of truth.** The app never edits Libib and never edits
around it: a problem with a title, format or genre is fixed in Libib and the
copy is picked up on the next run.

## Decisions (2026-10-15)

| # | Decision |
|---|---|
| 1 | **Client-run, on demand.** No schedule. Every product created is one the client reviewed in the app. |
| 2 | **Upload-first.** The client exports the Barcodes and Library CSVs from Libib himself and uploads them. A server-side auto-export (Libib has no API — it needs Playwright) is a later phase, not v1. |
| 3 | **Sized for 1–100 copies per run** (small and frequent at first, weekly ~20–100 later). Products are created one per request, driven from the browser. |
| 4 | **New-copy detection is by barcode, not by date.** A copy is "new" when its `201…` barcode isn't on any Shopify variant. "Last successful sync" is shown for information only. |
| 5 | **Bad format/genre sets the copy aside; the rest sync.** Set-aside copies return on the next run once fixed in Libib (the barcode diff still sees them as missing). |
| 6 | **Hosting: Vercel, Python functions reusing `catalog/`, one shared password.** Same host and deploy model as the review picker. |
| 7 | **Vercel project rooted at the repo root** so functions import `catalog/` directly; `.vercelignore` trims the bundle. |
| 8 | **"Last successful sync" lives in a Shopify shop metafield** (`lms.rental_sync_last_run`, JSON). No database; nothing committed to the (public) repo. |
| 9 | **Review fields are read-only** except the poster. Title, description, format, genre and tags are fixed in Libib. |
| 10 | **A tag within 1–2 edits of a known format or genre is treated as a misspelling** and sets the copy aside. |
| 11 | **Unsure TMDB matches are suggested, not applied** — the client clicks "Use it" or the poster stays blank. |
| 12 | Unchanged from the Action spec: scope is new-flow copies only (`^201\d{10}$`); **one Shopify product per physical copy**; **create-only** (later Libib edits don't reach existing products; a copy deleted in Libib is never removed from Shopify); rentals are **untaxed, Online Store only, never POS**; every product gets `Barcode Not Printed`; extra tags pass through. |
| 13 | Built and tested on the **dev store** first (`SHOPIFY_STORE` env var), then switched to production. |

### Verified 2026-10-15 (developer)

- `productVariants(query: "barcode:201*")` filters by barcode prefix.
- Shopify accepts a hotlinked TMDB poster URL as `originalSource`.
- Retail Barcode Labels prints the **existing** `201…` barcode (it does not
  generate one), so the print step works as designed.

## Libib conventions for the client (from the Action spec)

- **Collection:** `Rental Library`.
- **Title:** as it should appear on the website — delete lookup noise such as
  `[VHS]`, `(Widescreen Edition)`.
- **Tags:** exactly one format and 1–3 genres, from:

  | Formats | Genres |
  |---|---|
  | `vhs`, `dvd`, `blu-ray`, `4k`, `laserdisc`, `betamax` | `comedy`, `action`, `drama`, `kids-family`, `sci-fi`, `thriller`, `horror`, `romantic-comedy`, `musical`, `fantasy`, `documentary`, `foreign`, `holiday`, `special-interest`, `anime` |

  Any other tag is allowed and is copied to Shopify, unless it looks like a
  misspelt format/genre (decision 10).
- **Description:** optional; becomes the Shopify description.
- **Barcode:** leave Libib's generated `201…` value. **Call #:** blank.
- **More copies of a title:** add a copy to the existing Libib item. Each copy
  becomes its own Shopify product.

## Architecture

```
browser (tools/rental-sync/index.html + app.js, no build step)
   │  signed session cookie
   ▼
Vercel Python functions  api/rental_sync/*.py      ← thin HTTP wrappers
   ▼
catalog/rental_sync/  (new, tested)                 ← all logic lives here
   ├─ transform.py   Libib rows → copy records, set-aside reasons, warnings
   ├─ compare.py     Libib copies vs Shopify `201…` barcodes
   ├─ shopify_read.py barcode list, location, Online Store publication, last-run metafield
   ├─ posters.py     wraps catalog/tmdb/match.py
   ├─ create.py      productSet → inventory → publish → read back + verify
   └─ auth.py        password check, HMAC cookie sign/verify
reuses: catalog/libib/exports.py:load_libib, catalog/tmdb/match.py
        (match_product, poster_url, alt_text_for), catalog/core/handles.py:slugify,
        catalog/shopify/api.py (client-credentials token, throttling),
        catalog/client_sheet/template/genre-mappings.csv
```

`catalog/rental_sync/` has no knowledge of HTTP or Vercel, so a CLI or the
later auto-export can call it unchanged.

### Endpoints

| Endpoint | Does |
|---|---|
| `POST /api/rental_sync/login` | Checks `SYNC_PASSWORD`; sets the session cookie. |
| `GET /api/rental_sync/status` | Last successful sync (from the metafield) and the target store name. |
| `POST /api/rental_sync/prepare` | Body: JSON with both CSVs gzipped in the browser (`CompressionStream`) and base64-encoded — keeps two growing exports under Vercel's 4.5 MB request limit and avoids multipart parsing (`cgi` is gone from Python 3.13). Validates headers → `load_libib(..., "Rental Library")` → keep `^201\d{10}$` → read Shopify `201…` barcodes → diff → transform each new copy. Returns `ready[]` and `set_aside[]`, each with warnings/reasons. Stateless — the browser holds the result. |
| `POST /api/rental_sync/posters` | Body: up to 10 copies. Returns per copy `confident` (url, alt) / `unsure` (best candidate url, alt, title, year) / `none` / `error` (reason). |
| `POST /api/rental_sync/create` | Body: one copy (fields from `prepare` + chosen poster URL). Re-checks barcode and handle, creates, verifies. Returns `created` (admin URL, image status) / `skipped_exists` / `failed` (Shopify message, mismatch list). |
| `POST /api/rental_sync/finish` | Body: run summary (counts, timestamp). Writes the last-run metafield. Called only when the create loop reaches its end. |

`create` re-derives the Shopify fields server-side from the copy's Libib
fields (it does not trust browser-supplied Shopify values): the browser can
only choose which copies to create and which poster URL to use.

### Environment (Vercel env vars, Production + Preview)

`SYNC_PASSWORD`, `SESSION_SECRET`, `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`,
`SHOPIFY_CLIENT_SECRET`, `TMDB_API_KEY`.

### Custom app scopes

`write_products`, `write_inventory`, `read_locations`, `write_publications`,
and whatever the shop-metafield write needs (check against the existing app;
add any missing scope and reinstall on the dev store, then production).

## Client flow

One page, five steps, step bar at the top. Review state lives in the browser
for the session.

### Step 1 — Upload

- Header: "Last successful sync: <date time> — N created" (or "No sync yet").
- Short guide with screenshots: export **Barcodes** and **Library** from Libib.
- Two upload boxes → **Find new rentals**.
- Header check: each file must carry the columns `load_libib` needs (barcode
  export: `id, barcode, title, collection, tags, created`; library export:
  `id, title, description, tags, collection`). Wrong or swapped files → which
  file is wrong, with that export's screenshot.

### Step 2 — New copies found

- Table: title, barcode, date added in Libib (`created`), checkbox (all ticked).
- Unticked copies are skipped this run and reappear next run.
- No new copies → "Everything in Libib's Rental Library is already in Shopify."
- Hint: "Not what you expected? Re-export from Libib and upload again."

### Step 3 — Check the details

- One read-only card per ticked copy: Title, Description, Format, Genre(s),
  Extra tags.
- **Set aside** section at the top, each card with its reason(s) and the
  format/genre vocabulary beside it, plus: "Fix this in Libib — it will show up
  next time you sync."
- Warnings on the card (do not block).
- **Looks good** → step 4 with ready copies only.

### Step 4 — Posters

- Cards fill in as `posters` batches return.
  - `confident` → poster shown.
  - `unsure` → best candidate shown, "Not sure — check this", **Use it**
    button; blank unless clicked.
  - `none` / `error` → blank, with the reason.
- Every card: "Paste image URL" field, `https://` only, live preview; a URL
  that fails to load in the preview is flagged.
- Blank is allowed — the product is created without an image.

### Step 5 — Create

- **Create N products in Shopify** → progress bar; the browser calls `create`
  once per copy, sequentially; per-copy ✓/✗ as results arrive.
- Results:
  - **Created** — title linked to its Shopify admin page.
  - **Already in Shopify — skipped** — counted as success.
  - **Failed** — Shopify's message and a plain next step; "Fix the issue and
    run the sync again — products already created won't be duplicated."
  - **Created, but the poster didn't load** — add it in Shopify admin.
- Then `finish`, and a **Print barcodes** button: opens Shopify admin products
  filtered by tag `Barcode Not Printed`, with instructions — print labels with
  Retail Barcode Labels, apply them, remove the tag.

## Transform rules

Input: one joined Libib row per copy (barcode export joined to library export
on `id`). Tags are a comma-separated string, compared case-insensitively.

| Field | Rule | Set aside when | Warning when |
|---|---|---|---|
| Barcode | must match `^201\d{10}$` (others are silently out of scope) | the same barcode appears on two Libib copies (both set aside) | — |
| Title | whitespace collapsed | blank | contains `[`, `]`, `(`, `)` or `edition` → "title may need cleanup" |
| Format | the one tag in the format list → Vendor (`vhs→VHS, dvd→DVD, blu-ray→Blu-Ray, 4k→4K, laserdisc→Laserdisc, betamax→Betamax`) | none; more than one | — |
| Genres | tags in the genre list, Libib's order → handles; names from `genre-mappings.csv` | none | more than 3 (all kept) |
| Misspellings | a non-vocabulary tag (after `slugify`) that is a known alias in `catalog/core/taxonomy.py` (`bluray`, `ld`, `kids`, …) or, for tags of 4+ characters, within Damerau-Levenshtein distance 1 (4–5 characters) or 2 (6+) of a format or genre — e.g. `horor`, `bluray`, `scifi`, `thrillers` | any present — reason names the closest term | — |
| Extra tags | every remaining tag, original text | — | any present → listed |
| Description | library export `description`, whitespace collapsed | — | blank |

Normalisation that maps exactly onto a vocabulary term (e.g. `Blu Ray` →
`blu-ray`, `sci fi` / `SCI_FI` → `sci-fi`, `Kids & Family` → `kids-family`)
is accepted as that term, not flagged. Real extra tags must not
false-positive: tests pin known-good ones (`criterion`, `oop`, `signed`,
`music`).

## Product creation

One `productSet` per copy:

| Field | Value |
|---|---|
| Handle | `slug(title)-slug(format)-rental-<barcode>` (`catalog/core/handles.py:slugify`) |
| Title | from transform |
| Description | Libib description as plain text, HTML-escaped, wrapped in `<p>` |
| Vendor | format |
| Product category | `Media > Videos` — must be set or Shopify drops `shopify.genre` |
| Tags | `Rental`, `Barcode Not Printed`, plus extra tags |
| Status | `ACTIVE` |
| Option | `Genre` = first genre's name |
| Genre metafield | `shopify.genre`, genre handles in order |
| Variant | barcode = Libib barcode, price `0`, taxable `false`, inventory tracked, policy `DENY`, quantity `1` at the location |
| Image | chosen poster URL as `originalSource`; alt from `alt_text_for` (pasted URL: `"<title> poster"`) |
| Publication | Online Store only (`publishablePublish`); never Point of Sale |

**Rerun safety.** `prepare` excludes barcodes already on a Shopify variant.
`create` re-checks barcode and handle immediately before writing; either taken
→ `skipped_exists`. A double-click, second tab, or a re-run after a crash can't
duplicate a copy.

**Verify.** After create, read the product back and check handle, barcode,
tags, taxable, quantity, Online Store published and not on POS, and media
status. Any mismatch → `failed` with the list. Media `FAILED` (Shopify couldn't
fetch the image) → `created` with "poster didn't load"; `PROCESSING` after a
short wait → `created` with no warning.

**Location.** Read once per `create` (cheap) — exactly one active location
expected; more than one → setup error, nothing created.

## Errors and security

**Auth.** `SYNC_PASSWORD` checked in constant time. Session cookie =
`expiry.HMAC-SHA256(SESSION_SECRET, expiry)`, `HttpOnly; Secure;
SameSite=Strict`, 12 h. Every endpoint except `login` returns 401 without a
valid cookie; the page then shows the login form. A failed login sleeps ~2 s
before responding (functions are stateless, so this is a slowdown, not a
lockout — adequate for a single-user tool). Same origin, no CORS headers.

**Input.** CSV uploads capped at 5 MB each; header-checked. Pasted image URLs
must be `https://`; the server never fetches them, only passes them to
Shopify. All Libib text is HTML-escaped when rendered.

**Messages.**

| Situation | Client sees |
|---|---|
| Wrong/swapped export | which file, with that export's screenshot |
| No new copies | "Everything in Libib's Rental Library is already in Shopify." |
| Shopify/TMDB down or throttled (after `api.py`'s retries) | "Shopify didn't respond — try again in a few minutes. Nothing has been changed." |
| TMDB fails for one copy | poster blank, "lookup failed"; never blocks |
| One create fails | Shopify's message; the loop continues; summary "N created, M failed — fix and run again; created items won't be duplicated." |
| Tab closed mid-create | nothing lost; next run's diff picks up the rest; last-run metafield not written |
| Setup problem (missing scope, several locations, missing env var) | "Something's wrong with the app setup — contact Liam" + "Show details" |

**Logs.** Vercel function logs carry titles, barcodes and Shopify errors —
never the password, cookie, or tokens. Nothing from a run is committed to the
public repo.

## Repo layout

```
tools/rental-sync/            front end (index.html, app.js, styles.css, guide screenshots)
api/rental_sync/              Vercel Python functions (thin)
catalog/rental_sync/          logic (transform, compare, shopify_read, posters, create, auth)
tests/catalog/test_rental_sync_*.py   alongside the existing catalog tests
vercel.json, .vercelignore    repo root; ignore runs/, exports/, theme/, tools/review-picker/, …
```

The review picker's Vercel project (root `tools/review-picker`) is unchanged;
this is a second Vercel project on the same repo. Check that the picker
project's root-directory setting keeps it from picking up the new root
`vercel.json`.

## Testing

- **transform / compare** — fixtures from `exports/2026-10-08` plus hand-made
  rows: two formats, no genre, misspellings (`horor`, `bluray`, `sci fi`),
  real extra tags that must not flag (`criterion`), duplicate barcode, `[VHS]`
  title, non-`201` and legacy 8-digit barcodes (skipped).
- **create** — fake Shopify client that records requests: field mapping,
  barcode/handle already taken → `skipped_exists`, verify mismatch → `failed`,
  media `FAILED` → poster warning, several locations → setup error.
- **auth** — sign/verify, expiry, tampered cookie, every non-login endpoint
  protected.
- **Dev store end-to-end** — a real Libib export with a few `201…` test
  copies: created product correct (handle, barcode, untaxed, qty 1, tags,
  genre option + metafield, category, poster); on Online Store, not on POS;
  re-run creates nothing; two copies of one Libib item → two products; a
  misspelt tag is set aside.
- **Front end** — Playwright walk-through on a Vercel preview: login → upload
  → set-aside display → paste poster URL → create → results → print-barcodes
  link.

## Build order

Rough estimates, not measured.

| # | Step | Est. |
|---|---|---|
| 1 | `transform.py` + `compare.py` (incl. misspelling rule) + tests | 4–5 h |
| 2 | `shopify_read.py` + `create.py` (productSet, inventory, publication, verify, rerun safety) + fake-client tests + dev-store runs | 6–8 h |
| 3 | `posters.py` + last-run metafield | 1–2 h |
| 4 | Vercel functions + `auth.py` + `vercel.json` / `.vercelignore` + project setup | 3–4 h |
| 5 | Front end: five steps, upload guide with screenshots, results, print handoff | 6–8 h |
| 6 | Dev-store end-to-end + Playwright walk-through | 2–3 h |
| 7 | Pipeline changes (below) | 2–3 h |
| 8 | Docs (client guide, `catalog/README.md`, `CLAUDE.md` roadmap #3), switch `SHOPIFY_STORE` to production, watch the first real run | 2 h |
| | **Total** | **26–35 h** |

## Pipeline changes (carried over from the Action spec)

1. **Legacy Libib tooling skips new-flow copies.** `libib diff` / `fix` /
   `sync` ignore any Libib item whose barcode is `201…` and any Shopify rental
   whose variant barcode is — otherwise they show as orphans/drift.
2. **`apply` may only set the poster on new-flow rentals** — never their
   title, description, Vendor or genre (those come from Libib).
3. **`audit` flags** a new-flow rental that is taxable, unpublished, or
   whose handle doesn't end in its barcode. (POS is not in the audit
   snapshot; the app's own read-back already refuses a product that is on
   any channel besides the Online Store.)

## Later, not in this spec

- **Auto-export:** the app triggers a GitHub Action that runs the Playwright
  export (`catalog/libib/transfer.py:run_browser_export`) and feeds the result
  into `prepare`. Needs the Action spec's step-0 spike (does Libib accept a
  login from GitHub's runners?).
- **Bulk-upload CSV template for Libib** so the client can add many rentals at
  once.
- **Updates from Libib** to existing products (create-only for now).
- **Legacy 8-digit rentals:** once the last ~50 are in Libib, decide whether
  scope widens and whether `libib sync` retires.
- **Legacy rentals on POS:** removing them is a separate bulk action.
