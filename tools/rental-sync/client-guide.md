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
- **More copies of a title** — add a copy to the same Libib item. Each copy becomes its own Shopify product.

## 2. In the sync page

Open the sync page and log in.

1. **Upload** — in Libib go to Settings, export **Barcode Data** and **Collection Data** for the
   Rental Library, and upload both files.
2. **New copies** — check the list. Untick anything you don't want to sync yet.
3. **Details** — anything **set aside** needs fixing in Libib; it will show up next time. Yellow
   notes are just warnings.
4. **Posters** — check each poster. "Not sure — check this" means click **Use it** if it's right.
   Paste an image link (starting `https://`) to replace or add one, or leave it blank.
5. **Create** — wait for every row to finish. Click any title to open it in Shopify.

If something failed, fix what the message says and run the sync again — products already created
are never duplicated.

## 3. In Shopify

Click **Print barcodes in Shopify**, print the labels with Retail Barcode Labels, stick each on its
copy, and remove the **Barcode Not Printed** tag from the products you labelled.
