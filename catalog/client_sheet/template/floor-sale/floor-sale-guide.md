# Little Movie Store — floor sale sheet

This sheet turns a list of floor-sale copies into a file Shopify can import.
You fill in one tab, and the other tab builds the file for you.

Floor sale is sold **at the counter only**. These products never appear on
the website. (Rentals don't go through this sheet; they're added in Libib.)

You only ever **add** products with this sheet. Changing a price or deleting
a product happens in the Shopify admin.

---

## The whole flow, start to finish

1. **Start a batch.** Make a copy of the master sheet, clear out the old
   rows, and type today's date into the **Batch date** cell (G2).
2. **Fill in one row per copy.** Three copies of the same film means three
   rows.
3. **Import into Shopify.** Download the `Shopify import` tab and import it,
   with "Overwrite products with matching handles" **unticked**. The new
   products land on Point of Sale on their own, ready to ring up.
4. **Print the labels** in Retail Barcode Labels and stick them on. Shopify
   gives every new copy its barcode on its own, so the app only prints.

Each step is described below.

---

## One-time setup

Do this once, on your master copy.

1. **Create the sheet.** In Google Sheets: File → Import → Upload
   `floor-sale-template.csv` → "Replace spreadsheet". Rename the tab that
   appears to exactly **`Add floor sale`**. It has the five columns you fill
   in (A–E), the **Batch date** label in G1 and an example date in G2, and
   three example rows. Look at them, then delete the rows (not the date)
   before your first real batch.

2. **Make G2 a date.** Click G2 → Format → Number → Custom date and time →
   `yyyy-mm-dd`. Then Data → Data validation → **Is valid date** → **Reject
   the input**.

3. **Make Price a positive number.** Select `D2:D` → Data → Data validation
   → **Greater than** `0` → **Reject the input**. A blank or $0 price
   can't be typed.

4. **Add the `mappings` tab.** File → Import → Upload `genre-mappings.csv`
   → **Insert new sheet**. Rename the new tab to exactly `mappings`. Check
   that **A4 reads `Kids & Family`** and **A16 reads `Martial Arts`**. If either
   is wrong, delete the tab and import it again. Then right-click the tab →
   Hide sheet.

   Every genre you pick is looked up in this tab. A genre missing from it
   still imports, but with its genre silently left empty. That's why the
   tab is imported, not typed.

5. **Add the `Shopify import` tab.** Add a sheet, name it exactly
   `Shopify import`, and paste the formula from `import-tab-formula.txt`
   into cell **A1**. Nothing else goes on this tab.

6. **Add the dropdowns** on `Add floor sale`. Select from **row 2 down**,
   then Data → Data validation → Dropdown:

   - **Format** (`B2:B`): `VHS`, `DVD`, `Blu-Ray`, `4K`, `Laserdisc`, `Betamax`
   - **Genre** (`C2:C`): "Dropdown (from a range)" → `mappings!A:A`

Setup is done. From here on you only type on the `Add floor sale` tab.

---

## Step 1 — Start a batch

File → Make a copy of your master sheet. On the copy, delete the old rows
and type **today's date** into **G2**, as `yyyy-mm-dd` (for example
`2026-10-15`).

The date goes into every product's web address. That's what stops this
batch from clashing with an earlier one. Type the date; don't use
`=TODAY()`. A formula would change the date when you download on another
day, and importing that file would create the whole batch a second time.

If G2 is empty, the `Shopify import` tab shows a single **ERROR** line
instead of your products. Fill in G2 and it fixes itself.

---

## Step 2 — Fill in one row per copy

| Column | What goes in it |
|---|---|
| Title | The movie title |
| Format | Pick from the dropdown |
| Genre | Pick from the dropdown. It prints on the barcode label |
| Price | The shelf price, e.g. `8` or `12.50`. Must be more than 0 |
| Extra tags | Optional. Curation labels, comma-separated, e.g. `Criterion Collection, Rare Finds` |

No description or poster is needed, since these never go on the website.

**Restocking a title you've sold before?** Add a new row in a new batch.
Don't change the quantity on the old product. Every copy is its own
product.

Always pick from the dropdowns rather than typing. `Blu-Ray` and `BLU-RAY`
typed by hand count as two different formats.

---

## Step 3 — Import into Shopify

1. Click the **`Shopify import`** tab.
2. File → Download → **Comma-separated values (.csv)**.
3. In Shopify: **Products → Import → Add file**, choose the file.
   **Leave "Overwrite products with matching handles" unticked.**
   Then **Import products**.
4. **Read the summary.** It should say **all created, none updated**. If
   anything was updated, tell your developer before printing barcodes.

The new products are **Active** and on **Point of Sale**, so they can be
rung up straight away, but they're **not on the website**. They're also
marked **taxable**, so tax is charged at the counter.

**Import each batch once.** Downloading the tab again later is safe because
the batch date is typed, not calculated. Importing it twice still adds
nothing new.

---

## Step 4 — Print the labels

A few seconds after the import, Shopify gives each new copy its own barcode
automatically. In **Retail Barcode Labels**, pick the new products and
**print** their labels, then stick them on.

**Don't create (generate) barcodes in the app.** The app makes its barcodes
from the last 8 digits of Shopify's internal number, and on this store about
1 product in 50 gets a number another product already has. Two products
with one barcode means a scan can ring up the wrong movie. If the app ever
insists on generating, choose **only products without barcodes**, so the
ones Shopify set are left alone.

**If a label prints with no barcode**, or a scan rings up the wrong item,
tell your developer before printing more.

---

## Having a file checked

Before importing, you can send either tab's download to your developer to
run through a checker. It catches a missing genre, a $0 price, a product
accidentally set to show on the website, a missing batch date and similar
mistakes that Shopify would otherwise accept silently.

After importing, your developer can also check the store for any barcode
that's on more than one product, before you print.

---

## Adding a new format or genre

Ask your developer first. Both have to exist in Shopify and in the pipeline
before a sheet row can use them. A genre typed only into the sheet ends up
empty on the product. If a film doesn't fit any of the sixteen genres, use
the closest one and put the more specific label in **Extra tags**.
