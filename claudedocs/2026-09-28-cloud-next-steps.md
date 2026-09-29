# Cloud next steps — after the Libib renumber run

For the user and the cloud session, once the renumber run started from
`claudedocs/2026-09-28-cloud-handoff.md` has finished. Read that doc too: it
holds the cloud working rules and the things that bit us.

## Paste this into a new cloud session

> Read `claudedocs/2026-09-28-cloud-handoff.md` and
> `claudedocs/2026-09-28-cloud-next-steps.md`, then do "Step 1" in the
> next-steps doc. Stop and report after each step; don't start the next one
> until I say so.

## Step 1 — land the renumber run on `main`

The run checkpointed to branch `claude/friendly-darwin-nc0g40`, not `main`.

1. Confirm the run finished: the last lines of its log say
   `N fixed, M need review`, and `libib-sync/drift-2026-09-28/ready.sync-report.csv`
   has a row for every item in `ready.csv`.
2. Commit anything left in `libib-sync/` on that branch.
3. `git fetch origin && git merge origin/main` (main gained the Admin API
   reader and the publish-to-main changes since the branch started). The
   branch only touches `libib-sync/`, so expect no conflicts; if one appears
   in `libib-sync/_state.json`, stop and report — don't pick a side.
4. Run the tests: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`.
5. `git push origin HEAD:main`. This also answers whether cloud sessions may
   push to `main` (decided: they should). If it is refused, report the error.
6. Report: fixed / needs-review counts, and any `error` rows in the report.

## Step 2 — the user: fresh Libib exports

In Libib, export the item/barcode CSV and the collection CSV. Put both in
`exports/<YYYY-MM-DD>/`, then commit and push to `main` (as done on
2026-09-28). Tell the cloud session the folder name.

## Step 3 — confirm Libib matches Shopify

Start of session rule: always audit first.

    python3 -m catalog audit
    python3 -m catalog libib diff --barcode-export exports/<date>/<barcodes file> \
        --collection-export exports/<date>/<library file>

- The audit should say it read Shopify through the **Admin API** (needs the
  `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` secrets). A failure here is a
  setup problem — report it rather than falling back.
- Expect the old-call-number drift (~246 items) to be gone and drift overall
  to be small. Report the diff summary.
- If fixable drift remains: `libib fix --drift --headless --dry-run`, show the
  plan, and wait for approval before `--approve <code>`. It resumes if stopped.
- Commit `libib-sync/` and push to `main`.

## Step 4 — prove the publish path

- `python3 -m catalog picker push --dry-run` — report how many new cards it
  would add. Only run it for real with the user's approval; it publishes to
  the live picker (Vercel deploys `main`).
- `python3 -m catalog apply --dry-run` — if it lists changes, show them and,
  with approval, run it. Its CSVs land in `imports/<run id>/` on `main`; the
  user downloads them from GitHub and imports them in Shopify admin with
  "Overwrite products with matching handles" on.

## After that — open work (pick with the user)

- **Libib people-decisions:** 47 held needs-review rentals
  (`runs/<id>/libib/held.csv`), 45 orphans (`orphans.csv`), and the 2 rentals
  sharing barcode `08873722` (frances-vhs-rental-drama /
  swashbuckler-dvd-rental-action) — one needs a new label in Shopify.
- **Shopify manual fixes:** the audit's `manual` bucket in
  `runs/<id>/findings.csv` (121 products on 2026-09-28: missing genre, missing
  Rental/Floor Sale tag, untracked inventory, missing format, priced rentals,
  $0 floor sale).
- **TMDB title noise:** `tmdb-lookup --tag Issue_Needs_New_Barcode` found 55
  no-matches, mostly titles carrying "Vhs", edition names or a bare year;
  teaching `catalog/tmdb/match.py` to strip those would improve every audit.
- **Client picker queue:** 945 ambiguous + 178 unmatched cards; run `apply`
  when picks come in.
- **Optional cloud automation:** Libib export download via Playwright
  (fragile — Libib's pages changed twice this week); scheduled audit / diff
  via GitHub Actions.

## Rules to keep

- One writer for `libib-sync/_state.json` at a time: don't run Libib commands
  on the Mac while a cloud session is.
- `--dry-run` before anything that changes Libib, the picker, or the registry.
- Never write a secret into the repo (it is public); secrets live in the
  environment.
- Production (`p0wkgv-wy.myshopify.com`) is the working store; the pipeline
  only reads it. Shopify changes go through CSVs the user imports.
