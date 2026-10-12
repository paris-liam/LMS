# Non-movie products default to tax-exempt (Shopify Flow)

**Decided 2026-10-12.** Every product that is not a movie (category `Media > Videos`) is
tax-exempt — merch, mystery bags, membership, stickers, candles, etc. Movies stay taxable.

Shopify has no store-level "default taxable" setting: every new variant is created with
*Charge tax* on. So a Flow workflow on production (`p0wkgv-wy.myshopify.com`) turns tax off
the moment a non-movie product is created.

Movies are untouched by the workflow: the client upload sheet sets `Product Category` to
`Media > Videos`, and a CSV import with no `Variant Taxable` column creates variants with
tax on — so movies come in taxable without any extra step.

## One-time backfill (done 2026-10-12)

All 13 existing non-video products on production were set to `taxable: false`
(40 variants across 12 products; the annual membership was already exempt).
Verified by re-reading the store: 0 taxable non-video variants, all 7,554 video products
still taxable.

## Flow workflow setup (Shopify admin → Apps → Flow → Create workflow)

1. **Trigger:** `Product created`.
2. **Condition:** `Product / Category / Full name` **is not equal to** `Media > Videos`.
3. **Then → Action:** `Send Admin API request`
   - Mutation: `productVariantsBulkUpdate`
   - Mutation inputs:

     ```liquid
     {
       "productId": "{{ product.id }}",
       "variants": [
         {% for variant in product.variants %}
           { "id": "{{ variant.id }}", "taxable": false }{% unless forloop.last %},{% endunless %}
         {% endfor %}
       ]
     }
     ```
4. Name it `Non-movie products: tax off on create` and **Turn on**.

### Test

Create a throwaway product in admin with no category (or a merch category), save, wait
a few seconds, reload: *Charge tax* should be unticked on every variant. Check the run
under Flow → the workflow → Recent runs if not. Then delete the test product.

## Limits

- Only fires on **product creation**. A variant added later to an existing non-movie
  product starts taxable — untick *Charge tax* on it by hand.
- A movie created by hand in admin *before* its category is set to `Media > Videos` will be
  made exempt — set the category on the first save, or re-tick tax afterwards.
