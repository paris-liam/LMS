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
- 2026-09-29: 415+12 auto-fixes applied through the Admin API (Weapons →
  2025, Ghost in the Shell 2 → Innocence, Nosferatu → Eggers 2024 corrected
  by hand first). New genre **Anime** (`shopify--genre` `anime`, base genre
  Anime) + pipeline + client sheet; applied to 8 anime DVD rentals, and added
  as a second genre on Bubblegum Crisis. Career Opportunities Blanket and
  Patti Lapel Hat moved to the `retail` template. The client's live sheet also
  needs the row `Anime,anime`.
- 2026-09-30 tag cleanup (7,073 products, list in `runs/tag-cleanup-plan.txt`):
  removed `Formatted` (7,010), `update-barcode-in-libib` (306),
  `not-yet-in-libib` (200 — nothing in the pipeline reads it),
  `issue:held_for_libib_cleanup` (9), `Batch_6` (7), `Dark City` (1);
  removed stale `Issue_Needs_New_Barcode` from the 462 rentals that already
  have an 8-digit barcode (kept on the 26 deferred `191-` discs) and stale
  `Issue_Rental_Or_Sale` from 7 products already tagged Rental. Added
  `online-store` to the non-movie products except the membership
  (mystery-bag-dvd, mystery-bag-vhs, mystery-bag-vhs-horror, patti-lapel-hat,
  career-opportunities-blanket). `Reprint_These_Barcodes` left as is.
- Audit after all of the above (`runs/2026-09-28-5`): manual bucket 33
  products — only the deferred items below.

## Deferred

- **29 products with no Rental/Floor Sale tag, priced $0** (all DVD/Blu-Ray,
  probably rentals). 26 still carry old `191-…` call numbers as their Shopify
  barcode and are tagged `Issue_Needs_New_Barcode` — none has a new barcode in
  the reprint map yet, so each needs a new 8-digit label, the Shopify barcode
  updated, and Libib updated. The other 3 (For the Boys, Legend of Zorro,
  Paradise Now) have valid 8-digit barcodes. Open question: tag all 29 Rental?
- **DONE 2026-09-30 — Swashbuckler / Frances shared barcode `08873722`.** Not
  a typo: both variant IDs end in `08873722` (Frances `…49749808873722`,
  Swashbuckler `…50581808873722`), so Retail Barcode Labels' last-8-digits
  rule gave both the same number. Frances keeps it (it is the Libib item).
  Swashbuckler (`swashbuckler-dvd-rental-action`) got the next reprint number
  **`90000494`** (sequence last used `90000493`) and the
  `Reprint_These_Barcodes` tag. Still to do: print its new label; the next
  `libib sync` imports it and clears the Frances orphan.
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
