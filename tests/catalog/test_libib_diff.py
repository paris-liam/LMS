import unittest

from catalog.core.columns import GENRE_METAFIELD
from catalog.libib.diff import diff


def rental(handle="jaws", barcode="01577790", **overrides):
    base = {"Handle": handle, "Title": "Jaws", "Body (HTML)": "<p>A shark.</p>", "Image Src": "https://cdn/j.jpg",
            "Variant Barcode": barcode, "Variant Price": "0", "Tags": "Rental, VHS, Horror", "Vendor": "VHS",
            GENRE_METAFIELD: "horror"}
    base.update(overrides)
    return base


def item(item_id="i1", call="01577790", **overrides):
    base = {"id": item_id, "title": "Jaws", "barcode": call, "call_number": call, "tags": "horror,vhs",
            "description": "A shark.", "collection": "Rental Library"}
    base.update(overrides)
    return base


def fields(result, handle="jaws"):
    return {d["field"] for d in result.drift if d["handle"] == handle}


class TestDiff(unittest.TestCase):
    def test_in_sync(self):
        result = diff([rental()], [item()], {})
        self.assertEqual(result.in_sync, ["jaws"])
        self.assertEqual((result.drift, result.eligible, result.orphans), ([], [], []))

    def test_field_drift(self):
        result = diff([rental()], [item(title="JAWS", description="Old.", tags="vhs", barcode="99999999")], {})
        self.assertEqual(fields(result), {"title", "description", "tags", "barcode"})

    def test_whitespace_and_tag_order_are_not_drift(self):
        result = diff([rental()], [item(title=" Jaws ", description="A  shark.", tags="VHS, Horror")], {})
        self.assertEqual(result.in_sync, ["jaws"])

    def test_poster_drift_when_the_uploaded_poster_differs(self):
        self.assertEqual(fields(diff([rental()], [item()], {"jaws": {"status": "done", "poster_src": "https://cdn/old.jpg"}})),
                         {"poster"})

    def test_tracked_rental_with_an_unconfirmed_poster_is_poster_drift(self):
        result = diff([rental()], [item()], {"jaws": {"status": "done"}})
        self.assertEqual(fields(result), {"poster"})
        self.assertEqual(result.drift[0]["libib"], "unconfirmed")

    def test_untracked_rental_is_in_sync_without_poster_evidence(self):
        self.assertEqual(diff([rental()], [item()], {}).in_sync, ["jaws"])

    def test_no_poster_drift_when_shopify_has_no_image(self):
        result = diff([rental(**{"Image Src": ""})], [item()], {"jaws": {"status": "done"}})
        self.assertEqual(result.in_sync, ["jaws"])

    def test_missing_and_complete_is_eligible(self):
        result = diff([rental()], [], {})
        self.assertEqual(result.eligible, [{"handle": "jaws", "call_number": "01577790", "title": "Jaws"}])

    def test_missing_poster_alone_is_still_eligible(self):
        result = diff([rental(**{"Image Src": ""})], [], {})
        self.assertEqual(result.eligible, [{"handle": "jaws", "call_number": "01577790", "title": "Jaws"}])
        self.assertEqual(result.incomplete, [])

    def test_missing_and_incomplete_is_counted_not_eligible(self):
        result = diff([rental(**{"Body (HTML)": ""})], [], {})
        self.assertEqual((result.eligible, result.incomplete), ([], ["jaws"]))

    def test_poster_appearing_later_is_poster_drift_for_a_synced_rental(self):
        # synced without a poster (poster_src unset), Shopify now has one -> the fixer uploads it
        result = diff([rental()], [item()], {"jaws": {"status": "done", "call_number": "01577790"}})
        self.assertEqual(fields(result), {"poster"})

    def test_in_flight_rental_is_not_eligible(self):
        for status in ("queued", "imported"):
            with self.subTest(status=status):
                self.assertEqual(diff([rental()], [], {"jaws": {"status": status}}).eligible, [])

    def test_done_but_missing_becomes_eligible_again(self):
        self.assertEqual(len(diff([rental()], [], {"jaws": {"status": "done"}}).eligible), 1)

    def test_blocked_barcodes(self):
        rows = [rental("a", ""), rental("b", "1234567"), rental("c", "01577790"),
                {**rental("d", "01577790"), "Tags": "Floor Sale, DVD, Drama"}]
        result = diff(rows, [], {})
        reasons = {b["handle"]: b["reason"] for b in result.blocked}
        self.assertEqual(reasons["a"], "barcode missing")
        self.assertEqual(reasons["b"], "barcode is not 8 digits")
        self.assertIn("also on d", reasons["c"])
        self.assertNotIn("d", reasons)  # floor sale: not in Libib scope
        self.assertEqual(result.eligible, [])

    def test_floor_sale_is_ignored(self):
        result = diff([rental(Tags="Floor Sale, VHS, Horror")], [], {})
        self.assertEqual((result.eligible, result.blocked, result.in_sync), ([], [], []))

    def test_item_without_call_number_matches_on_barcode(self):
        result = diff([rental()], [item(call_number="")], {})
        self.assertEqual(result.eligible, [])
        self.assertEqual(fields(result), {"call_number"})
        self.assertEqual(result.orphans, [])

    def test_duplicate_call_number_lists_both_items(self):
        result = diff([rental()], [item("i1"), item("i2")], {})
        self.assertEqual(sorted(o["id"] for o in result.orphans), ["i1", "i2"])
        self.assertTrue(all("duplicate" in o["reason"] for o in result.orphans))
        self.assertEqual((result.eligible, result.in_sync, result.drift), ([], [], []))

    def test_orphans(self):
        result = diff([], [item("i1", "05555555"), item("i2", "", barcode="2010000000007")], {})
        reasons = {o["id"]: o["reason"] for o in result.orphans}
        self.assertIn("05555555", reasons["i1"])
        self.assertEqual(reasons["i2"], "no call number")

    def test_in_sync_in_flight_or_needs_review_is_promoted(self):
        for status in ("queued", "imported", "needs-review"):
            with self.subTest(status=status):
                state = {"jaws": {"status": status, "batch": "batch-0001", "poster_src": "https://cdn/j.jpg"}}
                result = diff([rental()], [item()], state)
                self.assertEqual(result.promoted, ["jaws"])
                self.assertEqual(state["jaws"]["status"], "done")

    def test_drifting_item_is_not_promoted(self):
        state = {"jaws": {"status": "imported"}}
        diff([rental()], [item(title="Wrong")], state)
        self.assertEqual(state["jaws"]["status"], "imported")


class TestReviewFixes(unittest.TestCase):
    def test_needs_review_missing_rental_is_held_not_eligible(self):
        result = diff([rental()], [], {"jaws": {"status": "needs-review", "note": "do not import yet"}})
        self.assertEqual(result.eligible, [])
        self.assertEqual(result.held, [{"handle": "jaws", "call_number": "01577790", "note": "do not import yet"}])

    def test_rental_found_under_its_old_call_number_is_matched_not_eligible(self):
        state = {"jaws": {"status": "needs-review", "call_number": "191-VHSJAW-001A"}}
        result = diff([rental()], [item("i9", "191-VHSJAW-001A", barcode="2010000000001")], state)
        self.assertEqual((result.eligible, result.held, result.orphans), ([], [], []))
        drift = {d["field"]: d for d in result.drift}
        self.assertEqual(drift["call_number"]["libib"], "191-VHSJAW-001A")

    def test_old_call_number_shared_by_two_items_is_not_used(self):
        state = {"jaws": {"status": "done", "call_number": "191-X"}}
        result = diff([rental()], [item("i1", "191-X"), item("i2", "191-X")], state)
        self.assertEqual(len(result.eligible), 1)


if __name__ == "__main__":
    unittest.main()
