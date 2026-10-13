# Libib item links — what the `?id=` number is (research, 2026-10-13)

**Question:** the published-site link for an item is
`https://www.libib.com/u/littlemoviestore?id=168726561`. What is that number,
and how do we get it for every rental so Shopify (homepage Recent Additions,
Community Picks) can link to the Libib item instead of the Shopify PDP?

## Answer

It is Libib's **`join_id`** — the row that joins an item to a collection
(our published `Rental Library`, `library_id` **2603141**). It is a
global, roughly sequential integer (current items span ~168.6M–169.6M).

It is **not** in either CSV export. The export `id` column is a different
key: for the example item, export `id` = `obaj4890an`, barcode `19980794`,
join_id `168726561`.

## Evidence (all public, no login)

The published site's JavaScript (`/u/littlemoviestore` page, inline script)
reads `data-join-id` from each item and pushes `?id=<join_id>`; opening a
link POSTs `join_id` to `/u/littlemoviestore/item-details-view`. The page
reads only two URL parameters: `id` (opens the detail panel over the grid)
and `solo` (the "Copy Link" button's single-item view,
`…/u/littlemoviestore?solo=<join_id>`). There is **no search URL
parameter**, so we can't link by barcode or title — we need the join_id.

The public search endpoint returns it:

```
POST https://www.libib.com/u/littlemoviestore/search
     keywords=<barcode>&library_id=2603141&offset=0&limit=50
→ JSON; item-info HTML contains data-join-id="…", title, tags, description, cover URL
```

Search matches on **barcode**, verified both ways:

| Barcode | Title | join_id |
|---|---|---|
| `19980794` (legacy 8-digit) | 2 Films: Deadly Drifter, Blood Tide | `168726561` (matches the link you gave) |
| `2010000002155` (new Libib-generated) | The Curse [VHS] | `169565504` |

`/get-account-items` (the A–Z browse) also lists join_ids, 50 at a time, but
without barcodes — usable only for a title cross-check.

## What this means

- **Store the join_id on each Shopify rental** — proposed product metafield
  `custom.libib_join_id` (integer). The theme builds
  `https://www.libib.com/u/littlemoviestore?id={{ join_id }}` (or `?solo=`)
  and falls back to the Shopify PDP when it's blank.
- **One join_id per Libib item, not per copy.** Copies of one title (one
  Libib item, decision 10 in the rental spec) share a link — fine.
- **Backfill (≈3,500 legacy rentals):** a pipeline step that searches each
  Shopify rental's `Variant Barcode` and writes the metafield. Exactly one
  hit = write; zero or several = report for a manual look. Throttle it
  (unofficial endpoint).
- **New uploads:** the client's Google Sheet can't get it — Sheets'
  `IMPORTXML`/`IMPORTDATA` only do GET, and the join_id isn't in the export.
  Options: (a) we run the same lookup step after each client batch (needs a
  developer run per batch); (b) the client pastes each item's link from
  Libib's "Copy Link" into the sheet (manual, error-prone); (c) a scheduled
  job (GitHub Actions, like the Libib selftest) that fills any rental
  missing the metafield. **(c) recommended** — no client step, self-healing.
  The rental-upload spec should add the metafield column (blank) and note
  that links appear after the job runs; the PDP fallback covers the gap.

## Caveats

- `/search` and `/item-details-view` are the published site's internal
  endpoints, not Libib's documented REST API. They may change without
  notice. The REST API (Pro, `api.libib.com`, `x-api-key` + `x-api-user`,
  already planned for patrons) may expose item IDs — its docs weren't
  publicly reachable today; check from the client's API settings page.
  Worth doing before building the backfill.
- Only **published** collections are searchable. If `Rental Library` is ever
  unpublished, lookups return nothing.
- A join_id is per item-in-collection: removing an item from the collection
  and re-adding it, or moving it to another collection, gives a new
  join_id and breaks the stored link. The scheduled job should also
  re-verify stored IDs (a link that 404s/returns "no item" gets refilled).
- Not yet checked: whether editing an item (title, tags, barcode) keeps its
  join_id. Expected yes (it's the collection join, not the item), verify
  once.
