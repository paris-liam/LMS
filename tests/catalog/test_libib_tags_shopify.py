import unittest

from catalog.errors import InputShapeError
from catalog.libib.tags import ShopifyChange
from catalog.libib.links import JoinIdChange
from catalog.libib.tags_shopify import read_state, write_changes, write_join_ids


def node(id, tags=("Rental",), barcodes=("111",), title=None, vendor="VHS", created="2026-10-01T00:00:00Z"):
    return {"id": id, "title": title or id, "tags": list(tags), "vendor": vendor, "createdAt": created,
            "variants": {"nodes": [{"barcode": b} for b in barcodes]}}


def pick(status, product):
    return {"capabilities": {"publishable": {"status": status} if status else None},
            "field": {"reference": product} if product is not None else None}


def page(nodes, next_cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor}}


class FakeGql:
    """Answers the reads by query text and search string; records mutations."""

    def __init__(self, rentals=None, new_arrivals=None, tagged=None, picks=None, user_error_for=None,
                 rental_pages=None):
        if rentals is None and rental_pages is None:
            rentals = [node("r0")]
        self.products = {"tag:Rental": rental_pages or [page(rentals)], "tag:new-arrival": [page(new_arrivals or [])],
                         "tag:community-pick": [page(tagged or [])]}
        self.picks = [page(picks or [])]
        self.user_error_for = user_error_for
        self.mutations = []

    def __call__(self, query, **variables):
        if query.lstrip().startswith("mutation"):
            root = "tagsAdd" if "tagsAdd" in query else "tagsRemove"
            self.mutations.append((root, variables["id"], variables["tags"]))
            errors = [{"message": "nope"}] if variables["id"] == self.user_error_for else []
            return {root: {"userErrors": errors}}
        index = int(variables.get("after") or 0)
        if "metaobjects" in query:
            return {"metaobjects": self.picks[index]}
        return {"products": self.products[variables["q"]][index]}


class TestReadState(unittest.TestCase):
    def test_reads_rentals_with_exact_tag_only(self):
        state = read_state(FakeGql(rentals=[node("p1", tags=["rental", "VHS"]), node("p2", tags=["Rentals"])]))
        self.assertEqual([p.id for p in state.rentals], ["p1"])

    def test_reads_vendor_and_created_at(self):
        p = read_state(FakeGql(rentals=[node("p1", vendor="Blu-Ray", created="2026-10-19T08:00:00Z")])).rentals[0]
        self.assertEqual((p.vendor, p.created_at, p.barcodes), ("Blu-Ray", "2026-10-19T08:00:00Z", ("111",)))

    def test_zero_rentals_raises(self):
        with self.assertRaises(InputShapeError):
            read_state(FakeGql(rentals=[]))

    def test_reads_new_arrivals_with_exact_tag_only(self):
        state = read_state(FakeGql(new_arrivals=[node("p1", tags=["Floor Sale", "new-arrival"]),
                                                 node("p2", tags=["Rental", "new-arrival-old"])]))
        self.assertEqual([p.id for p in state.tagged_new_arrivals], ["p1"])

    def test_blank_barcodes_are_dropped(self):
        state = read_state(FakeGql(rentals=[node("p1", barcodes=["", None, " 222 "])]))
        self.assertEqual(state.rentals[0].barcodes, ("222",))

    def test_paginates_products(self):
        state = read_state(FakeGql(rental_pages=[page([node("p1")], next_cursor="1"), page([node("p2")])]))
        self.assertEqual([p.id for p in state.rentals], ["p1", "p2"])

    def test_reads_tagged_picks(self):
        state = read_state(FakeGql(tagged=[node("p9", tags=["community-pick"])]))
        self.assertEqual([p.id for p in state.tagged_picks], ["p9"])

    def test_only_active_picks_with_a_product_count(self):
        state = read_state(FakeGql(picks=[pick("ACTIVE", node("p1")), pick("DRAFT", node("p2")),
                                          pick("ACTIVE", None)]))
        self.assertEqual([p.id for p in state.picked], ["p1"])

    def test_pick_without_publishable_capability_counts_as_active(self):
        state = read_state(FakeGql(picks=[pick(None, node("p1"))]))
        self.assertEqual([p.id for p in state.picked], ["p1"])

    def test_graphql_error_propagates(self):
        def failing(query, **variables):
            raise RuntimeError("[{'message': 'Throttled'}]")
        with self.assertRaises(RuntimeError):
            read_state(failing)


class TestWriteChanges(unittest.TestCase):
    def test_writes_change_tag(self):
        gql = FakeGql()
        write_changes(gql, [ShopifyChange("p1", "A", "new-arrival", "add"),
                            ShopifyChange("p2", "B", "community-pick", "remove")])
        self.assertEqual(gql.mutations, [("tagsAdd", "p1", ["new-arrival"]), ("tagsRemove", "p2", ["community-pick"])])

    def test_write_records_user_errors_and_continues(self):
        results = write_changes(FakeGql(user_error_for="p1"),
                                [ShopifyChange("p1", "A", "new-arrival", "add"),
                                 ShopifyChange("p2", "B", "new-arrival", "add")])
        self.assertEqual([r["status"] for r in results], ["error", "updated"])
        self.assertEqual(results[0]["title"], "A")
        self.assertIn("nope", results[0]["message"])

    def test_write_records_exceptions_and_continues(self):
        def boom(query, **variables):
            raise RuntimeError("HTTP 500")
        self.assertEqual(write_changes(boom, [ShopifyChange("p1", "A", "new-arrival", "add")])[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()


class TestJoinIds(unittest.TestCase):
    def test_join_id_metafield_is_parsed(self):
        values = [{"value": "169565504"}, None, {"value": ""}, {"value": "abc"}]
        rentals = [node(f"p{i}") | {"libibJoinId": v} for i, v in enumerate(values)]
        state = read_state(FakeGql(rentals=rentals))
        self.assertEqual([p.libib_join_id for p in state.rentals], [169565504, None, None, None])

    def test_write_join_ids_set_and_clear(self):
        calls = []

        def gql(query, **variables):
            root = "metafieldsSet" if "metafieldsSet" in query else "metafieldsDelete"
            calls.append((root, variables["metafields"]))
            return {root: {"userErrors": []}}

        results = write_join_ids(gql, [JoinIdChange("gid://p/1", "A", "i1", None, 7),
                                       JoinIdChange("gid://p/2", "B", "i2", 9, None)])
        self.assertEqual([c[0] for c in calls], ["metafieldsSet", "metafieldsDelete"])
        self.assertEqual(calls[0][1], [{"ownerId": "gid://p/1", "namespace": "custom", "key": "libib_join_id",
                                        "type": "number_integer", "value": "7"}])
        self.assertEqual(calls[1][1], [{"ownerId": "gid://p/2", "namespace": "custom", "key": "libib_join_id"}])
        self.assertEqual([(r["action"], r["status"]) for r in results], [("set", "updated"), ("clear", "updated")])

    def test_write_join_ids_user_error(self):
        def gql(query, **variables):
            return {"metafieldsSet": {"userErrors": [{"message": "nope"}]}}

        [result] = write_join_ids(gql, [JoinIdChange("gid://p/1", "A", "i1", None, 7)])
        self.assertEqual((result["status"], result["message"]), ("error", "nope"))
