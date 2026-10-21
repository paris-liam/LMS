"""Format assembled products as Shopify admin-export CSV rows.

The output must match what Products > Export writes, so the client can
re-import it. Pure functions only: no network, no file IO. A product spans
max(variants, images, 1) rows; product-level fields sit on the first row."""
import json
from dataclasses import dataclass
from decimal import Decimal

BEFORE_METAFIELDS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Option1 Linked To", "Option2 Name", "Option2 Value", "Option2 Linked To",
    "Option3 Name", "Option3 Value", "Option3 Linked To", "Variant SKU", "Variant Grams",
    "Variant Inventory Tracker", "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price", "Variant Compare At Price", "Variant Requires Shipping",
    "Variant Taxable", "Unit Price Total Measure", "Unit Price Total Measure Unit", "Unit Price Base Measure",
    "Unit Price Base Measure Unit", "Variant Barcodes", "Image Src", "Image Position", "Image Alt Text",
    "Gift Card", "SEO Title", "SEO Description",
]
AFTER_METAFIELDS = ["Variant Image", "Variant Weight Unit", "Variant Tax Code", "Cost per item", "Status"]

GRAMS_PER_UNIT = {"POUNDS": 453.59237, "OUNCES": 28.349523125, "KILOGRAMS": 1000, "GRAMS": 1}
WEIGHT_UNITS = {"POUNDS": "lb", "OUNCES": "oz", "KILOGRAMS": "kg", "GRAMS": "g"}
LEFT_OUT_PREFIXES = ("shopify--discovery--", "app--")
LEFT_OUT_NAMESPACES = ("supercycle",)
REFERENCE_SUFFIXES = ("metaobject_reference", "product_reference")


@dataclass(frozen=True)
class MetafieldColumn:
    name: str
    namespace: str
    key: str

    @property
    def header(self) -> str:
        return f"{self.name} (product.metafields.{self.namespace}.{self.key})"


def _is_left_out(column: MetafieldColumn) -> bool:
    return column.namespace.startswith(LEFT_OUT_PREFIXES) or column.namespace in LEFT_OUT_NAMESPACES


def split_definitions(definitions: list[dict]) -> tuple[list[MetafieldColumn], list[MetafieldColumn]]:
    """Return (kept, left_out), each sorted by (namespace, key)."""
    columns = sorted((MetafieldColumn(d["name"], d["namespace"], d["key"]) for d in definitions),
                     key=lambda c: (c.namespace, c.key))
    return [c for c in columns if not _is_left_out(c)], [c for c in columns if _is_left_out(c)]


def build_header(columns: list[MetafieldColumn]) -> list[str]:
    return BEFORE_METAFIELDS + [c.header for c in columns] + AFTER_METAFIELDS


def format_metafield(metafield: dict) -> str:
    kind = metafield.get("type") or ""
    value = metafield.get("value")
    if value is None:
        return ""
    if kind.endswith(REFERENCE_SUFFIXES):
        return "; ".join(ref["handle"] for ref in metafield.get("references") or [])
    if kind.startswith("list."):
        return "; ".join(str(v) for v in json.loads(value))
    return value


def _bool(value) -> str:
    return "true" if value else "false"


def _money(amount) -> str:
    return "" if amount is None else f"{Decimal(amount):.2f}"


def _weight(variant: dict) -> tuple[str, str]:
    measurement = (variant.get("inventoryItem") or {}).get("measurement") or {}
    weight = measurement.get("weight")
    if not weight:
        return "", ""
    return str(round(float(weight["value"] * GRAMS_PER_UNIT[weight["unit"]]), 1)), WEIGHT_UNITS[weight["unit"]]


def _unit_price(variant: dict) -> dict:
    blank = {"Unit Price Total Measure": "", "Unit Price Total Measure Unit": "",
             "Unit Price Base Measure": "", "Unit Price Base Measure Unit": ""}
    measure = variant.get("unitPriceMeasurement")
    if not measure or measure.get("quantityValue") is None:
        return blank
    return {"Unit Price Total Measure": str(measure["quantityValue"]),
            "Unit Price Total Measure Unit": (measure.get("quantityUnit") or "").lower(),
            "Unit Price Base Measure": str(measure["referenceValue"]),
            "Unit Price Base Measure Unit": (measure.get("referenceUnit") or "").lower()}


def _variant_fields(variant: dict, options: list[dict]) -> dict:
    item = variant.get("inventoryItem") or {}
    grams, unit = _weight(variant)
    chosen = {o["name"]: o["value"] for o in variant.get("selectedOptions") or []}
    fields = {
        "Variant SKU": variant.get("sku") or "", "Variant Grams": grams,
        "Variant Inventory Tracker": "shopify" if item.get("tracked") else "",
        "Variant Inventory Qty": "" if variant.get("inventoryQuantity") is None else str(variant["inventoryQuantity"]),
        "Variant Inventory Policy": variant["inventoryPolicy"].lower(),
        "Variant Fulfillment Service": "manual", "Variant Price": _money(variant.get("price")),
        "Variant Compare At Price": _money(variant.get("compareAtPrice")),
        "Variant Requires Shipping": _bool(item.get("requiresShipping")),
        "Variant Taxable": _bool(variant.get("taxable")), "Variant Barcodes": variant.get("barcode") or "",
        "Variant Image": (variant.get("image") or {}).get("url") or "", "Variant Weight Unit": unit,
        "Variant Tax Code": "", "Cost per item": _money((item.get("unitCost") or {}).get("amount")),
        **_unit_price(variant),
    }
    for n, option in enumerate(options[:3], start=1):
        fields[f"Option{n} Value"] = chosen.get(option["name"], "")
    return fields


def _product_fields(product: dict, options: list[dict], columns: list[MetafieldColumn]) -> dict:
    seo = product.get("seo") or {}
    fields = {
        "Title": product["title"], "Body (HTML)": product.get("descriptionHtml") or "",
        "Vendor": product.get("vendor") or "", "Product Category": (product.get("category") or {}).get("fullName") or "",
        "Type": product.get("productType") or "", "Tags": ", ".join(product.get("tags") or []),
        "Published": _bool(product.get("published")), "Gift Card": _bool(product.get("isGiftCard")),
        "SEO Title": seo.get("title") or "", "SEO Description": seo.get("description") or "",
        "Status": product["status"].lower(),
    }
    for n, option in enumerate(options[:3], start=1):
        link = option.get("linkedMetafield")
        fields[f"Option{n} Name"] = option["name"]
        fields[f"Option{n} Linked To"] = f"product.metafields.{link['namespace']}.{link['key']}" if link else ""
    by_key = {(m["namespace"], m["key"]): m for m in product.get("metafields") or []}
    for column in columns:
        metafield = by_key.get((column.namespace, column.key))
        fields[column.header] = format_metafield(metafield) if metafield else ""
    return fields


def product_rows(product: dict, columns: list[MetafieldColumn]) -> list[dict]:
    """One dict per CSV row, every header key present (missing = "")."""
    header = build_header(columns)
    options = sorted(product.get("options") or [], key=lambda o: o["position"])
    variants = sorted(product.get("variants") or [], key=lambda v: v["position"])
    images = [m["image"] for m in product.get("media") or []
              if m.get("__typename") == "MediaImage" and m.get("image")]
    rows = []
    for k in range(max(len(variants), len(images), 1)):
        row = dict.fromkeys(header, "")
        row["Handle"] = product["handle"]
        if k == 0:
            row.update(_product_fields(product, options, columns))
        if k < len(variants):
            row.update(_variant_fields(variants[k], options))
        if k < len(images):
            row.update({"Image Src": images[k]["url"], "Image Position": str(k + 1),
                        "Image Alt Text": images[k].get("altText") or ""})
        rows.append(row)
    return rows
