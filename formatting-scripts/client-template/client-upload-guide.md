# Little Movie Store — product upload sheet

This sheet turns a short list of movies into a file Shopify can import. You
fill in one tab; a second tab builds the import file for you.

You only ever **add** products with this sheet. Editing prices, fixing a
description or deleting a product all happen in the Shopify admin.

**Start a fresh copy of the sheet for each batch.** File → Make a copy,
delete the old rows, fill in the new ones.

---

## One-time setup

Do this once, on your master copy.

1. **Create the sheet.** In Google Sheets: File → Import → Upload
   `client-upload-template.csv` → "Replace spreadsheet". Rename the tab that
   appears to **`Add movies`**. It has the ten columns you fill in, plus two
   example rows — look at them, then delete them before your first real batch.

2. **Add the `mappings` tab.** Add a second sheet, name it exactly
   `mappings`, and paste this table starting in cell A1:

   | | |
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

   Right-click the tab → Hide sheet. You never need to look at it again.

3. **Add the `Shopify import` tab.** Add a third sheet, name it exactly
   `Shopify import`, and paste the formula from `import-tab-formula.txt`
   into cell **A1**. Nothing else goes on this tab.

4. **Add the dropdowns** on the `Add movies` tab. Select the whole column,
   then Data → Data validation → Dropdown:

   - **Format** (column B): `VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`
   - **Type** (column C): `Rental`, `Floor Sale`
   - **Genre 1, 2, 3** (columns D, E, F): "Dropdown (from a range)" →
     `mappings!A1:A13`

That's the whole setup. From here you only ever touch the `Add movies` tab.

---

## Filling in a movie

One row per physical copy. **Three copies of the same tape means three
rows** — select the row and press Ctrl+D twice.

**Always fill in:**

| Column | What goes in it |
|---|---|
| Title | The movie title, as you'd want it on the website |
| Format | Pick from the dropdown |
| Type | `Rental` or `Floor Sale` |
| Genre 1 | Pick from the dropdown — this is the shelf genre, and it prints on the barcode label |
| Description | A sentence or two about the film |
| Image URL | A public web address for the poster image |

**Fill in when it applies:**

| Column | When |
|---|---|
| Price | Floor Sale rows only. Leave blank on rentals — they're priced by membership, not a shelf price |
| Genre 2, Genre 3 | If the film genuinely fits more than one genre. Website only; doesn't affect the label |
| Extra tags | Curation labels, comma-separated — e.g. `Criterion Collection, A24` |

Holiday is a **genre**, not an extra tag — pick it in a Genre dropdown.

Always pick from the dropdowns rather than typing. `Blu-Ray` and `BLU-RAY`
typed by hand become two separate options in the website's filters.

---

## Uploading a batch

1. Click the **`Shopify import`** tab.
2. File → Download → **Comma-separated values (.csv)**. That downloads the
   tab you're looking at — no need to select or copy anything.
3. In Shopify: **Products → Import → Add file**, choose the file you just
   downloaded, then **Import products**.
4. **Read the summary Shopify shows you.** It tells you how many products
   were *created* and how many were *updated*. On a batch of new movies it
   should be **all created and none updated**. If it says anything was
   updated, see "When a movie gets updated instead of added" below.

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
tell your developer which titles were in the batch. It's fixable, and it's
caught by the regular catalogue cleanup anyway — but the sooner it's known,
the less there is to untangle.

**Unusual characters:** an accented or symbol-heavy title makes an ugly web
address — `Amélie` becomes `am-lie`. It still works. If you'd rather it read
properly, type over that one cell on the `Shopify import` tab (e.g.
`amelie-dvd-rental`). The rest of the column keeps working.

---

## Two things this sheet does not do

**1. It does not make a rental rentable.**

A row marked `Rental` becomes a product on the website with the right
labels, genre and poster. It is **not** yet something a member can borrow.
Adding it to the rental system — and recording how many physical copies you
have — is a separate job done inside the Supercycle app, not in this sheet.

**Ask your developer to do this** after a batch of rentals goes up.

**2. It does not merge duplicate copies.**

Uploading the same film several times is expected and fine — those are real
separate copies. Tidying them up is a periodic job your developer runs.

---

## Adding a new format

Two steps, and the second one needs your developer:

1. Add it to the **Format** dropdown (Data → Data validation on column B).
2. Ask your developer to add it to the theme setting **Recognised media
   formats** (Online Store → Themes → Customize → Theme settings). Until
   that's done the new format won't show as a badge on the product page and
   won't appear in the website's Format filter.

## Adding a new genre

You can't, and you don't need to. The thirteen genres in the dropdown are
Shopify's own standard film-genre list — it's fixed, and it's complete. If a
film doesn't fit any of them, use the closest one and put the more specific
label in **Extra tags**.
