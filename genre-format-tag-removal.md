# Remove genre & format tags from products

Status: investigation re-verified 2026-10-01, nothing changed yet. Goal: delete every **format** tag (VHS, DVD,
Blu-Ray, 4K, Laserdisc, Betamax) and every **genre** tag (the 15 shelf genres) from products. Keep `Rental` /
`Floor Sale`, curation tags (`new-arrival`, `Criterion Collection`, `A24`) and the audit's `Poster_Missing` /
`Issue_*` / `Reprint_These_Barcodes` markers.

Data: production audit snapshot `runs/2026-10-01-6/snapshot.json` (7,336 movies). 7,335 of them carry at least one
format or genre tag (all but `patti-lapel-enamel-pin`). None are multi-variant, so the audit can auto-fix all of them.

## Source of truth after removal

- **Format** = `Vendor`. Every product with a format tag has exactly one, and it matches Vendor (7,003 / 7,003).
  The 333 products with no format tag all have a valid Vendor, except the merch pin.
- **Genre** = `shopify.genre` metafield (every genre, `;`-separated, primary first) + Variant Option 1 (the primary
  genre only). On every product, Option 1 already equals the first metafield genre, and every genre tag is already
  in the metafield. No product has genre tags but no metafield.

## Verified: nothing outside the pipeline reads these tags

- **Smart collections (production, Admin API):** `all-movies` = tag `Rental` + category Media > Videos,
  `new-arrivals` = tags `Rental` + `new-arrival`, `online-store` = tag `online-store`, `plans` is manual.
- **Search & Discovery filters:** Format (`filter.p.vendor`), Genre (`filter.v.t.shopify.genre`) and one
  product-tag filter labelled "New Arrivals". In vertical style the theme hides that tag list and shows only a
  "New arrivals" toggle wired to the `new-arrival` value (`theme/lms-redesign-v4/blocks/filters.liquid:269-300`).
  Removing genre/format tags leaves the toggle working. The All Movies page has no tag filter.
  - Side note, not part of this work: the horizontal style (`/collections/all`, `/search`) renders the whole
    "New Arrivals" tag list, including `Issue_*` tags. Removing genre/format tags shortens that list, but the
    `Issue_*` / `Poster_Missing` / type tags are still exposed there.
- **Theme:** reads only the tags `Rental` (`sections/search-results.liquid:71`) and `rare`
  (`snippets/lms-product-card.liquid:66`, which no product carries).
- **Libib:** `expected_tags_string` builds Libib tags from Vendor + metafield. `is_rental` needs the type tag,
  which stays. `REQUIRED_FIELDS["tags"]` needs Tags non-empty, and the type tag keeps it non-empty.
- **Picker / TMDB:** read only the type tag (`picker/push.py`, `tmdb/candidates.py`). `tmdb-lookup --tag <genre>`
  will stop finding products by genre, which is expected.
- **Storefront search (not verified on the live store):** I believe the primary genre stays searchable through
  the variant title (Option 1) and format through Vendor. Secondary genres of the 15 multi-genre products would
  stop matching search.

## Decisions made

- `flags-of-our-fathers-dvd-rental-documentary` is **Documentary only**. Today: Option 1 Documentary, metafield
  `documentary; drama`, the only genre tag is Drama. Removing the tag is not enough: the metafield must also drop
  `drama`. Once `resolve_genres` reads the metafield (below), the audit will treat `drama` as correct, so fix it by
  hand in the admin (one product). The other copy, `flags-of-our-fathers-dvd-rental-drama`, is Drama everywhere and
  stays as is.
- The S&D "New Arrivals" tag filter stays (it is the new-arrivals toggle).
- All format and genre tags are removed.

## Code that must change

1. **`catalog/audit/resolvers.py` `resolve_genres`** today returns Option 1 + genre tags (`rules.py:39`, `resolve_row`)
   and never reads the metafield. Option 1 holds only the primary genre, so the tags are the only place the audit
   sees a secondary genre.
   - Simulation (current rules on the snapshot with genre/format tags stripped): all **15** multi-genre products get
     a `genre-metafield-sync` auto-fix that shrinks the metafield to the primary genre, e.g. Dazed and Confused
     `comedy; sci-fi` -> `comedy`. That includes `for-the-boys-dvd-rental-musical` and
     `bubblegum-crisis-hurricane-live-2033-...`, plus Flags (documentary). No other findings change.
   - **DONE (branch `feat/genre-from-metafield`):** `resolve_genres(option1_value, metafield_handles, tags)` is now
     a lossless union in that order: Option 1 stays the primary, the metafield adds the secondary genres, and tags add
     anything still missing (a stray upload's tag-only genre is written into the metafield in the same apply that
     strips the tag). Option 1 stays first, so metafield order still doesn't matter and no new `option1-genre` fixes
     appear. The unused `helper_genres` parameter is gone. Tests updated, plus a rule-level regression test
     (`test_secondary_genre_survives_without_genre_tags`, fails on the old code). Full suite: 605 OK
     (`PYTHONPATH=.:tests/catalog python3 -m unittest tests.catalog.test_*`).
   - Re-ran the simulation: **0** new `genre-metafield-sync` findings with tags stripped (was 15). Unchanged
     snapshot: 70 findings with both old and new code.
   - Flags (documentary copy) keeps `drama` under the union, so step 1's manual metafield fix is still needed.
2. **New audit auto-fix that strips the tags.** Nothing removes them today: `respelled_tags` / `final_tags`
   (`rules.py:43-68`) keep every type/format/genre tag by design, so `apply` alone cannot do it.
   - **DONE (branch `feat/genre-from-metafield`):** new AUTO_FIX rule `format-genre-tag` (field Tags). `respelled_tags`
     (and so `final_tags`, the single Tags value every Tags fix proposes) drops every tag where `canonical_format` or
     `canonical_genre` matches, misspelt ones too. `format-alias` / `genre-alias` on Tags are gone, while `type-alias`
     and the Vendor `format-alias` fix stay. `resolve_format` keeps its tag fallback, so a format found only in a tag
     still fixes Vendor in the same apply. Tests: new rule tests, plus fixtures in `test_rules.py`, `test_audit_run.py`
     and `test_audit_command.py` (they carried format/genre tags). Full suite 608 OK. `catalog/README.md` documents
     the rule.
   - Run against the production snapshot (`runs/2026-10-01-6`) vs the previous commit: **+7,335 `format-genre-tag`**
     findings and nothing else. Every non-Tags finding is identical, no product gets conflicting Tags auto-fixes, and
     no product ends up with empty Tags. The 30 `type-missing` products (MANUAL) keep their other tags.
   - `extra_tags` in `resolvers.py` is still used only by its test. Left alone.
3. **Upload sheet** stops writing format/genre into Tags — **repo side DONE 2026-10-02** as part of the sheet
   redesign (`claudedocs/2026-10-01-client-upload-sheet-shopify-and-libib.md`); the seam fixture's Tags column was
   recomputed, to be re-captured from the live sheet. Live sheet still to update:
   - live Google Sheet tab 2: `tags` line `TEXTJOIN(", ", TRUE, y, f, a, b, c, e)` -> `TEXTJOIN(", ", TRUE, y, e)`,
     and the `MAP(...)` arguments to match (`catalog/client_sheet/template/import-tab-formula.txt`)
   - `catalog/client_sheet/transform.py:57` (Python mirror of the formula)
   - fixtures: `client-upload-template.expected.csv`, `sheet-export.csv`, `sheet-export-input.csv` (seam test)
   - `catalog/client_sheet/check.py:83` comment ("labels survive only in Tags") goes stale. The checks already use
     Option 1 + metafield. Separately, `check.py`'s "is not one of the 13" message says 13 but there are 15 genres.
   - The client guide needs no change (it only describes Extra tags).

Keep the type tag: `resolve_type`, `is_rental`, picker push, `tmdb/candidates.py`, the theme's search results and
the `all-movies` / `new-arrivals` collections all read it.

## Proposed order

1. Fix Flags (documentary copy) by hand: set the metafield to `documentary` only.
2. ~~Change `resolve_genres` + tests~~ — done, simulation clean.
3. ~~Add the tag-strip rule + tests~~ — done.
4. Change the upload sheet (formula, `transform.py`, fixtures, `check.py` comment) together, so new uploads
   arrive without these tags.
5. Run a fresh audit, then `apply` with a dry run. Expect about 7,335 Tags changes and nothing else new. Review the
   plan, then approve.
6. Re-audit and confirm no `format-genre-tag` findings remain and no genre metafield changed.

## Separate track (does not block this work): handle genre slug vs data

Older uploads put a genre slug at the end of the handle. On 24 products that slug differs from Option 1 (16 of
those name a genre that is not in the metafield at all). Option 1, metafield and tags agree with each other on all
24, and nothing in the code or theme reads a genre from a handle. So these only matter if the handle is wrong
evidence of a mis-shelved copy. The handle is not a reliable signal: `open-call-dvd-rental-documentary` is titled
"Open Range" and `unknows-origins-...` is a typo. Review them as a data-quality pass if wanted. The earlier claim
that the audit's `option1-genre` fix would rewrite Option 1 on these was wrong. Option 1 is always the first
resolved genre, so that fix never fires when Option 1 holds a valid genre.

| # | Handle | Title | Genre in handle | Option 1 | Metafield |
|---|---|---|---|---|---|
| 1 | `dazed-and-confused-vhs-rental-sci-fi` | Dazed and Confused | Sci-Fi | Comedy | comedy, sci-fi |
| 2 | `youve-got-mail-vhs-rental-romatic-comedy` | You've Got Mail | Comedy | Romantic Comedy | romantic-comedy |
| 3 | `while-you-were-sleeping-vhs-rental-romatic-comedy` | While You Were Sleeping | Comedy | Romantic Comedy | romantic-comedy |
| 4 | `double-feature-first-wives-club-sliding-doors-dvd-floor-sale-comedy-drama` | Double Feature: First Wives Club, Sliding Doors | Drama | Comedy | comedy, drama |
| 5 | `code-of-silence-vhs-floor-sale-action` | Code of Silence | Action | Comedy | comedy, action |
| 6 | `on-the-beach-vhs-rental-sci-fi` | On the Beach | Sci-Fi | Drama | drama |
| 7 | `unknows-origins-vhs-rental-thriller` | Unknown Origins | Thriller | Sci-Fi | sci-fi |
| 8 | `without-mercy-vhs-rental-thriller` | Without Mercy | Thriller | Action | action |
| 9 | `killing-time-vhs-rental-drama` | Killing Time | Drama | Thriller | thriller |
| 10 | `in-search-of-the-castaways-vhs-rental-thriller` | In Search of the Castaways | Thriller | Kids & Family | kids-family |
| 11 | `underworld-dvd-floor-sale-horror` | Underworld | Horror | Thriller | thriller, horror |
| 12 | `galaxy-quest-dvd-floor-sale-sci-fi` | Galaxy Quest | Sci-Fi | Horror | horror, sci-fi |
| 13 | `donnie-darko-dvd-floor-sale-sci-fi` | Donnie Darko | Sci-Fi | Fantasy | fantasy, sci-fi |
| 14 | `eternals-dvd-floor-sale-sci-fi` | Eternals | Sci-Fi | Horror | horror, sci-fi |
| 15 | `eye-of-the-beholder-dvd-floor-sale-thriller` | Eye of the Beholder | Thriller | Action | action, thriller |
| 16 | `moonraker-bluray-rental-sci-fi` | Moonraker | Sci-Fi | Action | action |
| 17 | `paradise-now-bluray-drama` | Paradise Now | Drama | Thriller | thriller, drama |
| 18 | `poison-friends-dvd-rental-thriller` | Poison Friends | Thriller | Foreign | foreign |
| 19 | `booty-call-dvd-floor-sale-comedy` | Booty Call | Comedy | Thriller | thriller, comedy |
| 20 | `walking-tall-dvd-floor-sale-action` | Walking Tall | Action | Comedy | comedy, action |
| 21 | `open-call-dvd-rental-documentary` | Open Range | Documentary | Drama | drama |
| 22 | `its-christmastime-again-charlie-brown-vhs-floor-sale-kids-family` | It's Christmastime Again, Charlie Brown | Kids & Family | Holiday | holiday |
| 23 | `acceptable-risk-vhs-floor-sale-thriller` | Acceptable Risk | Thriller | Sci-Fi | sci-fi |
| 24 | `survival-of-the-illest-vhs-floor-sale-documentary` | Survival of the Illest | Documentary | Drama | drama, documentary |

## Other findings

- 15 products have more than one genre: 12 rows of the table above (1, 4, 5, 11-15, 17, 19, 20, 24), plus `for-the-boys-dvd-rental-musical`, `bubblegum-crisis-hurricane-live-2033-vhs-floor-sale-anime-sci-fi` and
  `flags-of-our-fathers-dvd-rental-documentary` (until step 1).
- 1 product has no genre metafield: `patti-lapel-enamel-pin` (merch, category Uncategorized, Option 1 reads
  "Air Bud", stray data).
- Format-tag counts: VHS 3,749 · DVD 2,181 · Blu-Ray 916 · 4K 123 · Laserdisc 33 · Betamax 1. No misspelt
  format or genre tags exist today.
- Genre-tag counts: Comedy 1,429 · Action 1,367 · Drama 1,322 · Kids & Family 788 · Thriller 762 · Horror 511 ·
  Sci-Fi 461 · Romantic Comedy 210 · Musical 123 · Fantasy 123 · Holiday 85 · Foreign 82 · Documentary 68 ·
  Special Interest 9 · Anime 9.
- Other tags (kept): Floor Sale 3,911 · Rental 3,395 · Poster_Missing 771 · Reprint_These_Barcodes 493 ·
  new-arrival 199 · Issue_Duplicate_Barcode 56 · Issue_Rental_Or_Sale 29 · Issue_Needs_New_Barcode 26 ·
  Criterion Collection 19 · Issue_No_Price 6 · A24 1.
