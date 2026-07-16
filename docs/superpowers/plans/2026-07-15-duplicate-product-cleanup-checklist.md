# Duplicate rental-product cleanup — checklist

**Source:** analysis of `data-cleanup/7.15-9.55/export-7.15-9.55.csv` (2,675 products; 925 Rental).
**Scope:** the only same-title + same-format collisions in the entire rental catalogue — **6 pairs**. Everything else is already one-product-per-movie+format, so this is a hand cleanup, not a bulk job.

## How to read the signal

Your real serialized rental copies carry a **`191-…` barcode** and the tags **`CircaOS Import` + `TMDB Filled`** — that's your tracked physical inventory, and its `191-…` barcode is the serial you'll use when creating its Supercycle item (A3). The plain-numeric-barcode twin in each pair is a stray with no serial and no CircaOS tag → the one to remove.

**All 6 pairs are confirmed NOT imported into Supercycle** (checked in the export), so you can delete the redundant product **directly in Shopify — no "exclude from Supercycle" step needed.**

## The 4 clear deletes

For each: **Shopify Admin → Products → [open the DELETE handle] → More actions → Delete** (or select + bulk Delete).

- [ ] **My Fair Lady (VHS)** — keep `my-fair-lady` (`191-VHSMYF-001A`, TMDB Filled) · **delete `my-fair-lady-vhs-rental-musical`** (plain barcode `57689594`, stray)
- [ ] **When a Man Loves a Woman (VHS)** — keep `when-a-man-loves-a-woman` (`191-VHSWHN-001A`, genre correctly = drama) · **delete `when-a-man-loves-a-woman-vhs`** (plain barcode, mis-genred as romantic-comedy)
- [ ] **Forrest Gump (VHS)** — keep `forrest-gump` (`191-VHSFOR-001A`, TMDB Filled) · **delete `forrest-gump-vhs`** (plain barcode `35726330`, stray)
- [ ] **Donnie Darko (DVD)** — *special: neither is a CircaOS serial.* Both are plain-barcode products with no `191-…` serial. Keep whichever you actually hold / prefer the handle of — recommend **keep `donnie-darko`** (cleaner handle; fix its genre to sci-fi if you like) · **delete `donnie-darko-dvd`**. If you physically stock a DVD copy, note its barcode so it can become the item serial in A3.

## The 2 judgment calls — LOTR Extended Editions (probably KEEP both)

These are **not true duplicates** — the second product in each pair is a distinct **Extended Edition** (different disc, runtime, cover, description). Under one-product-per-movie+format there's no clean variant axis for "edition," so keeping them as separate products is legitimate.

- [ ] **LOTR: The Two Towers (DVD)** — `the-lord-of-the-rings-the-two-towers` (theatrical, `191-DVDTHS-001A`) vs `...-two-towers-dvd-extended` (Extended, plain barcode). **Decide:**
  - Physically stock the Extended as a rentable → **keep both**; give the Extended a `191-`-style serial (or use its barcode) when you create its item in A3.
  - Extended was catalogue padding, not held → delete `...-two-towers-dvd-extended`.
- [ ] **LOTR: The Return of the King (DVD)** — `the-lord-of-the-rings-the-return-of-the-king` (theatrical, `191-DVDTH2-001A`) vs `...-return-of-the-king-dvd-extended` (Extended). Same decision as above.

## After cleanup

- Product count drops by 4 (or 6 if you also drop the two Extended editions). "All Movies" collection reflects it automatically.
- The kept `191-…` barcodes are your item serials for A3 — you don't need to invent new ones.
- Re-export isn't required; this is a targeted delete.

> Caveat: this list is every collision found by normalized **title + media-format** matching. A duplicate hiding under a differently-spelled title (e.g. a year suffix) wouldn't be caught — but with every rental product at inventory qty 1 and a clean set, that risk is low.
