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
                 extra_channels=(), lose=(), location_error=None, barcodes_error=None, last=None,
                 existing_unpublished=False):
        self.barcodes = {}
        self.handles = set(handles)
        self.set_error, self.publish_error = set_error, publish_error
        self.media = list(media)
        self.extra_channels = list(extra_channels)
        self.lose = set(lose)
        self.location_error, self.barcodes_error = location_error, barcodes_error
        self.last = last
        self.created, self.published, self.saved = [], [], []
        self.nodes = {}
        self.products = {}
        self.owner_calls = []
        self.reads = 0
        self.copy_products = {}
        self.writes = []
        for barcode in barcodes:
            pid = f"gid://shopify/Product/existing-{barcode}"
            self.barcodes[barcode] = {"id": pid, "handle": f"existing-{barcode}"}
            self.nodes[pid] = {
                "handle": f"existing-{barcode}", "tags": ["Rental", "Barcode Not Printed"],
                "variants": [{"barcode": barcode, "taxable": False, "inventoryItem": {"tracked": True},
                              "inventoryQuantities": [{"quantity": 1}]}]}
            if not existing_unpublished:
                self.published.append((pid, ONLINE_STORE_ID))

    def barcode_owner(self, barcode):
        self.owner_calls.append(barcode)
        return self.barcodes.get(barcode)

    def product_summary(self, product_id):
        return self.products.get(product_id)

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
        for variant in product_input["variants"]:
            self.barcodes[variant["barcode"]] = {"id": pid, "handle": product_input["handle"]}
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
        status = self.media[min(self.reads - 1, len(self.media) - 1)]
        pubs = [{"publication": {"id": pub, "name": "Online Store"}} for prod, pub in self.published if prod == product_id]
        pubs += [{"publication": {"id": POS_ID, "name": name}} for name in self.extra_channels]
        return {
            "id": product_id,
            "handle": p["handle"],
            "tags": [] if "tags" in self.lose else list(p["tags"]),
            "variants": {"nodes": [{
                "barcode": v["barcode"],
                "taxable": True if self._lost("taxable", v) else v["taxable"],
                "inventoryQuantity": 0 if self._lost("quantity", v) else v["inventoryQuantities"][0]["quantity"],
                "inventoryItem": {"tracked": v["inventoryItem"]["tracked"]},
            } for v in p["variants"]]},
            "resourcePublicationsV2": {"nodes": pubs},
            "media": {"nodes": [{"status": status}] if p.get("files") else []},
        }

    def _lost(self, kind, variant):
        """lose holds kinds that fail on every variant, or (kind, barcode) for one."""
        return kind in self.lose or (kind, variant["barcode"]) in self.lose

    def new_flow_barcodes(self):
        if self.barcodes_error:
            raise self.barcodes_error
        return set(self.barcodes)

    def last_run(self):
        return self.last

    def save_last_run(self, summary):
        self.saved.append(summary)
        self.last = summary

    # add_copy.py

    def add_rental(self, pid, barcodes, vendor="VHS", tags=("Rental", "Barcode Not Printed"), genre="Horror",
                   copies=None, options=None):
        """An existing rental product for add_copy: one variant per barcode,
        `copies` its Copy values (None = no Copy option)."""
        self.copy_products[pid] = {
            "id": pid, "handle": f"rental-{pid.rsplit('/', 1)[-1]}", "title": "Jaws", "vendor": vendor,
            "tags": list(tags),
            "options": options if options is not None else (
                [{"name": "Genre", "values": [genre]}] + ([{"name": "Copy", "values": list(copies)}] if copies else [])),
            "variants": [{
                "id": f"{pid}/v{n}", "barcode": b, "taxable": False, "inventoryQuantity": 1,
                "inventoryItem": {"tracked": True},
                "selectedOptions": [{"name": "Genre", "value": genre}]
                + ([{"name": "Copy", "value": copies[n]}] if copies else [])}
                for n, b in enumerate(barcodes)]}
        for b in barcodes:
            self.barcodes[b] = {"id": pid, "handle": self.copy_products[pid]["handle"]}

    def product_for_copy(self, product_id):
        p = self.copy_products.get(product_id)
        if p is None:
            return None
        variants = [dict(v) for v in p["variants"]
                    if not (self.writes and ("barcode", v["barcode"]) in self.lose)]
        for v in variants:
            if self._lost("taxable", v):
                v["taxable"] = True
        return {**p, "tags": list(p["tags"]), "options": [dict(o, values=list(o["values"])) for o in p["options"]],
                "variants": variants}

    def add_copy_option(self, product_id):
        self.writes.append(("add_copy_option", product_id))
        p = self.copy_products[product_id]
        p["options"].append({"name": "Copy", "values": ["Copy 1"]})
        for v in p["variants"]:
            v["selectedOptions"].append({"name": "Copy", "value": "Copy 1"})

    def add_variant(self, product_id, variant_input):
        self.writes.append(("add_variant", product_id, variant_input))
        p = self.copy_products[product_id]
        values = {o["optionName"]: o["name"] for o in variant_input["optionValues"]}
        for option in p["options"]:
            if values[option["name"]] not in option["values"]:
                option["values"].append(values[option["name"]])
        p["variants"].append({
            "id": f"{product_id}/v{len(p['variants'])}", "barcode": variant_input["barcode"],
            "taxable": variant_input["taxable"],
            "inventoryQuantity": sum(q["availableQuantity"] for q in variant_input["inventoryQuantities"]),
            "inventoryItem": {"tracked": variant_input["inventoryItem"]["tracked"]},
            "selectedOptions": [{"name": k, "value": v} for k, v in values.items()]})
        self.barcodes[variant_input["barcode"]] = {"id": product_id, "handle": p["handle"]}

    def add_tags(self, product_id, tags):
        self.writes.append(("add_tags", product_id, list(tags)))
        p = self.copy_products[product_id]
        p["tags"] += [t for t in tags if t not in p["tags"]]
