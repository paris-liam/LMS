# Daily Libib + Shopify backup (design, 2026-10-21)

**Status:** built 2026-10-21 (code + format check against a fresh production export); not deployed yet. Decisions confirmed with the developer 2026-10-20/21.

## Why

A safety net. If Libib or production Shopify data is lost or overwritten, there should
be a recent, dated copy to put back. Every day the backup overwrites the same files
in a private repo, so the git history is a timeline of what changed and when. To
restore, go back to the last good commit and take the file from there.

**Restoring Shopify is the client's job, from the Shopify admin** (Products → Import).
So the Shopify backup must be a file the admin import accepts as-is, and nobody
should need a script to use it.

## Goals

- Once a day, without anyone doing anything, back up:
  - **Libib:** both Rental Library exports (barcode data + collection data), exactly as Libib produces them.
  - **Production Shopify:** every product and every variant, in Shopify's product-CSV
    format, with every column the admin's own product export has.
- Commit to the **private** repo `paris-liam/LMS-data`, only when something changed.
- A failed run tells the developer and never replaces a good backup with a bad one.

## Non-goals

- **No copies of product images.** The CSV keeps the `Image Src` URLs as Shopify
  exports them, and that's all. A deleted product's images may be gone from
  Shopify's CDN, and this backup cannot bring them back. Most rental posters can be
  fetched again from TMDB; photos the client uploaded himself cannot.
- **No restore tool.** The files being there and importable is the whole feature.
- **No page on the rental sync site.** The developer reviews files on GitHub or
  downloads them. The site stays as it is, ready for later utilities.
- No dev-store backup, no other Libib collections, no customers/orders/collections/
  theme settings.

## Anti-goals (would make this a failure even if it runs)

- Any backup data landing in the **public** `paris-liam/LMS` repo or its GitHub
  Pages site. The data lives only in `LMS-data`.
- A Shopify CSV the admin import rejects, or that silently loses fields on import.
- A glitchy run (empty export, Libib error page saved as a CSV) overwriting the last
  good file.
- The backup writing anything to Libib or Shopify.

## Decided

| # | Decision |
|---|----------|
| 1 | Data goes to the new private repo `paris-liam/LMS-data` (created 2026-10-21). |
| 2 | Shopify: **every product and variant, from production** (`p0wkgv-wy.myshopify.com`). |
| 3 | Shopify format: the admin product-CSV format, so the client can restore with Products → Import. |
| 4 | No image copies (see Non-goals). |
| 5 | No sync-site page; the developer is the only user. |
| 6 | **Same Shopify app as the rental sync / pipeline** (`SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET`), even though its token can write. The backup code only sends queries. |
| 7 | Libib login from a GitHub runner **verified 2026-10-21**: the test workflow logged in and exported 3,962 + 3,962 rows, the same counts as a local export the night before. |

## How it fits together

```
LMS-data (private)                         LMS (public)
.github/workflows/daily-backup.yml  ──checkout──▶  catalog/ code (main)
   │  runs python -m catalog backup …
   ▼
libib/barcodes.csv
libib/library.csv
shopify/products.csv
README.md   (what's here + client restore steps)
```

- **Code lives in `LMS`** as a new `catalog/backup/` package with a `backup` CLI
  command (`register(subparsers)` like the other command modules), tests in
  `tests/catalog/test_backup_*.py`. It writes files into a directory passed on the
  command line, never into the LMS working tree.
- **The workflow lives in `LMS-data`.** It checks out `paris-liam/LMS` (public, so no
  token is needed) into a subfolder and runs the command against the `LMS-data`
  checkout. This is the shape the 2026-10-21 login test already proved.
  *My call:* track LMS `main` instead of pinning a commit, because the developer is
  the only one who pushes there.
- Replace the test workflow `libib-login-test.yml` with the real one.

### Libib

- Reuse `catalog/libib/transfer.py:run_browser_export` (Playwright, headless). It
  clicks only the two export buttons by id; the same settings page has Delete
  Collections.
- Save the two files to the fixed names `libib/barcodes.csv` and `libib/library.csv`
  **byte-for-byte as downloaded.** Row order is already stable between exports:
  two exports 12 days apart kept the same relative order of `id`s, so the diffs stay
  readable without sorting.

### Shopify

- Read with the Admin GraphQL API using the existing client-credentials flow
  (`catalog/shopify/api.py:request_token`). Bulk operation or paginated queries are
  the builder's choice. Production has roughly 7,000 products (an admin export on
  2026-09-20 had 7,066 rows / 7,019 handles, 4.3 MB).
- **Output must match Shopify's admin product export**, column for column and value
  format for value format, so that importing it back is the same as importing an
  admin export. Reference header (production admin export, 2026-09-20,
  `exports/9.20/shopify_export.csv`):

  `Handle, Title, Body (HTML), Vendor, Product Category, Type, Tags, Published,
  Option1 Name, Option1 Value, Option1 Linked To, Option2 …, Option3 …, Variant SKU,
  Variant Grams, Variant Inventory Tracker, Variant Inventory Qty, Variant Inventory
  Policy, Variant Fulfillment Service, Variant Price, Variant Compare At Price,
  Variant Requires Shipping, Variant Taxable, Unit Price …, Variant Barcodes, Image
  Src, Image Position, Image Alt Text, Gift Card, SEO Title, SEO Description,
  <one column per product metafield definition, e.g. "Genre
  (product.metafields.shopify.genre)">, Variant Image, Variant Weight Unit, Variant
  Tax Code, Cost per item, Status`

  The builder should take a **fresh admin export at build time** and treat its header
  as the target, because Shopify changes this format (e.g. `Variant Barcodes` is new).
  The metafield columns depend on the store's definitions, so generate them from the
  product metafield definitions rather than hardcoding. Value formats seen in the
  2026-09-20 export: metaobject references written as the metaobject handle
  (`drama`), booleans as lowercase `true`/`false`, status lowercase, extra images as
  extra rows under the same handle.
- **A column the app can't read faithfully is left out, not written blank**
  (*my call*). On import with "Overwrite products with matching handles", a blank
  metafield cell probably clears the stored value. A missing column leaves the
  field alone. Candidates are other apps' metafields: Search & Discovery's
  `shopify--discovery--product_recommendation.*` / `…product_search_boost.*`, and
  the deprecated `supercycle.methods`. Product-reference lists that *can* be read are
  written the way the admin export writes them. The README lists every left-out
  column, and the format check (Verify 1) compares everything else.
- Rows sorted by handle, then the admin export's own variant/image order, so a
  product that didn't change produces no diff.
- `shopify/products.csv`. *My call:* if the file ever passes the admin import's
  15 MB limit, write `products-1.csv`, `products-2.csv`, … split on handle
  boundaries, and remove the single file.
- Inventory: the admin export's `Variant Inventory Qty` is what gets backed up. If
  production has more than one location, follow whatever the current admin export
  does and note it in the README.

### Workflow

- **When:** daily at 08:00 UTC (4am Eastern in summer, 3am in winter), plus
  `workflow_dispatch` for a manual run. *My call.*
- Use the current major versions of `actions/checkout` and `actions/setup-python`
  (the v4/v5 ones gave Node 20 deprecation warnings on 2026-10-21). Cache the
  Playwright browser if it's easy; the login test spent most of its 5m20s installing.
- `permissions: contents: write` (to push to `LMS-data` with `GITHUB_TOKEN`),
  `concurrency` so two runs never overlap, a timeout of about 30 minutes.
- Secrets in `LMS-data`: `LIBIB_EMAIL` and `LIBIB_PASSWORD` (already set);
  `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` (**to add**, by the developer: the
  agent session wasn't allowed to upload credentials). `SHOPIFY_STORE` is the plain
  value `p0wkgv-wy.myshopify.com` in the workflow, not a secret.
- **Commit:** stage the three paths; if nothing changed, end successfully without a
  commit. Commit message is the date plus row counts per file, e.g.
  `Backup 2026-10-22 — libib 3962/3962 rows, shopify 7031 products`. *My call.*

### Failures

- **Each source on its own** (*my call*): if Libib fails but Shopify works, commit
  Shopify, then fail the run, and the reverse too. A partial backup beats none.
- **Sanity guard before overwriting a file** (*my call*): refuse to write a file
  that has zero data rows, that isn't a CSV, or whose header is missing the columns
  the rest of the pipeline relies on (Libib: `id`, `title`, `barcode`/`call_number`
  as applicable; Shopify: `Handle`, `Title`, `Status`). A refused file keeps
  yesterday's version and fails the run. A real drop in row count is **not** refused:
  it gets committed, because recording it is the point.
- **Notification:** GitHub's built-in email for failed workflow runs, which goes to
  the account that last changed the schedule (`paris-liam`). Nothing custom.
- **Logs:** counts and file names only, never row contents, credentials or tokens.
  The repo is private, but logs stay minimal anyway.
- Private repos don't get the 60-day inactivity auto-disable that public repos'
  scheduled workflows do. Note that in the README in case the repo ever becomes
  public.

### README in LMS-data

Short, for the developer and the client:
- what each file is and that history = daily snapshots;
- **client restore steps:** find the date on GitHub → download `shopify/products.csv`
  from that commit → Shopify admin → Products → Import → tick "Overwrite products
  with matching handles" → import. Plus the caveat that images of deleted products
  may not come back;
- **what a restore can't bring back** (*my call: document it, no sidecar file*):
  the CSV import can't set a template suffix. So a restored non-movie product comes
  back on the read-only movie PDP until its template is set to `retail` again by
  hand. List the products that use `retail` (two membership plans, the shirt, the
  bumper sticker; the builder confirms them from the store), because a restored
  membership plan without it can't be bought. Also list the left-out columns
  (above) and the missing images;
- Libib: the files are Libib's own exports; restoring them isn't covered here.

## Reference exports and test data

- **The developer supplies two fresh admin product exports** (Products → Export →
  all products, CSV for Excel or plain CSV): one from production (the target header)
  and one from the dev store (for Verify 1). They arrive by email; an agent can't
  produce them. Format work can't be finished until they exist, so the plan should
  ask for them early.
- They are real store data, so **they never go in the public `LMS` repo.** Keep them
  outside both repos (e.g. the builder's scratch folder) or in a gitignored path.
- Test fixtures in `tests/catalog/` are **synthetic** (a handful of made-up products
  that use the real header), never cut from a real export.
- Already-committed exports in the public repo (`exports/`, 229 files as of
  2026-10-21) are **not part of this work**. This build only makes sure nothing new
  lands there.

## Left to the builder

Bulk vs paginated reads; exact module/file split inside `catalog/backup/`; how the
value formatting is tested; Playwright caching; README wording; updating
`catalog/README.md` and the CLAUDE.md roadmap with the new command.

## Verify

1. **Format match on the dev store:** run the Shopify backup against
   `lms-sandbox-lutsfahz.myshopify.com`, take an admin export of the same store, and
   compare. Same header, same values per handle (allow a different row order only if
   the admin export's order isn't stable).
2. **Round trip on the dev store:** delete or alter a handful of test products, import
   the backup CSV with "Overwrite products with matching handles", and confirm they
   come back, including genre, tags, status, published, price, barcode and
   inventory. Never do this on production.
3. **Workflow:** a manual run in `LMS-data` commits all three files; a second run with
   no changes makes no commit; a run with a bad Libib password commits Shopify, keeps
   the old Libib files and fails with an email.
4. Watch the first two scheduled runs on production.
