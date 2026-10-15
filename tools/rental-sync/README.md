# Rental sync app

The client's page for turning new Libib rentals into Shopify products.
Design: `docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`.
Client instructions: `client-guide.md`.

## Layout

- `tools/rental-sync/` — the page (no build step): `index.html`, `app.js`, `logic.js`, `styles.css`, `guide/`.
- `api/rental_sync/*.py` — Vercel Python functions, three lines each, all calling
  `catalog/rental_sync/web.py`. Logic and tests live in `catalog/rental_sync/`.
- `vercel.json` / `.vercelignore` (repo root) — function config, the `/` rewrite, security
  headers, and a deploy allow-list (only `api/`, `catalog/`, `tools/rental-sync/`).
- Only tracked files reach a Git deployment; a CLI `vercel deploy` uploads the working tree, so never
  run it from a checkout with secrets or exports inside the allowed folders.

## Vercel project (one-time)

Root Directory = repo root, Framework = Other, no build. Env vars (Preview + Production):
`SYNC_PASSWORD`, `SESSION_SECRET`, `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`,
`TMDB_API_KEY`. `SHOPIFY_STORE` decides which store products are created in.
The review picker is a separate Vercel project rooted at `tools/review-picker`.

## Shopify app scopes

read/write_products, read/write_inventory, read_locations, read/write_publications,
read_metaobjects — installed on whichever store `SHOPIFY_STORE` names.

## Before the first deploy

Capture the two Libib export screenshots the upload guide shows:
`tools/rental-sync/guide/export-barcodes.png` and `export-library.png` (Libib → Settings →
Export Barcode Data / Export Collection Data with Rental Library selected; crop out the account
email; never click anything else on that page — it also holds Delete Collections).

## Password and sessions

Sessions are signed with `SESSION_SECRET` and last 12 hours. Changing `SYNC_PASSWORD` does not
log out existing sessions — rotate `SESSION_SECRET` as well to end them.
After changing the Shopify app's scopes, redeploy so warm functions drop their cached token.

## Tests

    python3 -m unittest discover -s tests/catalog -p "test_rental_sync_*.py"
    node --test tests/rental_sync/*.test.js

## Logs

Vercel → project → Logs: one line per created copy (barcode, status, title, message).
Never the password, cookie or tokens.
