import unittest

from catalog.audit.findings import AUTO_FIX, MANUAL
from catalog.audit.rules import canonical_tags, check_catalogue, check_row, resolve_row
from catalog.core.columns import GENRE_METAFIELD
from catalog.shopify.snapshot import blank_row


def movie(**overrides):
    base = blank_row()
    base.update({
        "Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
        "Vendor": "VHS", "Tags": "Rental, VHS, Comedy", "Status": "active",
        "Image Src": "https://cdn/r.jpg", "Image Alt Text": "Rushmore poster",
        "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0.00",
        "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
        "Variant Count": "1", GENRE_METAFIELD: "comedy",
    })
    base.update(overrides)
    return base


def floor_sale(**overrides):
    base = {"Handle": "heat-dvd-floor-sale", "Title": "Heat", "Vendor": "DVD",
            "Tags": "Floor Sale, DVD, Action", "Option1 Value": "Action", "Variant Price": "9.99",
            "Variant Barcode": "", GENRE_METAFIELD: "action"}
    base.update(overrides)
    return movie(**base)


def by_rule(findings):
    return {(f.rule, f.field): f for f in findings}


class TestCleanProduct(unittest.TestCase):
    def test_clean_rental_has_no_findings(self):
        self.assertEqual(check_row(movie()), [])

    def test_clean_floor_sale_has_no_findings(self):
        self.assertEqual(check_row(floor_sale()), [])


class TestAutoFixRules(unittest.TestCase):
    def test_misspelt_genre_everywhere(self):
        f = by_rule(check_row(movie(Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor", GENRE_METAFIELD: ""})))
        self.assertEqual(f[("genre-alias", "Tags")].proposed_value, "Rental, VHS, Horror")
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Horror")
        self.assertEqual(f[("genre-metafield-sync", GENRE_METAFIELD)].proposed_value, "horror")
        self.assertTrue(all(x.bucket == AUTO_FIX for x in f.values()))

    def test_misspelt_type_tag(self):
        f = by_rule(check_row(floor_sale(Tags="floorsale, DVD, Action")))
        self.assertEqual(f[("type-alias", "Tags")].proposed_value, "Floor Sale, DVD, Action")

    def test_vendor_alias(self):
        f = by_rule(check_row(movie(Vendor="bluray", Tags="Rental, Blu-Ray, Comedy")))
        self.assertEqual(f[("format-alias", "Vendor")].proposed_value, "Blu-Ray")

    def test_format_tag_alias_keeps_formatted_last_and_curation_tags(self):
        f = by_rule(check_row(movie(Tags="Rental, vhs, Comedy, Formatted, Staff Picks")))
        self.assertEqual(f[("format-alias", "Tags")].proposed_value,
                         "Rental, VHS, Comedy, Staff Picks, Formatted")

    def test_formatted_is_never_added(self):
        self.assertNotIn("Formatted", canonical_tags(resolve_row(movie(Tags="Rental, vhs, Comedy"))))

    def test_metafield_order_does_not_matter(self):
        self.assertEqual(check_row(movie(Tags="Rental, VHS, Comedy, Drama", **{GENRE_METAFIELD: "drama; comedy"})), [])

    def test_default_title_option_gets_genre(self):
        f = by_rule(check_row(movie(**{"Option1 Name": "Title", "Option1 Value": "Default Title"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Comedy")
        self.assertEqual(f[("option1-genre", "Option1 Name")].proposed_value, "Genre")

    def test_compound_option1(self):
        f = by_rule(check_row(movie(Vendor="4K", Tags="Rental, 4K, Action",
                                    **{"Option1 Value": "4K, Action", GENRE_METAFIELD: "action"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Action")

    def test_alt_text_missing(self):
        f = by_rule(check_row(movie(**{"Image Alt Text": ""})))
        self.assertEqual(f[("alt-text-missing", "Image Alt Text")].proposed_value, "Rushmore poster")

    def test_no_alt_text_rule_without_image(self):
        self.assertNotIn(("alt-text-missing", "Image Alt Text"),
                         by_rule(check_row(movie(**{"Image Src": "", "Image Alt Text": ""}))))

    def test_rental_blank_price(self):
        f = by_rule(check_row(movie(**{"Variant Price": ""})))
        self.assertEqual(f[("rental-price-blank", "Variant Price")].proposed_value, "0")
        self.assertEqual(f[("rental-price-blank", "Variant Price")].bucket, AUTO_FIX)


class TestManualRules(unittest.TestCase):
    def test_type_missing_skips_price_and_barcode_rules(self):
        rules = {f.rule for f in check_row(movie(Tags="VHS, Comedy", **{"Variant Price": "4.99", "Variant Barcode": ""}))}
        self.assertIn("type-missing", rules)
        self.assertFalse(rules & {"rental-price-nonzero", "rental-barcode-missing"})

    def test_type_conflict(self):
        self.assertIn("type-conflict", {f.rule for f in check_row(movie(Tags="Rental, Floor Sale, VHS, Comedy"))})

    def test_format_missing(self):
        self.assertIn("format-missing", {f.rule for f in check_row(movie(Vendor="", Tags="Rental, Comedy"))})

    def test_genre_missing_has_no_genre_autofixes(self):
        rules = {f.rule for f in check_row(movie(Tags="Rental, VHS", **{"Option1 Value": "Default Title", GENRE_METAFIELD: ""}))}
        self.assertIn("genre-missing", rules)
        self.assertFalse(rules & {"option1-genre", "genre-metafield-sync"})

    def test_floor_sale_prices(self):
        for price in ("", "0", "0.00", "-3"):
            with self.subTest(price=price):
                self.assertIn("floor-sale-price", {f.rule for f in check_row(floor_sale(**{"Variant Price": price}))})

    def test_price_unreadable(self):
        self.assertIn("price-unreadable", {f.rule for f in check_row(floor_sale(**{"Variant Price": "abc"}))})

    def test_rental_price_nonzero(self):
        self.assertIn("rental-price-nonzero", {f.rule for f in check_row(movie(**{"Variant Price": "4.99"}))})

    def test_inventory_untracked(self):
        f = by_rule(check_row(movie(**{"Variant Inventory Tracker": ""})))
        self.assertEqual(f[("inventory-untracked", "Variant Inventory Tracker")].bucket, MANUAL)

    def test_rental_barcode_missing(self):
        self.assertIn("rental-barcode-missing", {f.rule for f in check_row(movie(**{"Variant Barcode": ""}))})

    def test_rental_barcode_seven_digits(self):
        self.assertIn("rental-barcode-format", {f.rule for f in check_row(movie(**{"Variant Barcode": "1577790"}))})

    def test_rental_barcode_with_letter(self):
        self.assertIn("rental-barcode-format", {f.rule for f in check_row(movie(**{"Variant Barcode": "0157779A"}))})

    def test_rental_barcode_whitespace_is_tolerated(self):
        self.assertEqual(check_row(movie(**{"Variant Barcode": " 01577790 "})), [])

    def test_floor_sale_barcode_has_no_rules(self):
        self.assertEqual(check_row(floor_sale(**{"Variant Barcode": "abc"})), [])

    def test_multi_variant_gets_no_autofix(self):
        findings = check_row(movie(Tags="Rental, VHS, Horor", **{"Variant Count": "2", "Image Alt Text": ""}))
        self.assertIn("multiple-variants", {f.rule for f in findings})
        self.assertFalse([f for f in findings if f.bucket == AUTO_FIX])


class TestCatalogueRules(unittest.TestCase):
    def test_rental_sharing_with_floor_sale_is_flagged_on_the_rental_only(self):
        findings = check_catalogue([movie(), floor_sale(**{"Variant Barcode": "01577790"})])
        self.assertEqual([(f.handle, f.rule) for f in findings], [("rushmore-vhs-rental", "rental-barcode-duplicate")])
        self.assertIn("heat-dvd-floor-sale", findings[0].detail)

    def test_two_rentals_flag_each_other(self):
        findings = check_catalogue([movie(), movie(Handle="rushmore-vhs-rental-2")])
        self.assertEqual(sorted(f.handle for f in findings), ["rushmore-vhs-rental", "rushmore-vhs-rental-2"])

    def test_floor_sales_may_share(self):
        self.assertEqual(check_catalogue([floor_sale(**{"Variant Barcode": "1"}),
                                          floor_sale(Handle="b", **{"Variant Barcode": "1"})]), [])

    def test_duplicate_ignores_surrounding_whitespace(self):
        findings = check_catalogue([movie(), floor_sale(**{"Variant Barcode": " 01577790"})])
        self.assertEqual(len(findings), 1)

    def test_blank_barcodes_are_not_duplicates(self):
        self.assertEqual(check_catalogue([movie(**{"Variant Barcode": ""}),
                                          movie(Handle="x", **{"Variant Barcode": ""})]), [])


if __name__ == "__main__":
    unittest.main()
