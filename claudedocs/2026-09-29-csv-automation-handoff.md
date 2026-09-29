# Handoff — automating Libib & Shopify CSV import/export

Written 2026-09-29 for a new cloud session. Read `claudedocs/2026-09-28-cloud-handoff.md`
and `CLAUDE.md` first for the working rules and project context.

## Status (2026-09-29, end of day)

Done — see `catalog/README.md` (Approval, Stage 3, Stage 4):

- **Libib exports**: `libib export` (Playwright, Settings → Export).
- **Libib imports**: `libib import <batch>` (CSV Import, Force Import Mode,
  waits for Libib's background import, never uploads a batch twice).
- **One command for the Libib round trip**: `libib sync`.
- **Shopify writes**: `apply` writes through the Admin API by default
  (`--via csv` keeps the old import files), skipping fields changed since the
  audit and verifying every write by reading it back.
- **Approval**: every mutating command lists every change; outside a terminal
  it needs `--approve <code>` from a `--dry-run` of the same list (no `--yes`).
- **Health check**: `libib selftest` (read-only) — run it periodically.

## Goal

Find every place the catalogue pipeline relies on a person moving a CSV by hand
(Libib or Shopify), and design/implement automation for it.

## Where CSVs are still manual today

1. **Libib exports (manual).** The user downloads the item/barcode CSV and the
   collection CSV from Libib and pushes them to `exports/<YYYY-MM-DD>/`.
   Every `libib diff` depends on them. Automating means driving Libib's export
   pages with Playwright — possible, but fragile: Libib's UI changed twice in
   the week of 2026-09-21 and broke the fixer both times
   (see "Things that bit us" in the cloud handoff).
2. **Libib imports (manual).** `python3 -m catalog libib prepare` writes a
   batch `import.csv` (+ `ready.csv`, posters) under `libib-sync/batch-NNNN/`;
   the user imports `import.csv` through Libib's UI, then `libib fix <batch>`
   fixes barcodes/content in the browser.
3. **Shopify imports (manual).** `apply` and ad-hoc fixes write narrow CSVs to
   `imports/<run id>/` (one per field group; see `catalog/apply/csv_groups.py`)
   that the user imports in Shopify admin with "Overwrite products with
   matching handles". Since 2026-09-28 the Dev Dashboard app has
   `write_products` (and many more scopes), so these could become direct
   Admin API writes. Tags (`tagsAdd`/`tagsRemove`), Vendor (`productUpdate`),
   category, genre option value (`productOptionUpdate`) and the
   `shopify.genre` metafield (`metafieldsSet`) were all written directly on
   2026-09-28/29 and verified by reading back.
4. **Shopify reads — already automated.** `audit` reads through the Admin API
   (`catalog/shopify/api.py`, client-credentials token per run).

Likely order: (3) is the easiest, highest-value win; (1) is the riskiest.

## Relevant code

- `catalog/libib/` — diff, prepare, fix (Playwright in `browser.py`), state
- `catalog/apply/` — picks → narrow import CSVs
- `catalog/shopify/api.py`, `reader.py` — Admin API client
- `catalog/README.md` — pipeline stages and commands

## Rules while another session is working in Libib

A separate session is (as of writing) running the category-7 Libib import
batch and fixer. Until it's finished:

- **OK now:** reading code, mapping CSV touchpoints, design, writing a plan in
  `claudedocs/`, building + unit-testing on a separate branch without touching
  live systems.
- **Wait:** anything that logs into Libib (libib commands, test Playwright
  scripts, export downloads) — two sessions on one Libib account can collide;
  anything that writes `libib-sync/_state.json` (one writer at a time);
  Shopify writes via the Admin API; pushes to `main` touching `libib-sync/`,
  `exports/` or `imports/`.

## Standing rules (from the cloud handoff)

- `--dry-run` / preview before anything that changes Libib, the picker, the
  registry or Shopify.
- Never write a secret into the repo (it's public).
- Production (`p0wkgv-wy.myshopify.com`) is the working store.
- Note: the app's token now has ~150 scopes; the recommendation is to narrow it
  to `read_products`, `read_inventory`, `read_metaobjects`, `write_products`
  (+ `write_inventory` if inventory writes are automated).
