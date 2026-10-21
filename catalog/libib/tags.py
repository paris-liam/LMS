"""`libib tags` — which tags to add and remove, worked out from Shopify.

Spec: docs/superpowers/specs/2026-10-20-libib-tag-sync-design.md.

- New arrivals: the newest `count` titles (a title = movie + format, its age
  = its first copy's Shopify createdAt) among rentals that are in Libib. All
  their copies carry `new-arrival` in Shopify and `new arrival` in Libib;
  every other product and item loses it. Settings: tag_settings.json.
- Community Picks: a Libib item carries `community pick` while its Shopify
  product is the product of an Active Community Pick entry (only that copy);
  the same entries set the Shopify `community-pick` tag.

Matching is one Shopify variant barcode to one Libib copy barcode. Pure: no
Shopify or Libib calls here.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from catalog.duplicates.match import normalize_title, product_format, title_year
from catalog.libib.fields import normalized_tag_set
from catalog.libib.tag_settings import TagSettings

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
    vendor: str = ""
    created_at: str = ""   # Shopify createdAt, ISO 8601

    @property
    def is_rental(self) -> bool:
        return any(t.strip().lower() == "rental" for t in self.tags)


@dataclass(frozen=True)
class ShopifyState:
    rentals: tuple[Product, ...]              # every product tagged Rental
    picked: tuple[Product, ...]               # products of Active Community Pick entries
    tagged_picks: tuple[Product, ...]         # products tagged community-pick
    tagged_new_arrivals: tuple[Product, ...] = ()   # products tagged new-arrival (any type)


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
    tag: str
    action: str  # "add" | "remove"


@dataclass(frozen=True)
class Unmatched:
    title: str
    reason: str


@dataclass(frozen=True)
class TagPlan:
    libib: list[LibibChange]
    shopify: list[ShopifyChange]
    unmatched: list[Unmatched]
    new_arrival_titles: int


def title_key(p: Product) -> tuple[str, str, str]:
    """Movie + format: edition words ignored, the year kept (Halloween 1978 ≠ 2018)."""
    fmt = product_format({"Vendor": p.vendor}) or p.vendor.strip().lower()
    return normalize_title(p.title), title_year(p.title), fmt


def _created(p: Product) -> datetime:
    return datetime.fromisoformat(p.created_at.replace("Z", "+00:00"))


class _Libib:
    """Libib items indexed by copy barcode; a barcode on several items excludes them all."""

    def __init__(self, items: list[dict]):
        self.by_id = {it["id"]: it for it in items}
        by_barcode: dict[str, set[str]] = defaultdict(set)
        for it in items:
            if it["barcode"]:
                by_barcode[it["barcode"]].add(it["id"])
        self.by_barcode = by_barcode
        self.excluded: set[str] = set()
        self.unmatched: list[Unmatched] = []
        for ids in (ids for _, ids in sorted(by_barcode.items()) if len(ids) > 1):
            self.excluded |= ids
            self.unmatched.append(Unmatched(self.by_id[sorted(ids)[0]]["title"], f"barcode is on {len(ids)} Libib items"))

    def ids_for(self, p: Product) -> set[str]:
        return set().union(*(self.by_barcode.get(b, set()) for b in p.barcodes))

    def item_for(self, p: Product) -> str | None:
        """The one Libib item this product is, or None (not in Libib, or ambiguous)."""
        ids = self.ids_for(p)
        return next(iter(ids)) if len(ids) == 1 and not ids & self.excluded else None


def _newest_titles(eligible: list[Product], settings: TagSettings, now: datetime) -> tuple[list[Product], int]:
    groups: dict[tuple, list[Product]] = defaultdict(list)
    for p in eligible:
        groups[title_key(p)].append(p)
    arrivals = {key: min(_created(p) for p in members) for key, members in groups.items()}
    keys = list(groups)
    if settings.new_arrivals_max_age_days is not None:
        cutoff = now - timedelta(days=settings.new_arrivals_max_age_days)
        keys = [k for k in keys if arrivals[k] >= cutoff]
    keys.sort(key=lambda k: (-arrivals[k].timestamp(), k))
    chosen = keys[:settings.new_arrivals_count]
    return [p for k in chosen for p in groups[k]], len(chosen)


def _shopify_tag(tag: str, wanted: dict[str, Product], tagged: Iterable[Product]) -> list[ShopifyChange]:
    changes = {pid: ShopifyChange(pid, p.title, tag, "add") for pid, p in wanted.items() if tag not in p.tags}
    for p in tagged:
        if p.id not in wanted and tag in p.tags:
            changes[p.id] = ShopifyChange(p.id, p.title, tag, "remove")
    return list(changes.values())


def plan_tags(items: list[dict], state: ShopifyState, settings: TagSettings, now: datetime) -> TagPlan:
    libib = _Libib(items)
    unmatched = list(libib.unmatched)
    desired: dict[str, set[str]] = defaultdict(set)

    eligible = [p for p in state.rentals if p.is_rental and libib.item_for(p)]
    arrivals, title_count = _newest_titles(eligible, settings, now)
    for p in arrivals:
        desired[libib.item_for(p)].add(LIBIB_NEW_ARRIVAL)

    for p in (p for p in state.picked if p.is_rental):
        if not p.barcodes:
            unmatched.append(Unmatched(p.title, "no barcode in Shopify"))
            continue
        if not libib.ids_for(p):
            unmatched.append(Unmatched(p.title, "no Libib item has this barcode"))
        item_id = libib.item_for(p)
        if item_id:
            desired[item_id].add(LIBIB_COMMUNITY_PICK)

    libib_changes = []
    for item_id, it in libib.by_id.items():
        if item_id in libib.excluded:
            continue
        current = normalized_tag_set(it["tags"]) & MANAGED_LIBIB_TAGS
        wanted = desired.get(item_id, set())
        add, remove = frozenset(wanted - current), frozenset(current - wanted)
        if add or remove:
            libib_changes.append(LibibChange(item_id, it["title"], it["barcode"], add, remove))
    libib_changes.sort(key=lambda c: (c.title.lower(), c.item_id))

    shopify_changes = (
        _shopify_tag(SHOPIFY_NEW_ARRIVAL, {p.id: p for p in arrivals}, [*state.tagged_new_arrivals, *state.rentals])
        + _shopify_tag(SHOPIFY_COMMUNITY_PICK, {p.id: p for p in state.picked}, state.tagged_picks))
    shopify_changes.sort(key=lambda c: (c.title.lower(), c.product_id, c.tag))
    return TagPlan(libib_changes, shopify_changes, unmatched, title_count)


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
