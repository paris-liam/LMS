# catalog — Little Movie Store catalogue pipeline

Design: `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md`.
Run everything from the repo root. Standard library only (Libib `fix` will need Playwright).

## Stage 1 — audit (read-only)

    export TMDB_API_KEY=...            # not needed with --skip-tmdb
    python3 -m catalog audit           # production
    python3 -m catalog audit --from-export products_export.csv
    python3 -m catalog audit --store lms-sandbox-lutsfahz.myshopify.com

Shopify is read through the Admin API when `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET`
are set: a Dev Dashboard custom app with read-only scopes (`read_products`,
`read_inventory`, `read_metaobjects`), installed on the store. Each run trades them for a
fresh 24-hour token (client credentials grant) held only in memory. The app is installed
on production only — for another store, install it there too or unset the two variables.
Without them the audit falls back to the Shopify CLI; if that is not authenticated:
`shopify store auth --store <domain> --scopes read_products`.

Writes `runs/<date>/` (a second run the same day gets `-2`, `-3`, …):

| file | contents |
|---|---|
| `snapshot.json` | every audited movie, normalised (archived, retail-template and non-catalogue products excluded) |
| `findings.csv` | one row per problem: `handle, title, type, rule, field, current_value, proposed_value, bucket, detail` |
| `autofix.json` | safe fixes, `{handle: {"changes": {field: value}, "rules": [...]}}` — applied by stage 3 |
| `review.json` | products that need the client in the picker — pushed by stage 2 |
| `run-report.txt` | counts per bucket and rule; written last, so its presence means the run completed |
| `audit.log` | everything printed, plus per-rule detail |

Buckets: **auto-fix** (safe, goes to autofix.json), **picker** (needs the client), **manual** (fix in Shopify admin).
Rental barcodes must be 8 digits and unique across every movie.

Flags: `--skip-tmdb` (no lookups), `--no-cache` (bypass `runs/.tmdb-cache.json`), `-v` / `-q`.

The audit changes nothing outside its run folder except the shared TMDB cache and
promoting picker registry entries from `applied` to `resolved` once Shopify shows the fix.

## Approval

Every command that changes anything outside its run folder shows a plan first and asks
`Proceed? [y/N]`. `--dry-run` shows the plan and changes nothing; `--yes` approves without
asking. Outside a terminal (scripts, agents) the command refuses unless `--yes` is given.

## Stage 2 — picker push

    python3 -m catalog picker push            # uses the latest complete audit run
    python3 -m catalog picker push --dry-run

Adds the run's `review.json` products the registry doesn't know yet to the hosted
picker's `ambiguous-queue` / `unmatched-queue` (fetching TMDB candidates — needs
`TMDB_API_KEY`), marks them `queued`, then commits and pushes `tools/review-picker/`.
It publishes to `main` (Vercel deploys `main`) from whatever branch is checked out — a
cloud session works on its own branch: it merges `origin/main` in, commits, and pushes
`HEAD:main` (a fast-forward, never a force). If the push is refused, the commit stays on
the branch. `--no-git-sync` never commits.

## Stage 3 — apply

    python3 -m catalog apply --dry-run        # see what would change
    python3 -m catalog apply                  # write runs/<id>/import/*.csv, publish imports/<id>/

Combines the run's `autofix.json` with the client's picks (read from `origin/main` — the
branch the picker saves to; `--local-picks` reads the working tree) and writes one CSV per
field group — `image`, `alt-text`, `description`, `genre`, `tags`, `vendor`, `price` —
each with only the columns it changes plus `Handle, Title, Option1 Name, Option1 Value`.
Import each in Shopify admin. `apply-plan.csv` lists every change (handle, field, before,
after, source). Picks become `applied` in the registry; the next audit promotes them to
`resolved` once Shopify shows them, or reports `applied-but-missing`.

The CSVs are also copied to `imports/<run id>/` (tracked), and the registry and that folder
are committed and published to `main` the same way `picker push` publishes — so CSVs made
in a cloud session can be downloaded from GitHub. `--no-git-sync` skips the publish.

`genre.csv` also sets `Product Category` to `Media > Videos` on any movie that lacks it:
`shopify.genre` is a category metafield, and Shopify silently drops it on products in
any other category (or none). Import `image.csv` before `alt-text.csv`. Hold `genre.csv`
only when it changes Option1 — `apply` warns when it does.

## Stage 4 — Libib

Libib has no API: its exports and CSV imports are manual; only fixing items runs in a browser.

    # 1. Export from Libib: the item/barcode export and the collection export (both needed).
    python3 -m catalog libib diff --barcode-export libib_barcodes.csv --collection-export libib_collections.csv
    # -> runs/<id>/libib/: drift.csv, eligible.csv, orphans.csv, blocked.csv, libib-report.txt

    python3 -m catalog libib prepare --size 200     # -> libib-sync/batch-NNNN/{import.csv, posters, ready.csv}
    # 2. In Libib: Add Items -> CSV -> import.csv with Force Import Mode on.
    python3 -m catalog libib mark-imported batch-NNNN
    .venv-libib/bin/python -m catalog libib fix batch-NNNN      # barcode + title/description/tags/poster
    .venv-libib/bin/python -m catalog libib fix --drift         # fix what the diff found drifted
    python3 -m catalog libib status

`fix` needs `LIBIB_EMAIL` / `LIBIB_PASSWORD` and the Playwright venv. Items are matched by
Shopify barcode = Libib call number (items without a call number fall back to their copy
barcode; that drift needs a manual fix). Rentals with a bad or shared barcode are `blocked`
until the audit's barcode findings are fixed. Orphans are listed, never deleted.
`diff` promotes in-sync handles to `done` in `libib-sync/_state.json` and keeps the previous
state as `runs/<id>/libib/state-before.json`.

## Running in the cloud

    bash scripts/cloud-setup.sh                 # Python check, Playwright + Chromium, proxy CA for Chromium
    python3 -m catalog libib check-login        # read-only: log in headless, open one synced item

Set `TMDB_API_KEY`, `LIBIB_EMAIL` and `LIBIB_PASSWORD` in the environment's secret
settings (never in the repo — it is public). On a cloud box use `python3`, not
`.venv-libib/bin/python`, and pass `--headless` to `libib fix`. `check-login` exits 1
and saves `libib-login-check.png` when Libib challenges or blocks the machine.
Add `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` too, and `audit` reads Shopify from
the cloud through the Admin API (no Shopify CLI needed).

## TMDB lookup by tag (not a pipeline stage)

    python3 -m catalog tmdb-lookup --tag "Criterion Collection"

Runs only the audit's TMDB matcher over the latest run's snapshot, for every movie
carrying that tag — including ones that already have a poster — and writes
`runs/<id>/tmdb-lookup-<tag>.csv` (match, TMDB title/year/id, poster URL, overview).
Read-only: nothing is applied or queued. Re-run `audit` first for fresh Shopify data.

## Client upload sheet (not a pipeline stage)

`catalog/client_sheet/template/` holds the client's Google Sheet scaffold, the tab-2
formula, `genre-mappings.csv` and the client guide.

    python3 -m catalog check-upload <sheet.csv>     # exit 0 clean, 1 problems, 2 unreadable
    python3 -m catalog.client_sheet.generate_expected   # after a taxonomy change

## Secrets

`TMDB_API_KEY`, `LIBIB_EMAIL` and `LIBIB_PASSWORD` are read from the gitignored `.env` at the
repo root (see `.env.example`); an exported variable wins over the file.

## Tests

    python3 -m unittest discover -s tests/catalog -p "test_*.py"
