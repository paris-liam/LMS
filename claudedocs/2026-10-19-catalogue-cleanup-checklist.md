# Catalogue cleanup checklist — Shopify + Libib (2026-10-19)

Everything left to make every product in Shopify (production, `p0wkgv-wy.myshopify.com`) and
every item in Libib's Rental Library clean. Numbers are from audit run `runs/2026-10-19-3`
and the Libib diff after that day's sync.

**Where things stand:** 8,088 movies audited. Every automatic fix is applied (0 left). Libib
matches Shopify for all 3,860 synced rentals (no drift). What is left needs a person.

| Who | What | Count |
|---|---|---|
| Client | Picker: choose TMDB matches | 105 rentals |
| Client | Physical checks: barcodes, Rental vs Floor Sale, a price, Libib shelf checks | 12 Shopify products, 3 Libib items |
| Developer (in Libib) | Delete duplicate records left by reprinted labels | 3 Libib items |
| Developer | Fixes applied earlier that never showed up in Shopify, and client-skipped cards | 17 products |
| Developer | Not measured by the audit: duplicate copies, retired picker groups, sheet genre row | — |

---

## 1. Client — finish the picker (105 rentals)

- [ ] Work through the `rentals` group in the review picker: 104 rentals with no description
      (this is what keeps them out of Libib) plus 1 with only a missing poster.
- [ ] Mark *Nemesis 4: Cry of Angels* in the `untyped` group (also see §2).
- [ ] For a card with no TMDB match, type the description (and add a poster) in Shopify admin.
- [ ] Developer: after each picker session, `apply` the picks and run `libib sync`.

## 2. Client — physical checks

**Barcodes** — check the printed label; type the correct 8-digit barcode into Shopify. All three
are tagged `Issue_Needs_New_Barcode` and are held out of Libib until fixed.

- [ ] *Matrix Reloaded* (`matrix-reloaded`, DVD) — barcode `191-UNKTHM-001A` is not 8 digits.
- [ ] *It Happened on 5th Avenue* — `33610490` is also on `rocky-floor-sale-drama`.
- [ ] *The Lorax* (`the-lorax-dvd-rental-kids-family`) — `83728890` is also on the *Harry Potter
      and the Deathly Hallows Part 1* Floor Sale copy. Check which label is wrong.

**Rental or Floor Sale** — each is tagged `Issue_Rental_Or_Sale`; replace it with `Rental` or
`Floor Sale`.

- [ ] *4400: The Complete First Season*
- [ ] *Legend of Zorro*
- [ ] *Paradise Now*
- [ ] *Prince of Persia: The Sands of Time*
- [ ] *Star Trek: Nemesis*
- [ ] *Texas Chainsaw Massacre*
- [ ] *Transformers: Two-Disc Special Edition*
- [ ] *Nemesis 4: Cry of Angels*

**Price**

- [ ] *The Call* (`the-call-dvd-floor-sale-thriller`) — Floor Sale with no price.

**Libib shelf checks** — Libib items with no Shopify rental.

- [ ] *The Shawshank Redemption* `07444730` (DVD) — a fourth copy not in Shopify, or a stale
      record? The three Shopify rentals are already in Libib under their own barcodes.
- [ ] *Adam's Rib* `90000017` — no Shopify product at all.
- [ ] *Best of Abbott and Costello Volume 4* `90000060` — no Shopify product at all.

For each: if the copy exists, create its Shopify rental with that barcode (the next sync matches
it); if not, delete the Libib record.

## 3. Developer, in Libib — delete duplicates from reprinted labels

Each copy got a new label, Shopify was updated, and the sync imported the new barcode as a new
item. The old record is the duplicate. Check for an active loan before deleting (a loan on the
old record would be lost).

- [ ] *One Rainy Afternoon* — delete `90000278` (same copy is `32299770`).
- [ ] *The Man In The Moon* — delete `90000380` (same copy is `20077306`).
- [ ] *Matrix Reloaded* 4K — delete `90000228` (same copy is `30407162`, `the-matrix-reloaded`).

The sync now detects reprints and renumbers the existing item instead (`44de37b`), so this
should not recur.

## 4. Developer — fixes that didn't stick, and skipped cards (17)

- [x] 14 `applied-but-missing` — **investigated 2026-10-19: nothing was lost.** Each was a manual
      picker entry where the client wrote a description but gave no poster (mostly double
      features, collections and TV episodes with no single TMDB poster). The description landed;
      the poster was never supplied. The audit now reports these as `poster-missing` (manual,
      "the client's picker entry had none"), not `applied-but-missing`. **Still owed: a poster
      (e.g. a photo of the case) for each, added in Shopify admin.** Posters don't block Libib.
  - [ ] *Candyman / The Fog / Terror Train* · *Dracula Sucks* · *Faerie Tale Theater: The Snow
        Queen* · *Going My Way / Holiday Inn* · *Incubus Volume 2* · *Miami Vice II* ·
        *Pet Sematary / A Quiet Place* · *The Dentist / The Dentist 2* · *The Dogfighters* ·
        *The Fog / The Howling* · *The Gun Run* · *The World According to Goofy* ·
        *Warlock Collection* · *Wildside: Crimea of the Century*
- [x] 3 `client-skipped` cards — decided 2026-10-19:
  - [x] *Hugo Mask Special! Horrible Full Head Mask With Hair!* (Blu-Ray, `90000192`) — it is its
        own title, not a copy of *Hugo*. Left as is (ignore).
  - [x] *Warner Bros. Animation Collection* (DVD, `19271674`) — the 3-disc 2008 Academy Awards
        Animation Collection (41 cartoons). Description written to Shopify.
        - [ ] Poster still owed (photo of the case).
  - [x] *WB Academy Award Animation* (DVD, `30551290`) — the single-disc 15 winners. Description
        written to Shopify.
        - [ ] Poster still owed (photo of the case).

## 5. Not measured by the audit

- [ ] **Duplicate copies.** The periodic dedupe + consolidate pass has not been run on the
      ~8,000-product catalogue. Plans: `2026-07-15-duplicate-product-cleanup-checklist.md`,
      `2026-07-15-circaos-same-format-copy-consolidation.md`. Biggest remaining job.
- [x] **Retire the old picker groups** `floor-sale-01`–`08` (749 cards from before Floor Sale
      stopped needing posters and descriptions). Done 2026-10-19: hidden from the launcher (no
      picks had been made in any of them) and their handles dropped from the registry, so a copy
      later changed to Rental is queued normally.
- [ ] **Martial Arts genre in the client sheets.** Add a `Martial Arts | martial-arts` row to the
      `mappings` tab of both live Google Sheets (rental and Floor Sale), or it won't appear in the
      genre dropdown.

## Keeping it clean

The client uploads continuously (365 new products 2026-10-15 → 19), so a one-off pass won't stay
clean. Run this weekly:

1. `python3 -m catalog audit`
2. `python3 -m catalog apply --dry-run`, then `--approve <code>`
3. `python3 -m catalog picker push --dry-run`, then `--approve <code>`
4. Unpublish any Floor Sale items found on the Online Store, and fix anything else listed as manual.
5. `python3 -m catalog libib sync --dry-run`, then `--approve <code>`
