# Floor Sale barcodes from Shopify Flow (2026-10-20)

**Status:** designed, not yet built in Flow. Set it up on the dev store
(`lms-sandbox-lutsfahz.myshopify.com`) first, run the checks below, then
production (`p0wkgv-wy.myshopify.com`).

## Why

Retail Barcode Labels' "generate" makes a barcode from the **last 8 digits
of the variant ID**. Every variant ID on production leaves the same
remainder mod 32768 (250), so only ~390,000 of the 100 million 8-digit codes
can come up, and about 1 new product in 50 gets a barcode another product
already has. On 2026-10-19 production had **29 shared barcodes**, 4 of them
created that day against older Rentals. Regenerating doesn't help: the
same ID gives the same number again.

## What

A Flow workflow sets each new Floor Sale copy's barcode to its variant's
**full ID** (`legacyResourceId`, ~14 digits) as soon as the product is
created.

- **Unique by construction.** Shopify never reuses a variant ID.
- **Can't clash with other codes.** Old app codes are 8 digits and Libib
  rental barcodes are 13 (`201…`), so a 14-digit ID matches neither.
- **Nothing for the client to type.** The sheet and the import are
  unchanged. The client only **prints** in Retail Barcode Labels and never
  generates.

This replaces an earlier idea (same day, never shipped) where the sheet
wrote `yymmdd` + a row number. That broke as soon as two batches shared a
date, and the alternative needed the client to type a batch number.

## The workflow

Shopify admin → **Apps → Flow → Create workflow**.

**1. Trigger: Product created** (listed as "Product added to store" in
older versions of Flow).

Not "Product variant added": Shopify documents that one as firing when a
variant is added to an *existing* product, so it may not fire for a
brand-new product's first variant.

**2. Condition** (both must be true):

- `product.tags` includes `Floor Sale`
- `product.variants`, **at least one**: `barcode` is empty

The second condition means a product that already has a barcode (typed in
by hand, or an older copy) is never touched. Rentals made by the rental
sync app already carry their Libib barcode, and they aren't tagged
Floor Sale anyway.

**3. Action: Send Admin API request**

- Mutation: `productVariantsBulkUpdate`
- Mutation inputs:

```liquid
{
  "productId": "{{ product.id }}",
  "variants": [
    {%- assign sep = "" -%}
    {%- for variant in product.variants -%}
      {%- if variant.barcode == blank -%}
        {{ sep }}{ "id": "{{ variant.id }}", "barcode": "{{ variant.legacyResourceId }}" }
        {%- assign sep = "," -%}
      {%- endif -%}
    {%- endfor -%}
  ]
}
```

- **Keep the quotes around every value.** The one public report of this
  exact setup failed until the Liquid placeholders were quoted. Without
  them the JSON is malformed. See the
  [Shopify Community thread](https://community.shopify.com/t/set-unique-barcode-via-shopify-flow-api-call/582034).
- **The loop only fills variants with no barcode.** Every Floor Sale
  product has exactly one variant (one product per copy), so in practice
  this sets one barcode.
- **The `sep` assignment keeps the JSON valid** when a variant is skipped,
  so there's no stray comma.

**Name it** `Floor Sale: barcode = variant ID` and **turn it on**.

## Check on the dev store before production

None of these has been verified yet. Each is a reason the workflow could
quietly do nothing.

1. **Fires on a CSV import.** Import a 2-row Floor Sale sheet. In Flow →
   the workflow → **Run history**, both runs succeed, and each product's
   variant shows its own ID as the barcode.
2. **The trigger sees the tags.** If the condition fails on imported
   products, the tags may not be on the product yet when the trigger reads
   it. Add a **Wait** of 1 minute before the condition and test again.
3. **Variant fields are available in the trigger.** If the Liquid editor
   won't accept `variant.legacyResourceId` or `variant.barcode` inside the
   loop, open the field picker under Product → Variants and use the names
   it offers.
4. **Prints and scans.** In Retail Barcode Labels, print a label for one
   test product **without generating**. It shows the 14-digit number, it
   fits the label, and a scan at POS rings up that product.
5. **The app leaves it alone.** If the app's print flow insists on a
   generate step, choose **only products without barcodes**, and confirm
   the barcode is unchanged afterwards.
6. **The repo check agrees.** Run
   `python3 -m catalog check-barcodes --store lms-sandbox-lutsfahz.myshopify.com --since <today>`.
   It prints ✓: no shared barcodes and no Floor Sale copy without one.

## Day to day

1. The client imports the Floor Sale sheet as usual.
2. Flow sets the barcodes within a few seconds.
3. The client **prints** the labels in Retail Barcode Labels.

Any number of batches a day is fine. To catch anything Flow missed, run
`python3 -m catalog check-barcodes --since <batch date>` after an import.
It lists shared barcodes and any Floor Sale copy still without a barcode.

## Not covered

- **The 29 existing shared barcodes.** One side of each pair needs a new
  barcode typed in by hand; its own variant ID is a safe choice. Then
  reprint that label. `check-barcodes` with no `--since` lists them all.
- **Same-day handle clashes.** Two batches on one date that both contain
  the same title + format produce the same handle, and Shopify **skips**
  the second copy on import (overwrite unticked). Flow doesn't change
  that. Until it's solved, put a day's copies of the same title + format
  in one batch.
- **Products other than Floor Sale** (merch, etc.). Widen the condition
  if they also get app-generated labels.
