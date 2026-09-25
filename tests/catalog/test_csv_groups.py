import csv
import tempfile
import unittest
from pathlib import Path

from catalog.apply.csv_groups import REQUIRED_COLUMNS, build_import_files, warnings_for, write_import_files
from catalog.apply.merge import Change
from catalog.core.columns import GENRE_METAFIELD


def row(handle, **overrides):
    base = {"Handle": handle, "Title": f"Title {handle}", "Option1 Name": "Genre", "Option1 Value": "Comedy",
            "Image Src": "", "Image Alt Text": "", "Body (HTML)": "", "Tags": "Rental, VHS, Comedy",
            "Vendor": "VHS", "Variant Price": "0.00", GENRE_METAFIELD: "comedy"}
    base.update(overrides)
    return base


ROWS = {
    "img": row("img"),
    "alt": row("alt", **{"Image Src": "https://cdn/a.jpg"}),
    "desc": row("desc"),
    "genre": row("genre", **{"Option1 Name": "Title", "Option1 Value": "Default Title", GENRE_METAFIELD: ""}),
    "tags": row("tags", Tags="Rental, vhs, Comedy"),
    "vendor": row("vendor", Vendor="bluray"),
    "price": row("price", **{"Variant Price": ""}),
}
CHANGES = [
    Change("img", "Image Src", "", "https://tmdb/i.jpg", "pick:q"),
    Change("img", "Image Alt Text", "", "Title img poster", "pick:q"),
    Change("img", "Body (HTML)", "", "<p>x</p>", "pick:q"),
    Change("alt", "Image Alt Text", "", "Title alt poster", "auto-fix"),
    Change("desc", "Body (HTML)", "", "<p>d</p>", "auto-fix"),
    Change("genre", "Option1 Name", "Title", "Genre", "auto-fix"),
    Change("genre", "Option1 Value", "Default Title", "Comedy", "auto-fix"),
    Change("genre", GENRE_METAFIELD, "", "comedy", "auto-fix"),
    Change("tags", "Tags", "Rental, vhs, Comedy", "Rental, VHS, Comedy", "auto-fix"),
    Change("vendor", "Vendor", "bluray", "Blu-Ray", "auto-fix"),
    Change("price", "Variant Price", "", "0", "auto-fix"),
]


class TestBuildImportFiles(unittest.TestCase):
    def setUp(self):
        self.files = build_import_files(CHANGES, ROWS)

    def handles(self, name):
        return [r["Handle"] for r in self.files[name][1]]

    def test_each_change_lands_in_its_group(self):
        self.assertEqual(self.handles("image.csv"), ["img"])
        self.assertEqual(self.handles("alt-text.csv"), ["alt"])
        self.assertEqual(self.handles("description.csv"), ["desc", "img"])
        self.assertEqual(self.handles("genre.csv"), ["genre"])
        self.assertEqual(self.handles("tags.csv"), ["tags"])
        self.assertEqual(self.handles("vendor.csv"), ["vendor"])
        self.assertEqual(self.handles("price.csv"), ["price"])

    def test_only_needed_columns(self):
        self.assertEqual(self.files["description.csv"][0], REQUIRED_COLUMNS + ["Body (HTML)"])
        self.assertEqual(self.files["image.csv"][0], REQUIRED_COLUMNS + ["Image Src", "Image Alt Text"])
        self.assertEqual(self.files["genre.csv"][0], REQUIRED_COLUMNS + [GENRE_METAFIELD])

    def test_no_file_contains_a_blank_cell(self):
        for name, (columns, rows) in self.files.items():
            for r in rows:
                for column in columns:
                    with self.subTest(file=name, handle=r["Handle"], column=column):
                        self.assertTrue(str(r[column]).strip())

    def test_alt_text_file_restates_the_existing_image(self):
        self.assertEqual(self.files["alt-text.csv"][1][0]["Image Src"], "https://cdn/a.jpg")

    def test_genre_file_carries_the_new_option1(self):
        r = self.files["genre.csv"][1][0]
        self.assertEqual((r["Option1 Name"], r["Option1 Value"]), ("Genre", "Comedy"))

    def test_other_files_carry_the_final_option1_too(self):
        changes = CHANGES + [Change("genre", "Body (HTML)", "", "<p>g</p>", "auto-fix")]
        files = build_import_files(changes, ROWS)
        r = [x for x in files["description.csv"][1] if x["Handle"] == "genre"][0]
        self.assertEqual(r["Option1 Value"], "Comedy")

    def test_empty_groups_are_not_produced(self):
        files = build_import_files([Change("desc", "Body (HTML)", "", "<p>d</p>", "auto-fix")], ROWS)
        self.assertEqual(list(files), ["description.csv"])


class TestWarnings(unittest.TestCase):
    def test_warns_about_option1_and_image_restating(self):
        text = " ".join(warnings_for(build_import_files(CHANGES, ROWS)))
        self.assertIn("genre.csv", text)
        self.assertIn("alt-text.csv", text)

    def test_no_warnings_for_safe_files(self):
        self.assertEqual(warnings_for(build_import_files([Change("desc", "Body (HTML)", "", "<p>d</p>", "a")], ROWS)), [])


class TestWriteImportFiles(unittest.TestCase):
    def test_writes_files_and_clears_stale_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            import_dir = Path(tmp) / "import"
            import_dir.mkdir()
            (import_dir / "price.csv").write_text("stale", encoding="utf-8")
            paths = write_import_files(import_dir, build_import_files(CHANGES[:3], ROWS))
            self.assertEqual(sorted(p.name for p in import_dir.iterdir()), ["description.csv", "image.csv"])
            with open(import_dir / "image.csv", newline="", encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f)), REQUIRED_COLUMNS + ["Image Src", "Image Alt Text"])
            self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
