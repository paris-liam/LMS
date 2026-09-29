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
- 9 priced VHS with no type → `Floor Sale`, `Issue_Rental_Or_Sale` removed.
- New genre **Special Interest** — `shopify--genre` metaobject
  `special-interest` (base genre: Other), pipeline taxonomy, client sheet
  mappings + guide. Applied to 9 products. The client's live Google Sheet
  still needs the row `Special Interest,special-interest` in its `mappings`
  tab and the option in its Genre dropdowns.
- Western → Action (The Hateful Eight, The Searchers); Music → Musical
  (Good Charlotte); Chicago → Musical, Ivory Hunters → Action, Zoolander →
  Comedy. Replaced tags removed.
- 26 genre-missing products: genre from a TMDB lookup, approved by the user
  (`runs/2026-09-28-4/genre-approved.json`, not tracked). Each genre is set
  as Option1 value + tag + `shopify.genre` metafield + category
  `Media > Videos`; `Issue_Genre_Needed` removed.
- Decision: **Floor Sale items don't need new barcodes.** Removed
  `Issue_Needs_New_Barcode` from the 7 floor-sale items that had it.
- Audit after all of the above (`runs/2026-09-28-5`): manual bucket 33
  products — only the deferred items below.

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

## Follow-ups

- **DONE 2026-09-29 — Removed the 2019 cut-off from the TMDB tie-break**, and
  from the ambiguous-match retry and the picker's candidate list (same false
  premise). `classify_match` in `catalog/tmdb/match.py`
  drops candidates newer than `GLOBAL_YEAR_CUTOFF` (2019) before breaking a
  tie between same-titled films, so a new release can never win its own tie:
  it matched *Weapons* (2025 Blu-Ray) to the 2007 film. The store carries new
  releases, so the cut-off is wrong for ties. (The VHS cut-off,
  `VHS_YEAR_CUTOFF`, is a separate format check and stays.)
