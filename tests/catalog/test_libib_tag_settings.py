import json
import tempfile
import unittest
from pathlib import Path

from catalog.errors import InputShapeError
from catalog.libib.tag_settings import TagSettings, load_settings


class TestLoadSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tag_settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return self.path

    def settings(self, count=50, max_age_days=None, max_changes=125):
        return {"new_arrivals": {"count": count, "max_age_days": max_age_days}, "max_changes": max_changes}

    def assert_rejected(self, data, key):
        with self.assertRaises(InputShapeError) as ctx:
            load_settings(self.write(data))
        self.assertIn("tag_settings.json", str(ctx.exception))
        self.assertIn(key, str(ctx.exception))

    def test_shipped_file_loads(self):
        self.assertEqual(load_settings(), TagSettings(50, None, 125))

    def test_max_age_days_number(self):
        self.assertEqual(load_settings(self.write(self.settings(max_age_days=7))).new_arrivals_max_age_days, 7)

    def test_rejects_zero_count(self):
        self.assert_rejected(self.settings(count=0), "new_arrivals.count")

    def test_rejects_non_integer_count(self):
        self.assert_rejected(self.settings(count="50"), "new_arrivals.count")

    def test_rejects_boolean_count(self):
        self.assert_rejected(self.settings(count=True), "new_arrivals.count")

    def test_rejects_negative_max_age(self):
        self.assert_rejected(self.settings(max_age_days=-1), "new_arrivals.max_age_days")

    def test_rejects_missing_key(self):
        self.assert_rejected({"new_arrivals": {"count": 50, "max_age_days": None}}, "max_changes")

    def test_rejects_bad_json(self):
        self.assert_rejected("{not json", "JSON")


if __name__ == "__main__":
    unittest.main()
