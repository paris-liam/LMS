# Libib/Shopify Automation Roadmap

Captured 2026-09-19. This is a planning doc, not a build plan — nothing
here is implemented yet. See `LIBIB_MIGRATION_PROGRESS.md` for the actual
migration's current status.

## Where automation could run

The current pipeline (`formatting-scripts/libib_sync*.py`) runs locally,
driven interactively. Two separate questions came up: *where* it runs, and
*what else* it should eventually cover.

### Running it in the cloud

Feasible — Playwright is designed to run headless in CI/cloud environments,
and today's network flakiness (repeated `ERR_NETWORK_CHANGED` errors mid-run)
is exactly the kind of thing a more stable cloud runner would likely fix.

Options, roughly by how much new infrastructure they need:
1. **GitHub Actions** — lowest lift, this repo already has `.github/workflows/`.
   A workflow on `workflow_dispatch` (manual trigger) or a schedule, checking
   out the repo, installing Playwright + Chromium, running
   `libib_sync.py sync <batch>`. State (`libib-sync/_state.json`) lives in
   the repo like it does now.
2. **A small cloud VM/container** (Fly.io, Railway, a cheap VPS) if an
   always-on or non-git-triggered setup is wanted.
3. **This tool's own remote/cloud session support**, if available on the
   account — same orchestration as now, just not running on a laptop.

**Security note for whenever this happens**: credentials are currently
hardcoded in `libib_sync_fix.py` (`LIBIB_EMAIL`/`LIBIB_PASSWORD`), which was
an explicit choice while everything ran locally in a private repo. Before
running anywhere shared (a CI runner, any place with logs another person
could see), these should move to a secret/environment variable instead.

**What cloud hosting does *not* solve**: Libib has no import API at all, so
CSV export → force-import → fresh-export stays a manual loop regardless of
where the automation runs. Cloud hosting only speeds up/stabilizes the
`sync`/`prepare`/`reverify-posters` steps.

## What else might get automated

Four candidate automations were discussed, roughly split by whether they
need Playwright (Libib has no API, so anything touching Libib does) or can
be done through Shopify's real Admin API (no browser automation needed).

### 1. Routine Shopify → Libib sync
**Feasible — already built.** This is exactly what `libib_sync.py` does
today (audit → queue → prepare → sync → verify). Open questions are just
cadence and how much runs unattended — see the import-step risk below.

### 1a. Catch malformed Shopify uploads
**Feasible, cheapest of the four, no Playwright at all.** The client
periodically uploads products to Shopify with missing/bad fields. This is
pure Shopify-data validation — already partially covered by
`libib_fields.is_complete()` (checks the 7 required fields), but should be
broadened past "is it present" to "is it sane," given what surfaced this
session:
- **Duplicate `Variant Barcode` across different products** — a live,
  already-confirmed problem (13 pairs found 2026-09-19).
- **`Vendor` outside the known-format whitelist**
  (`VHS/DVD/BLU-RAY/4K/LASERDISC/BETAMAX`).
- Possibly a call-number format check (8-digit), to catch the next
  `191-XXX`-style situation before it's 40 items deep.

**Recommended first thing to build** — smallest, no unknowns, directly
prevents the next data-quality fire.

### 2. Libib lending status → Shopify stock status
**Feasible — data source confirmed 2026-09-19.** Libib Pro has a
`Reports → Current Checkouts` CSV ("returns all actively checked out
items", ignores the date range; docs: support.libib.com/libib/website/reports).
That is a stable file download, not a DOM scrape, so the Libib-read half
is a Playwright login + one report download. Everything else is plain
Shopify Admin API.

**Shape:**
```
every N min (GitHub Actions cron or local launchd)
  Playwright: login → Reports → Current Checkouts (all collections) → CSV
  out_set = barcodes in the report
  all_set = barcodes in the Rental collection (libib-barcode export, cached)
  in_set  = all_set − out_set
  diff against last run's state → only the barcodes that changed
  Shopify Admin GraphQL: productVariants(query: "barcode:NNNNNNNN")
                        → inventorySetQuantities 0 | 1
  write state + last_success_at (also stamped to a shop metafield)
```

- **Join key already exists:** Libib copy `barcode == call_number ==
  Shopify variant.barcode` (8 digits, one product per copy). No new
  mapping.
- **Write inventory quantity (0/1), not a metafield.** Quantity lights up
  "sold out" on product cards and Search & Discovery's built-in
  availability filter for free — the filter the old back-in-stock plan
  never got working. The movie PDP is read-only, so there is no checkout
  side-effect.
- **Shopify side needs no Playwright.** Diff sizes are a few dozen rows
  per run; API rate limits are a non-issue.

**Caveats / design constraints:**

| Issue | Mitigation |
|---|---|
| Polling, not events — lag = cron interval (Actions realistically 10–15 min) | PDP shows "as of HH:MM" from the stamped shop metafield; keep the Libib published-site "Check availability" link as the live fallback (see `claudedocs/2026-09-19-libib-barcodes-and-published-site.md`) |
| Report columns unverified — docs say "with patron info", not which item columns | One manual download to confirm it carries `barcode`/`call_number`. Fallback: scrape `Lending → Checkouts` (per-row Check In button ⇒ barcode is in the DOM) |
| Overwrites client-set inventory on Rental products | Only write to products whose barcode is present in the Libib export; Floor Sale never touched |
| Silent staleness if the job dies | PDP hides the stock badge when `last_success_at` is older than 2× the interval |
| Credentials hardcoded in `libib_sync_fix.py` | Move to secrets before any scheduled run (see security note above) |
| Libib login churn | Persist Playwright storage state; re-login only on failure |
| Duplicate 8-digit barcodes (13 pairs, `duplicate-barcode.csv`) | Skip and log until relabelled |

**Effort estimate:** ~½ day report-download step (reuses the existing
Playwright session code), ~½ day Shopify diff-writer, ~½ day scheduling +
freshness stamp + PDP badge. Only unknown is the report's columns — a
two-minute check on the live account.

**Hold until** Shopify is actually live as the client-facing inventory
page, and until the 8-digit barcode scan verification in the barcodes doc
has passed (the same join key this depends on).

### 3. Shopify member ↔ Libib patron sync check
**Feasible as a periodic audit, but depends on an unanswered question**:
how does patron creation currently happen when someone signs up in
Shopify? Is it a real automated integration already (an app, a Shopify
Flow, a webhook), or is someone doing it by hand? That changes the
priority a lot — if manual, this check is the only safety net that
exists; if automated, it's a drift-detector for silent failures.
Mechanically it's the same audit pattern as everything else: pull
Shopify's active-member customer list via API, pull Libib's patron list
(Libib supports patrons as first-class records with their own barcodes,
so likely has a similar export — not yet confirmed), match by email, flag
mismatches. No Playwright needed unless Libib turns out to have no patron
export at all.

**Needs a conversation first**: how does patron creation actually work today.

## Recommended priority order

1. **1a** — cheap, no unknowns, prevents the next data-quality fire.
2. **1** — already built; wrap in a schedule + decide the import-gate policy.
3. **3** — depends on how patron creation works today; clarify that first.
4. **2** — data source now confirmed (Current Checkouts report); hold until
   Shopify is serving as the client-facing inventory page and the 8-digit
   scan verification has passed.

## Open design question: how automated should the import step get?

Even in a fully-scheduled setup, **importing new batches should probably
stay a human-gated step**, even if the mechanics (CSV upload → Force
Import Mode → confirm) are automatable via Playwright. Everything else in
the pipeline only *fixes* data already in Libib — idempotent, safe to
retry, reversible. Import is the one step that *creates* new live data at
scale; a bad CSV slipping through unattended on a schedule could silently
create hundreds of bad entries before anyone noticed, and Libib has no
bulk-undo for that.

Suggested shape: fully automate export → audit → queue → prepare → sync →
re-export → verify (all read/fix operations, safe unattended), but have
the daily job stage the next batch and notify for approval rather than
force-importing on its own.
