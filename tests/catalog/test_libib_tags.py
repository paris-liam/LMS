import unittest
from datetime import datetime, timezone

from catalog.libib.tag_settings import TagSettings
from catalog.libib.tags import (
    LibibChange, Product, ShopifyChange, ShopifyState, Unmatched, apply_tag_change, plan_tags, title_key,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def item(id, barcode, tags="vhs", title="T"):
    return {"id": id, "title": title, "barcode": barcode, "call_number": "", "tags": tags,
            "description": "", "collection": "Rental Library", "created": ""}


def product(id, barcodes, tags=("Rental",), title=None, vendor="VHS", created="2026-10-01T00:00:00Z"):
    return Product(id, title or id, tuple(tags), tuple(barcodes), vendor, created)


def state(rentals=(), picked=(), tagged_picks=(), tagged_new_arrivals=()):
    return ShopifyState(tuple(rentals), tuple(picked), tuple(tagged_picks), tuple(tagged_new_arrivals))


def plan(items, st, count=50, max_age_days=None):
    return plan_tags(items, st, TagSettings(count, max_age_days, 125), NOW)


def libib_adds(p):
    return {c.item_id: c.add for c in p.libib if c.add}


def shopify(p, tag="new-arrival"):
    return {(c.product_id, c.action) for c in p.shopify if c.tag == tag}


class TestNewArrivals(unittest.TestCase):
    def test_newest_titles_are_tagged_in_both_places(self):
        items = [item("a", "1"), item("b", "2"), item("c", "3")]
        rentals = [product("pA", ("1",), created="2026-10-01T00:00:00Z"),
                   product("pB", ("2",), created="2026-10-02T00:00:00Z"),
                   product("pC", ("3",), created="2026-10-03T00:00:00Z")]
        p = plan(items, state(rentals), count=2)
        self.assertEqual(libib_adds(p), {"b": frozenset({"new arrival"}), "c": frozenset({"new arrival"})})
        self.assertEqual(shopify(p), {("pB", "add"), ("pC", "add")})
        self.assertEqual(p.new_arrival_titles, 2)

    def test_already_tagged_newest_title_has_no_change(self):
        rental = product("pA", ("1",), tags=("Rental", "new-arrival"))
        p = plan([item("a", "1", "vhs, new arrival")], state([rental], tagged_new_arrivals=[rental]))
        self.assertEqual((p.libib, p.shopify), ([], []))

    def test_copies_count_as_one_title(self):
        items = [item(x, x) for x in ("1", "2", "3", "4", "5")]
        rentals = [product("legend1", ("1",), title="Legend", created="2026-10-05T00:00:00Z"),
                   product("legend2", ("2",), title="Legend", created="2026-10-06T00:00:00Z"),
                   product("legend3", ("3",), title="Legend", created="2026-10-07T00:00:00Z"),
                   product("alien", ("4",), title="Alien", created="2026-10-01T00:00:00Z"),
                   product("old", ("5",), title="Old", created="2026-09-01T00:00:00Z")]
        p = plan(items, state(rentals), count=2)
        self.assertEqual(set(libib_adds(p)), {"1", "2", "3", "4"})
        self.assertEqual({pid for pid, _ in shopify(p)}, {"legend1", "legend2", "legend3", "alien"})

    def test_format_separates_titles(self):
        items = [item("a", "1"), item("b", "2")]
        rentals = [product("vhs", ("1",), title="Legend", vendor="VHS", created="2026-10-01T00:00:00Z"),
                   product("dvd", ("2",), title="Legend", vendor="DVD", created="2026-10-02T00:00:00Z")]
        self.assertEqual(set(libib_adds(plan(items, state(rentals), count=1))), {"b"})

    def test_year_separates_titles(self):
        items = [item("a", "1"), item("b", "2")]
        rentals = [product("h78", ("1",), title="Halloween (1978)", created="2026-10-01T00:00:00Z"),
                   product("h18", ("2",), title="Halloween (2018)", created="2026-10-02T00:00:00Z")]
        self.assertEqual(set(libib_adds(plan(items, state(rentals), count=1))), {"b"})

    def test_title_key_ignores_edition_words_and_case(self):
        self.assertEqual(title_key(product("x", (), title="Legend (Director's Cut)")),
                         title_key(product("y", (), title="legend")))

    def test_title_age_is_its_first_copy(self):
        items = [item("old1", "1"), item("old2", "2"), item("new", "3")]
        rentals = [product("o1", ("1",), title="Old", created="2026-09-01T00:00:00Z"),
                   product("o2", ("2",), title="Old", created="2026-10-10T00:00:00Z"),   # extra copy, newest product
                   product("n", ("3",), title="New", created="2026-10-05T00:00:00Z")]
        p = plan(items, state(rentals), count=1)
        self.assertEqual(set(libib_adds(p)), {"new"})
        self.assertEqual(shopify(p), {("n", "add")})

    def test_old_title_drops_out_when_newer_arrive(self):
        old = product("old", ("1",), tags=("Rental", "new-arrival"), created="2026-09-01T00:00:00Z")
        new = product("new", ("2",), created="2026-10-01T00:00:00Z")
        p = plan([item("a", "1", "vhs, new arrival"), item("b", "2")], state([old, new], tagged_new_arrivals=[old]),
                 count=1)
        self.assertEqual({c.item_id: c.remove for c in p.libib if c.remove}, {"a": frozenset({"new arrival"})})
        self.assertEqual(shopify(p), {("old", "remove"), ("new", "add")})

    def test_not_in_libib_or_not_rental_loses_shopify_tag_and_takes_no_slot(self):
        floor = product("floor", ("9",), tags=("Floor Sale", "new-arrival"), created="2026-10-19T00:00:00Z")
        lost = product("lost", ("8",), tags=("Rental", "new-arrival"), created="2026-10-19T00:00:00Z")
        real = product("real", ("1",), created="2026-10-01T00:00:00Z")
        p = plan([item("a", "1")], state([lost, real], tagged_new_arrivals=[floor, lost]), count=1)
        self.assertEqual(shopify(p), {("floor", "remove"), ("lost", "remove"), ("real", "add")})
        self.assertEqual(set(libib_adds(p)), {"a"})

    def test_max_age_days_drops_old_titles(self):
        items = [item("a", "1"), item("b", "2")]
        rentals = [product("eight", ("1",), created="2026-10-12T11:00:00Z"),
                   product("six", ("2",), created="2026-10-14T12:00:00Z")]
        p = plan(items, state(rentals), count=50, max_age_days=7)
        self.assertEqual(set(libib_adds(p)), {"b"})

    def test_ambiguous_barcode_rental_is_not_eligible(self):
        items = [item("a", "1"), item("b", "1"), item("c", "2")]
        rentals = [product("amb", ("1",), created="2026-10-10T00:00:00Z"),
                   product("ok", ("2",), created="2026-10-01T00:00:00Z")]
        p = plan(items, state(rentals), count=1)
        self.assertEqual(set(libib_adds(p)), {"c"})
        self.assertEqual(shopify(p), {("ok", "add")})
        self.assertEqual([u.reason for u in p.unmatched], ["barcode is on 2 Libib items"])

    def test_rentals_missing_from_libib_are_not_listed_unmatched(self):
        p = plan([], state([product("p1", ("111",)), product("p2", ())]))
        self.assertEqual(p.unmatched, [])

    def test_changes_are_sorted_by_title_then_item_id(self):
        items = [item("b", "2", "", "Zed"), item("a", "1", "", "Alpha")]
        rentals = [product("p1", ("2",), title="Zed"), product("p2", ("1",), title="Alpha")]
        self.assertEqual([c.item_id for c in plan(items, state(rentals)).libib], ["a", "b"])


class TestCommunityPicks(unittest.TestCase):
    def test_only_the_picked_copy_is_tagged(self):
        items = [item("a", "111", "vhs", "Legend"), item("b", "222", "vhs", "Legend")]
        pick = product("p1", ("111",), title="Legend")
        p = plan(items, state(picked=[pick]))
        self.assertEqual([(c.item_id, c.add) for c in p.libib], [("a", frozenset({"community pick"}))])

    def test_tag_removed_when_no_longer_picked(self):
        p = plan([item("a", "111", "drama, Community Pick")], state())
        self.assertEqual(p.libib, [LibibChange("a", "T", "111", frozenset(), frozenset({"community pick"}))])

    def test_non_rental_pick_has_no_libib_change_and_is_not_unmatched(self):
        p = plan([], state(picked=[product("p1", ("999",), tags=("Floor Sale",))]))
        self.assertEqual((p.libib, p.unmatched), ([], []))

    def test_rental_pick_with_no_libib_item_is_unmatched(self):
        p = plan([], state(picked=[product("p1", ("111",), title="Bottoms")]))
        self.assertEqual(p.unmatched, [Unmatched("Bottoms", "no Libib item has this barcode")])

    def test_rental_pick_without_barcode_is_unmatched(self):
        p = plan([], state(picked=[product("p1", (), title="X")]))
        self.assertEqual(p.unmatched, [Unmatched("X", "no barcode in Shopify")])

    def test_ambiguous_barcode_touches_neither_item(self):
        p = plan([item("a", "111", "community pick"), item("b", "111", "vhs")], state())
        self.assertEqual(p.libib, [])
        self.assertEqual([u.reason for u in p.unmatched], ["barcode is on 2 Libib items"])

    def test_shopify_pick_tag_add_and_remove(self):
        st = state(picked=[product("p1", ("1",), title="A")],
                   tagged_picks=[product("p2", ("2",), tags=("Rental", "community-pick"), title="B")])
        self.assertEqual([c for c in plan([], st).shopify if c.tag == "community-pick"],
                         [ShopifyChange("p1", "A", "community-pick", "add"),
                          ShopifyChange("p2", "B", "community-pick", "remove")])

    def test_shopify_pick_already_tagged_is_unchanged(self):
        pick = product("p1", ("1",), tags=("Rental", "community-pick"))
        self.assertEqual(shopify(plan([], state(picked=[pick], tagged_picks=[pick])), "community-pick"), set())

    def test_non_rental_pick_still_gets_shopify_tag(self):
        pick = product("p1", (), tags=("Floor Sale",), title="F")
        self.assertEqual(shopify(plan([], state(picked=[pick])), "community-pick"), {("p1", "add")})

    def test_product_picked_twice_is_one_change(self):
        pick = product("p1", ("1",), title="A")
        self.assertEqual(len([c for c in plan([], state(picked=[pick, pick])).shopify]), 1)

    def test_both_tags_on_one_item(self):
        rental = product("p1", ("111",))
        p = plan([item("a", "111")], state([rental], picked=[rental]))
        self.assertEqual(p.libib[0].add, frozenset({"new arrival", "community pick"}))


class TestApplyTagChange(unittest.TestCase):
    def test_apply_keeps_other_tags(self):
        self.assertEqual(apply_tag_change("blu-ray, fantasy", {"new arrival"}, ()), "blu-ray, fantasy, new arrival")

    def test_apply_removes_case_insensitively(self):
        self.assertEqual(apply_tag_change("blu-ray, New Arrival, Drama", (), {"new arrival"}), "blu-ray, Drama")

    def test_apply_is_idempotent(self):
        self.assertEqual(apply_tag_change("drama, new arrival", {"new arrival"}, ()), "drama, new arrival")

    def test_apply_to_empty_tags(self):
        self.assertEqual(apply_tag_change("", {"community pick", "new arrival"}, ()), "community pick, new arrival")


class TestProduct(unittest.TestCase):
    def test_is_rental_is_case_insensitive(self):
        self.assertTrue(product("p", (), tags=("rental",)).is_rental)
        self.assertFalse(product("p", (), tags=("Floor Sale",)).is_rental)


class TestEditWithRetries(unittest.TestCase):
    def change(self):
        return LibibChange("a", "T", "111", frozenset({"new arrival"}), frozenset())

    def test_retries_errors_then_returns_success(self):
        from catalog.libib.tag_editor import edit_with_retries
        answers = iter([("error", "slow"), RuntimeError("boom"), ("updated", "ok")])
        pauses = []

        def edit(page, barcode, add, remove):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        self.assertEqual(edit_with_retries(edit, None, self.change(), pause=lambda: pauses.append(1)), ("updated", "ok"))
        self.assertEqual(len(pauses), 2)

    def test_gives_up_after_the_last_attempt(self):
        from catalog.libib.tag_editor import edit_with_retries
        result = edit_with_retries(lambda *a: ("error", "slow"), None, self.change(), pause=lambda: None, attempts=2)
        self.assertEqual(result, ("error", "slow"))


if __name__ == "__main__":
    unittest.main()
