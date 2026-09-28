# Shopify manual fixes — 2026-09-28

Working through the audit's `manual` bucket on production
(`p0wkgv-wy.myshopify.com`). Changes are made through the Admin API (the
Dev Dashboard app has `write_products` since 2026-09-28) and verified by
reading each product back.

## Done

- 4 priced VHS rentals (Easyriders, Our Town, Retribution, September) →
  Floor Sale; `Rental`, `Issue_Rental_Price`, `not-yet-in-libib` removed.
- 29 untracked products → inventory tracked (CSV import).
- 6 format-missing floor-sale items → Vendor `VHS`, `Issue_Needs_Format`
  removed (Antz, Blind Side, Blind Trust, Meteor, Star 80, Tie Me Up Tie Me Down).

## Decided (in progress)

- 9 priced VHS with no type → `Floor Sale`, remove `Issue_Rental_Or_Sale`.
- New genre **Special Interest** (Shopify genre value + pipeline taxonomy +
  client upload sheet). Applied to the 9 products tagged `Special Interest`.
- Western → Action (The Hateful Eight, The Searchers); Music → Musical
  (Good Charlotte); title-as-tag → Chicago: Musical, Ivory Hunters: Action,
  Zoolander: Comedy. The replaced tags are removed.
- The remaining genre-missing products: TMDB genre lookup, applied only
  after the user approves each proposal.

## Deferred

- **29 products with no Rental/Floor Sale tag, priced $0** (all DVD/Blu-Ray,
  probably rentals). 26 still carry old `191-…` call numbers as their Shopify
  barcode and are tagged `Issue_Needs_New_Barcode` — none has a new barcode in
  the reprint map yet, so each needs a new 8-digit label, the Shopify barcode
  updated, and Libib updated. The other 3 (For the Boys, Legend of Zorro,
  Paradise Now) have valid 8-digit barcodes. Open question: tag all 29 Rental?
- **Swashbuckler / Frances share barcode `08873722`.** Swashbuckler
  (`swashbuckler-dvd-rental-action`) is a Rental (tagged Rental + new-arrival,
  $0), created 2026-09-25 — two months after Frances (2026-07-24), and the
  Libib item under `08873722` is Frances. Likely the number was entered on
  Swashbuckler by mistake. Needs: check the physical label on Swashbuckler;
  if it reads `08873722`, print it a new label.
- **Floor Sale at $0** — Earth Girls Are Easy, The Call (`Issue_No_Price`):
  need prices.
