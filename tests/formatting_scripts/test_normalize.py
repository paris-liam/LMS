import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from columns import EXPORT_COLUMNS, GENRE_METAFIELD, TEMPLATE_COLUMNS
from normalize import normalize_rows, output_columns


def export_row(**overrides):
    row = {
        "Handle": "legend-of-zorro",
        "Title": "Legend of Zorro",
        "Body (HTML)": "<p>A masked hero rides again.</p>",
        "Vendor": "DVD",
        "Product Category": "",
        "Type": "",
        "Tags": "Floor Sale, Action",
        "Published": "TRUE",
        "Option1 Name": "Condition",
        "Option1 Value": "Standard",
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": "1",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": "9.99",
        "Variant Barcode": "88302842",
        "Image Src": "https://cdn.shopify.com/x.jpg",
        "Image Position": "1",
        "Image Alt Text": "",
    }
    row.update(overrides)
    return row


def template_row(**overrides):
    row = {
        "Handle": "",
        "Title": "Rushmore",
        "Body (HTML)": "",
        "Vendor": "",
        "Product Category": "",
        "Tags": "Rental, VHS, Comedy",
        "Status": "",
        "Option1 Name": "",
        "Option1 Value": "",
        "Variant Inventory Tracker": "",
        "Variant Inventory Qty": "",
        "Variant Inventory Policy": "",
        "Variant Fulfillment Service": "",
        "Variant Price": "",
        "Image Src": "",
        "Image Alt Text": "",
        GENRE_METAFIELD: "",
        "Format": "VHS",
        "Genre 1": "Comedy",
        "Genre 2": "",
        "Genre 3": "",
        "Year": "1998",
        "Extra tags": "",
    }
    row.update(overrides)
    return row


class TestOutputColumns(unittest.TestCase):
    def test_picks_the_contract_by_shape(self):
        self.assertEqual(output_columns("template"), TEMPLATE_COLUMNS)
        self.assertEqual(output_columns("export"), EXPORT_COLUMNS)


class TestExportNormalization(unittest.TestCase):
    def test_produces_exactly_the_export_columns(self):
        clean, issues = normalize_rows([export_row()], "export")
        self.assertEqual(issues, [])
        self.assertEqual(list(clean[0]), EXPORT_COLUMNS)

    def test_preserves_the_existing_handle_verbatim(self):
        clean, _ = normalize_rows([export_row(Handle="lEgEnd-of-zorro-99")], "export")
        self.assertEqual(clean[0]["Handle"], "lEgEnd-of-zorro-99")

    def test_carries_the_barcode_through(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Variant Barcode"], "88302842")

    def test_rewrites_option1_from_condition_to_the_primary_genre(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Option1 Name"], "Genre")
        self.assertEqual(clean[0]["Option1 Value"], "Action")

    def test_fills_the_genre_metafield_with_semicolon_joined_handles(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Floor Sale, Action, Sci-Fi")], "export"
        )
        self.assertEqual(clean[0][GENRE_METAFIELD], "action; sci-fi")

    def test_rebuilds_tags_as_type_format_genres_extras(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Floor Sale, Action, Criterion Collection")], "export"
        )
        self.assertEqual(clean[0]["Tags"], "Floor Sale, DVD, Action, Criterion Collection, Formatted")

    def test_normalizes_vendor_case(self):
        clean, _ = normalize_rows([export_row(Vendor="BLU-RAY")], "export")
        self.assertEqual(clean[0]["Vendor"], "Blu-Ray")

    def test_applies_the_fixed_values(self):
        clean, _ = normalize_rows([export_row(**{"Product Category": ""})], "export")
        self.assertEqual(clean[0]["Product Category"], "Media > Videos")
        self.assertEqual(clean[0]["Variant Inventory Tracker"], "shopify")
        self.assertEqual(clean[0]["Variant Inventory Qty"], "1")
        self.assertEqual(clean[0]["Variant Inventory Policy"], "deny")
        self.assertEqual(clean[0]["Variant Fulfillment Service"], "manual")

    def test_forces_rental_price_to_zero(self):
        clean, _ = normalize_rows(
            [export_row(Tags="Rental, Action", **{"Variant Price": "0.00"})], "export"
        )
        self.assertEqual(clean[0]["Variant Price"], "0")

    def test_writes_alt_text_when_an_image_has_none(self):
        clean, _ = normalize_rows([export_row()], "export")
        self.assertEqual(clean[0]["Image Alt Text"], "Legend of Zorro poster")

    def test_leaves_existing_alt_text_alone(self):
        clean, _ = normalize_rows(
            [export_row(**{"Image Alt Text": "Legend of Zorro (2005) poster"})], "export"
        )
        self.assertEqual(clean[0]["Image Alt Text"], "Legend of Zorro (2005) poster")

    def test_extra_image_rows_pass_through_with_image_fields_only(self):
        rows = [
            export_row(),
            {"Handle": "legend-of-zorro", "Title": "", "Vendor": "", "Tags": "",
             "Option1 Name": "", "Option1 Value": "", "Variant Price": "",
             "Variant Barcode": "", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2", "Image Alt Text": ""},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), 2)
        self.assertEqual(clean[1]["Image Src"], "https://cdn.shopify.com/y.jpg")
        self.assertEqual(clean[1]["Image Position"], "2")
        self.assertEqual(clean[1]["Title"], "")
        self.assertEqual(clean[1]["Vendor"], "")


class TestExportBestEffort(unittest.TestCase):
    """A row missing genre/format/type/price still uploads, tagged Issue_*
    so the client can fix it in the admin — it doesn't get blocked into
    issues.csv. Only genuinely bad data still blocks (see TestExportIssues)."""

    def test_no_usable_genre_uploads_with_issue_tag(self):
        clean, issues = normalize_rows(
            [export_row(**{"Option1 Value": "Special Interest", "Tags": "Floor Sale",
                           "Variant Price": "9.99"})],
            "export",
        )
        self.assertEqual(issues, [])
        self.assertEqual(clean[0]["Option1 Value"], "")
        self.assertEqual(clean[0][GENRE_METAFIELD], "")
        self.assertIn("Issue_Genre_Needed", clean[0]["Tags"])

    def test_no_format_uploads_with_raw_vendor_and_issue_tag(self):
        clean, issues = normalize_rows([export_row(Vendor="Unknown")], "export")
        self.assertEqual(issues, [])
        self.assertEqual(clean[0]["Vendor"], "Unknown")
        self.assertIn("Issue_Needs_Format", clean[0]["Tags"])
        self.assertNotIn("Unknown,", clean[0]["Tags"])  # not treated as a format tag

    def test_no_type_tag_uploads_with_raw_price_and_issue_tag(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Action", **{"Variant Price": "12.99"})], "export"
        )
        self.assertEqual(issues, [])
        tag_list = [t.strip() for t in clean[0]["Tags"].split(",")]
        self.assertIn("Issue_Rental_Or_Sale", tag_list)
        self.assertNotIn("Rental", tag_list)
        self.assertNotIn("Floor Sale", tag_list)
        # type unknown -> price can't be validated, passes through as-is
        self.assertEqual(clean[0]["Variant Price"], "12.99")

    def test_rental_priced_above_zero_uploads_with_raw_price_and_issue_tag(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Rental, Action", **{"Variant Price": "12.99"})], "export"
        )
        self.assertEqual(issues, [])
        self.assertEqual(clean[0]["Variant Price"], "12.99")
        self.assertIn("Issue_Rental_Price", clean[0]["Tags"])

    def test_floor_sale_with_no_price_uploads_with_issue_tag(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Floor Sale, Action", **{"Variant Price": ""})], "export"
        )
        self.assertEqual(issues, [])
        self.assertEqual(clean[0]["Variant Price"], "")
        self.assertIn("Issue_No_Price", clean[0]["Tags"])

    def test_an_existing_issue_tag_is_not_duplicated(self):
        clean, issues = normalize_rows(
            [export_row(Vendor="Unknown", Tags="Floor Sale, Action, Issue_Needs_Format")],
            "export",
        )
        self.assertEqual(issues, [])
        self.assertEqual(clean[0]["Tags"].count("Issue_Needs_Format"), 1)


class TestExportIssues(unittest.TestCase):
    def test_flags_ambiguous_type(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Rental, Floor Sale, Action")], "export"
        )
        self.assertEqual(clean, [])
        self.assertIn("tagged as both", issues[0]["Reason"])

    def test_flags_an_unreadable_price(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Rental, Action", **{"Variant Price": "abc"})], "export"
        )
        self.assertEqual(clean, [])
        self.assertIn("unreadable price", issues[0]["Reason"])

    def test_flags_a_negative_floor_sale_price(self):
        clean, issues = normalize_rows(
            [export_row(Tags="Floor Sale, Action", **{"Variant Price": "-5"})], "export"
        )
        self.assertEqual(clean, [])
        self.assertIn("negative price", issues[0]["Reason"])

    def test_flags_a_multi_variant_product(self):
        rows = [
            export_row(**{"Option1 Value": "Standard"}),
            export_row(**{"Option1 Value": "50%", "Variant Barcode": "88302843"}),
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(clean, [])
        self.assertIn("2 variants", issues[0]["Reason"])

    def test_issue_rows_carry_the_original_columns_verbatim_for_editing(self):
        original = export_row(Tags="Rental, Floor Sale, Action")
        _, issues = normalize_rows([original], "export")
        for key, value in original.items():
            self.assertEqual(issues[0][key], value, key)
        self.assertIn("Reason", issues[0])

    def test_every_row_of_a_flagged_product_goes_to_issues(self):
        rows = [
            export_row(Tags="Rental, Floor Sale, Action"),
            {"Handle": "legend-of-zorro", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2"},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(clean, [])
        self.assertEqual(len(issues), 2)


class TestTemplateNormalization(unittest.TestCase):
    def test_produces_exactly_the_template_columns(self):
        clean, issues = normalize_rows([template_row()], "template")
        self.assertEqual(issues, [])
        self.assertEqual(list(clean[0]), TEMPLATE_COLUMNS)

    def test_derives_the_handle_and_sets_status_active(self):
        clean, _ = normalize_rows([template_row()], "template")
        self.assertEqual(clean[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(clean[0]["Status"], "Active")

    def test_second_copy_gets_a_numeric_suffix(self):
        clean, _ = normalize_rows([template_row(), template_row()], "template")
        self.assertEqual(clean[0]["Handle"], "rushmore-vhs-rental")
        self.assertEqual(clean[1]["Handle"], "rushmore-vhs-rental-2")

    def test_a_hand_typed_handle_override_is_kept(self):
        clean, _ = normalize_rows(
            [template_row(Handle="amelie-dvd-rental", Title="Amélie", Format="DVD")],
            "template",
        )
        self.assertEqual(clean[0]["Handle"], "amelie-dvd-rental")

    def test_vendor_comes_from_the_format_helper(self):
        clean, _ = normalize_rows([template_row(Format="Blu-Ray")], "template")
        self.assertEqual(clean[0]["Vendor"], "Blu-Ray")

    def test_helper_genres_drive_option1_metafield_and_tags(self):
        clean, _ = normalize_rows(
            [template_row(**{"Genre 1": "Sci-Fi", "Genre 2": "Thriller",
                             "Extra tags": "A24"})],
            "template",
        )
        self.assertEqual(clean[0]["Option1 Value"], "Sci-Fi")
        self.assertEqual(clean[0][GENRE_METAFIELD], "sci-fi; thriller")
        self.assertEqual(clean[0]["Tags"], "Rental, VHS, Sci-Fi, Thriller, A24, Formatted")

    def test_extra_tags_column_rejects_a_genre_already_set_via_genre_1(self):
        """Genre 1=Comedy, Extra tags=Rental must not duplicate the type tag
        or leak a second copy of it into Tags."""
        clean, _ = normalize_rows(
            [template_row(**{"Genre 1": "Comedy", "Extra tags": "Rental"})],
            "template",
        )
        self.assertEqual(clean[0]["Tags"], "Rental, VHS, Comedy, Formatted")

    def test_extra_tags_column_rejects_a_format_word(self):
        """A DVD product must not end up tagged Blu-Ray via Extra tags."""
        clean, _ = normalize_rows(
            [template_row(Format="DVD", **{"Extra tags": "Blu-Ray"})],
            "template",
        )
        self.assertEqual(clean[0]["Vendor"], "DVD")
        self.assertEqual(clean[0]["Tags"], "Rental, DVD, Comedy, Formatted")

    def test_extra_tags_column_rejects_a_genre_word_not_set_via_genre_1(self):
        """A Comedy product must not ship tagged Horror with no Horror genre,
        and the genre metafield must stay comedy-only."""
        clean, _ = normalize_rows(
            [template_row(**{"Genre 1": "Comedy", "Extra tags": "Horror"})],
            "template",
        )
        self.assertEqual(clean[0]["Tags"], "Rental, VHS, Comedy, Formatted")
        self.assertEqual(clean[0][GENRE_METAFIELD], "comedy")

    def test_floor_sale_without_a_price_uploads_with_issue_tag(self):
        clean, issues = normalize_rows(
            [template_row(Tags="Floor Sale, VHS, Comedy")], "template"
        )
        self.assertEqual(issues, [])
        self.assertIn("Issue_No_Price", clean[0]["Tags"])


class TestGrouping(unittest.TestCase):
    def test_template_rows_are_one_product_each_despite_blank_handles(self):
        """Blank Handle cells must not collapse a batch into one product."""
        clean, issues = normalize_rows(
            [template_row(Title="Rushmore"), template_row(Title="Bottle Rocket")],
            "template",
        )
        self.assertEqual(issues, [])
        self.assertEqual([r["Handle"] for r in clean],
                         ["rushmore-vhs-rental", "bottle-rocket-vhs-rental"])

    def test_export_rows_sharing_a_handle_are_one_product(self):
        rows = [
            export_row(),
            {"Handle": "legend-of-zorro", "Image Src": "https://cdn.shopify.com/y.jpg",
             "Image Position": "2"},
        ]
        clean, issues = normalize_rows(rows, "export")
        self.assertEqual(issues, [])
        self.assertEqual(len(clean), 2)


class TestDuplicateHandles(unittest.TestCase):
    def test_two_template_rows_typing_the_same_handle_are_both_flagged(self):
        rows = [
            template_row(Handle="amelie-dvd-rental", Title="Amélie", Format="DVD"),
            template_row(Handle="amelie-dvd-rental", Title="Amelie", Format="DVD"),
        ]
        clean, issues = normalize_rows(rows, "template")
        self.assertEqual(clean, [])
        self.assertEqual(len(issues), 2)
        self.assertIn("duplicate handle", issues[0]["Reason"])


if __name__ == "__main__":
    unittest.main()
