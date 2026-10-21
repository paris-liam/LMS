# Adding rentals: Libib → Shopify

## 1. In Libib

Add each rental to the **Rental Library** collection (UPC lookup or typed in).

Adding a batch? The **Libib rental upload sheet** imports many at once and fills these fields for you.

- **Title** — as it should appear on the website. Delete extras like `[VHS]` or `(Widescreen Edition)`.
- **Tags** — exactly **one format** and **one to three genres**:
  - Formats: `vhs`, `dvd`, `blu-ray`, `4k`, `laserdisc`, `betamax`
  - Genres: `comedy`, `action`, `drama`, `kids-family`, `sci-fi`, `thriller`, `horror`,
    `romantic-comedy`, `musical`, `fantasy`, `documentary`, `foreign`, `holiday`,
    `special-interest`, `anime`
  - Any other tag is fine and is copied to Shopify — unless it looks like a misspelt format or genre.
- **Description** — optional; it becomes the website description.
- **Barcode** — leave the number Libib generates (starts with `201`). Leave **Call #** blank.

### Adding another copy of a movie

Got a second (or third) copy of a movie you already have? Open the movie's **existing** item in
Libib and add a copy to it. Don't add the movie again as a new item — that creates a duplicate.
In Shopify the copy is added to the movie's existing product, not made into a new one.

## 2. In the sync page

Open the sync page and log in.

1. **Upload** — in Libib go to Settings, export **Barcode Data** and **Collection Data** for the
   Rental Library, and upload both files.
2. **New copies** — check the list. Untick anything you don't want to sync yet.
3. **Details** — anything **set aside** needs fixing in Libib; it will show up next time. Yellow
   notes are just warnings. You may also see two kinds of card to answer first (below).
4. **Posters** — check each poster. "Not sure — check this" means click **Use it** if it's right.
   Paste an image link (starting `https://`) to replace or add one, or leave it blank.
5. **Create** — wait for every row to finish. Click any title to open it in Shopify.

### Possible duplicates in Libib

This card means a new movie looks like one that's already an item in Libib (same title and format).
- If it's the same movie, fix it in Libib (add the copy to the existing item). It will sync next time.
- If it's a different movie, such as a remake, click **Not a duplicate**. It becomes its own product.

### Already in Shopify?

This card means another copy of the same Libib item is already in Shopify. You have to choose one
before you can continue:
- **Add as a copy** — this copy is added to the existing Shopify product.
- **Skip this run** — nothing happens now. The copy shows up again next time you sync.

If something failed, fix what the message says and run the sync again — products already created
are never duplicated.

## 3. In Shopify

Click **Print barcodes in Shopify** and print the labels with Retail Barcode Labels. The last page
lists **Print labels for these barcodes only**. Print just those barcodes: a movie that gained a copy
already has labelled copies on the shelf, so don't reprint its other labels. Stick each label on its
copy, then remove the **Barcode Not Printed** tag from the products you labelled.
