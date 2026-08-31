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

## Generating a new batch

After running `formatting-scripts/run.py` on a catalogue batch and getting
its ambiguous review rows:

```python
import sys
sys.path.insert(0, "formatting-scripts")
from hosted_review_page import write_hosted_picker
import tmdb_fill
from pathlib import Path

fetch_fn = tmdb_fill.make_tmdb_fetcher(API_KEY)
write_hosted_picker(review_rows, Path("tools/review-picker"), "out-my-batch", fetch_fn)
```

Commit and push `tools/review-picker/` — Vercel redeploys, and the new
batch appears on the launcher page automatically.

## When the client finishes a batch

```bash
git pull
python3 formatting-scripts/apply_picks.py \
  tools/review-picker/data/out-my-batch.json \
  catalogue-batches/out-my-batch/upload.csv
```

This is unchanged from the pre-hosted workflow — `apply_picks.py` reads
the exact same pick shape either way.
