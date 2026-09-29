"""A fake Shopify store for writer/apply tests (shaped like ApiStore.get())."""

import copy

from catalog.core.columns import GENRE_METAFIELD


class FakeStore:
    """In-memory products shaped like ApiStore.get(); write() applies values."""

    def __init__(self, products, lose=(), fail=()):
        self.products = products
        self.lose = set(lose)      # fields a write silently doesn't persist
        self.fail = set(fail)      # handles whose write raises
        self.writes = []

    def get(self, handle, wait_for_media=False):
        return copy.deepcopy(self.products.get(handle))

    def write(self, product, values):
        handle = next(h for h, p in self.products.items() if p["id"] == product["id"])
        if handle in self.fail:
            raise RuntimeError("boom")
        self.writes.append((handle, dict(values)))
        stored = self.products[handle]
        for field, value in values.items():
            if field in self.lose:
                continue
            if field == "Image Src":
                stored["images"].insert(0, {"id": "m-new", "src": value, "alt": values.get("Image Alt Text", ""),
                                            "ready": True})
            elif field == "Image Alt Text":
                if stored["images"]:
                    stored["images"][0]["alt"] = value
            else:
                stored["fields"][field] = value


def product(pid, **fields):
    base = {"Vendor": "VHS", "Body (HTML)": "", "Tags": "Rental, VHS", "Product Category": "",
            GENRE_METAFIELD: "", "Option1 Name": "Genre", "Option1 Value": "Drama", "Variant Price": "0.00"}
    base.update(fields)
    return {"id": pid, "option": None, "variant_id": "v", "images": [], "fields": base}
