"""Write catalogue changes straight to Shopify through the Admin API, instead
of narrow import CSVs the user imports by hand.

Input is the same list of Change(handle, field, before, after) that `apply`
builds for its CSVs. For each product:

1. read the product as it is now; a field whose current value no longer
   equals the `before` the plan was built from is SKIPPED (someone changed it
   since the audit — never overwrite that with a stale plan);
2. write the remaining fields;
3. read the product again and check every written field landed.

Every change ends as written / skipped / failed in the returned results; the
caller reports them all. Store access goes through a small interface (a real
Admin API one here, a fake one in the tests).
"""

import json
import time
from dataclasses import dataclass

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.text import strip_html

SUPPORTED_FIELDS = (
    "Body (HTML)", "Vendor", "Tags", "Product Category", GENRE_METAFIELD,
    "Option1 Name", "Option1 Value", "Variant Price", "Image Src", "Image Alt Text",
)
REPORT_COLUMNS = ["handle", "field", "status", "message"]


@dataclass
class Result:
    handle: str
    field: str
    status: str   # written / skipped / failed
    message: str = ""


def _tags(value: str) -> list[str]:
    return sorted({t.strip() for t in (value or "").split(",") if t.strip()}, key=str.lower)


def _genres(value: str) -> list[str]:
    return [g.strip() for g in (value or "").split(";") if g.strip()]


def _same(field: str, a: str, b: str) -> bool:
    """Compare a field's values the way Shopify stores them."""
    a, b = a or "", b or ""
    if field == "Tags":
        return [t.lower() for t in _tags(a)] == [t.lower() for t in _tags(b)]
    if field == GENRE_METAFIELD:
        return _genres(a) == _genres(b)
    if field == "Body (HTML)":
        return " ".join(strip_html(a).split()) == " ".join(strip_html(b).split())
    if field == "Variant Price":
        try:
            return float(a or 0) == float(b or 0)
        except ValueError:
            return a.strip() == b.strip()
    return a.strip() == b.strip()


def current_value(product: dict, field: str) -> str:
    """The product's value for a snapshot-style field, from Store.get()."""
    if field == "Image Src":
        return product["images"][0]["src"] if product["images"] else ""
    if field == "Image Alt Text":
        return product["images"][0]["alt"] if product["images"] else ""
    return product["fields"].get(field, "")


def write_changes(changes, store, log_fn=lambda line: None) -> list[Result]:
    unsupported = sorted({c.field for c in changes} - set(SUPPORTED_FIELDS))
    if unsupported:
        raise ValueError(f"no Admin API writer for field(s): {', '.join(unsupported)}")
    by_handle: dict[str, list] = {}
    for change in changes:
        by_handle.setdefault(change.handle, []).append(change)

    results: list[Result] = []
    for index, (handle, product_changes) in enumerate(by_handle.items(), start=1):
        results += _write_product(handle, product_changes, store)
        done = [r for r in results if r.handle == handle]
        log_fn(f"[{index}/{len(by_handle)}] {handle}: "
               + ", ".join(f"{r.field} {r.status}" + (f" ({r.message})" if r.message else "") for r in done))
    return results


def _write_product(handle: str, changes: list, store) -> list[Result]:
    try:
        product = store.get(handle)
    except Exception as exc:  # one product's failure must not stop the rest
        return [Result(handle, c.field, "failed", f"{type(exc).__name__}: {exc}") for c in changes]
    if product is None:
        return [Result(handle, c.field, "failed", "product not found in Shopify") for c in changes]

    todo, results = {}, []
    for c in changes:
        now = current_value(product, c.field)
        if _same(c.field, now, c.after):
            results.append(Result(handle, c.field, "skipped", "already set"))
        elif not _same(c.field, now, c.before):
            results.append(Result(handle, c.field, "skipped",
                                  f"changed in Shopify since the audit (now {now[:60]!r}) — not overwritten"))
        else:
            todo[c.field] = c.after
    if not todo:
        return results

    try:
        store.write(product, todo)
    except Exception as exc:  # one product's failure must not stop the rest
        return results + [Result(handle, f, "failed", f"{type(exc).__name__}: {exc}") for f in todo]

    try:
        after = store.get(handle, wait_for_media="Image Src" in todo)
    except Exception as exc:  # written but unverified: report it failed, the next audit re-checks it
        return results + [Result(handle, f, "failed", f"written, but could not read back: {type(exc).__name__}: {exc}")
                          for f in todo]
    for field, value in todo.items():
        now = current_value(after, field) if after else ""
        if field == "Image Src":
            ok = bool(after and after["images"] and after["images"][0].get("ready"))
            results.append(Result(handle, field, "written" if ok else "failed",
                                  "" if ok else "new image did not become the product's ready first image"))
        elif _same(field, now, value):
            results.append(Result(handle, field, "written"))
        else:
            results.append(Result(handle, field, "failed", f"read back {now[:60]!r}"))
    return results


# --- the real store: Admin GraphQL ---------------------------------------

MOVIE_CATEGORY_IDS = {"Media > Videos": "gid://shopify/TaxonomyCategory/me-7"}

PRODUCT_QUERY = """
query($q: String!) {
  products(first: 1, query: $q) { nodes {
    id handle vendor descriptionHtml tags
    category { id fullName }
    options { id name optionValues { id name } }
    variants(first: 1) { nodes { id price } }
    metafield(namespace: "shopify", key: "genre") { value }
    media(first: 20) { nodes { id alt status mediaContentType ... on MediaImage { image { url } } } }
  } }
}"""


class _Query:
    """api.make_executor reads its query from a path; this hands it text."""

    def __init__(self, text: str):
        self._text = text

    def read_text(self, encoding="utf-8") -> str:
        return self._text


class ApiStore:
    def __init__(self, execute, store_domain: str, sleep=time.sleep, media_wait_seconds: int = 60):
        self._execute, self._store, self._sleep = execute, store_domain, sleep
        self._media_wait = media_wait_seconds
        self._genre_ids: dict[str, str] = {}
        self._genre_handles: dict[str, str] = {}

    def gql(self, query: str, **variables) -> dict:
        payload = self._execute(self._store, _Query(query), variables)
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"])[:300])
        return payload["data"]

    def _mutate(self, query: str, root: str, **variables) -> dict:
        data = self.gql(query, **variables)[root]
        errors = data.get("userErrors") or []
        if errors:
            raise RuntimeError("; ".join(e.get("message", "") for e in errors))
        return data

    # reading

    def get(self, handle: str, wait_for_media: bool = False) -> dict | None:
        deadline = self._media_wait if wait_for_media else 0
        while True:
            nodes = self.gql(PRODUCT_QUERY, q=f"handle:{handle}")["products"]["nodes"]
            node = next((n for n in nodes if n["handle"] == handle), None)
            if node is None:
                return None
            product = self._shape(node)
            pending = any(m["status"] in ("UPLOADED", "PROCESSING") for m in node["media"]["nodes"])
            if not pending or deadline <= 0:
                return product
            self._sleep(3)
            deadline -= 3

    def _shape(self, node: dict) -> dict:
        option = next((o for o in node["options"] if o["optionValues"]), None)
        variant = (node["variants"]["nodes"] or [{}])[0]
        genre_ids = json.loads((node.get("metafield") or {}).get("value") or "[]")
        images = [{"id": m["id"], "src": (m.get("image") or {}).get("url") or "", "alt": m.get("alt") or "",
                   "ready": m["status"] == "READY"}
                  for m in node["media"]["nodes"] if m["mediaContentType"] == "IMAGE"]
        return {
            "id": node["id"],
            "option": option,
            "variant_id": variant.get("id"),
            "images": images,
            "fields": {
                "Vendor": node["vendor"],
                "Body (HTML)": node["descriptionHtml"],
                "Tags": ", ".join(node["tags"]),
                "Product Category": (node.get("category") or {}).get("fullName") or "",
                GENRE_METAFIELD: "; ".join(self._genre_handle(g) for g in genre_ids),
                "Option1 Name": option["name"] if option else "",
                "Option1 Value": option["optionValues"][0]["name"] if option else "",
                "Variant Price": variant.get("price") or "",
            },
        }

    def _genre_handle(self, gid: str) -> str:
        if gid not in self._genre_handles:
            node = self.gql("query($id: ID!) { metaobject(id: $id) { handle } }", id=gid)["metaobject"]
            self._genre_handles[gid] = node["handle"] if node else gid
        return self._genre_handles[gid]

    def _genre_id(self, handle: str) -> str:
        if handle not in self._genre_ids:
            node = self.gql('query($h: String!) { metaobjectByHandle(handle: {type: "shopify--genre", handle: $h}) '
                            '{ id } }', h=handle)["metaobjectByHandle"]
            if not node:
                raise RuntimeError(f"no shopify--genre value {handle!r} exists in Shopify")
            self._genre_ids[handle] = node["id"]
        return self._genre_ids[handle]

    # writing

    def write(self, product: dict, values: dict) -> None:
        pid = product["id"]
        update: dict = {"id": pid}
        if "Vendor" in values:
            update["vendor"] = values["Vendor"]
        if "Body (HTML)" in values:
            update["descriptionHtml"] = values["Body (HTML)"]
        if "Tags" in values:
            update["tags"] = _tags(values["Tags"])
        if "Product Category" in values:
            category = MOVIE_CATEGORY_IDS.get(values["Product Category"])
            if not category:
                raise RuntimeError(f"unknown product category {values['Product Category']!r}")
            update["category"] = category
        if len(update) > 1:
            self._mutate("mutation($p: ProductUpdateInput!) { productUpdate(product: $p) { userErrors { message } } }",
                         "productUpdate", p=update)

        if "Option1 Name" in values or "Option1 Value" in values:
            option = product["option"]
            if not option:
                raise RuntimeError("product has no option to rename")
            option_input = {"id": option["id"]}
            if "Option1 Name" in values:
                option_input["name"] = values["Option1 Name"]
            value_updates = ([{"id": option["optionValues"][0]["id"], "name": values["Option1 Value"]}]
                             if "Option1 Value" in values else [])
            self._mutate("mutation($pid: ID!, $o: OptionUpdateInput!, $u: [OptionValueUpdateInput!]) { "
                         "productOptionUpdate(productId: $pid, option: $o, optionValuesToUpdate: $u) "
                         "{ userErrors { message } } }", "productOptionUpdate", pid=pid, o=option_input, u=value_updates)

        if GENRE_METAFIELD in values:
            ids = [self._genre_id(g) for g in _genres(values[GENRE_METAFIELD])]
            self._mutate("mutation($m: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $m) "
                         "{ userErrors { message } } }", "metafieldsSet",
                         m=[{"ownerId": pid, "namespace": "shopify", "key": "genre",
                             "type": "list.metaobject_reference", "value": json.dumps(ids)}])

        if "Variant Price" in values:
            self._mutate("mutation($pid: ID!, $v: [ProductVariantsBulkInput!]!) { "
                         "productVariantsBulkUpdate(productId: $pid, variants: $v) { userErrors { message } } }",
                         "productVariantsBulkUpdate", pid=pid,
                         v=[{"id": product["variant_id"], "price": values["Variant Price"]}])

        if "Image Src" in values:
            alt = values.get("Image Alt Text") or (product["images"][0]["alt"] if product["images"] else "")
            data = self._mutate("mutation($p: ProductUpdateInput!, $m: [CreateMediaInput!]) { "
                                "productUpdate(product: $p, media: $m) { product { media(first: 20) "
                                "{ nodes { id } } } userErrors { message } } }", "productUpdate",
                                p={"id": pid}, m=[{"originalSource": values["Image Src"], "alt": alt,
                                                   "mediaContentType": "IMAGE"}])
            existing = {i["id"] for i in product["images"]}
            new_ids = [n["id"] for n in data["product"]["media"]["nodes"] if n["id"] not in existing]
            if new_ids and existing:  # the new poster becomes the first (featured) image
                self._mutate("mutation($id: ID!, $moves: [MoveInput!]!) { productReorderMedia(id: $id, moves: $moves) "
                             "{ userErrors: mediaUserErrors { message } } }", "productReorderMedia",
                             id=pid, moves=[{"id": new_ids[0], "newPosition": "0"}])
        elif "Image Alt Text" in values:
            if not product["images"]:
                raise RuntimeError("no image to set alt text on")
            self._mutate("mutation($f: [FileUpdateInput!]!) { fileUpdate(files: $f) { userErrors { message } } }",
                         "fileUpdate", f=[{"id": product["images"][0]["id"], "alt": values["Image Alt Text"]}])


def api_store(store_domain: str, client_id: str, client_secret: str) -> ApiStore:
    from catalog.shopify import api
    return ApiStore(api.make_executor(store_domain, api.request_token(store_domain, client_id, client_secret)),
                    store_domain)
