"""The two output column contracts and the values fixed on every row.

Template output creates new products and matches the client sheets'
17-column header exactly. Export output updates products that already
exist and deliberately omits every column it does not intend to set —
Shopify leaves absent columns untouched, so anything omitted here cannot
be clobbered by the import.
"""

GENRE_METAFIELD = "Genre (product.metafields.shopify.genre)"
REASON_COLUMN = "Reason"
FORMATTED_TAG = "Formatted"

# A row missing one of these fields still uploads — the field is left
# unresolved and one of these tags is added so the client can find and fix
# it in the admin. Only genuinely bad data (an ambiguous type, an unreadable
# or negative price) still blocks the row into issues.csv.
ISSUE_TAG_RENTAL_OR_SALE = "Issue_Rental_Or_Sale"
ISSUE_TAG_NEEDS_FORMAT = "Issue_Needs_Format"
ISSUE_TAG_GENRE_NEEDED = "Issue_Genre_Needed"
ISSUE_TAG_NO_PRICE = "Issue_No_Price"
ISSUE_TAG_RENTAL_PRICE = "Issue_Rental_Price"

TEMPLATE_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Tags",
    "Status",
    "Option1 Name",
    "Option1 Value",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Image Src",
    "Image Alt Text",
    GENRE_METAFIELD,
]

EXPORT_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Tags",
    "Option1 Name",
    "Option1 Value",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    GENRE_METAFIELD,
]

FIXED_VALUES = {
    "Product Category": "Media > Videos",
    "Option1 Name": "Genre",
    "Variant Inventory Tracker": "shopify",
    "Variant Inventory Qty": "1",
    "Variant Inventory Policy": "deny",
    "Variant Fulfillment Service": "manual",
}
