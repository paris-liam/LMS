# Little Movie Store — product upload sheets: setup & fill guide

Two sheets, same layout:

- **`client-upload-template-rental.csv`** — movies that go into the rental library. Price is always `0`.
- **`client-upload-template-floor-sale.csv`** — movies sold off the floor. You type a real price.

You fill a few friendly columns; the sheet builds the exact Shopify import fields for you. You only ever **add** products with these sheets — edits and removals happen in the Shopify admin.

There are two ways to finish a batch:

- **Path A — upload it yourself.** Fill everything including description and poster URL, export, import to Shopify.
- **Path B — let the script fill it.** Leave `Body (HTML)`, `Image Src` and `Image Alt Text` blank, fill in **Year**, and hand the export to your developer. A TMDB script fills the description and poster, you both review anything it wasn't sure about, then it gets imported.

Either way the sheet is filled the same. Path B just leaves three columns blank.

---

## One-time setup (do this for each of the two sheets)

1. **Import the scaffold.** In Google Sheets: File → Import → Upload the CSV → "Replace spreadsheet". You get the header row plus two example rows. Delete the examples once you've had a look.
2. **Add the hidden mapping tab.** Add a sheet named `mappings` and paste:

   | A (Genre) | B (handle) |
   |---|---|
   | Comedy | comedy |
   | Action | action |
   | Drama | drama |
   | Kids & Family | kids-family |
   | Sci-Fi | sci-fi |
   | Thriller | thriller |
   | Horror | horror |
   | Romantic Comedy | romantic-comedy |
   | Musical | musical |
   | Fantasy | fantasy |
   | Documentary | documentary |
   | Foreign | foreign |
   | Holiday | holiday |

   (Genre labels in `mappings!A2:A14`, handles in `B2:B14`.)

3. **Add dropdowns (Data → Data validation) on the helper columns:**
   - `Format` (col R): list of items `VHS`, `DVD`, `Blu-Ray`, `4K`
   - `Genre 1/2/3` (cols S, T, U): list from range `mappings!A2:A14`

4. **Paste these formulas into row 2**, then select row 2 and drag the fill handle down as far as you need.

   **Both sheets:**

   | Column | Formula |
   |---|---|
   | A `Handle` | see **"The Handle builds itself"** below — the formula differs per sheet |
   | D `Vendor` | `=R2` |
   | E `Product Category` | `="Media > Videos"` |
   | G `Status` | `="Active"` |
   | H `Option1 Name` | `="Genre"` |
   | I `Option1 Value` | `=S2` |
   | J `Variant Inventory Tracker` | `="shopify"` |
   | K `Variant Inventory Qty` | `=1` |
   | L `Variant Inventory Policy` | `="deny"` |
   | M `Variant Fulfillment Service` | `="manual"` |
   | P `Image Alt Text` | `=IF(O2="","",B2&IF(V2="",""," ("&V2&")")&" poster")` |
   | Q `Genre (…shopify.genre)` | `=TEXTJOIN("; ", TRUE, IFERROR(VLOOKUP(S2,mappings!$A:$B,2,FALSE),""), IFERROR(VLOOKUP(T2,mappings!$A:$B,2,FALSE),""), IFERROR(VLOOKUP(U2,mappings!$A:$B,2,FALSE),""))` |

   **Rental sheet only:**

   | Column | Formula |
   |---|---|
   | F `Tags` | `=TEXTJOIN(", ", TRUE, "Rental", R2, S2, T2, U2, W2)` |
   | N `Variant Price` | `=0` |

   **Floor-sale sheet only:**

   | Column | Formula |
   |---|---|
   | F `Tags` | `=TEXTJOIN(", ", TRUE, "Floor Sale", R2, S2, T2, U2, W2)` |
   | N `Variant Price` | *(typed by hand — the real sale price)* |

   Columns B, C, O and helpers R–W are typed by hand.

---

## The Handle builds itself

You don't type handles. The formula makes one from the title, the format, and which sheet you're on.

**Rental sheet — paste into A2:**

```
=IF($B2="","",LET(
  t,    REGEXREPLACE(LOWER(TRIM($B2)), "['’]", ""),
  slug, REGEXREPLACE(REGEXREPLACE(t, "[^a-z0-9]+", "-"), "^-+|-+$", ""),
  fmt,  REGEXREPLACE(LOWER($R2), "[^a-z0-9]+", "-"),
  n,    COUNTIFS($B$2:$B2, $B2, $R$2:$R2, $R2),
  slug & "-" & fmt & "-rental" & IF(n>1, "-" & n, "")
))
```

**Floor-sale sheet — same thing, with `"-floor-sale"` in place of `"-rental"`:**

```
=IF($B2="","",LET(
  t,    REGEXREPLACE(LOWER(TRIM($B2)), "['’]", ""),
  slug, REGEXREPLACE(REGEXREPLACE(t, "[^a-z0-9]+", "-"), "^-+|-+$", ""),
  fmt,  REGEXREPLACE(LOWER($R2), "[^a-z0-9]+", "-"),
  n,    COUNTIFS($B$2:$B2, $B2, $R$2:$R2, $R2),
  slug & "-" & fmt & "-floor-sale" & IF(n>1, "-" & n, "")
))
```

What you get:

| Title | Format | Handle |
|---|---|---|
| Rushmore | VHS | `rushmore-vhs-rental` |
| Rushmore *(2nd copy)* | VHS | `rushmore-vhs-rental-2` |
| Rushmore | DVD | `rushmore-dvd-rental` |
| Paris, Texas | DVD | `paris-texas-dvd-rental` |
| The Monkey's Uncle | VHS | `the-monkeys-uncle-vhs-floor-sale` |
| The Thing | 4K | `the-thing-4k-floor-sale` |

**Handles must be unique — this is the one thing that can really go wrong.** Two rows sharing a handle don't become two products; they become *one* product with two variants. That would merge two physical copies into a single item with a single barcode.

Two limits to know about:

1. **Accented and unusual characters get dropped.** `Amélie` becomes `am-lie`, `8½` becomes `8`. Still valid and still unique — just ugly in the web address. For those rare titles, **type over the formula in that one cell** with something better (`amelie-dvd-rental`). Overwriting a single cell is fine; the rest of the column keeps working.
2. **The counter only sees the sheet it's in.** It knows this is your third Rushmore VHS *in this sheet*. It can't know you uploaded two more last month. If you upload another copy of a movie you already have, from a fresh sheet, the handle repeats and Shopify **updates the existing product instead of adding a copy**. Two ways to avoid it:
   - **Keep one running sheet per type** and just add new rows to the bottom, exporting only the new rows. Then the counter sees everything you've ever uploaded.
   - Or use **Path B** — the script checks handles against the live catalogue before importing and fixes collisions properly.

   Watch the Shopify import summary: if it says products were **updated** when you expected all **new**, a handle collided.

---

## Filling in a movie (one row per row)

**Always type:** `Title`, `Year`, and pick `Format` + `Genre 1` from the dropdowns. *(The handle writes itself.)*
**Optional:** `Genre 2` / `Genre 3`, `Extra tags` (comma-separated, e.g. `Criterion Collection, A24`).
**Floor-sale sheet:** also type `Variant Price`.
**Path A only:** also type `Body (HTML)` and `Image Src`.

Rules:

- **One row per physical copy.** Each row becomes one Shopify product for one physical disc or tape. Three copies of the same movie = three rows. `Variant Inventory Qty` stays `1`.
- **Year is the movie's release year**, not the year of the tape or disc. It's what tells the poster script *which* movie you mean — there are two *The Thing*s (1982, 2011) and two *Little Shop of Horrors* (1960, 1986). Getting it wrong gets you the wrong poster.
- **Genre 1 is the shelf genre** — it prints on the barcode label (see below). Genre 2/3 are extra genres for the website only.
- **Holiday is a genre**, not an extra tag — pick it in a Genre dropdown.
- The grey formula columns fill themselves. Don't type in them.

---

## Why some columns look redundant

`Format` appears in three places on purpose, and each one does a different job:

- **`Vendor`** — what the website reads to show the format badge on the product page and to power the Format filter.
- **a tag** — what Shopify's automatic collections match on.
- **the `Format` helper column** — the dropdown you actually pick from; the other two are built from it.

Same for genre: the metafield drives the website, the tag drives collections, the dropdown feeds both. You only ever pick once.

---

## Columns we deliberately leave out

Shopify fills these in automatically for new products, so the sheet stays short:

| Left out | What Shopify does |
|---|---|
| `Published` | publishes to the online store |
| `Variant Requires Shipping` | `true` |
| `Variant Taxable` | `true` |
| `Variant Grams` / `Weight Unit` | `0` — nothing here ships, so it doesn't matter |
| `Variant Barcode` | assigned by the barcode app when you print (see below) |
| `Variant SKU` | not used for movies |
| `SEO Title` / `SEO Description` | generated from the title and description |

The three inventory columns (`Variant Inventory Tracker`, `Policy`, `Fulfillment Service`) **cannot** be left out. If `Inventory Tracker` is missing, Shopify stops tracking stock, and the website can never show a title as unavailable.

---

## How this connects to your barcode labels

Your Retail Barcode Labels templates (**LMS: RENTAL** and **LMS: FOR SALE**) print the **genre from Variant Option 1**. The sheet sets Option 1 to your **Genre 1** pick automatically, so the genre lands on the label with no extra step.

You don't enter a barcode here — the app assigns one per product when you print. Because every row is its own product (one per copy), every physical copy gets its own barcode.

---

## Exporting

**Path A — you upload it:**

1. Select columns **A through Q** only (Handle … Genre). Do **not** include helper columns R–W.
2. Copy into a new blank sheet → File → Download → **Comma-separated values (.csv)**.
3. Shopify: **Products → Import → Add file** → upload → review → **Import products**.

**Path B — the script fills posters and descriptions:**

1. File → Download → **Comma-separated values (.csv)** on the whole sheet (helper columns included — the script needs `Year` and strips the rest).
2. Send that file to your developer.

---

## Adding new genres, formats, or tags

- **New genre:** add a row to `mappings` (label in col A, its metaobject handle in col B), then extend the `Genre 1/2/3` dropdown ranges. Ask your developer for the handle.
- **New format:** add it to the `Format` dropdown's list of items (Data → Data validation on col R), then tell your developer — the website needs to learn to recognise it before the badge and filter will work.
- **New curation tag:** just type it into `Extra tags`. No setup needed.

---

## Notes

- **One row = one physical copy = one product.** Inventory qty stays `1`.
- Accidental exact duplicates are fine — they get combined in a periodic cleanup pass. Don't try to prevent them here.
- Spelling matters on Format and Genre: `BLU-RAY` and `Blu-Ray` become two separate filter options. Always pick from the dropdown, never type.
