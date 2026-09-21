# Libib sync — remaining manual cleanup items

Status as of 2026-09-20. Two real, unresolved issues remain in the
`needs-review` pile (the ~428 legacy `191-XXX` call-number items and the
retriable network-flake stragglers are tracked separately in
`LIBIB_MIGRATION_PROGRESS.md` — not covered here).

("A Knights Tale" was previously listed here as an orphan with no Shopify
match — resolved 2026-09-20, it was just missing from the narrower
rental-only export; it exists in the fuller catalogue export and is now
fully verified and marked `done`.)

---

## 1. Thirteen Shopify products with a duplicate `Variant Barcode`

Two different Shopify products share the same physical barcode value.
Only one can ever hold that barcode as its Libib physical barcode — the
fix is to assign the **wrong-side** product a new, real 8-digit barcode in
Shopify (`Variant Barcode` field), matching whatever your next free serial
is.

**Ten pairs are already live in Libib** — one side already has the
correct barcode set, the other is stuck on a random auto-generated SKU and
needs relabeling:

| shared barcode | ✅ already correct | ⚠️ relabel this one |
|---|---|---|
| `00177914` | All About the Benjamins | **Reversal of Fortune** |
| `00341754` | Hang 'Em High | **Cutthroat Island** |
| `00112378` | Silk 2 | **Century** |
| `48189690` | I, Robot | **A World Apart** |
| `48091386` | Sing | **Hearts of Fire** |
| `48058618` | Marketa Lazarova | **Igby Goes Down** |
| `47927546` | Taken 2 | **No Contest** |
| `48124154` | Happy Feet | **October Sky** |
| `48222458` | 2012 | **The Yards** |
| `48255226` | Mary Poppins | **You Can Count on Me** |

**Three pairs have only had one side imported into Libib so far** — the
imported side already has the correct barcode; the other side is still
waiting in the queue and should be relabeled *before* it gets imported
(otherwise it'll just create the same collision once it does):

| shared barcode | ✅ already correct (live) | ⚠️ relabel before importing |
|---|---|---|
| `48156922` | Lakota Woman | **The Losers** |
| `47993082` | Minority Report | **The Way Back** |
| `00276218` | Circumstances Unknown | **Baywatch The Movie** |

**Action**: in Shopify admin, open each "relabel" product and give it a
new, correct `Variant Barcode` (an unused 8-digit serial). Once done, tell
me and I'll re-run the affected batch to pick up the fix.

---

## 2. Products held back pending the untracked-items collection move

**Update 2026-09-21**: the original "91 held back" list below was built
from a *title*-only collision check, which was too broad. Cross-checking
against a fresh Libib export (`exports/9.21/`) showed that **41 of the 60
"clean" items in the old 2a list weren't actually blocked at all** — the
Libib item their title matched already carries the *exact same* call
number listed here (40 cases), or is a separate, legitimately-coexisting
copy under a different barcode entirely ("Far from Heaven" VHS vs. DVD, 1
case). There was no real duplicate to move for any of these 41. They've
been released back into the pipeline and run through `reverify-posters` +
`sync` (batch-0015) as of 2026-09-21 — no manual Libib action was needed
for them.

Only the **19 items below are a genuine collision**: each one's title
matches a product still sitting live in Libib under a *different*,
old/legacy call number (from the September 2026 accidental mass-restore
cleanup). Importing the Shopify-side copy now, before that legacy
duplicate is moved out of the main Rental Library collection, would create
a second entry for the same movie under two different call numbers.

### 2a. Nineteen genuine collisions — need the collection move

**Action**: move these specific legacy-numbered items (not the full old
108-row list — see `libib-sync/untracked-singles-for-new-collection.csv`
for the broader set) into their own Libib collection. Once that's done,
these are safe to release back into the normal `queue`/`prepare`/import
pipeline — no further Shopify changes needed.

| target call number (Shopify) | title | current (legacy) call number in Libib |
|---|---|---|
| `72531706` | A Serious Man | `191-DVDASE-001A` |
| `32781050` | Bambi | `191-BLRBAM-001A` |
| `94509818` | Casino | `191-DVDCAS-001A` |
| `85307130` | Cinderella | `91308282` |
| `91401722` | Elizabethtown | `191-DVDELI-001A` |
| `97133818` | Enchanted | `191-DVDENC-001A` |
| `94883834` | Fear and Loathing in Las Vegas | `191-DVDFEA-001A` |
| `03956986` | Fear and Loathing in Las Vegas | `191-DVDFEA-001A` |
| `69451514` | Lost in Translation | `191-DVDLOS-001A` |
| `40715002` | Rear Window | `91635962` |
| `93723386` | Saving Private Ryan | `191-BLRSAV-001A` |
| `17927162` | Saving Private Ryan | `191-BLRSAV-001A` |
| `53087226` | Sleepless in Seattle | `191-DVDSLE-001A` |
| `79135226` | Tango & Cash | `191-BLRTAN-001A` |
| `29385210` | The Edge | `35734522` (already-live copy, not a legacy number — verify before moving) |
| `32077306` | The Lord of the Rings: The Return of the King | `191-DVDTH2-001A` |
| `32404986` | The Lord of the Rings: The Two Towers | `191-DVDTHS-001A` |
| `78086650` | The Thin Blue Line | `18621946` |
| `39437050` | You've Got Mail | `191-DVDYOU-001A` |

### 2b. Thirty-one that ALSO need a proper barcode assigned in Shopify

**Action**: same as above (move the collection), **plus** assign each of
these a real 8-digit `Variant Barcode` in Shopify — the collection move
alone won't be enough for these.

| current (legacy) call number | title | Shopify handle |
|---|---|---|
| `191-BLR16B-001A` | 16 Blocks | `16-blocks` |
| `191-DVDASE-001A` | A Serious Man | `a-serious-man` |
| `191-BLRBLV-001A` | Blue Velvet | `blue-velvet` |
| `191-DVDCAN-001A` | Can't Hardly Wait | `cant-hardly-wait` |
| `191-DVDCAT-001A` | Catch Me If You Can | `catch-me-if-you-can` |
| `191-BLRCWB-001A` | Cowboys & Aliens | `cowboys-aliens` |
| `191-DVDELI-001A` | Elizabethtown | `elizabethtown` |
| `191-DVDENC-001A` | Enchanted | `enchanted` |
| `191-DVDFEA-001A` | Fear and Loathing in Las Vegas | `fear-and-loathing-in-las-vegas` |
| `191-BLRGET-001A` | Get Out | `get-out` |
| `191-WALHER-001A` | Herbie: Fully Loaded | `herbie-fully-loaded` |
| `191-DVDLOS-001A` | Lost in Translation | `lost-in-translation` |
| `191-DVDRAT-001A` | Ratatouille | `ratatouille` |
| `191-BLRREA-001A` | Re-Animator | `re-animator` |
| `191-BLRSAV-001A` | Saving Private Ryan | `saving-private-ryan` |
| `191-DVDSAY-001A` | Say Anything | `say-anything` |
| `191-DVDSLE-001A` | Sleepless in Seattle | `sleepless-in-seattle` |
| `191-DVDSNA-001A` | Snatch (Special Edition) | `snatch-special-edition` |
| `191-DVDSPI-001A` | Spirited Away | `spirited-away` |
| `191-BLRSYR-001A` | SYRIANA | `syriana` |
| `191-BLRTAN-001A` | Tango & Cash | `tango-cash` |
| `191-DVDTHB-001A` | The Beales of Grey Gardens | `the-beales-of-grey-gardens` |
| `191-DVDTHC-001A` | The Cabin in the Woods | `the-cabin-in-the-woods` |
| `191-BL2THE-001A` | The Forgotten | `the-forgotten` |
| `191-BLRTHZ-001A` | The Last Waltz | `the-last-waltz` |
| `191-DVDTH2-001A` | The Lord of the Rings: The Return of the King | `the-lord-of-the-rings-the-return-of-the-king` |
| `191-DVDTHS-001A` | The Lord of the Rings: The Two Towers | `the-lord-of-the-rings-the-two-towers` |
| `191-BLRTHT-50-001A` | The Texas Chainsaw Massacre | `the-texas-chainsaw-massacre` |
| `191-DVDTHR-001A` | Three Kings | `three-kings` |
| `191-DVDVIL-001A` | Village of the Damned | `village-of-the-damned` |
| `191-DVDYOU-001A` | You've Got Mail | `youve-got-mail` |
