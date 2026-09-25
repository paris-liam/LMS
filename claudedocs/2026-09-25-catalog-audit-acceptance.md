# Catalog audit — production acceptance run (2026-09-25)

Plan: `docs/superpowers/plans/2026-09-25-catalog-pipeline-1-foundation-audit.md` (Task 11).
Run: `runs/2026-09-25-2` · source `api p0wkgv-wy.myshopify.com` (read-only) · TMDB on.

## run-report.txt

```
audited:   7149 movies (excluded — retail template: 6)
findings:  2202 across 1092 products
by bucket (products):  auto-fix 143 · picker 906 · manual 122
by rule (products):
  alt-text-missing 4 · description-missing 890 · floor-sale-price 2 · format-missing 7
  genre-metafield-sync 136 · genre-missing 42 · inventory-untracked 30 · poster-missing 964
  rental-barcode-duplicate 2 · rental-price-nonzero 4 · type-missing 39
auto-fix:  143 products in autofix.json
picker:    56 new products in review.json
tmdb:      2 cache hits, 136 fetches
```

Catalogue shape: 7,149 movies — 3,258 Rental, 3,852 Floor Sale (39 have neither tag); 7,055 active, 94 draft, 0 archived.

## Against the reference counts (each on its own scope)

| measure | reference | this run | explanation |
|---|---|---|---|
| Rentals missing a poster | 133 (rental catalogue, 2026-09-16) | 250 | Rental count grew (3,130 → 3,258 primary products) and the 9-16 figure came from a static export file; most of today's gaps are already in the picker (below). Not a rule error: the check is "Image Src empty" on the live product. |
| Rentals missing a description | 118 (same) | 237 | Same explanation. |
| Barcodes shared by >1 movie | 13 pairs (2026-09-19, all products) | 21 barcodes | Catalogue roughly doubled since (Floor Sale uploads). Only **2** involve a Rental (`frances-vhs-rental-drama` ↔ `swashbuckler-dvd-rental-action`, barcode `08873722`); the rest are Floor-Sale-only, which the rules allow. |
| Rental barcodes that are 8 digits | — | 3,258 / 3,258 | Every rental passes the format rule. |

## Why only 136 TMDB lookups for 988 products missing content

The picker registry already holds 1,073 queued handles (904 `ambiguous-queue`, 169 `unmatched-queue`). 826 of the 988 are among them, so the audit reports them as "already queued" and skips the lookup — the intended behaviour. The remaining 162 were looked up: ~82 got a confident poster and ~82 a confident description (auto-fix), 56 went to `review.json` for the picker.

## Spot-check (two per rule, checked against the product data)

All correct. Examples:
- `genre-metafield-sync` — `300-bluray-rental-action`, `a-christmas-story-bluray-rental-holiday`: metafield empty, tag carries the genre → proposes `action` / `holiday`. **136 live products are missing from the genre filter for this reason.**
- `poster-missing` / `description-missing` auto-fix — `300` → *300 (2007)*, `A Fistful of Dollars` → *(1964)*.
- `type-missing` — `30-days-of-night`, `4400-the-complete-first-season`: no Rental/Floor Sale tag (carry legacy `Issue_*` tags).
- `format-missing` — `antz`, `blind-side`: Vendor is `Little Movie Store`.
- `rental-price-nonzero` — `easyriders-vhs` 5.00, `our-town-vhs` 4.00.
- `floor-sale-price` — `earth-girls-are-easy`, `the-call-dvd-floor-sale-thriller` at 0.00.

No rule looked wrong; no fix-up task needed before Plan 2.

## Notes for Plan 2

- No `option1-genre` findings in production today, so the risky Option1 change is not needed for any live product yet.
- No `type-alias` / `format-alias` / `genre-alias` findings: tag spelling is clean.
- The picker backlog (1,073 queued, 0 applied) is the largest item; Plan 2's `apply` is what turns client picks into imports.
