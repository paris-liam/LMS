"""`libib tags` — which tags to add and remove, worked out from Shopify.

Shopify is the source of truth (spec 2026-10-20-libib-tag-sync-design):
a Libib item carries `new arrival` while its Shopify product carries
`new-arrival`, and `community pick` while its product is the product of an
Active Community Pick entry; that same entry list sets the Shopify
`community-pick` tag. Matching is one Shopify variant barcode to one Libib
copy barcode — only the matched copy is tagged, never other copies of the
same movie. Pure: no Shopify or Libib calls here.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from catalog.libib.fields import normalized_tag_set

SHOPIFY_NEW_ARRIVAL = "new-arrival"
SHOPIFY_COMMUNITY_PICK = "community-pick"
LIBIB_NEW_ARRIVAL = "new arrival"
LIBIB_COMMUNITY_PICK = "community pick"
MANAGED_LIBIB_TAGS = frozenset({LIBIB_NEW_ARRIVAL, LIBIB_COMMUNITY_PICK})


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    tags: tuple[str, ...]
    barcodes: tuple[str, ...]

    @property
    def is_rental(self) -> bool:
        return any(t.strip().lower() == "rental" for t in self.tags)


@dataclass(frozen=True)
class ShopifyState:
    new_arrivals: tuple[Product, ...]   # products tagged new-arrival
    picked: tuple[Product, ...]         # products of Active Community Pick entries
    tagged_picks: tuple[Product, ...]   # products tagged community-pick


@dataclass(frozen=True)
class LibibChange:
    item_id: str
    title: str
    barcode: str      # used to open the item; never printed (the repo's logs are public)
    add: frozenset[str]
    remove: frozenset[str]


@dataclass(frozen=True)
class ShopifyChange:
    product_id: str
    title: str
    action: str  # "add" | "remove"


@dataclass(frozen=True)
class Unmatched:
    title: str
    reason: str


def libib_changes(items: list[dict], state: ShopifyState) -> tuple[list[LibibChange], list[Unmatched]]:
    by_barcode: dict[str, set[str]] = defaultdict(set)
    by_id: dict[str, dict] = {}
    for it in items:
        by_id[it["id"]] = it
        if it["barcode"]:
            by_barcode[it["barcode"]].add(it["id"])

    # A barcode on several items is ambiguous: leave all of them alone.
    unmatched: list[Unmatched] = []
    excluded: set[str] = set()
    for barcode, ids in sorted(by_barcode.items()):
        if len(ids) > 1:
            excluded |= ids
            first = by_id[sorted(ids)[0]]["title"]
            unmatched.append(Unmatched(first, f"barcode is on {len(ids)} Libib items"))

    desired: dict[str, set[str]] = defaultdict(set)

    def want(products: Iterable[Product], tag: str) -> None:
        for p in products:
            if not p.barcodes:
                unmatched.append(Unmatched(p.title, "no barcode in Shopify"))
                continue
            ids = set().union(*(by_barcode.get(b, set()) for b in p.barcodes))
            if not ids:
                unmatched.append(Unmatched(p.title, "no Libib item has this barcode"))
            for item_id in ids - excluded:
                desired[item_id].add(tag)

    want((p for p in state.new_arrivals if p.is_rental), LIBIB_NEW_ARRIVAL)
    want((p for p in state.picked if p.is_rental), LIBIB_COMMUNITY_PICK)

    changes = []
    for item_id, it in by_id.items():
        if item_id in excluded:
            continue
        current = normalized_tag_set(it["tags"]) & MANAGED_LIBIB_TAGS
        wanted = desired.get(item_id, set())
        add, remove = frozenset(wanted - current), frozenset(current - wanted)
        if add or remove:
            changes.append(LibibChange(item_id, it["title"], it["barcode"], add, remove))
    changes.sort(key=lambda c: (c.title.lower(), c.item_id))
    return changes, unmatched


def shopify_changes(state: ShopifyState) -> list[ShopifyChange]:
    picked = {p.id: p for p in state.picked}
    changes = {pid: ShopifyChange(pid, p.title, "add") for pid, p in picked.items()
               if SHOPIFY_COMMUNITY_PICK not in p.tags}
    for p in state.tagged_picks:
        if p.id not in picked:
            changes[p.id] = ShopifyChange(p.id, p.title, "remove")
    return sorted(changes.values(), key=lambda c: (c.title.lower(), c.product_id))


def apply_tag_change(current: str, add: Iterable[str], remove: Iterable[str]) -> str:
    """The item's tag string with only `add`/`remove` changed: every other tag
    keeps its text and order (Libib lowercases on save anyway)."""
    drop = {t.lower() for t in remove}
    kept, seen = [], set()
    for token in (current or "").split(","):
        token = token.strip()
        if not token or token.lower() in drop or token.lower() in seen:
            continue
        kept.append(token)
        seen.add(token.lower())
    kept += sorted(t for t in add if t.lower() not in seen)
    return ", ".join(kept)
