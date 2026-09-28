# Cloud session handoff — 2026-09-28

Work moves from the local Mac to a Claude Code on the web session. This note is
what the cloud session needs to pick up. Read `catalog/README.md` for the full
pipeline; `CLAUDE.md` for the project.

## What works in the cloud today

- `bash scripts/cloud-setup.sh` (the environment's setup script): Playwright +
  Chromium, apt deps with a retry that disables blocked PPAs, and the sandbox
  proxy CA imported into Chromium's NSS store.
- `python3 -m catalog libib check-login` — **passed** from the cloud.
- Every `libib` command, `tmdb-lookup`, `check-upload`, and the test suite
  (`python3 -m unittest discover -s tests/catalog -p "test_*.py"`).
- Secrets come from the environment: `TMDB_API_KEY`, `LIBIB_EMAIL`,
  `LIBIB_PASSWORD`. The repo is **public** — never write a secret into it.

## Shopify reads (cloud step 2 — done 2026-09-28)

- `audit` reads Shopify through the Admin API when `SHOPIFY_CLIENT_ID` and
  `SHOPIFY_CLIENT_SECRET` are set (Dev Dashboard app "read-only", installed on
  production; scopes read_products, read_inventory, read_metaobjects). A fresh
  24-hour token is requested per run. Verified: a full production read through
  the API matched the Shopify CLI read exactly (7,155 products, 0 differences).
  The app is not installed on the dev store.

## Not settled yet

- `picker push` pushes to `main` (the picker and Vercel read `main`; `apply`
  reads picks from `origin/main`). Confirm the cloud session may push to
  `main`; if not, the flow becomes a PR the user merges.
- `runs/` is gitignored. The one run the cloud needs, `runs/2026-09-28/`
  (snapshot, drift, findings), was force-added to git for this handoff. It is
  the latest complete run, so every `libib` command resolves to it.

## Immediate task: finish the Libib renumber run

On 2026-09-28 a `libib fix --drift` run renumbered Libib items still carrying
pre-reprint `191-…` call numbers to their Shopify barcodes (the reprint maps in
`exports/` confirm each old→new pair). It was stopped after 55 of 264 items;
those 55 are recorded in `libib-sync/_state.json`, and the run resumes from the
report in `libib-sync/drift-2026-09-28/`. Preview first:

    python3 -m catalog libib fix --drift --headless \
      --call-number-map exports/9.23-reprint-barcode-map.csv \
      --call-number-map exports/9.23-reprint-barcode-map-mixed-pairs.csv \
      --call-number-map libib-sync/call-number-map-2026-09-28-manual.csv \
      --dry-run

Expect: 212 items, "resuming: 55 … skipped", 208 renumbers, no manual items.
Then run it with `--yes` instead of `--dry-run`. It takes ~2 items/minute
(~1¾ h) — run it in the background and watch the log. Every change is
verified by reloading the item; failures are reported, not retried.

When it finishes: commit `libib-sync/` (state, report, posters) and push to
`main`. If it is stopped again, re-running the same command resumes.

After that the user takes fresh Libib exports (item/barcode + collection) into
`exports/<date>/` and runs `libib diff` to confirm; drift should be near zero.

## Things that bit us (don't rediscover them)

- **Libib's UI changed twice this week** and broke the fixer both times:
  the barcode lock icon moved into the barcode cell, and tags moved into a
  collapsed "Tags / Notes / Group" section of the Edit form. Both are fixed in
  `catalog/libib/browser.py`. If a new wave of identical timeouts appears, stop
  the run and inspect the page read-only before changing selectors.
- The call number field is in the Edit form's collapsed "Catalog Information"
  section (`.anchor[data-section='catalog-section']`).
- Commands that change things ask for approval; with no terminal they need
  `--yes`. Always `--dry-run` first.
- Production (`p0wkgv-wy.myshopify.com`) is the working store. Direct
  production mutations are blocked by the auto-mode permission classifier —
  the user runs those; the pipeline itself only writes CSVs for the user to
  import.
- `shopify.genre` is a category metafield: it only sticks on products whose
  category is `Media > Videos` (the pipeline now sets both together).
- The TMDB genre boost only orders candidates; it never makes a match
  confident (a near-miss title auto-matched the wrong sequel before).

## Open work after the renumber run

- Cloud step 2: Shopify Admin API token reader (`catalog/shopify/reader.py`).
- Libib: 47 held needs-review rentals, 45 orphans, 2 rentals sharing barcode
  `08873722` (frances-vhs-rental-drama / swashbuckler-dvd-rental-action).
- Shopify manual fixes (121 products): see `runs/2026-09-28/findings.csv`
  (bucket `manual`).
- `tmdb-lookup --tag Issue_Needs_New_Barcode`: 119 products (64 ambiguous,
  55 no match) kept their old descriptions; most no-matches are title noise
  ("Vhs", edition names, trailing years) the matcher could learn to strip.
- The client's picker queue (945 ambiguous + 178 unmatched) — `apply` when
  picks come in (needs Shopify access: local until step 2).
