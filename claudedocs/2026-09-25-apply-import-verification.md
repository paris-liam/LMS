# Apply — dry runs and dev-store import verification (2026-09-25/26)

Plan: `docs/superpowers/plans/2026-09-25-catalog-pipeline-2-picker-apply.md` (Task 12).

## Production dry runs (read-only), audit run `2026-09-25-2`

`python3 -m catalog picker push --dry-run`
- ambiguous-queue: +47 cards, unmatched-queue: +9 cards (56 = the run's `review.json`)
- registry: 56 handles -> queued; git: commit + push on `main`
- nothing changed

`python3 -m catalog apply --dry-run`
- 87 picks read from `origin/main` (the evergreen queues hold no picks yet; 85 `skip` + 2 empty `manual` from the older 8.31 / 9.2 batches)
- `import/image.csv` 82 · `import/alt-text.csv` 4 · `import/description.csv` 82 · `import/genre.csv` 136
- 386 changes, all auto-fix; registry: 85 -> skipped; 2 ignored (empty manual picks)
- `genre.csv` is 136 **metafield-only** genre fixes (no Option1 change) — so after the Task 12 fix the Option1 warning no longer fires for it
- nothing changed

## Dev-store check (`lms-sandbox-lutsfahz`)

The dev store has no product with a barcode or tracked inventory, so only the alt-text check was run (the user chose this; production has no Option1 fixes pending).

### Alt-text restating `Image Src` — PASS

File: `runs/devcheck/alt-text.csv` (built with `build_import_files`, exactly as `apply` does), product `a-quiet-place-4k-floor-sale`, imported by the user with "Overwrite products with matching handles".

| | before | after |
|---|---|---|
| media count | 1 | 1 |
| image URL | `…/nAU74GmpUk7t5iklEp3bufwDq4n_cdbbda2d-…jpg?v=1789147900` | same |
| alt text | `A Quiet Place poster` | `A Quiet Place poster (devcheck)` |
| Option1 | Genre / Horror | Genre / Horror |
| price | 16.00 | 16.00 |

Restating the existing `Image Src` does **not** duplicate the image; only the alt text changed.

### Option1 change — NOT RUN

Deferred until an audit actually proposes an `option1-genre` fix on production. The `genre.csv` Option1 warning stays active for that case; running the check then needs a dev product with a test barcode and tracked inventory.

The `alt-text.csv` warning text is unchanged (it points here); removing it is the user's call.
