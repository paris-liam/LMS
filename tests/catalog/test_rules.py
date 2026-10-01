import unittest

from catalog.audit.findings import AUTO_FIX, MANUAL
from catalog.audit.rules import check_catalogue, check_row, resolve_row, respelled_tags
from catalog.core.columns import GENRE_METAFIELD
from catalog.shopify.snapshot import blank_row


def movie(**overrides):
    base = blank_row()
    base.update({
        "Handle": "rushmore-vhs-rental", "Title": "Rushmore", "Body (HTML)": "<p>A student.</p>",
        "Vendor": "VHS", "Tags": "Rental", "Status": "active",
        "Image Src": "https://cdn/r.jpg", "Image Alt Text": "Rushmore poster",
        "Option1 Name": "Genre", "Option1 Value": "Comedy", "Variant Price": "0.00",
        "Variant Barcode": "01577790", "Variant Inventory Tracker": "shopify",
        "Variant Count": "1", GENRE_METAFIELD: "comedy", "Product Category": "Media > Videos",
    })
    base.update(overrides)
    return base


def floor_sale(**overrides):
    base = {"Handle": "heat-dvd-floor-sale", "Title": "Heat", "Vendor": "DVD",
            "Tags": "Floor Sale", "Option1 Value": "Action", "Variant Price": "9.99",
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
    def test_movie_without_a_category_gets_media_videos(self):
        # shopify.genre is a category metafield: Shopify drops it on import
        # unless the product's category is Media > Videos.
        for category in ("", "Uncategorized", "Media > Music & Sound Recordings"):
            with self.subTest(category=category):
                f = by_rule(check_row(movie(**{"Product Category": category, GENRE_METAFIELD: ""})))
                finding = f[("category-missing", "Product Category")]
                self.assertEqual((finding.current_value, finding.proposed_value), (category, "Media > Videos"))
                self.assertEqual(finding.bucket, AUTO_FIX)
                self.assertIn(("genre-metafield-sync", GENRE_METAFIELD), f)

    def test_category_is_left_alone_when_there_is_no_genre_to_set(self):
        f = by_rule(check_row(movie(Tags="Rental, VHS", **{"Option1 Value": "", GENRE_METAFIELD: "",
                                                           "Product Category": ""})))
        self.assertNotIn(("category-missing", "Product Category"), f)

    def test_misspelt_genre_everywhere(self):
        f = by_rule(check_row(movie(Tags="Rental, VHS, Horor", **{"Option1 Value": "Horor", GENRE_METAFIELD: ""})))
        self.assertEqual(f[("format-genre-tag", "Tags")].proposed_value, "Rental")
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Horror")
        self.assertEqual(f[("genre-metafield-sync", GENRE_METAFIELD)].proposed_value, "horror")
        self.assertTrue(all(x.bucket == AUTO_FIX for x in f.values()))

    def test_misspelt_type_tag(self):
        f = by_rule(check_row(floor_sale(Tags="floorsale, Criterion Collection")))
        self.assertEqual(f[("type-alias", "Tags")].proposed_value, "Floor Sale, Criterion Collection")

    def test_vendor_alias(self):
        f = by_rule(check_row(movie(Vendor="bluray")))
        self.assertEqual(f[("format-alias", "Vendor")].proposed_value, "Blu-Ray")

    def test_format_and_genre_tags_are_removed(self):
        # Format lives in Vendor and genre in Option1 + shopify.genre, so those
        # tags are redundant. Everything else is kept, in order.
        f = by_rule(check_row(movie(Tags="Rental, VHS, Comedy, new-arrival, Criterion Collection")))
        finding = f[("format-genre-tag", "Tags")]
        self.assertEqual(finding.bucket, AUTO_FIX)
        self.assertEqual(finding.proposed_value, "Rental, new-arrival, Criterion Collection")
        self.assertIn("VHS", finding.detail)
        self.assertIn("Comedy", finding.detail)
        self.assertEqual(set(f), {("format-genre-tag", "Tags")})

    def test_misspelt_format_or_genre_tag_is_removed_not_respelled(self):
        f = by_rule(check_row(movie(Tags="Rental, vhs, comedy, Formatted, Staff Picks")))
        self.assertEqual(f[("format-genre-tag", "Tags")].proposed_value, "Rental, Formatted, Staff Picks")
        self.assertFalse({rule for rule, _ in f} & {"format-alias", "genre-alias"})

    def test_genre_only_in_a_tag_moves_to_the_metafield_as_the_tag_goes(self):
        f = by_rule(check_row(movie(Tags="Rental, Horror", **{"Option1 Value": "", GENRE_METAFIELD: ""})))
        self.assertEqual(f[("format-genre-tag", "Tags")].proposed_value, "Rental")
        self.assertEqual(f[("genre-metafield-sync", GENRE_METAFIELD)].proposed_value, "horror")
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Horror")

    def test_format_only_in_a_tag_moves_to_vendor_as_the_tag_goes(self):
        f = by_rule(check_row(movie(Vendor="", Tags="Rental, DVD")))
        self.assertEqual(f[("format-genre-tag", "Tags")].proposed_value, "Rental")
        self.assertEqual(f[("format-alias", "Vendor")].proposed_value, "DVD")

    def test_tag_fix_on_type_conflict_keeps_both_type_tags(self):
        f = by_rule(check_row(movie(Tags="Rental, Floor Sale, VHS, horror", **{"Option1 Value": "Horror",
                                                                              GENRE_METAFIELD: "horror"})))
        proposed = f[("format-genre-tag", "Tags")].proposed_value
        self.assertIn("Rental", proposed)
        self.assertIn("Floor Sale", proposed)

    def test_type_respelling_and_tag_removal_propose_one_value(self):
        f = check_row(movie(Tags="VHS, DVD, Comedy, rental"))
        self.assertEqual({x.proposed_value for x in f if x.field == "Tags"}, {"Rental"})
        self.assertEqual({x.rule for x in f if x.field == "Tags"}, {"type-alias", "format-genre-tag"})

    def test_formatted_is_never_added(self):
        self.assertNotIn("Formatted", respelled_tags(resolve_row(movie(Tags="Rental, vhs, Comedy"))))

    def test_metafield_order_does_not_matter(self):
        self.assertEqual(check_row(movie(**{GENRE_METAFIELD: "drama; comedy"})), [])

    def test_secondary_genre_survives_without_genre_tags(self):
        # Genre/format tags are being removed: the metafield alone must keep
        # a multi-genre product's secondary genre (no genre-metafield-sync).
        self.assertEqual(check_row(movie(Tags="Rental", **{GENRE_METAFIELD: "comedy; sci-fi"})), [])

    def test_default_title_option_gets_genre(self):
        f = by_rule(check_row(movie(**{"Option1 Name": "Title", "Option1 Value": "Default Title"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Comedy")
        self.assertEqual(f[("option1-genre", "Option1 Name")].proposed_value, "Genre")

    def test_compound_option1(self):
        f = by_rule(check_row(movie(Vendor="4K", **{"Option1 Value": "4K, Action", GENRE_METAFIELD: "action"})))
        self.assertEqual(f[("option1-genre", "Option1 Value")].proposed_value, "Action")

    def test_alt_text_missing(self):
        f = by_rule(check_row(movie(**{"Image Alt Text": ""})))
        self.assertEqual(f[("alt-text-missing", "Image Alt Text")].proposed_value, "Rushmore poster")

    def test_no_alt_text_rule_without_image(self):
        self.assertNotIn(("alt-text-missing", "Image Alt Text"),
                         by_rule(check_row(movie(**{"Image Src": "", "Image Alt Text": ""}))))

    def test_imageless_movie_gets_the_poster_missing_tag(self):
        for maker in (movie, floor_sale):
            with self.subTest(maker=maker.__name__):
                f = by_rule(check_row(maker(**{"Image Src": "", "Image Alt Text": ""})))
                finding = f[("poster-tag-sync", "Tags")]
                self.assertEqual(finding.bucket, AUTO_FIX)
                self.assertTrue(finding.proposed_value.endswith(", Poster_Missing"))

    def test_poster_missing_tag_is_removed_once_there_is_an_image(self):
        f = by_rule(check_row(movie(Tags="Rental, new-arrival, poster_missing")))
        self.assertEqual(f[("poster-tag-sync", "Tags")].proposed_value, "Rental, new-arrival")

    def test_poster_missing_tag_already_right_is_left_alone(self):
        self.assertEqual(check_row(movie(**{"Image Src": "", "Image Alt Text": "",
                                            "Tags": "Rental, Poster_Missing"})), [])

    def test_poster_missing_tag_folds_into_the_same_tags_value_as_a_respelling(self):
        f = check_row(movie(**{"Image Src": "", "Image Alt Text": "", "Tags": "rental, VHS, Comedy"}))
        proposed = {x.proposed_value for x in f if x.field == "Tags"}
        self.assertEqual(proposed, {"Rental, Poster_Missing"})

    def test_multi_variant_gets_no_poster_tag_fix(self):
        f = check_row(movie(**{"Image Src": "", "Image Alt Text": "", "Variant Count": "2"}))
        self.assertNotIn("poster-tag-sync", {x.rule for x in f})

    def test_rental_blank_price(self):
        f = by_rule(check_row(movie(**{"Variant Price": ""})))
        self.assertEqual(f[("rental-price-blank", "Variant Price")].proposed_value, "0")
        self.assertEqual(f[("rental-price-blank", "Variant Price")].bucket, AUTO_FIX)


class TestManualRules(unittest.TestCase):
    def test_type_missing_skips_price_and_barcode_rules(self):
        rules = {f.rule for f in check_row(movie(Tags="", **{"Variant Price": "4.99", "Variant Barcode": ""}))}
        self.assertIn("type-missing", rules)
        self.assertFalse(rules & {"rental-price-nonzero", "rental-barcode-missing"})

    def test_type_conflict(self):
        self.assertIn("type-conflict", {f.rule for f in check_row(movie(Tags="Rental, Floor Sale"))})

    def test_format_missing(self):
        self.assertIn("format-missing", {f.rule for f in check_row(movie(Vendor=""))})

    def test_genre_missing_has_no_genre_autofixes(self):
        rules = {f.rule for f in check_row(movie(**{"Option1 Value": "Default Title", GENRE_METAFIELD: ""}))}
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
