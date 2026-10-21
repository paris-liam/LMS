# Little Movie Store — Libib rental upload sheet

This sheet lets you add a batch of rentals to Libib in one go, instead of
one at a time. You list the movies on one tab, and the other tab builds a
file Libib can import.

After the import, nothing changes from the usual routine. Libib gives every
copy its own barcode (starting `201`), and the **sync page** turns the new
copies into Shopify products, exactly as if you'd added them by hand.

You only ever **add** rentals with this sheet. Fixing a title or genre later,
or adding one more copy of something already in Libib, happens in Libib.

---

## The whole flow, start to finish

1. **Start a batch.** Make a copy of the master sheet and clear out the old
   rows.
2. **Fill in one row per title and format.** Three copies of the same VHS is
   one row with **Copies** = 3.
3. **Check the Check column.** Every row should say **OK**.
4. **Import into Libib.** Download the `Libib import` tab and import it into
   the Rental Library.
5. **Sync to Shopify** with the sync page, as usual.

Each step is described below.

---

## One-time setup

Do this once, on your master copy.

1. **Create the sheet.** In Google Sheets: File → Import → Upload
   `libib-rental-template.csv` → "Replace spreadsheet". Rename the tab that
   appears to exactly **`Add rentals`**. It has the eight columns you fill in
   (A–H) and four example rows. Leave them for now; you'll use them to check
   the setup.

2. **Add the `mappings` tab.** File → Import → Upload `genre-mappings.csv`
   → **Insert new sheet**. Rename the new tab to exactly `mappings`. Check
   that **A4 reads `Kids & Family`** and **A16 reads `Martial Arts`**. Then
   right-click the tab → Hide sheet.

3. **Add the Check column.** On `Add rentals`, paste formula 1 from
   `formulas.txt` into cell **I1**, and the status line into **K1**. Never
   type anything else in column I.

4. **Add the `Libib import` tab.** Add a sheet, name it exactly
   `Libib import`, and paste formula 2 from `formulas.txt` into cell **A1**.
   Nothing else goes on this tab.

5. **Add the dropdowns** on `Add rentals`. Select from **row 2 down**, then
   Data → Data validation → Dropdown:

   - **Format** (`B2:B`): `VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`
   - **Genre 1, 2, 3** (`C2:E`): "Dropdown (from a range)" → `mappings!A:A`

6. **Check it works.** The example rows should read **OK**, **OK**, **OK**,
   **pick a genre** in column I, and `Libib import` should show three movies
   (not Speed). Then delete the example rows.

Setup is done. From here on you only type on the `Add rentals` tab.

---

## Step 1 — Start a batch

File → Make a copy of your master sheet. On the copy, delete the old rows.
A fresh copy per batch means you can never import an old batch twice by
accident. Libib doesn't spot duplicates, so a second import adds every movie
again.

---

## Step 2 — Fill in the rows

| Column | What goes in it |
|---|---|
| Title | The movie title exactly as it should appear on the website. No `[VHS]`, `(Widescreen Edition)` or similar |
| Format | Pick from the dropdown |
| Genre 1 | Pick from the dropdown. Required |
| Genre 2, Genre 3 | Optional. More genres from the dropdown |
| Copies | How many copies of this title in this format you're adding. Blank means 1 |
| Description | Optional. Becomes the description on the website |
| Extra tags | Optional. Curation labels, comma-separated, e.g. `Criterion Collection, Rare Finds` |

**Same title, different formats?** Use one row per format. Jaws on VHS and
Jaws on DVD are two rows.

**Adding a copy of something already in Libib?** Don't use the sheet. Open
the item in Libib and add a copy there. The sheet always creates a new item,
so the website would list the movie twice.

Always pick from the dropdowns rather than typing.

---

## Step 3 — The Check column

Column **I** checks each row as you type, and **K1** counts how many rows are
ready.

| Check says | Fix |
|---|---|
| **OK** | Nothing. This row will be imported |
| no title | Type the title |
| pick a format | Choose a format from the dropdown |
| pick a genre | Choose at least Genre 1 |
| unknown genre '…' | A genre was typed, not picked. Pick it from the dropdown |
| copies must be a whole number | Use 1, 2, 3… or leave it blank |

Rows that don't say OK are **left out** of the `Libib import` tab. Nothing
breaks. They just wait until you fix them.

---

## Step 4 — Import into Libib

1. Click the **`Libib import`** tab.
2. File → Download → **Comma-separated values (.csv)**.
3. In Libib: **Add Items → CSV Import**.
   - Library: **Rental Library**
   - Item type: **Movie**
   - Choose the file you downloaded, and continue.
4. On the column-matching page, check that **title → Title**, **description
   → Description**, **tags → Tags** and **copies → Copies**.
5. Turn on **Force Import Mode**. Without it, Libib rejects every row, because
   the sheet doesn't include UPCs.
6. **Process Import.** Libib imports in the background and emails you when
   it's done.

When the email arrives, spot-check one or two movies in the Rental Library:
right title, right tags, one barcode per copy.

---

## Step 5 — Sync to Shopify

Open the sync page and run it as usual (see the sync page's own guide). The
new copies show up under **New copies**, one per copy. Then print barcode
labels from Shopify and stick them on.

---

## Adding a new format or genre

Ask your developer first. Both have to exist in Shopify, in Libib's tags and
in the sync page before a sheet row can use them. If a film doesn't fit any
of the sixteen genres, use the closest one and put the more specific label in
**Extra tags**.

---

## For the developer — check before handing this over

Untested against the client's Libib account. Try one small import (the
three example rows) into the **Rental Library** and confirm:

1. **Copies → barcodes.** A row with Copies = 2 becomes one item with two
   copies, each with its own `201…` barcode, and both appear in the
   Barcodes export. (Imported copies did get `201…` barcodes in the
   2026-09 legacy import — `claudedocs/2026-09-25-libib-acceptance.md` (removed 2026-10-20; in git history).)
2. **Column matching.** Libib auto-matches title, description, tags and
   copies to the right fields.
3. **Tags.** Arrive lowercase and split on commas (`vhs`, `horror`,
   `criterion collection`), so the sync page finds the format and genres.
4. **Sync.** The imported copies show up on the sync page as new, none set
   aside.
