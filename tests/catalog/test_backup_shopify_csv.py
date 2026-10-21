import unittest

from catalog.backup.shopify_csv import (AFTER_METAFIELDS, BEFORE_METAFIELDS, MetafieldColumn, build_header,
                                        format_metafield, product_rows, split_definitions)


def _variant(position, size="Default Title", option="Title", **overrides):
    variant = {
        "__typename": "ProductVariant", "id": f"gid://shopify/ProductVariant/{position}", "position": position,
        "sku": f"SKU-{position}", "price": "5", "compareAtPrice": None, "taxable": True, "barcode": None,
        "inventoryQuantity": 1, "inventoryPolicy": "DENY", "selectedOptions": [{"name": option, "value": size}],
        "image": None, "unitPriceMeasurement": None,
        "inventoryItem": {"tracked": True, "requiresShipping": True, "unitCost": None,
                          "measurement": {"weight": {"unit": "POUNDS", "value": 0}}},
    }
    variant.update(overrides)
    return variant


def _image(n, alt=None):
    return {"__typename": "MediaImage", "id": f"gid://shopify/MediaImage/{n}",
            "image": {"url": f"https://cdn.example.com/img{n}.jpg", "altText": alt}}


def _product(**overrides):
    product = {
        "handle": "test-movie", "title": "Test Movie", "descriptionHtml": "<p>Hi</p>", "vendor": "DVD",
        "productType": "Movie", "tags": ["Rental", "Horror"], "status": "ACTIVE", "isGiftCard": False,
        "category": {"fullName": "Media > DVDs"}, "seo": {"title": "SEO T", "description": None},
        "published": True, "options": [{"name": "Title", "position": 1, "linkedMetafield": None}],
        "variants": [_variant(1)], "media": [], "metafields": [],
    }
    product.update(overrides)
    return product


def _shirt():
    sizes = ["s", "m", "l", "xl", "2xl"]
    return _product(
        handle="shirt", options=[{"name": "Size", "position": 1,
                                  "linkedMetafield": {"namespace": "shopify", "key": "size"}}],
        variants=[_variant(i + 1, size=s, option="Size") for i, s in enumerate(sizes)],
        media=[_image(1), _image(2), _image(3)])


def _meta(type_, value, references=(), namespace="custom", key="f"):
    return {"__typename": "Metafield", "id": "gid://shopify/Metafield/1", "namespace": namespace, "key": key,
            "type": type_, "value": value, "references": [{"handle": h} for h in references]}


class TestHeader(unittest.TestCase):
    def test_header_places_metafields_between_seo_and_variant_image(self):
        cols = [MetafieldColumn("Year", "custom", "year")]
        header = build_header(cols)
        self.assertEqual(header, BEFORE_METAFIELDS + ["Year (product.metafields.custom.year)"] + AFTER_METAFIELDS)
        self.assertEqual(header[header.index("SEO Description") + 1], "Year (product.metafields.custom.year)")
        self.assertEqual(header[header.index("Variant Image") - 1], "Year (product.metafields.custom.year)")


class TestSplitDefinitions(unittest.TestCase):
    def test_split_definitions_sorts_and_leaves_out_app_namespaces(self):
        defs = [{"name": n, "namespace": ns, "key": k} for n, ns, k in [
            ("Year", "custom", "year"), ("Genre", "shopify", "genre"), ("Country", "custom", "country"),
            ("Related", "shopify--discovery--product_recommendation", "related_products"),
            ("Methods", "supercycle", "methods"), ("X", "app--123", "x")]]
        kept, left_out = split_definitions(defs)
        self.assertEqual([(c.namespace, c.key) for c in kept],
                         [("custom", "country"), ("custom", "year"), ("shopify", "genre")])
        self.assertEqual([(c.namespace, c.key) for c in left_out],
                         [("app--123", "x"), ("shopify--discovery--product_recommendation", "related_products"),
                          ("supercycle", "methods")])


class TestRows(unittest.TestCase):
    def test_rows_pair_variants_and_images_by_index(self):
        rows = product_rows(_shirt(), [])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["Title"], "Test Movie")
        self.assertEqual(rows[0]["Option1 Name"], "Size")
        self.assertEqual(rows[0]["Option1 Linked To"], "product.metafields.shopify.size")
        self.assertEqual(rows[0]["Image Position"], "1")
        self.assertEqual(rows[3]["Option1 Value"], "xl")
        self.assertEqual(rows[3]["Image Src"], "")
        for row in rows[1:]:
            self.assertEqual(row["Title"], "")
        self.assertEqual(rows[2]["Image Src"], "https://cdn.example.com/img3.jpg")
        self.assertTrue(all(set(r) == set(build_header([])) for r in rows))

    def test_movie_with_extra_images_has_image_only_rows(self):
        rows = product_rows(_product(media=[_image(n, alt="a") for n in range(1, 6)]
                                     + [{"__typename": "Video", "id": "v"}]), [])
        self.assertEqual(len(rows), 5)
        for k, row in enumerate(rows[1:], start=1):
            filled = {h: v for h, v in row.items() if v != ""}
            self.assertEqual(set(filled), {"Handle", "Image Src", "Image Position", "Image Alt Text"})
            self.assertEqual(row["Image Position"], str(k + 1))

    def test_default_title_product(self):
        row = product_rows(_product(), [])[0]
        self.assertEqual(row["Option1 Name"], "Title")
        self.assertEqual(row["Option1 Value"], "Default Title")
        self.assertEqual(row["Option2 Name"], "")

    def test_product_with_no_images_has_one_row_per_variant(self):
        rows = product_rows(_shirt() | {"media": []}, [])
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["Image Src"] == "" and r["Image Position"] == "" for r in rows))

    def test_variants_sorted_by_position(self):
        p = _product(variants=[_variant(2, size="b"), _variant(1, size="a")])
        self.assertEqual([r["Option1 Value"] for r in product_rows(p, [])], ["a", "b"])

    def test_variant_values(self):
        v = _variant(1, inventoryQuantity=-3, compareAtPrice=None)
        row = product_rows(_product(variants=[v]), [])[0]
        self.assertEqual(row["Variant Price"], "5.00")
        self.assertEqual(row["Variant Compare At Price"], "")
        self.assertEqual(row["Variant Inventory Tracker"], "shopify")
        self.assertEqual(row["Variant Inventory Policy"], "deny")
        self.assertEqual(row["Variant Grams"], "0.0")
        self.assertEqual(row["Variant Weight Unit"], "lb")
        self.assertEqual(row["Variant Inventory Qty"], "-3")
        self.assertEqual(row["Variant Fulfillment Service"], "manual")
        self.assertEqual(row["Variant Taxable"], "true")
        self.assertEqual(row["Variant Tax Code"], "")
        self.assertEqual(row["Variant Barcodes"], "")

    def test_requires_shipping_false_untracked_and_cost(self):
        item = {"tracked": False, "requiresShipping": False, "unitCost": {"amount": "2.5"}, "measurement": None}
        row = product_rows(_product(variants=[_variant(1, inventoryItem=item, compareAtPrice="9.9")]), [])[0]
        self.assertEqual(row["Variant Requires Shipping"], "false")
        self.assertEqual(row["Variant Inventory Tracker"], "")
        self.assertEqual(row["Cost per item"], "2.50")
        self.assertEqual(row["Variant Compare At Price"], "9.90")
        self.assertEqual((row["Variant Grams"], row["Variant Weight Unit"]), ("", ""))

    def test_weight_conversion(self):
        item = {"tracked": True, "requiresShipping": True, "unitCost": None,
                "measurement": {"weight": {"unit": "OUNCES", "value": 10}}}
        row = product_rows(_product(variants=[_variant(1, inventoryItem=item)]), [])[0]
        self.assertEqual(row["Variant Grams"], "283.5")
        self.assertEqual(row["Variant Weight Unit"], "oz")

    def test_unit_price_and_variant_image(self):
        measure = {"quantityValue": 750.0, "quantityUnit": "ML", "referenceValue": 100, "referenceUnit": "ML"}
        v = _variant(1, unitPriceMeasurement=measure, image={"url": "https://cdn.example.com/v.jpg"}, barcode="123")
        row = product_rows(_product(variants=[v]), [])[0]
        self.assertEqual(row["Unit Price Total Measure"], "750.0")
        self.assertEqual(row["Unit Price Total Measure Unit"], "ml")
        self.assertEqual(row["Unit Price Base Measure"], "100")
        self.assertEqual(row["Unit Price Base Measure Unit"], "ml")
        self.assertEqual(row["Variant Image"], "https://cdn.example.com/v.jpg")
        self.assertEqual(row["Variant Barcodes"], "123")

    def test_missing_category_is_blank(self):
        self.assertEqual(product_rows(_product(category=None), [])[0]["Product Category"], "")

    def test_product_level_fields_on_first_row(self):
        row = product_rows(_product(published=False, isGiftCard=True), [])[0]
        self.assertEqual(row["Published"], "false")
        self.assertEqual(row["Gift Card"], "true")
        self.assertEqual(row["Status"], "active")
        self.assertEqual(row["Tags"], "Rental, Horror")
        self.assertEqual(row["Product Category"], "Media > DVDs")
        self.assertEqual((row["SEO Title"], row["SEO Description"]), ("SEO T", ""))
        self.assertEqual(product_rows(_product(published=True), [])[0]["Published"], "true")

    def test_metafield_columns_on_first_row_only(self):
        col = MetafieldColumn("Year", "custom", "year")
        p = _shirt() | {"metafields": [_meta("single_line_text_field", "1999", namespace="custom", key="year")]}
        rows = product_rows(p, [col])
        self.assertEqual(rows[0][col.header], "1999")
        self.assertEqual(rows[1][col.header], "")
        self.assertEqual(product_rows(_product(), [col])[0][col.header], "")


class TestFormatMetafield(unittest.TestCase):
    def test_metaobject_list_writes_handles(self):
        self.assertEqual(format_metafield(_meta("list.metaobject_reference", "[]", ["beige", "white"])), "beige; white")

    def test_single_metaobject_reference(self):
        self.assertEqual(format_metafield(_meta("metaobject_reference", "gid://x", ["eng-english"])), "eng-english")

    def test_product_reference_list(self):
        self.assertEqual(format_metafield(_meta("list.product_reference", "[]", ["a", "b"])), "a; b")

    def test_text_list_joins_with_semicolons(self):
        self.assertEqual(format_metafield(_meta("list.single_line_text_field", '["a","b"]')), "a; b")

    def test_unknown_metafield_type_writes_raw_value(self):
        self.assertEqual(format_metafield(_meta("rating", '{"value":"4.5"}')), '{"value":"4.5"}')


if __name__ == "__main__":
    unittest.main()
