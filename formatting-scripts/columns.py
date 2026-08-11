"""The two output column contracts and the values fixed on every row.

Template output creates new products and matches the client sheets'
17-column header exactly. Export output updates products that already
exist and deliberately omits every column it does not intend to set —
Shopify leaves absent columns untouched, so anything omitted here cannot
be clobbered by the import.
"""

GENRE_METAFIELD = "Genre (product.metafields.shopify.genre)"
REASON_COLUMN = "Reason"

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
