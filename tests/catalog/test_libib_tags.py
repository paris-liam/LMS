import unittest

from catalog.libib.tags import (
    LibibChange, Product, ShopifyChange, ShopifyState, Unmatched, apply_tag_change, libib_changes, shopify_changes,
)


def item(id, barcode, tags, title="T"):
    return {"id": id, "title": title, "barcode": barcode, "call_number": "", "tags": tags,
            "description": "", "collection": "Rental Library", "created": ""}


def product(id, barcodes, tags=("Rental",), title="T"):
    return Product(id, title, tuple(tags), tuple(barcodes))


class TestLibibChanges(unittest.TestCase):
    def test_new_arrival_added_to_matched_item(self):
        changes, unmatched = libib_changes([item("a", "111", "blu-ray, drama")],
                                           ShopifyState((product("p1", ("111",)),), (), ()))
        self.assertEqual(changes, [LibibChange("a", "T", "111", frozenset({"new arrival"}), frozenset())])
        self.assertEqual(unmatched, [])

    def test_tag_removed_when_shopify_no_longer_has_it(self):
        changes, _ = libib_changes([item("a", "111", "drama, New Arrival")], ShopifyState((), (), ()))
        self.assertEqual(changes[0].remove, frozenset({"new arrival"}))
        self.assertEqual(changes[0].add, frozenset())

    def test_already_correct_item_has_no_change(self):
        changes, _ = libib_changes([item("a", "111", "drama, new arrival")],
                                   ShopifyState((product("p1", ("111",)),), (), ()))
        self.assertEqual(changes, [])

    def test_only_the_picked_copy_is_tagged(self):
        items = [item("a", "111", "vhs", "Legend"), item("b", "222", "vhs", "Legend")]
        changes, _ = libib_changes(items, ShopifyState((), (product("p1", ("111",)),), ()))
        self.assertEqual([c.item_id for c in changes], ["a"])
        self.assertEqual(changes[0].add, frozenset({"community pick"}))

    def test_non_rental_pick_has_no_libib_change_and_is_not_unmatched(self):
        state = ShopifyState((), (product("p1", ("999",), tags=("Floor Sale",)),), ())
        self.assertEqual(libib_changes([], state), ([], []))

    def test_rental_with_no_libib_item_is_unmatched(self):
        _, unmatched = libib_changes([], ShopifyState((product("p1", ("111",), title="Bottoms"),), (), ()))
        self.assertEqual(unmatched, [Unmatched("Bottoms", "no Libib item has this barcode")])

    def test_product_without_barcode_is_unmatched(self):
        _, unmatched = libib_changes([], ShopifyState((product("p1", (), title="X"),), (), ()))
        self.assertEqual(unmatched, [Unmatched("X", "no barcode in Shopify")])

    def test_ambiguous_barcode_touches_neither_item(self):
        items = [item("a", "111", "new arrival"), item("b", "111", "vhs")]
        changes, unmatched = libib_changes(items, ShopifyState((), (), ()))
        self.assertEqual(changes, [])
        self.assertEqual([u.reason for u in unmatched], ["barcode is on 2 Libib items"])

    def test_ambiguous_barcode_wanted_by_shopify_is_reported_once(self):
        items = [item("a", "111", "vhs"), item("b", "111", "vhs")]
        changes, unmatched = libib_changes(items, ShopifyState((product("p1", ("111",)),), (), ()))
        self.assertEqual(changes, [])
        self.assertEqual([u.reason for u in unmatched], ["barcode is on 2 Libib items"])

    def test_both_tags_on_one_item(self):
        p = product("p1", ("111",))
        changes, _ = libib_changes([item("a", "111", "vhs")], ShopifyState((p,), (p,), ()))
        self.assertEqual(changes[0].add, frozenset({"new arrival", "community pick"}))

    def test_changes_are_sorted_by_title_then_item_id(self):
        items = [item("b", "2", "", "Zed"), item("a", "1", "", "Alpha")]
        state = ShopifyState((product("p1", ("2",)), product("p2", ("1",))), (), ())
        self.assertEqual([c.item_id for c in libib_changes(items, state)[0]], ["a", "b"])


class TestShopifyChanges(unittest.TestCase):
    def test_shopify_changes_add_and_remove(self):
        state = ShopifyState((), (product("p1", ("1",), title="A"),),
                             (product("p2", ("2",), tags=("Rental", "community-pick"), title="B"),))
        self.assertEqual(shopify_changes(state),
                         [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "remove")])

    def test_shopify_pick_already_tagged_is_unchanged(self):
        p = product("p1", ("1",), tags=("Rental", "community-pick"))
        self.assertEqual(shopify_changes(ShopifyState((), (p,), (p,))), [])

    def test_non_rental_pick_still_gets_shopify_tag(self):
        p = product("p1", (), tags=("Floor Sale",), title="F")
        self.assertEqual(shopify_changes(ShopifyState((), (p,), ())), [ShopifyChange("p1", "F", "add")])

    def test_product_picked_twice_is_one_change(self):
        p = product("p1", ("1",), title="A")
        self.assertEqual(shopify_changes(ShopifyState((), (p, p), ())), [ShopifyChange("p1", "A", "add")])


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


if __name__ == "__main__":
    unittest.main()
