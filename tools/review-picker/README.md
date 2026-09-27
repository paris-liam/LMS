# Hosted review picker

Lets the client pick TMDB matches from a public URL. Picks are committed
straight into this repo (`tools/review-picker/data/<batch>.json`) — no
database, no manual JSON export/import.

See `docs/superpowers/specs/2026-08-30-hosted-review-picker-design.md` for
the full design.

## Deploying (one-time setup)

1. In Vercel, "Add New Project" → import `paris-liam/LMS`.
2. Set **Root Directory** to `tools/review-picker`.
3. Framework preset: **Other** (no build step).
4. Environment variables (Production + Preview):
   - `GITHUB_TOKEN` — a fine-grained GitHub PAT scoped to **only**
     `paris-liam/LMS`, permission **Contents: Read and write**, nothing else.
   - `GITHUB_OWNER` — `paris-liam` (optional; this is also the default)
   - `GITHUB_REPO` — `LMS` (optional; this is also the default)
   - `GITHUB_BRANCH` — the branch this Vercel project deploys from (optional; defaults to `main`)
5. Deploy. Every push to the connected branch redeploys automatically.

## Adding products to the picker

The audit decides which products need the client; `picker push` publishes them:

```bash
python3 -m catalog audit                 # writes runs/<date>/review.json
python3 -m catalog picker push           # appends to ambiguous-queue / unmatched-queue, commits + pushes (on main)
```

New cards land in the two evergreen queues; `data/_handle-index.json` records every
handle ever queued so nothing is asked twice.

## Applying the client's picks

```bash
python3 -m catalog apply --dry-run       # reads picks from origin/main, shows the plan
python3 -m catalog apply                 # writes runs/<date>/import/*.csv to import in Shopify admin
```

See `catalog/README.md`.
