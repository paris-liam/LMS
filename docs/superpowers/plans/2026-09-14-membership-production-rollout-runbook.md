# Membership Production Rollout Runbook

Repeatable sequence for standing up the membership system on **production** (`p0wkgv-wy.myshopify.com`), once dev-store validation (Tasks 1–11 of `2026-09-13-membership-system-implementation.md`) is complete and approved.

This reflects what was **actually built and corrected** during the dev-store build, not just the original plan — several mutation shapes and assumptions in the original plan turned out to need fixing along the way; those fixes are baked into the steps below. Where a step references a dev-store ID, production will get its own new ID — do not reuse dev's.

**Do not run any of this against production until explicitly told to.** Per this repo's rules, production is off-limits by default outside the current TEMPORARY override — restate the target store before each write.

---

## Part A — Theme code (already portable, no manual rebuild)

Everything below lives in git on this branch and pushes like any normal theme change — no manual UI reconstruction needed on production:

- `theme/lms-redesign-v4/templates/product.membership.json` — membership PDP (terms checkbox + optional birthday field, no character counter, single-button checkout)
- `theme/lms-redesign-v4/templates/page.membership-terms.json` — terms page template (only relevant if production's existing Membership Terms page is switched onto it — see Part D, Step 4 note)
- `theme/lms-redesign-v4/blocks/buy-buttons.liquid` — adds `hide_dynamic_checkout` and `enable_checkout_redirect` toggles (both default off — safe for every other product on the site)
- `theme/lms-redesign-v4/blocks/membership-checkout-redirect.liquid` + `assets/membership-checkout-redirect.js`
- `theme/lms-redesign-v4/blocks/membership-terms-dialog.liquid` + `assets/membership-terms-dialog.js`
- `theme/lms-redesign-v4/blocks/product-custom-property.liquid` — adds `hide_character_count` toggle (default off)
- `theme/lms-redesign-v4/templates/page.membership.json` — "Join the Club" CTA button
- `theme/lms-redesign-v4/templates/page.json` — default page template's heading-block removal (already merged to `main` and live on production as of 2026-09-14 — confirm it's still there before assuming this step is needed)

**Step 1:** Pull production's live theme first (client edits colour schemes/settings there directly):
```bash
shopify theme pull --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme <PRODUCTION_LIVE_THEME_ID>
```
Run `shopify theme list --store p0wkgv-wy.myshopify.com` first to confirm the current live theme ID — don't trust a remembered one.

**Step 2:** Reconcile any incoming changes with git, resolve conflicts if the files above were also touched live.

**Step 3:** Push the membership-related files listed above:
```bash
shopify theme push --path theme/lms-redesign-v4 --store p0wkgv-wy.myshopify.com --theme <PRODUCTION_LIVE_THEME_ID> --allow-live \
  --only templates/product.membership.json \
  --only blocks/buy-buttons.liquid \
  --only blocks/membership-checkout-redirect.liquid \
  --only blocks/membership-terms-dialog.liquid \
  --only blocks/product-custom-property.liquid \
  --only assets/membership-checkout-redirect.js \
  --only assets/membership-terms-dialog.js \
  --only templates/page.membership.json
```

**Step 4:** Verify each pushed file actually took effect via the Admin API (a push can silently no-op — this happened once during dev-store work; always re-check rather than trust the CLI's success message alone):
```bash
shopify store execute --store p0wkgv-wy.myshopify.com \
  --query 'query { theme(id: "gid://shopify/OnlineStoreTheme/<PRODUCTION_LIVE_THEME_ID>") { files(filenames: ["templates/product.membership.json"], first: 1) { nodes { body { ... on OnlineStoreThemeFileBodyText { content } } } } } }'
```

---

## Part B — Admin config (must be redone per store — not portable via git)

### Step 1: Customer metafield definitions

```bash
SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-membership-metafield-definitions.sh
```
Requires the CLI session to have `write_customers` scope on production (**not** `write_metafield_definitions` — that scope name doesn't exist; see the memory note on this). Grant with:
```bash
shopify store auth --store p0wkgv-wy.myshopify.com --scopes write_customers
```
Verify:
```bash
shopify store execute --store p0wkgv-wy.myshopify.com \
  --query 'query { metafieldDefinitions(first: 10, ownerType: CUSTOMER) { nodes { namespace key type { name } } } }'
```
Expect `custom.libib_barcode` and `custom.birthday`, both `single_line_text_field`.

### Step 2: Create the membership product

Check first whether a leftover/test product already exists on production (the dev store had one — "LMS Annual Membership" — left over from an earlier abandoned attempt; production may or may not).

```bash
shopify store execute --store p0wkgv-wy.myshopify.com --allow-mutations \
  --query 'mutation CreateProduct($product: ProductCreateInput!) { productCreate(product: $product) { product { id handle templateSuffix variants(first: 1) { nodes { id } } } userErrors { field message } } }' \
  -v '{
    "product": {
      "title": "Little Movie Club Membership",
      "descriptionHtml": "<p>A full year of access to our rental library. Renews automatically each year — pause or cancel anytime.</p>",
      "status": "ACTIVE",
      "templateSuffix": "membership",
      "tags": ["Membership"]
    }
  }'
```
Set price to $160.00 on the returned variant:
```bash
shopify store execute --store p0wkgv-wy.myshopify.com --allow-mutations \
  --query 'mutation SetPrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $productId, variants: $variants) { productVariants { id price } userErrors { field message } } }' \
  -v '{ "productId": "<NEW_PRODUCT_ID>", "variants": [{ "id": "<NEW_VARIANT_ID>", "price": "160.00" }] }'
```

**Step 2a — Publish to sales channels (easy to miss — a new product is NOT auto-published anywhere).**
```bash
shopify store execute --store p0wkgv-wy.myshopify.com --query 'query { publications(first: 10) { nodes { id name } } }'
```
Find the "Online Store" and "Point of Sale" publication IDs (they differ per store), then:
```bash
shopify store execute --store p0wkgv-wy.myshopify.com --allow-mutations \
  --query 'mutation Publish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { field message } } }' \
  -v '{ "id": "<NEW_PRODUCT_ID>", "input": [{ "publicationId": "<ONLINE_STORE_PUB_ID>" }, { "publicationId": "<POS_PUB_ID>" }] }'
```
Requires `write_publications` scope (grant with `shopify store auth --store p0wkgv-wy.myshopify.com --scopes write_publications,read_publications`).

**Step 2b — Verify the storefront actually renders it** (production is presumably not password-protected — adjust if it still is):
```bash
curl -sS "https://littlemoviestore.com/products/little-movie-club-membership"
```
Confirm the page returns 200 (not 404) and contains the terms checkbox + birthday field + Add to cart button.

### Step 3: Shopify Subscriptions setup (manual, Admin UI)

Same as dev Task 6:
1. Confirm Shopify Payments is active.
2. Install Shopify Subscriptions app (if not already — check first, production may already have apps dev doesn't).
3. Create a `Yearly` selling plan on the new product: 1-year interval, auto-renew on, full price.
4. **Skip the manual "cancellation policy" step** — confirmed during dev-store work that Shopify auto-generates a default subscription cancellation policy once a selling plan exists; it doesn't need a separate manual step, and the "Create policy" button this plan originally assumed doesn't exist in this Shopify version.
5. Add the Subscriptions tile to POS smart grid.
6. Customize the renewal-reminder email (brick `#973123` / parchment `#fff9ef`), confirm timing, send a test.

Verify the selling plan via API:
```bash
shopify store execute --store p0wkgv-wy.myshopify.com \
  --query 'query { product(id: "<NEW_PRODUCT_ID>") { sellingPlanGroups(first: 5) { nodes { name sellingPlans(first: 5) { nodes { name billingPolicy { ... on SellingPlanRecurringBillingPolicy { interval intervalCount } } } } } } } }'
```

### Step 4: Member discount (10% off, automatic)

**Corrected mutation shape** — the original plan used a `customerSelection` field on `DiscountAutomaticBasicInput` that does not exist in the current Shopify schema (confirmed via live `__type` introspection during dev-store work). The correct field is `context.customerSegments`.

Create the segment:
```bash
shopify store execute --store p0wkgv-wy.myshopify.com --allow-mutations \
  --query 'mutation CreateSegment($name: String!, $query: String!) { segmentCreate(name: $name, query: $query) { segment { id name } userErrors { field message } } }' \
  -v '{ "name": "Active Member", "query": "customer_tags CONTAINS '"'"'Active Member'"'"'" }'
```
Create the discount (requires `write_discounts` scope):
```bash
shopify store execute --store p0wkgv-wy.myshopify.com --allow-mutations \
  --query 'mutation CreateDiscount($discount: DiscountAutomaticBasicInput!) { discountAutomaticBasicCreate(automaticBasicDiscount: $discount) { automaticDiscountNode { id } userErrors { field message } } }' \
  -v '{
    "discount": {
      "title": "Active Member 10% off",
      "startsAt": "<TODAYS_DATE>T00:00:00Z",
      "context": { "customerSegments": { "add": ["<SEGMENT_ID>"] } },
      "customerGets": { "value": { "percentage": 0.10 }, "items": { "all": true } },
      "combinesWith": { "orderDiscounts": false, "productDiscounts": false, "shippingDiscounts": true }
    }
  }'
```
No product/gift-card exclusion needed — confirmed during dev-store work that automatic discounts don't apply to subscription recurring billing (a Shopify platform limitation) and don't apply to gift cards by default, so neither case can double-discount.

### Step 5: Flow automation

Follow `2026-09-14-membership-flow-automation-runbook.md`, substituting production's own product ID from Step 2 above (and its own Libib credentials — same Libib account, so likely the same key/user, but confirm).

### Step 6: Email blast capability

Confirm Shopify Email is installed, create a test campaign targeting the `Active Member` segment, verify the audience count, discard without sending.

### Step 7: POS staff checklist

`docs/pos-membership-terms-checklist.md` is store-agnostic content — print/post it at the production register. No changes needed unless the process itself changes.

---

## Part C — Content (not code, not Admin config — plain editing)

### Membership Terms page

Production **already has** a "Membership Terms" page (handle `membership-terms`, `templateSuffix: null` — it uses the theme's default page template, not the custom `page.membership-terms.json` built for dev). As of 2026-09-13 its body was still a placeholder: *"Membership sign-up is not yet open online. Full membership terms and conditions will be posted here before enrollment begins."*

**Before launch:** replace that body with the final legal-reviewed agreement text via **Admin → Online Store → Pages → Membership Terms** — a plain content edit, no theme/code change needed. Confirm this has happened before enabling online membership sales on production.

(Optional, not required: if you want production's terms page to use the same custom template as dev — e.g. for the DRAFT-marker mechanism — assign `templateSuffix: "membership-terms"` to the page via `pageUpdate`. Not necessary if the default template already displays the body content fine, which it does.)

---

## Part D — Testing

Same shape as dev Task 11: one online test purchase, one POS test purchase, one induced Libib-failure test, one pause/cancel test via the customer account portal, then clean up test data (delete test Libib patrons, archive/cancel test orders).

**Extra care on production:** these are real customer-facing systems — use a personal test card/account, and double check the discount/tag/Libib effects don't leak into any real marketing segment or customer communication before you're done testing.

---

## Known gotchas hit during the dev-store build (avoid repeating)

- `write_metafield_definitions` is not a real Shopify OAuth scope — use the resource's actual scope (`write_customers` for CUSTOMER metafields, `write_products` for PRODUCT, etc.). Confirmed via memory note `shopify-oauth-scope-names.md`.
- A newly created product is **not** automatically published to any sales channel — always run `publishablePublish` (Part B, Step 2a) or the storefront will 404.
- `DiscountAutomaticBasicInput.customerSelection` doesn't exist — use `context.customerSegments.add`.
- Always verify a theme push actually took effect via the Admin API (`theme { files { ... } }` query) rather than trusting the CLI's success message — one push silently no-op'd during dev-store work and required a second push to actually land.
- Confirm the live theme ID with `shopify theme list` before every push/pull — don't trust a remembered ID (this exact mistake happened once on the dev store, where a stale doc reference pointed at an unpublished theme).
