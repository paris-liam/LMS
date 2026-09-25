# catalog — Little Movie Store catalogue pipeline

Design: `docs/superpowers/specs/2026-09-25-catalog-pipeline-design.md`.
Run everything from the repo root. Standard library only (Libib `fix` will need Playwright).

## Stage 1 — audit (read-only)

    export TMDB_API_KEY=...            # not needed with --skip-tmdb
    python3 -m catalog audit           # production, via the Shopify CLI
    python3 -m catalog audit --from-export products_export.csv
    python3 -m catalog audit --store lms-sandbox-lutsfahz.myshopify.com

If the CLI is not authenticated: `shopify store auth --store <domain> --scopes read_products`.

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

## Tests

    python3 -m unittest discover -s tests/catalog -p "test_*.py"
