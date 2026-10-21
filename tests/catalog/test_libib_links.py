import http.client
import io
import unittest
import urllib.error

from catalog.libib.links import JoinIdChange, LookupFailed, lookup_join_ids, parse_join_ids, plan_join_ids
from catalog.libib.tags import LinkTarget


def t(pid, stored=None):
    return LinkTarget(pid, f"Movie {pid}", f"item-{pid}", f"9202{pid}", stored)


def fake_lookup(replies):
    def lookup(barcode):
        reply = replies[barcode]
        if isinstance(reply, Exception):
            raise reply
        return reply
    return lookup


def run(targets, replies):
    return plan_join_ids(targets, fake_lookup(replies), sleep=lambda s: None)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestParse(unittest.TestCase):
    def test_parse_unique_join_ids(self):
        payload = {"outcome": "success",
                   "item-info": '<a data-join-id="5"></a><b data-join-id="5"></b><c data-join-id="7">'}
        self.assertEqual(parse_join_ids(payload), ["5", "7"])

    def test_parse_error_outcome_raises(self):
        with self.assertRaises(LookupFailed):
            parse_join_ids({"outcome": "error"})

    def test_non_json_reply_is_a_failure(self):
        with self.assertRaises(LookupFailed):
            lookup_join_ids("92021234", urlopen=lambda *a, **k: FakeResponse(b"<html>"))

    def test_dropped_connection_is_a_failure(self):
        def urlopen(*a, **k):
            raise http.client.IncompleteRead(b"")
        with self.assertRaises(LookupFailed):
            lookup_join_ids("92021234", urlopen=urlopen)

    def test_item_info_of_wrong_type_is_a_failure(self):
        with self.assertRaises(LookupFailed):
            parse_join_ids({"outcome": "success", "item-info": ["not", "html"]})

    def test_error_outcome_text_is_not_echoed(self):
        with self.assertRaises(LookupFailed) as caught:
            parse_join_ids({"outcome": "no results for 92021234"})
        self.assertNotIn("92021234", str(caught.exception))

    def test_errors_never_contain_the_barcode(self):
        def urlopen(*a, **k):
            raise urllib.error.URLError("keywords=92021234")
        with self.assertRaises(LookupFailed) as caught:
            lookup_join_ids("92021234", urlopen=urlopen)
        self.assertNotIn("92021234", str(caught.exception))


class TestPlanJoinIds(unittest.TestCase):
    def test_one_hit_sets_value(self):
        changes, warnings = run([t("1")], {"92021": ["169565504"]})
        self.assertEqual(changes, [JoinIdChange("1", "Movie 1", "item-1", None, 169565504)])
        self.assertEqual(warnings, [])

    def test_unchanged_value_makes_no_change(self):
        self.assertEqual(run([t("1", 169565504)], {"92021": ["169565504"]}), ([], []))

    def test_several_hits_keep_value_and_report(self):
        changes, warnings = run([t("1", 1)], {"92021": ["2", "3"]})
        self.assertEqual(changes, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("2 Libib items", warnings[0].reason)

    def test_zero_hits_clears_when_another_lookup_succeeded(self):
        changes, _ = run([t("1", 9), t("2")], {"92021": [], "92022": ["4"]})
        self.assertIn(JoinIdChange("1", "Movie 1", "item-1", 9, None), changes)

    def test_no_clears_without_a_successful_lookup(self):
        changes, warnings = run([t("1", 9), t("2", 8)], {"92021": [], "92022": []})
        self.assertEqual(changes, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("no lookup succeeded", warnings[0].reason)

    def test_too_many_clears_are_all_dropped(self):
        targets = [t(str(i), 9) for i in range(11)] + [t("x")]
        replies = {f"9202{i}": [] for i in range(11)} | {"9202x": ["4"]}
        changes, warnings = run(targets, replies)
        self.assertEqual(changes, [JoinIdChange("x", "Movie x", "item-x", None, 4)])
        self.assertEqual(len(warnings), 1)
        self.assertIn("11", warnings[0].reason)
        self.assertIn("10", warnings[0].reason)

    def test_failed_lookup_keeps_stored_value(self):
        changes, warnings = run([t("1", 9)], {"92021": LookupFailed("HTTPError 503")})
        self.assertEqual(changes, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("HTTPError 503", warnings[0].reason)

    def test_zero_hits_without_stored_value_is_reported_only(self):
        changes, warnings = run([t("1")], {"92021": []})
        self.assertEqual(changes, [])
        self.assertEqual([w.reason for w in warnings], ["not found on the public Libib page"])


if __name__ == "__main__":
    unittest.main()
