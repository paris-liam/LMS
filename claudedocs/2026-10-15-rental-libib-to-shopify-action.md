# Rental sync — daily GitHub Action, Libib → Shopify (design, 2026-10-15)

**Status: SUPERSEDED 2026-10-15, never built** — replaced by the client-run
webapp in `docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`.
Kept as background: its Libib conventions, transform rules, product field
mapping, handle rule and pipeline changes carry over there; its schedule,
GitHub-issue reporting and "creates without approval" decision are dropped.
Decisions confirmed with the developer 2026-10-15.

**Supersedes** `claudedocs/2026-10-09-rental-upload-libib-first.md` (the
Google Sheet route). Its Libib conventions and handle/column rules carry over
where noted below; its sheet, formulas, seam test, `check-upload` rental
shape and client import steps are dropped. The floor-sale sheet
(`claudedocs/2026-10-08-floor-sale-upload-sheet.md`) is unaffected.

## Goal

The client adds rentals **in Libib only** (UPC lookup or typed in) and checks
them during the day. Once a day, while nobody is entering items, a GitHub
Action exports Libib, creates a Shopify product for every new copy, and opens
a GitHub issue summarising what it did and what needs attention. The client
does nothing in Shopify except, when the issue says so, add a missing poster
in the admin.

**Libib is the source of truth for these rentals.** Shopify copies it once,
at creation; nothing writes back into Libib.

## Decisions (2026-10-15)

| # | Decision |
|---|---|
| 1 | Runs **daily on a schedule** (early morning, Eastern), plus a manual "Run workflow" button. Libib has no API or webhooks, so it cannot be event-driven. |
| 2 | **Creates without approval.** The job only ever *creates* new rental products; it never updates or deletes. This is a deliberate exception to the "every change is approved" rule, limited to this job. |
| 3 | **Create-only.** A later edit in Libib (title, tags, description) does not reach a product that already exists in Shopify. A copy deleted in Libib is reported, never removed from Shopify. |
| 4 | **Scope is new-flow copies only:** Libib barcode is 13 digits starting `201`. Legacy rentals (8-digit barcodes, joined on call number) stay with `libib diff` / `fix` / `sync` until the last ~50 are in Libib — the developer handles those by hand. Comparing the whole library is out of scope. |
| 5 | **One Shopify product per physical copy** (per Libib barcode), even when one Libib item has several copies. |
| 6 | **Nothing is held back.** A copy with a title and a barcode is created; anything wrong or missing is a note in the issue. Only a blank title or blank/invalid barcode skips a copy. |
| 7 | **Poster comes from TMDB**, not Libib (neither export carries a cover URL). Only a *confident* match sets the image; anything else is created without one and flagged so the client adds it in Shopify admin. |
| 8 | **Reporting is a GitHub issue — a new one every run.** GitHub's issue emails are the daily summary email. |
| 9 | **If Libib blocks the login from GitHub's servers**, the run fails and opens an issue telling the developer to run the same command locally. |
| 10 | Every created product gets the tag **`Barcode Not Printed`**. The client currently may not label rentals at all; the tag is there so that, if he starts, he can find unlabelled copies. He removes it after printing. (Rentals only — floor-sale items are always labelled.) |
| 11 | Tags outside the format/genre vocabulary are **passed through** to Shopify `Tags` and listed in the issue so typos are visible. |
| 12 | Rentals are **not taxable** and **not on POS** — Online Store only. |
| 13 | Built and tested on the **dev store** first; the custom app gets installed there. |

## Libib conventions for the client (unchanged from 2026-10-09)

- **Collection:** `Rental Library`.
- **Title:** the film's title as it should appear on the website — delete
  lookup noise such as `[VHS]`, `(Widescreen Edition)`.
- **Tags:** exactly one format and 1–3 genres, from:

  | Formats | Genres |
  |---|---|
  | `vhs`, `dvd`, `blu-ray`, `4k`, `laserdisc`, `betamax` | `comedy`, `action`, `drama`, `kids-family`, `sci-fi`, `thriller`, `horror`, `romantic-comedy`, `musical`, `fantasy`, `documentary`, `foreign`, `holiday`, `special-interest`, `anime` |

  Any other tag is allowed and is copied to Shopify (decision 11).
- **Description:** optional; becomes the Shopify description.
- **Barcode:** leave Libib's generated `201…` value. **Call #:** blank.
- **More copies of a title:** add a copy to the existing Libib item. Each
  copy becomes its own Shopify product.
- **Finish the day's entries before the run** — a copy is created from
  whatever Libib holds at run time, and later Libib edits don't carry over
  (decision 3).

## Run, step by step

```
schedule / manual
 » 1. libib export (headless)               catalog/libib/transfer.py:run_browser_export
 » 2. transform                             catalog/rental_sync/transform.py   (new)
 » 3. read Shopify new-flow rentals         catalog/rental_sync/shopify_read.py (new)
 » 4. compare by barcode
 » 5. TMDB poster for each new copy         catalog/tmdb/match.py:match_product
 » 6. create products                       catalog/rental_sync/create.py      (new)
 » 7. report → GitHub issue                 catalog/rental_sync/report.py      (new)
```

Entry point: `python -m catalog rental-sync` with `--store` (default
production, per `config.DEFAULT_STORE`), `--dry-run` (do steps 1–5 and print
the report, create nothing) and `--report-file <path>` (where the issue body
is written for the workflow to post).

### 1. Export

`run_browser_export` into a temp dir (not `exports/`, not committed, not
uploaded). A login failure (`PlaywrightTimeoutError` in `browser.login`, or
the post-login URL not reaching `/library`) exits with a distinct code
(**3**) so the workflow can tell "Libib blocked us" from any other failure.

### 2. Transform

`load_libib(barcodes, library, "Rental Library")` joins the exports on `id`.
Keep rows whose barcode matches `^201\d{10}$`. For each copy:

| Field | Rule | Note when |
|---|---|---|
| Title | whitespace collapsed | blank → **skip**; contains `[`, `]`, `(`, `)` or `edition` → note "title may need cleanup" |
| Format | the one tag in the format list → Vendor via `vhs→VHS, dvd→DVD, blu-ray→Blu-Ray, 4k→4K, laserdisc→Laserdisc, betamax→Betamax` | none → note, Vendor blank; >1 → note, first alphabetically used |
| Genres | tags in the genre list, Libib's (alphabetical) order → handles; names via `catalog/client_sheet/template/genre-mappings.csv` | none → note, no genre option or metafield; >3 → note, all kept |
| Extra tags | every other tag, original text | any present → note listing them |
| Description | library export `description`, whitespace collapsed | blank → note |

Tags are compared case-insensitively. Libib exports them as one
comma-separated string.

### 3. Read Shopify

Query products with `tag:Rental` and read every variant barcode
(`catalog/shopify/queries/` — new query). Keep those with a `201…` barcode.
Also read the Online Store publication ID and the store's location (one
location expected; more than one → fail with a clear error rather than
guess).

### 4. Compare by barcode

- **In Libib, not in Shopify** → create (step 6).
- **In Shopify, not in Libib** → note only ("copy removed from Libib?").
- **In both** → nothing (create-only).
- A barcode on **two Shopify products** → note; never create a third.

### 5. TMDB poster

Build a snapshot-shaped row (`Title`, `Body (HTML)`, `Vendor`, genre
metafield) and call `match_product` — the description is its tiebreak hint.
`confident` → `poster_url(best)` and `alt_text_for(title, best)`.
`ambiguous` / `none` / `error` → no image, note "no poster — add one in
Shopify admin" with the reason (and the best candidate for `ambiguous`).
Uses `TMDB_API_KEY`; the TMDB cache is not committed from CI.

### 6. Create

One `productSet` per copy, then verify by reading it back.

| Field | Value |
|---|---|
| Handle | `slug(title)-slug(format)-rental-<barcode>`; no format → `slug(title)-rental-<barcode>` (`catalog/core/handles.py:slugify`) |
| Title | from step 2 |
| Description | Libib description |
| Vendor | format (blank if none) |
| Product category | `Media > Videos` — must be set or Shopify drops `shopify.genre` |
| Tags | `Rental`, `Barcode Not Printed`, plus extra tags |
| Status | `ACTIVE` |
| Option | `Genre` = first genre's name; no genre → Shopify's default single variant |
| Genre metafield | `shopify.genre`, genre handles in order |
| Variant | barcode = Libib barcode, price `0`, taxable `false`, inventory tracked, policy `DENY`, quantity `1` at the location |
| Image | TMDB poster + alt text, when confident |
| Publication | **Online Store only** (`publishablePublish`); never Point of Sale |

Before each create, re-check the handle doesn't exist (a run that died
half-way must not duplicate on re-run). After each create, read the product
and confirm handle, barcode, tags, taxable, quantity, publication; a
mismatch is a **failed** line in the report, not a silent pass. Throttling
handled as in `catalog/shopify/api.py`.

Scopes needed on the custom app (verify; add if missing): `write_products`,
`write_inventory`, `read_locations`, `write_publications`.

### 7. Report

Markdown written to `--report-file`, also printed to the job log. The
workflow posts it as a **new issue** every run, titled
`Rental sync YYYY-MM-DD — N created, M notes`, label `rental-sync`. Sections,
each omitted when empty:

1. **Failed** — create/verify errors (with Shopify's message).
2. **Created** — title, format, barcode, admin link.
3. **Needs a poster** — added without an image; TMDB reason.
4. **Data notes** — per copy: missing format/genre/description, extra tags,
   title cleanup, duplicate barcodes.
5. **In Shopify, not in Libib** — barcode, title, admin link.
6. **Skipped** — blank title / bad barcode.

A run that created nothing and has no notes still opens a (one-line) issue
and closes it immediately — the email confirms the job ran; open issues
remain only for runs that need attention.

Never include the Libib login, raw exports or screenshots in an issue — the
repo is public.

## Workflow (`.github/workflows/rental-sync.yml`)

- **Triggers:** `schedule` (cron in UTC, e.g. `0 9 * * *` ≈ 5 am Eastern;
  GitHub may start it late) and `workflow_dispatch` with a `dry_run` input.
- **Permissions:** `contents: read`, `issues: write`.
- **Concurrency:** group `libib`, `cancel-in-progress: false` — shared with
  any other Libib workflow.
- **Steps:** checkout → setup-python 3.11 → `pip install playwright` +
  `playwright install --with-deps chromium` → `python -m catalog
  rental-sync --report-file report.md` → `gh issue create` (always, via
  `if: always()` and the exit code).
- **Exit code 3 (login blocked):** issue labelled `libib-login-blocked`,
  body = the local command
  (`.venv-libib/bin/python -m catalog rental-sync`), job marked failed so
  GitHub also emails the failure.
- **Any other failure:** issue with the error tail, job failed.
- **Secrets:** `LIBIB_EMAIL`, `LIBIB_PASSWORD`, `SHOPIFY_CLIENT_ID`,
  `SHOPIFY_CLIENT_SECRET`, `TMDB_API_KEY`. Actions secrets only.
- **No artifacts** — exports and screenshots would be public.
- A repo with no activity for 60 days has its schedules disabled by GitHub;
  re-enable from the Actions tab.

**Email:** the developer watches the repo with email notifications on;
each daily issue and each failed run arrives as an email. No mail service
needed.

## Pipeline changes (existing code)

1. **Legacy Libib tooling skips new-flow copies.** `libib diff` / `fix` /
   `sync` ignore any Libib item whose barcode is `201…` and any Shopify
   rental whose variant barcode is — otherwise they show as orphans/drift.
2. **`apply` may only set the poster on new-flow rentals** — never their
   title, description, Vendor or genre (those come from Libib).
3. **`audit` flags** a new-flow rental that is taxable, on POS, unpublished,
   or whose handle doesn't end in its barcode.

## Build order

| # | Step | Est. hours |
|---|---|---|
| 0 | Spike: selftest workflow on Actions (can GitHub log into Libib?); check/add app scopes; install the app on the dev store | 1–2 |
| 1 | `transform.py` + tests against `exports/2026-10-08` fixtures | 3–4 |
| 2 | Shopify read + barcode compare | 1–2 |
| 3 | TMDB poster step | 1–2 |
| 4 | `create.py` (`productSet`, inventory, publication, verify) + fake-store tests + dev-store runs | 5–8 |
| 5 | `report.py` + issue posting + login-blocked path | 2–3 |
| 6 | Workflow YAML | 1–2 |
| 7 | Pipeline changes 1–3 | 2–3 |
| 8 | Docs: client Libib guide, `catalog/README.md`, `CHECKLIST.md`, `CLAUDE.md` roadmap #3 | 1–2 |
| 9 | Watch the first production runs | 1–2 |
| | **Total** | **18–28** |

If Libib blocks GitHub's servers, the hours don't change but every run falls
back to the developer's machine; automating that locally (launchd) is
about 2–3 more hours.

## Verify on the dev store

1. A created product: correct handle, barcode, untaxed, qty 1, tags
   (`Rental`, `Barcode Not Printed`, extras), genre option + metafield,
   category, poster.
2. It is on Online Store and **not** on Point of Sale.
3. Re-running the job creates nothing new (barcode already present).
4. A copy with no format, no genre and an extra tag is created and every
   problem appears in the issue.
5. Two copies of one Libib item → two products, two barcodes.
6. Login-blocked path: run with bad credentials → exit 3 →
   `libib-login-blocked` issue.

## Open, not in this change

- **Label printing** (old Verify #1): only matters if the client starts
  labelling rentals. Then confirm Retail Barcode Labels prints the existing
  `201…` barcode (not a generated one) and that Libib's Lending page scans it.
- **Updates from Libib** to existing products (decision 3) — add later if
  create-only proves too limiting.
- **Legacy rentals:** after the last ~50 are in Libib, decide whether the
  job's scope widens to all Libib rentals and whether `libib sync` retires.
- **Legacy rentals on POS:** existing rentals are on POS today; removing
  them is a separate bulk action.
