# Catalog pipeline — design

Date: 2026-09-25
Status: approved in brainstorming, pending written-spec review
Replaces: `formatting-scripts/` (and its README), `tests/formatting_scripts/`, `tests/data_cleanup/`
Supersedes as the operating process: `docs/superpowers/specs/2026-08-11-catalogue-format-script-design.md`,
`docs/superpowers/specs/2026-08-30-hosted-review-picker-design.md` (picker behaviour carries over, its generator moves)

## 1. Purpose

`formatting-scripts/` grew one script per problem: an intake pipeline, several one-off batch
tools, two generations of review-picker page, and a Libib sync bolted on beside them. It has
three copies of the picker HTML, three `strip_html`s, hardcoded credentials, a dead test
directory, and no tests for any Libib code.

Replace it with one package, `catalog/`, organised around the four things the store actually
needs to do, in order:

1. **Audit** the Shopify movie catalogue: find every product that is mis-formatted or
   incomplete, fix what is safe to fix, and sort the rest.
2. **Picker push**: put the products that need the client's judgement into the hosted review
   picker.
3. **Apply**: turn safe fixes + the client's picks into Shopify import CSVs.
4. **Libib**: compare Libib against Shopify, prepare uploads for missing items, report drift,
   and (on request) fix drift.

### Success criteria

- Each stage is one command with defined file inputs and outputs, runnable on its own.
- Each stage lives in its own module with its own tests; shared rules are defined once.
- No stage changes anything outside its own run folder without showing a plan and getting
  approval. The only exceptions are the idempotent status promotions `audit` and `libib diff`
  make to record what Shopify/Libib already show (§4, §7), plus the shared TMDB cache.
- Every run shows live progress and leaves a log.
- No credentials in source.
- A read-only audit against production reproduces the known data-quality counts (§10).

### Decisions made in brainstorming

| Decision | Choice |
|---|---|
| Shopify I/O | Read via Admin API (`shopify store execute`); write via CSV the operator imports by hand |
| Audit behaviour | Auto-fix what is safe; everything else goes to the picker or the report |
| New-product intake (template shape) | Dropped. Audit runs after the client uploads. A pre-import mode is possible future work (§11) |
| Scope | Audit every movie (Rental + Floor Sale); only Rentals flow to Libib |
| Picker | TMDB poster/description only for now; pick schema reserves room for genre/type/format/price |
| Libib drift | Reported by `diff`; fixed only by an explicit `libib fix` |
| Code shape | One package, single CLI (`python3 -m catalog …`) |

## 2. Architecture

```
 Shopify (prod) ──API read──▶ [1 audit] ──▶ runs/<date>/
                                              snapshot.json   normalized movie rows
                                              findings.csv    one row per problem
                                              autofix.json    safe fixes (field → value)
                                              review.json     products needing the picker
                                              audit.log, run-report.txt
                                                   │
                         [2 picker push] ◀─────────┘  → tools/review-picker queues + git sync
                                │
                        client picks on Vercel
                                │
                         [3 apply] ──▶ runs/<date>/import/*.csv ──▶ operator imports in Shopify admin
                                ▼
                         next [1 audit] confirms the fixes landed

 Libib exports (manual) ─▶ [4 libib diff]      reads latest snapshot ─▶ drift.csv, eligible.csv, orphans.csv
                           [4 libib prepare]   ─▶ libib-sync/batch-NNNN/
                           [4 libib mark-imported <batch>]
                           [4 libib fix <batch> | --drift]   (Playwright)
                           [4 libib status]
```

### Package layout

```
catalog/
  __main__.py        entry point → cli.main()
  cli.py             argparse subcommands, dispatch only
  config.py          store domain default, paths, env-var names
  core/
    taxonomy.py      genres, formats, types, alias tables (from taxonomy.py)
    columns.py       Shopify column names, fixed values (from columns.py; template contract kept for client_sheet)
    handles.py       handle derivation (from handles.py; used by client_sheet)
    csv_io.py        load/write CSV, group by handle (from catalog_common.py)
    text.py          the one strip_html / norm_ws
    runs.py          run-folder creation and "latest run" resolution
    log.py           logging setup (§8)
    plan.py          Plan object, render, confirm prompt (§9)
  shopify/
    reader.py        paginated GraphQL via `shopify store execute --json` → snapshot rows
    export_reader.py Shopify export CSV → snapshot rows (--from-export)
    queries/products.graphql
  tmdb/
    match.py         matcher (from tmdb_fill.py: clean title, classify_match, tiebreaks, cutoffs)
    client.py        HTTP fetcher; reads TMDB_API_KEY
    cache.py         shared on-disk cache, periodic save
    candidates.py    picker candidate ranking (from review_page.fetch_candidates/collect_products)
  audit/
    resolvers.py     type/format/genre/price resolution (from resolve.py)
    rules.py         rule functions: row → [Finding]
    autofix.py       Finding → proposed field changes
    run.py           orchestrates a run; writes the run folder
  picker/
    schema.py        pick format, parse/validate
    registry.py      _handle-index.json (from review_registry.py, new statuses)
    queues.py        append to evergreen queues, manifest, launcher (from hosted_review_page.py)
    page.html        picker page template (HTML/JS moved out of the Python f-string)
    launcher.html
    git_sync.py      (from git_sync.py, unchanged behaviour)
    push.py          the `picker push` stage
  apply/
    merge.py         autofix + picks, checked against the snapshot
    csv_groups.py    changes → narrow import CSVs grouped by field set
    run.py           the `apply` stage
  libib/
    fields.py        completeness + comparison rules (from libib_fields.py)
    columns.py       Libib Movie CSV columns (from libib_export.py)
    diff.py          pure diff: snapshot rentals × Libib exports → categories
    prepare.py       batch builder (import.csv, posters, ready.csv)
    state.py         _state.json (from libib_sync_state.py, simplified)
    browser.py       Playwright page operations (from libib_sync_fix.py)
    fix.py           the `libib fix` stage; imports Playwright lazily
  client_sheet/
    transform.py     (from sheet_transform.py)
    check.py         (from check_upload.py) → `python3 -m catalog check-upload <csv>`
    template/        (from formatting-scripts/client-template/, contents unchanged)
  README.md
```

### Boundaries

- Stages communicate **only through files** (run folder, picker data, Libib state). No stage
  module imports another stage module; all may import `core/`, `tmdb/`, `shopify/`.
- `audit/rules.py`, `apply/merge.py`, `apply/csv_groups.py`, `libib/diff.py` are pure
  (data in, data out) and carry the bulk of the tests.
- Only `libib/fix.py` imports Playwright, and only inside the command. Everything else is
  standard library only.
- `client_sheet/` is the client-side upload tooling. It shares `core/` but is not a pipeline
  stage.

### Runs

- `audit` creates `runs/<YYYY-MM-DD>/` (suffix `-2`, `-3` for a second run the same day).
- Later stages default to the latest run; `--run <id>` selects another.
- `runs/` is gitignored; it is local working data. (Snapshots contain only catalogue data
  already in Shopify.)
- The TMDB cache lives at `runs/.tmdb-cache.json`, shared across runs.

### Configuration and secrets

- `config.py` defaults the store to production `p0wkgv-wy.myshopify.com` (per CLAUDE.md's
  temporary "production is the working store" rule); `--store` overrides.
- Secrets come only from env vars: `TMDB_API_KEY`, `LIBIB_EMAIL`, `LIBIB_PASSWORD`. A command
  that needs a missing one stops and names it.
- The pipeline never writes to Shopify. Only `read_products` scope is needed.

## 3. Snapshot rows

Every product is normalized to a dict keyed by **Shopify export column names**, so the API
path and `--from-export` path produce identical rows and the existing resolvers work
unchanged:

`Handle, Title, Body (HTML), Vendor, Tags, Status, Template Suffix, Image Src, Image Alt Text,
Option1 Name, Option1 Value, Variant Price, Variant Barcode, Variant Inventory Tracker,
Variant Count, Genre (product.metafields.shopify.genre)`

- Genre metafield: the referenced metaobjects' handles, joined `"; "` (matches export format).
- `Variant Count`: number of variants (the export path counts variant rows per handle).
- `Variant Barcode` is always a string; leading zeros preserved.
- `export_reader` accepts `Variant Barcode` or `Variant Barcodes`.
- Products with `Template Suffix == "retail"` are excluded from the snapshot (membership plans,
  shirt, sticker). The export path has no template column; it falls back to the current
  `is_non_catalogue_product` check (Supercycle vendor / `online-store` tag).

## 4. Stage 1 — audit

```
python3 -m catalog audit [--store <domain>] [--from-export <csv>] [--skip-tmdb] [--no-cache]
```

1. Read the snapshot (API or export) → `snapshot.json`.
2. Load the picker registry; promote `applied` handles whose fix is now visible in the snapshot
   to `resolved`; flag the rest (see `applied-but-missing`). Registry writes from audit are
   limited to this promotion, which only records what Shopify already shows. (This is the one
   write outside the run folder audit makes; it is idempotent and needs no approval.)
3. Run every rule over every row → findings.
4. For products missing poster and/or description **and not already queued/applied/skipped/
   resolved in the registry**, run the TMDB matcher: confident → auto-fix; ambiguous or no
   match → picker.
5. Write `findings.csv`, `autofix.json`, `review.json`, `run-report.txt`, `audit.log`.

### Findings

`findings.csv`: `handle, title, type, rule, field, current_value, proposed_value, bucket, detail`.
Products with no findings are omitted. `bucket` is exactly one of:

**auto-fix** (also written to `autofix.json`)

| rule | fix |
|---|---|
| `genre-alias` | misspelt genre tag / Option1 → canonical label |
| `genre-metafield-sync` | metafield empty or disagrees with canonical genre tags → recomputed handles |
| `format-alias` | Vendor alias (`bluray`, `laser disc`, …) → canonical format |
| `alt-text-missing` | image present, alt text empty → `"<Title> poster"` |
| `rental-price-blank` | Rental with blank price → `0` |
| `poster-missing` (confident TMDB) | TMDB poster URL + alt text |
| `description-missing` (confident TMDB) | `<p>overview</p>` |

**picker** (written to `review.json`)

| rule | when |
|---|---|
| `poster-missing` / `description-missing` | TMDB match ambiguous (→ `ambiguous-queue`) or none (→ `unmatched-queue`) |

**manual** (report only)

| rule | when |
|---|---|
| `type-missing` / `type-conflict` | no Rental/Floor Sale tag, or both |
| `format-missing` | no recognisable format in Vendor/Option1/tags |
| `genre-missing` | no recognisable genre anywhere |
| `floor-sale-price` | Floor Sale price missing, 0, or negative |
| `rental-price-nonzero` | Rental with a nonzero price |
| `price-unreadable` | price not a number |
| `multiple-variants` | Variant Count > 1 |
| `inventory-untracked` | tracker ≠ `shopify` |
| `rental-barcode-missing` | Rental with no barcode |
| `rental-barcode-format` | Rental barcode not `^[0-9]{8}$` |
| `rental-barcode-duplicate` | Rental barcode also on **any** other movie (Rental or Floor Sale); detail names the other handle(s) |
| `tmdb-request-failed` | TMDB call errored; not cached, retried next audit |
| `client-skipped` | registry says `skipped` and the field is still missing |
| `applied-but-missing` | registry says `applied` but the snapshot does not show the fix |

Floor Sale barcodes carry no rule of their own (duplicates among Floor Sale items are allowed).

**Amended 2026-09-30 — poster optional for Libib.** `poster` moved out of the Libib
required fields (`libib/fields.py` `WANTED_FIELDS`): a rental without a poster is eligible
and imports blank; the existing poster-drift path uploads it later. New audit auto-fix
`poster-tag-sync` adds/removes the `Poster_Missing` tag (one final `Tags` value per product,
shared with the alias fixes; dropped for products whose poster TMDB fills in the same run).
Review entries gain `Missing`; `picker push` orders poster-only cards last and the picker
badges them; `run-report.txt` splits gaps into *blocks Libib* vs *poster only*.

### TMDB

- Matcher logic moves unchanged (confidence thresholds, year cutoffs, genre/overview/
  popularity tiebreaks, the "cutoff only as a tiebreak" rule).
- One shared cache; saved every 50 new fetches and at the end, so an interrupted run keeps its
  work. `--no-cache` bypasses reads and writes, as today.
- Failed requests are never cached.

### Out of scope

Whether a genre is *correct* for the film; storefront visibility; collection membership.

## 5. Stage 2 — picker push

```
python3 -m catalog picker push [--run <id>] [--no-git-sync] [--dry-run] [--yes]
```

- Reads `review.json`, drops handles already in the registry, fetches candidates (shared TMDB
  cache), appends new cards to `ambiguous-queue` / `unmatched-queue`, rewrites each queue's
  `index.html`, `batches.json` and the launcher, marks new handles `queued`, then git-syncs
  `tools/review-picker/` (existing conservative behaviour: refuses if the tree is dirty outside
  it, never force-pushes, reports failures).
- Plan shows: cards added per queue, registry changes, the git commit message.
- The page HTML/JS moves to `picker/page.html` / `launcher.html` with simple placeholder
  substitution (`__PRODUCTS__`, `__BATCH_ID__`, …). Behaviour of the hosted page is unchanged.
- `BATCH_ID_PATTERN` stays in sync with `tools/review-picker/api/_github.js` (comment updated
  to point at the new path).
- The local-only pages (`review_page.build_picker_html`, `unmatched_page`) are deleted.

### Pick schema (`picker/schema.py`)

```
{handle, choice: "tmdb"|"manual"|"skip", poster_path?, overview?, image_src?, fields?: {...}}
```

- `fields` is reserved for future genre/type/format/price picks. Until apply supports it, a
  pick carrying `fields` is **rejected with an error**, never silently ignored.
- Known dependency: `/api/save-pick` rebuilds the pick from an allowlist of keys, so it drops
  `fields` today. The future picker-fields feature must extend that allowlist.

### Registry statuses

`queued` → `applied` → `resolved`, plus `skipped`. Existing `queued` and `resolved` entries are
kept as-is. Every status blocks re-queuing. Entries record `batch`, and for `applied` the run
id and fields changed.

## 6. Stage 3 — apply

```
python3 -m catalog apply [--run <id>] [--dry-run] [--yes]
```

1. Pull `tools/review-picker/data/` (same dirty-tree refusal as git sync).
2. Load picks from **every batch listed in `batches.json`** (evergreen queues and the older
   8.31 / 9.2 batches). Skip handles already `applied`/`resolved`.
3. Merge with the run's `autofix.json`, **checked against the snapshot**:
   - Pick beats auto-fix on the same field.
   - `tmdb` pick fills a field only if the snapshot shows it empty.
   - `manual` pick overwrites the non-empty fields it carries, unconditionally.
   - `skip` → registry `skipped`; no change.
4. Group changes by the set of columns they touch and write one CSV per group under
   `runs/<id>/import/`:

| file | columns set |
|---|---|
| `image.csv` | Image Src, Image Alt Text |
| `description.csv` | Body (HTML) |
| `genre.csv` | Tags, Option1 Value, Genre metafield |
| `vendor.csv` | Vendor, Tags |
| `price.csv` | Variant Price |

   Every row also carries the product's live `Title`, `Option1 Name`, `Option1 Value` (the
   importer requires them). Any change to Tags writes the **full** recomputed tag list. A
   product needing changes in several groups appears in several files.
5. Write `apply-plan.csv` (`handle, field, before, after, source`) and mark handles `applied`.

**Invariant (tested):** no import CSV contains a blank cell in a column that row did not
intend to change.

**Risk to verify before the first real `genre.csv` import:** changing `Option1 Value` may
interact with how Shopify matches variants on import. Import a handful of rows to the dev
store, re-export, and confirm barcode and inventory survive. This is a task in the
implementation plan, not an assumption.

## 7. Stage 4 — Libib

Join key: Shopify `Variant Barcode` = Libib `call_number`. The audit's rental-barcode rules
make it unique; rentals failing those rules are reported as `blocked (barcode)` and skipped.

```
python3 -m catalog libib diff --barcode-export <csv> --collection-export <csv> [--run <id>]
python3 -m catalog libib prepare [--size 200] [--dry-run] [--yes]
python3 -m catalog libib mark-imported <batch> [--dry-run] [--yes]
python3 -m catalog libib fix (<batch> | --drift) [--limit N] [--headless] [--dry-run] [--yes]
python3 -m catalog libib status
```

### `diff`

Reads the snapshot's Rentals and the two Libib exports (joined on `id`; the collection export
carries `description`, the barcode export carries `barcode`). Each item lands in one category:

| category | output |
|---|---|
| in sync | count |
| drift: title / description / tags / barcode differ | `drift.csv` (handle, call_number, field, shopify, libib) |
| poster drift: snapshot `Image Src` ≠ state `poster_src` | `drift.csv` |
| missing in Libib, eligible (all 7 required fields) | `eligible.csv` |
| missing in Libib, incomplete | count (already in audit findings) |
| orphan: in Libib, no Shopify rental with that call number | `orphans.csv` — never auto-deleted |
| duplicate: >1 Libib item with one call number | `orphans.csv`, flagged duplicate |

Comparison rules stay in `libib/fields.py` (whitespace-normalised title/description, tag
*set* comparison). `diff` also promotes in-flight (`imported`) handles that now match to
`done` — it replaces today's `verify`. `diff` writes only to the run folder and this state
promotion, and needs no approval.

### `prepare`, `mark-imported`, `fix`

- `prepare`: next `--size` of `eligible.csv` → `libib-sync/batch-NNNN/` with `import.csv`
  (Force Import Mode), downloaded posters, `ready.csv`; state `queued`.
- `mark-imported`: operator confirms the manual import; state `imported`.
- `fix <batch>` runs the fixer on the batch's `ready.csv`; `fix --drift` builds a `ready.csv`
  from `drift.csv` first. Records `poster_src` for every successful poster upload. Browser
  behaviour is unchanged from `libib_sync_fix.py` (scope forcing, reload-verify, collision
  detection).

### State (`libib-sync/_state.json`)

Holds only what the exports cannot show: in-flight status (`queued`/`imported`/`done`/
`needs-review`), `batch`, `poster_src`, `note`. One-time migration: for existing entries with
`poster_confirmed`, set `poster_src` from the first snapshot's `Image Src`. Entries without
`poster_src` are never flagged for poster drift.

## 8. Logging

- `core/log.py` configures stdlib `logging` once per command: console + `runs/<id>/<stage>.log`
  (Libib `fix` also logs into its batch folder).
- Each stage prints a header (inputs, store, run id), per-item progress for every long step
  (`[412/3130] Rushmore: filled image, description`) — API pages, TMDB lookups, candidate
  fetches, poster downloads, Playwright items — and a closing summary of counts.
- `--verbose` adds per-rule detail; `--quiet` shows headers and summary only.

## 9. Plan and approval

Every command that changes anything outside its own run folder builds a `Plan`, renders it,
and asks before executing. `core/plan.py`:

- `Plan`: title, summary lines (counts per target), up to 10 sample changes, path to the full
  change list.
- Prompt: `Proceed? [y/N]`. Default is no.
- `--dry-run`: render and exit 0, change nothing.
- `--yes`: skip the prompt.
- **Non-interactive (stdin not a TTY) without `--yes`: refuse**, exit non-zero, and say so.
  An agent running the command therefore cannot proceed without explicit approval.

| command | asks? | what the plan lists |
|---|---|---|
| `audit` | no | — (reads Shopify; writes its run folder, TMDB cache, registry promotion) |
| `picker push` | yes | cards per queue, registry changes, git commit |
| `apply` | yes | rows per import CSV, source split (auto-fix vs pick), Option1 warning, registry changes, samples; full list in `apply-plan.csv` |
| `libib diff` | no | — (writes run folder, state promotion) |
| `libib prepare` | yes | batch id, handle count, posters to download |
| `libib mark-imported` | yes | handles to mark |
| `libib fix` | yes | items and fields per item that will be edited in Libib |
| `check-upload` | no | — (read-only) |

Shopify is only ever changed by the operator importing the CSVs — a second approval on top.

## 10. Migration, errors, testing

### File mapping

| from | to |
|---|---|
| `taxonomy`, `columns`, `handles`, `catalog_common` | `core/` |
| `resolve` + rules from `normalize` | `audit/` (template-shape branches removed) |
| `tmdb_fill`, `tmdb_cache` | `tmdb/` |
| `hosted_review_page`, `review_registry`, `git_sync`, candidate half of `review_page` | `picker/` |
| `apply_picks` | `apply/` |
| `libib_sync`, `libib_sync_fix`, `libib_sync_state`, `libib_fields`, `libib_export` | `libib/` |
| `sheet_transform`, `check_upload`, `client-template/` | `client_sheet/` |
| `run`, `detect`, `unmatched_page`, `format_issue_batch`, `circa_refill`, `master_resolve`, `run_master_resolve`, `extract_master_queue`, `build_master_queue` | deleted |
| `tests/formatting_scripts/` | `tests/catalog/`, ported module by module |
| `tests/data_cleanup/` | deleted (imports a `data-cleanup/` dir that no longer exists) |

References to update: `CLAUDE.md` (repo layout, roadmap #2/#3 mentions of `formatting-scripts/`),
`tools/review-picker/README.md`, the keep-in-sync comment in `tools/review-picker/api/_github.js`,
`scripts/set-product-templates.sh`.

### Secrets

The hardcoded Libib password (`libib_sync_fix.py`) and TMDB key (`run.py`,
`format_issue_batch.py`, `circa_refill.py`) are removed from source. They remain in git
history; rotating them is the owner's decision and is outside this work.

### Error handling

| condition | behaviour |
|---|---|
| Shopify CLI not authenticated | stop; print `shopify store auth --store <domain> --scopes read_products` |
| required env var missing | stop; name the variable |
| stage input missing (e.g. `apply` with no run) | stop; name the command that produces it |
| TMDB request fails | not cached; `tmdb-request-failed` finding; retried next audit |
| git pull/commit/push fails | reported, not retried; files left for manual sync (existing behaviour) |
| pick with unknown shape / `fields` | stop; name the batch and handle |
| CSV row with extra fields | stop; name the handle (existing `write_csv` check) |

### Testing

- **Baseline first:** run the current suite before moving any code and record the result in
  the plan.
- Standard-library `unittest`: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`
- Tests move with their code; tests for deleted modules are deleted.
- New coverage:
  - `shopify/reader`: recorded GraphQL response fixtures → snapshot rows (CLI invocation is
    injected; tests never call the store).
  - `audit/rules`: table-driven, one case per rule, including all three rental-barcode rules
    and the Rental-vs-Floor-Sale cross-duplicate case.
  - `apply`: merge precedence; grouping; the no-blank-cell invariant.
  - `libib/diff`: fixture exports covering every category.
  - `core/plan`: dry-run changes nothing; non-TTY without `--yes` refuses.
- The Playwright fixer is verified manually with `libib fix <batch> --limit 1`.
- **Acceptance:** one read-only `audit` against production, with results compared to the
  known counts **on their own scopes** — 133 rentals missing a poster and 118 missing a
  description (rental catalogue, 2026-09-16, `LIBIB_MIGRATION_PROGRESS.md`); 13 duplicate-
  barcode pairs (2026-09-19, not rental-scoped). Differences are explained, not forced to match.

## 11. Future work (not in this build)

- **Pre-import intake**: run a client batch through the audit rules and TMDB fill before the
  client imports it. The rules are loader-agnostic, so this is a new loader + command.
- **Picker fields**: genre/type/format/price picks via `fields` (needs the `/api/save-pick`
  allowlist change and apply support).
- Libib lending status → Shopify stock (see `LIBIB_AUTOMATION_ROADMAP.md` #2).
- Running `libib fix` in CI/cloud.
