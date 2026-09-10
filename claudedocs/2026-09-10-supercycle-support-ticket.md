# Supercycle support ticket — draft

**Store:** `p0wkgv-wy.myshopify.com` (Little Movie Store)
**Date of investigation:** 2026-09-10, all times UTC
**Method:** Shopify Admin GraphQL API reads + storefront requests. Every claim below is a direct observation.

Three issues, most important first. They may share a root cause.

---

## Issue 1 — `supercycle.methods` and `supercycle.total_uncommitted_inventory` are not written for most products

**Summary:** enabling a rental method writes `supercycle.membership_configuration` reliably, but the product-level metafields (`supercycle.methods`, `supercycle.total_uncommitted_inventory`) and the `Supercycle product` tag are written for only some products. We cannot determine what distinguishes them.

**Scope:** 79 products are imported into Supercycle (per the Supercycle → Products export, 2026-09-09). Only **3** currently carry a `supercycle.methods` value.

### Controlled test

On 2026-09-10 between 18:14 and 18:21 we performed the identical action on six products: Supercycle → Products → [product] → Membership → toggle **off** → Save → toggle **on** → Save.

| Product | `methods` | `total_uncommitted_inventory` | `Supercycle product` tag | `membership_configuration` |
|---|---|---|---|---|
| Fatal Attraction | ✅ `["Membership"]` | ✅ | ✅ | ✅ |
| Rear Window | ✅ `["Membership"]` | ✅ | ✅ | ✅ |
| 007: Tomorrow Never Dies | ❌ absent | ❌ absent | ❌ absent | ✅ |
| 2 Films: Deadly Drifter, Blood Tide | ❌ absent | ❌ absent | ❌ absent | ✅ |
| 2 Days in the Valley | ❌ absent | ❌ absent | ❌ absent | ✅ |
| Small Time Crooks | ❌ absent | ❌ absent | ❌ absent | ✅ |

On **all six**, `supercycle.membership_configuration` was written with a fresh `MembershipOption` global_id and a new `selling_plan.shopify_id`, so the app registered the change every time. On **all six**, the variant metafields are present and correct: `uncommitted_inventory: true`, `uncommitted_inventory_count: 1`, `future_availability_inventory: true`.

So variant-level sync works for every product; product-level sync works for some.

### Hypotheses we eliminated

- **Missing Supercycle items** — ruled out. Every failing product reports `uncommitted_inventory_count: 1`, and the items are visible in the Supercycle inventory table.
- **Shopify inventory tracking** — ruled out. The two products that succeeded had `inventoryItem.tracked: true`; the four that failed had `false`. We set 007: Tomorrow Never Dies to `tracked: true` (`totalInventory` went 0 → 1) and re-toggled Membership at 18:37. `methods`, `total_uncommitted_inventory` and the tag were **all still absent** afterward.

### Questions

1. What determines whether the product-level write runs? Is there a per-product state in Supercycle we can inspect?
2. Is there a manual resync or bulk re-push for products stuck in this state?
3. Is the `Supercycle product` tag written by the same job? It is missing on exactly the same products.

---

## Issue 2 — deleting the `supercycle.methods` definition wiped values store-wide, and re-creating it does not restore them

On 2026-09-10 we accidentally deleted the `supercycle.methods` **product metafield definition** in Shopify admin. Shopify removed the values from all 79 products in a single sweep (product `updatedAt` timestamps 17:53:41 → 17:53:45, ~4 seconds).

Re-creating the definition — name `Supercycle Methods`, type `list.single_line_text_field`, with "Filter on the product list and in the Admin API" and "Use as a condition in smart collections" enabled, per your setup guide — produced an empty definition (`metafieldsCount: 0`). Supercycle did not repopulate it. The only way we have found to restore a value is toggling the method off/on per product, which then only works on the subset described in Issue 1.

**Note on the original type.** Before deletion, `supercycle.methods` was type **`single_line_text_field`** (scalar) holding a JSON-ish string such as `"[\"Membership\"]"`. Your docs and setup guide both specify **List of single line text**. After we re-created it correctly, the value written by the app is a proper `list.single_line_text_field`. It looks like the app may have originally created this metafield with the wrong type on our store, which would also have prevented it working as a filter.

### Questions

1. Is there a way to trigger a bulk re-push of `supercycle.methods` for all Supercycle-enabled products?
2. Should the app be creating this metafield as `list.single_line_text_field`? Ours was scalar before we re-created it.

---

## Issue 3 — storefront availability filter returns no products

**Variant metafield definition:** `supercycle.uncommitted_inventory`, display name "Rental availability", type **boolean**, `metafieldsCount: 81`, storefront access `PUBLIC_READ`.

Storefront results on `/collections/all-movies` (57 products, password protection off):

| Filter | Result |
|---|---|
| `?filter.p.m.supercycle.methods=Membership` | **3 items** — correct, matches the 3 products that have a value |
| `?filter.v.m.supercycle.uncommitted_inventory=1` | **No products** |
| `?filter.v.m.supercycle.uncommitted_inventory=true` | **No products** |

The `methods` filter works. The availability filter matches nothing, in either value form, despite 81 variants carrying `true`.

We also found that Shopify **rejects** the admin-filterable capability on this definition:

```
INVALID_CAPABILITY: The capability admin_filterable is not valid for this definition.
```

so the product-level filter setup instructions cannot be applied to the variant metafield. We enabled `smartCollectionCondition` successfully; it made no difference to the storefront filter.

One possibility we cannot test from outside: the 81 values were written by Supercycle **before** any definition existed for that metafield, and Shopify may not have indexed them for storefront filtering.

### Questions

1. What is required to make `supercycle.uncommitted_inventory` usable as a storefront filter? Does the definition need to exist before the app writes values?
2. Should we be creating this definition ourselves, or does the app create it? Ours is named "Rental availability" — we did not create it.
3. Is there a known indexing delay after the definition is created?

---

## Documentation note (already filed via docs feedback)

`/developers/app-blocks/availability-search` documents `supercycle.uncommitted_inventory` as `number_integer` "set to `1`", while `/developers/metafields` documents it as `boolean`. Our store has it as boolean `true`. Worth reconciling.
