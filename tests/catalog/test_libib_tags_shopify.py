import unittest

from catalog.libib.tags import ShopifyChange
from catalog.libib.tags_shopify import read_state, write_changes


def node(id, tags=("Rental",), barcodes=("111",), title=None):
    return {"id": id, "title": title or id, "tags": list(tags),
            "variants": {"nodes": [{"barcode": b} for b in barcodes]}}


def pick(status, product):
    return {"capabilities": {"publishable": {"status": status} if status else None},
            "field": {"reference": product} if product is not None else None}


def page(nodes, next_cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor}}


class FakeGql:
    """Answers the three reads by query text; records mutations."""

    def __init__(self, new_arrivals=None, tagged=None, picks=None, user_error_for=None, pages=None):
        self.products = {"tag:new-arrival": [page(new_arrivals or [])], "tag:community-pick": [page(tagged or [])]}
        if pages:
            self.products["tag:new-arrival"] = pages
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
    def test_reads_new_arrivals_with_exact_tag_only(self):
        state = read_state(FakeGql(new_arrivals=[node("p1", tags=["Rental", "new-arrival"], barcodes=["111"]),
                                                 node("p2", tags=["Rental", "new-arrival-old"])]))
        self.assertEqual([p.id for p in state.new_arrivals], ["p1"])
        self.assertEqual(state.new_arrivals[0].barcodes, ("111",))
        self.assertEqual(state.new_arrivals[0].tags, ("Rental", "new-arrival"))

    def test_blank_barcodes_are_dropped(self):
        state = read_state(FakeGql(new_arrivals=[node("p1", tags=["new-arrival"], barcodes=["", None, " 222 "])]))
        self.assertEqual(state.new_arrivals[0].barcodes, ("222",))

    def test_paginates_products(self):
        pages = [page([node("p1", tags=["new-arrival"])], next_cursor="1"),
                 page([node("p2", tags=["new-arrival"])])]
        state = read_state(FakeGql(pages=pages))
        self.assertEqual([p.id for p in state.new_arrivals], ["p1", "p2"])

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
    def test_write_uses_tags_add_and_tags_remove(self):
        gql = FakeGql()
        write_changes(gql, [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "remove")])
        self.assertEqual(gql.mutations,
                         [("tagsAdd", "p1", ["community-pick"]), ("tagsRemove", "p2", ["community-pick"])])

    def test_write_records_user_errors_and_continues(self):
        results = write_changes(FakeGql(user_error_for="p1"),
                                [ShopifyChange("p1", "A", "add"), ShopifyChange("p2", "B", "add")])
        self.assertEqual([r["status"] for r in results], ["error", "updated"])
        self.assertEqual(results[0]["title"], "A")
        self.assertIn("nope", results[0]["message"])

    def test_write_records_exceptions_and_continues(self):
        def boom(query, **variables):
            raise RuntimeError("HTTP 500")
        results = write_changes(boom, [ShopifyChange("p1", "A", "add")])
        self.assertEqual(results[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
