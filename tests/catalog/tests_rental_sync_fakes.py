"""Fakes for the rental sync tests: a GraphQL executor and a RentalShop."""

ONLINE_STORE_ID = "gid://shopify/Publication/1"
POS_ID = "gid://shopify/Publication/2"


class FakeExecute:
    """execute(store, query_obj, variables) answering by the first matching
    substring of the query text. A payload may be a callable(variables)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, store, query, variables):
        text = query.read_text()
        self.calls.append((text, dict(variables)))
        for needle, payload in self.responses:
            if needle in text:
                return payload(variables) if callable(payload) else payload
        raise AssertionError(f"unexpected query: {text[:120]}")


class FakeShop:
    """Duck-types RentalShop for create.py and web.py tests."""

    store = "lms-sandbox-lutsfahz.myshopify.com"

    def __init__(self, barcodes=(), handles=(), set_error=None, publish_error=None, media=("READY",),
                 extra_channels=(), lose=(), location_error=None, barcodes_error=None, last=None):
        self.barcodes = {b: f"existing-{b}" for b in barcodes}
        self.handles = set(handles)
        self.set_error, self.publish_error = set_error, publish_error
        self.media = list(media)
        self.extra_channels = list(extra_channels)
        self.lose = set(lose)
        self.location_error, self.barcodes_error = location_error, barcodes_error
        self.last = last
        self.created, self.published, self.saved = [], [], []
        self.nodes = {}
        self.reads = 0

    def barcode_owner(self, barcode):
        return self.barcodes.get(barcode)

    def handle_taken(self, handle):
        return handle in self.handles

    def location_id(self):
        if self.location_error:
            raise self.location_error
        return "gid://shopify/Location/1"

    def genre_ids(self, handles):
        return [f"gid://shopify/Metaobject/{h}" for h in handles]

    def online_store_publication_id(self):
        return ONLINE_STORE_ID

    def product_set(self, product_input):
        if self.set_error:
            raise self.set_error
        self.created.append(product_input)
        pid = f"gid://shopify/Product/{100 + len(self.created)}"
        self.barcodes[product_input["variants"][0]["barcode"]] = product_input["handle"]
        self.handles.add(product_input["handle"])
        self.nodes[pid] = product_input
        return {"id": pid, "handle": product_input["handle"]}

    def publish(self, product_id, publication_id):
        if self.publish_error:
            raise self.publish_error
        self.published.append((product_id, publication_id))

    def read_back(self, product_id):
        self.reads += 1
        p = self.nodes[product_id]
        v = p["variants"][0]
        status = self.media[min(self.reads - 1, len(self.media) - 1)]
        pubs = [{"publication": {"id": pub, "name": "Online Store"}} for prod, pub in self.published if prod == product_id]
        pubs += [{"publication": {"id": POS_ID, "name": name}} for name in self.extra_channels]
        return {
            "id": product_id,
            "handle": p["handle"],
            "tags": [] if "tags" in self.lose else list(p["tags"]),
            "variants": {"nodes": [{
                "barcode": v["barcode"],
                "taxable": True if "taxable" in self.lose else v["taxable"],
                "inventoryQuantity": 0 if "quantity" in self.lose else v["inventoryQuantities"][0]["quantity"],
                "inventoryItem": {"tracked": v["inventoryItem"]["tracked"]},
            }]},
            "resourcePublicationsV2": {"nodes": pubs},
            "media": {"nodes": [{"status": status}] if p.get("files") else []},
        }

    def new_flow_barcodes(self):
        if self.barcodes_error:
            raise self.barcodes_error
        return set(self.barcodes)

    def last_run(self):
        return self.last

    def save_last_run(self, summary):
        self.saved.append(summary)
        self.last = summary
