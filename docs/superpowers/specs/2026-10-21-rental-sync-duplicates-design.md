# Rental sync: catch Libib duplicates, add copies to existing products (design, 2026-10-21)

**Status: spec, not built.** Decisions confirmed with the developer
2026-10-21 in a brainstorming session. Extends the rental sync app
(`docs/superpowers/specs/2026-10-15-libib-shopify-sync-app-design.md`, live at
`https://lms-rental-sync.vercel.app`; code `catalog/rental_sync/` +
`tools/rental-sync/`).

## Why

When the client adds a movie in Libib that Libib already has, he tends to
create a second Libib **item** instead of adding a **copy** to the existing
item. The sync app finds new copies by barcode, so the new item's `201…`
barcode looks new and a second Shopify product is created for the same
movie. That is what happened last time: client added the movie, the app said
"new product", it was created.

At the same time the client is moving from **one product per physical copy**
to **one product per movie + format** (decided by 2026-10-20; Floor Sale sheet
already done). This feature brings rentals onto that model: further copies of
a movie become **variants** of one Shopify product, each variant carrying its
own copy's `201…` barcode (Libib won't let copies share a barcode, and the
labels need one barcode per physical copy).

## Definitions

- **Same movie** = same title **and** same format. "The Godfather" on DVD and
  on VHS are different movies (different Libib items, different Shopify
  products).
- **Libib item** = one Libib `id`; its copies are the rows sharing that `id`
  in the Barcodes export.
- **Rental product** = Shopify product tagged `Rental`.

## Goals

1. **Catch Libib duplicates during the sync.** A new copy whose Libib item
   looks like another Libib item of the same movie is flagged, and the client
   is told to delete the new item in Libib and add it as a copy of the
   existing item instead.
2. **Add copies to existing products.** A new copy whose movie is already a
   rental product in Shopify is added to that product as a new variant (with
   the copy's barcode), not created as a new product.
3. **Find the matching product exactly**, by sibling barcode: another copy of
   the same Libib item already on a Shopify variant — a `201…` copy, or a
   legacy 8-digit one (decision 3). (A fuzzy Shopify search was considered and
   dropped — see Decisions.)
4. **The client approves every match.** Nothing is attached to an existing
   product or flagged as a duplicate without the client seeing it.
5. **Build and test on the dev store and the developer's test Libib account**
   before production.

## Decisions (2026-10-21)

| # | Decision |
|---|---|
| 1 | Same movie = same title + same format. |
| 2 | Every match (Libib duplicate or Shopify copy) is approved by the client; "Not a duplicate" is always available. |
| 3 | Shopify match is **by sibling barcode only**. A fuzzy Shopify search (format + genre + title) was dropped: after cleanup it would only fire for legacy 8-digit rentals with no Libib item. **Revised 2026-10-23:** a legacy copy *in the same Libib item* is a sibling too, because the client keeps the existing 8-digit barcodes and many of those copies are in Libib. A legacy copy's Shopify barcode is its Libib call number, or its copy barcode when it has none (the rule the Libib tooling uses). Legacy siblings are looked up one by one; one that isn't in Shopify is ignored, so a Libib item whose legacy copies never reached Shopify is created as a new product. A new copy added to a legacy product makes a mixed product: the legacy variant stays first (`Copy 1`), and the snapshot readers keep one row per product from the first variant, so `libib diff`/`fix`/`sync`, the audit and `apply` keep treating it as legacy (pinned by a `libib diff` test). An item that has legacy copies is never a Libib-duplicate candidate — it isn't new. |
| 4 | **Cleanup is a separate project, complete before go-live:** the developer (with Claude: analysis, plan, scripts) dedupes Libib and Shopify so that every new-flow rental product maps to exactly one Libib item and vice versa, including merging the existing one-product-per-copy rentals of a Libib item into one product with a variant per copy. The app may assume this holds. |
| 5 | Built and tested on the dev store + the developer's test Libib account first. |

## Non-goals

- **Cleaning up the existing duplicates.** A separate project with its own
  brainstorm, plan and scripts (decision 4), done after this tool is built on
  the dev store and before either goes live. Its merged products must take
  the shape this spec defines (Genre option 1, Copy option 2, one variant per
  barcode). `python3 -m catalog duplicates` already lists duplicate groups.
- Fuzzy matching against Shopify products (decision 3).
- Editing Libib from the app (Libib stays the source of truth; the client
  fixes Libib himself).
- Pushing later Libib edits (title, description, poster, tags) onto existing
  products — still create-only for product fields.
- Floor Sale products. Legacy 8-digit rentals are never created or changed,
  except that a new copy can be added to one as a variant (decision 3).
- Reworking the audit `multiple-variants` rule or the Libib `copies = 1`
  check. They will start flagging merged rentals; that is the deferred phase
  of the inventory change and is decided separately (ask the developer).

## Anti-goals (failure even if it "works")

- Attaching a copy to an existing product without the client's approval.
- Attaching a copy to the wrong format (a VHS copy on a DVD product).
- Losing or changing an existing variant's barcode, quantity, or the
  product's title / description / poster / genre when a copy is added.
- Ever creating the same barcode twice (the existing rerun safety must hold
  for added variants too).
- Testing against production or the client's real Libib account.

## How it works

### Detection (in `prepare`)

For each new copy (barcode not on any Shopify variant, as today), after the
existing transform/set-aside checks:

**1. Libib duplicate check.** Compare the copy's Libib item with every *other*
Libib item in the Rental Library collection (the uploaded exports contain the
whole library, synced or not):

- same format tag, and
- titles match by `catalog/duplicates/match.py`'s title tiers (exact,
  normalized, fuzzy; editions such as "Director's Cut" are not the same movie),
  or — **added 2026-10-23** — every word of the shorter title (2+ words, small
  words like "the"/"of" aside) is in the longer one, with the same numbers,
  editions and years: "GODFATHER: CODA" vs "Mario Puzo's THE GODFATHER, Coda:
  The Death of Michael Corleone" (two releases, different UPCs, so a UPC match
  wouldn't catch it either). This also flags sequels ("Star Trek" / "Star Trek
  Into Darkness"); the client clears them with **Not a duplicate**. Measured on
  the 2026-10-19 Libib export (3,861 items): 64 more pairs flagged, touching 103
  items (about 2.7%), roughly 1 in 5 the same film. One-word titles are left
  out ("Speed" / "Speed Racer" would add about 300 false flags).

A match is shown as **"Possible duplicate in Libib"**: the new item and the
existing item side by side (title, format, genres, copies, date added). The
client either:

- **Leaves it** → the copy is set aside this run, with: "In Libib, delete
  *<new item>* and add this copy to *<existing item>* instead. It will show up
  next time you sync."
- **Clicks "Not a duplicate"** (remakes, e.g. Halloween 1978 vs 2018) → the
  copy carries on to step 2 and is created as normal.

The dismissal is not stored: once the copy is created its barcode is in
Shopify, so it is never re-checked. If both items are new in the same run,
only the later one (by Libib `created`) is flagged.

**2. Shopify match (sibling barcode).** For copies that pass step 1: if
another copy of the *same Libib item* — `201…` or legacy 8-digit (decision 3) —
has its barcode on a Shopify variant, that variant's product is the match. The
client chooses:

- **Add as a copy of this product**, or
- **Skip this run** — the copy is set aside with "If this copy isn't the same
  movie, move it to its own item in Libib." (Creating a separate product here
  would split one Libib item across two products and break decision 4; changed
  from "Create a new product" when the fuzzy search was dropped.)

If the siblings' barcodes are spread over **more than one** product (before
the cleanup this is common for legacy items, which are one product per copy),
the cleanup assumption (decision 4) is broken: set the copy aside with "This Libib
item is on several Shopify products — combine them first" and the product
links. Never guess.

No match → created as a new product, as today.

**3. New Libib item with several copies in one run** (*developer's-agent
call*): they become **one** product with one variant per copy. Exact by
construction, so no approval card. One poster for the product. `create`
therefore takes a group of copies (one Libib item), not a single copy, and the
handle no longer embeds one barcode — the builder picks a stable scheme that
can't collide (e.g. `title-format-rental-<first barcode>` kept as-is).

### Client flow changes

The five steps stay. In step 3 ("Check the details"):

- A new **"Possible duplicates in Libib"** section above Set aside, one card
  per flagged copy, with the Libib instruction and a "Not a duplicate" button.
- A new **"Already in Shopify?"** section: one card per matched copy showing
  the Libib copy next to the matched product (title, format, genres, poster,
  number of copies, link to Shopify admin), with the two choices above.
  "Looks good" stays disabled until every match card has a choice.

Step 4 (posters) only covers copies becoming new products — an added copy
uses the existing product's poster.

Step 5 results gain **"Added as a copy"** (linked to the product), alongside
Created / Already in Shopify / Failed. The print hand-off also **lists the
exact barcodes to label** this run, because a product gaining a copy already
has labelled copies on the shelf (see Open item).

## Open item: printing one copy's label

**Unknown:** whether Retail Barcode Labels can print a single variant of a
multi-variant product. **First task of the plan:** on the dev store, give a
rental two variants and try printing just one. Then:

- **It can** → keep the `Barcode Not Printed` product tag + the barcode list in
  step 5; the client guide says "print only the barcodes listed".
- **It can't** → bring the finding back to the developer before building the
  print hand-off (the alternative — a per-variant marker — changes the
  client's print routine).

Either way the label's genre comes from **Variant Option 1**
(`barcode-driven-upload-model`), so `Genre` must stay Option 1.

**Resolved 2026-10-22 (developer, dev store):** a single variant can be
printed; the LMS: RENTAL label shows the genre (Option 1), not `Copy N`; the
storefront PDP and collection grid show no variant picker, swatch or "Copy"
text. → **It can** branch: keep the `Barcode Not Printed` tag + barcode list.

### Adding a copy (new endpoint or a mode of `create`)

Server-side, re-derived from Libib fields like `create` (the browser only
supplies the copy and the chosen product id):

- Re-check the barcode is on no variant (rerun safety; hit →
  `skipped_exists`).
- Check the chosen product is a rental with the same Vendor (else `failed`).
- Add one variant: barcode = copy barcode, price `0`, untaxed, inventory
  tracked, policy `DENY`, quantity `1` at the location — the same variant
  fields `create` uses today.
- Add `Barcode Not Printed` to the product's tags so the print step still
  catches it.
- Don't touch title, description, Vendor, genre, image, other variants.
- Read back and verify the new variant (barcode, taxable, tracked, qty 1) and
  that the existing variants are unchanged.

### Variant options (builder's call, constraints only)

Today each rental has one option, `Genre` = first genre, and one variant.
Shopify needs each variant to have a distinct option-value combination, so a
second copy needs an option that differs per copy. *Developer's-agent call:*
add a **second** option such as `Copy` (`Copy 1`, `Copy 2`, …), turning the
existing variant into `Copy 1` the first time. Constraints:

- `Genre` stays **Option 1** — the rental label prints its genre from it;

- must not show a variant picker or swatches on the storefront (the movie PDP
  is read-only; check the product card / collection grid too);
- must not surface barcodes or serials on the storefront;
- new products from `create` can stay single-variant until a copy is added,
  or start with `Copy 1` — whichever keeps the code simpler.

### Ripple effects in the app

- `create.verify` and `_existing` assume exactly one variant. A barcode hit on
  a multi-variant product must verify the **matching variant**, not fail on
  variant count.
- `new_flow_barcodes()` already reads every variant — the diff is unchanged.
- `catalog/libib/tags_*` and `custom.libib_join_id`: one product now maps to
  one Libib item with several copies — check the tag job still picks the
  right product and doesn't double-count copies of one movie in the "newest
  50". `tags_shopify.py` reads only `variants(first: 5)`; raise or paginate.
- The sync app's own reads (`READ_BACK` uses `variants(first: 5)`) need the
  same care.

## Testing

- **Unit (fake Shopify client, fixtures):** Libib duplicate check (exact,
  normalized, fuzzy, different format not flagged, edition not flagged,
  both-new-in-one-run flags only the later); sibling-barcode match; siblings
  on several products → set aside; new item with several copies → one
  product; add-copy writes only the new variant + tag, rerun safety,
  wrong-format product refused; verify passes on a multi-variant product.
- **End-to-end on the dev store + the developer's test Libib account**, via a
  Vercel **Preview** deployment whose env vars point at the dev store
  (`SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com`); Production env keeps
  pointing at production and is not touched until the feature is approved.
  Scenarios: new movie → created; second Libib item for the same movie →
  flagged → fix in Libib (delete item, add copy) → re-run → sibling match →
  added as variant; remake → "Not a duplicate" → created; new item with two
  copies → one product, two variants; re-run creates nothing; print step
  shows the product and the new barcode.
- Front end: extend the node tests (`tests/rental_sync/*.test.js`) and do a
  Playwright walk-through on the preview.

## Rollout

1. Build + test on the dev store / test Libib (above).
2. The cleanup project (separate spec) dedupes production and the real Libib.
3. Deploy to production, update the client guide (`tools/rental-sync/client-guide.md`)
   with the new cards and the Libib "add a copy" instructions, update
   `CLAUDE.md` roadmap #3 and the inventory memory.

## Left to the builder

- Exact endpoint shape (new `add_copy` endpoint vs a mode on `create`).
- Option naming/mechanics for multi-variant products, within the constraints
  above.
- Fuzzy thresholds for the Libib duplicate check — reuse
  `catalog/duplicates/match.py` rather than invent new ones.
