# Little Movie Store — product upload sheet

This sheet turns a list of movies into two import files: one for **Shopify**
(the website) and one for **Libib** (the rental library). You fill in one
tab; the other two build the files for you.

You only ever **add** products with this sheet. Editing prices, fixing a
description or deleting a product all happen in the Shopify admin (and in
Libib for rentals).

**Start a fresh copy of the sheet for each batch.** File → Make a copy,
delete the old rows, fill in the new ones.

---

## The whole flow, start to finish

1. **Fill in the `Add movies` tab** — one row per physical copy. Paste each
   poster's web address into Image URL, and **download the poster image**
   too (Libib needs the file). Save it under the movie's title.
2. **Import into Shopify** — download the `Shopify import` tab, import it.
3. **Print the barcodes**, stick them on, and **type each copy's barcode**
   into the `Barcode` column on that copy's row.
4. **Import into Libib** — once every rental has its barcode, download the
   `Libib import` tab and import it with Force Import Mode.
5. **Finish each rental in Libib** — set its barcode and upload its poster.

Each step is described below.

---

## One-time setup

Do this once, on your master copy.

1. **Create the sheet.** In Google Sheets: File → Import → Upload
   `client-upload-template.csv` → "Replace spreadsheet". Rename the tab that
   appears to **`Add movies`**. It has the eleven columns you fill in, plus two
   example rows — look at them, then delete them before your first real batch.

2. **Make the Barcode column plain text.** Select column K from K2 down →
   Format → Number → **Plain text**. Barcodes can start with a 0
   (`07530234`), and without this Sheets quietly drops the 0 — and that copy
   can no longer be found in Libib. Then Data → Data validation → Custom
   formula is `=REGEXMATCH(TO_TEXT(K2), "^\d{8}$")` → **Reject the input**, so
   anything that isn't exactly 8 digits is refused.

3. **Add the barcode counter.** In cell **M1** of `Add movies`, paste:
   `="Rentals missing a barcode: "&COUNTIFS(C2:C,"Rental",A2:A,"<>",K2:K,"")`

4. **Add the `mappings` tab.** Don't type or paste this one — import it, so
   the values land exactly right. File → Import → Upload →
   `genre-mappings.csv` → **Insert new sheet**. Rename the new tab to exactly
   `mappings`.

   You should end up with 15 rows: genre names in column A, and a matching
   code in column B (`Comedy` / `comedy`, `Kids & Family` / `kids-family`,
   and so on). Check that **A4 reads `Kids & Family`** and **A15 reads
   `Anime`** — if either is missing or split across two cells, the import
   didn't land cleanly. Delete the tab and import again.

   Right-click the tab → Hide sheet. You never need to look at it again.

   **Why this matters more than it looks.** Every genre you pick is looked up
   in this tab. If a genre is missing from it, the upload still works and the
   product still appears — but its genre is silently left empty, so it won't
   show on the product page and won't appear in the website's genre filter.
   Nothing warns you. That's why it's imported rather than typed.

5. **Add the `Shopify import` tab.** Add a sheet, name it exactly
   `Shopify import`, and paste the formula from `import-tab-formula.txt`
   into cell **A1**. Nothing else goes on this tab.

6. **Add the `Libib import` tab.** Add another sheet, name it exactly
   `Libib import`, and paste the formula from `libib-tab-formula.txt` into
   cell **A1**. Nothing else goes on this tab.

7. **Add the dropdowns** on the `Add movies` tab. For each column, select
   from **row 2 down** (not the header row — including it makes the header
   cell flag as invalid), then Data → Data validation → Dropdown:

   - **Format** (range `B2:B`): `VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`
   - **Type** (range `C2:C`): `Rental`, `Floor Sale`
   - **Genre 1, 2, 3** (ranges `D2:D`, `E2:E`, `F2:F`): "Dropdown (from a
     range)" → `mappings!A:A` (the whole column, so a genre added later shows
     up without editing the dropdown)

That's the whole setup. From here you only ever type on the `Add movies` tab.

---

## Step 1 — Filling in a movie

One row per physical copy. **Three copies of the same tape means three
rows** — select the row and press Ctrl+D twice.

**Always fill in:**

| Column | What goes in it |
|---|---|
| Title | The movie title, as you'd want it on the website |
| Format | Pick from the dropdown |
| Type | `Rental` or `Floor Sale` |
| Genre 1 | Pick from the dropdown — this is the shelf genre, and it prints on the barcode label |
| Price | **Floor Sale rows only.** Leave blank on Rental rows — they're priced by membership, not a shelf price |

**A blank Price on a Floor Sale row still imports** — and rings up at
**$0.00** at the counter. Double-check Price on every Floor Sale row.

**Fill in when you have it:**

| Column | When |
|---|---|
| Description | A sentence or two about the film. Optional — a missing one is filled in later from the movie database |
| Image URL | A public web address for the poster. Optional, same as Description. When you add one, **also download the image** and save it under the movie's title — you'll upload it to Libib in step 5 |
| Genre 2, Genre 3 | If the film genuinely fits more than one genre |
| Extra tags | Curation labels, comma-separated — e.g. `Criterion Collection, A24` |
| Barcode | **Leave blank for now** — it's filled in at step 3 |

Holiday is a **genre**, not an extra tag — pick it in a Genre dropdown.

Always pick from the dropdowns rather than typing. `Blu-Ray` and `BLU-RAY`
typed by hand become two separate options in the website's filters.

---

## Step 2 — Import into Shopify

1. Click the **`Shopify import`** tab.
2. File → Download → **Comma-separated values (.csv)**. That downloads the
   tab you're looking at — no need to select or copy anything.
3. In Shopify: **Products → Import → Add file**, choose the file you just
   downloaded, then **Import products**.
4. **Read the summary Shopify shows you.** It tells you how many products
   were *created* and how many were *updated*. On a batch of new movies it
   should be **all created and none updated**. If it says anything was
   updated, see "When a movie gets updated instead of added" below.

Imported **Rentals** are set **Active** and go live on the website
immediately — there is no draft or review step.

**Floor Sale items are in-store only.** The sheet keeps them off the website
for you (the `Published` column on the `Shopify import` tab is `FALSE` on
every Floor Sale row) — they're still **Active**, so you can ring them up
at the counter as usual. There's nothing to do here; just don't edit that
column.

**Import this tab once per batch.** Importing it again doesn't add anything
new — it re-applies the sheet's values to the same products.

---

## Step 3 — Barcodes

Create and print the labels for the new products as usual, and stick them
on. Then, for each copy, type the number printed on its label into the
**Barcode** column on that copy's row — all 8 digits, including any leading
0.

Every **Rental** needs one before the Libib step. (Floor Sale rows can have
one too; it's simply not used.) Watch the counter in M1 — when it reads
**Rentals missing a barcode: 0**, you're ready for Libib.

---

## Step 4 — Import into Libib

1. Click the **`Libib import`** tab. It lists every rental that has a
   barcode — nothing else. Check the number of rows matches the number of
   rentals in the batch.
2. File → Download → **Comma-separated values (.csv)**.
3. In Libib, import it into the rentals library with **Force Import Mode**
   turned on. On the column-matching screen check that **title, description,
   tags, price, copies and call_number** each land on the matching Libib
   field (call_number → **Call #**).

**Import this tab once per batch**, and only when the counter reads 0.
Importing a half-finished batch and then the whole one creates every early
copy twice.

---

## Step 5 — Finish each rental in Libib

Libib's import can't set the barcode or the cover, so for each new rental:

1. Search `call:` followed by its barcode (e.g. `call:07530234`) — exactly
   one item should come up.
2. Set its **Barcode** to the same 8 digits as its call number.
3. Upload the poster image you downloaded in step 1, if you have one.

The barcode must be **exactly** the number on the label and in the sheet.
That number is how the rental, its Shopify product and the shop's records
are matched up — a typo here means the copy can't be found.

---

## When a movie gets updated instead of added

Every product needs its own web address, and the sheet builds one from the
title, the format and the type — `rushmore-vhs-rental`. If two copies of the
same movie are in the same batch, the sheet notices and names the second one
`rushmore-vhs-rental-2`.

What it can't see is what you uploaded **last time**. If you add another
Rushmore VHS rental in a later batch, it builds `rushmore-vhs-rental` again,
Shopify recognises that address, and **updates the existing product instead
of creating a new one** — so you end up with one product where you wanted
two, and only one barcode.

If the import summary says something was updated when you expected all new:
tell your developer which titles were in the batch **before printing
barcodes for them**. It's fixable, and it's caught by the regular catalogue
cleanup anyway — but the sooner it's known, the less there is to untangle.

**Unusual characters:** an accented or symbol-heavy title makes an ugly web
address — `Amélie` becomes `am-lie`. It still works. If you'd rather it read
properly, type over that one cell on the `Shopify import` tab (e.g.
`amelie-dvd-rental`). The rest of the column keeps working.

---

## What this sheet does not do

**It does not merge duplicate copies.** Uploading the same film several
times is expected and fine — those are real separate copies. Tidying them up
is a periodic job your developer runs.

**It does not fill in missing descriptions or posters.** Those are added
later from the movie database by your developer, on both Shopify and Libib.

---

## Having a file checked

Before importing, you can send either downloaded file to your developer to
run through a checker. It catches a missing genre, a $0 floor sale, a
barcode that lost its leading 0, a barcode used twice, and similar mistakes
that both Shopify and Libib would otherwise accept silently.

---

## Adding a new format

Two steps, and the second one needs your developer:

1. Add it to the **Format** dropdown (Data → Data validation on column B).
2. Ask your developer to add it to the theme setting **Recognised media
   formats** (Online Store → Themes → Customize → Theme settings). Until
   that's done the new format won't show as a badge on the product page.
   (It appears in the website's Format filter automatically — no developer
   step needed for that part.)

## Adding a new genre

Ask first — it's a developer step, not a sheet edit. A genre has to exist in
Shopify (as a genre value) and in the pipeline's genre list before a sheet row
can use it; a genre typed only into the sheet is silently left empty on the
product. The fifteen genres in the dropdown are the complete list today
(Special Interest and Anime were added this way on 2026-09-28/29). If a film
doesn't fit any of them, use the closest one and put the more specific label
in **Extra tags**.
