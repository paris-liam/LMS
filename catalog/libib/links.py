"""`libib tags` — each homepage movie's public Libib link (its join_id).

Spec: docs/superpowers/specs/2026-10-20-libib-poster-links-design.md.

The homepage's New Arrivals and Community Picks posters open the movie's
item on the public Libib page, `…/u/littlemoviestore?id=<join_id>`. The
join_id isn't in Libib's exports, so the daily job looks it up on the
published site's own search, which matches copy barcodes. That endpoint is
undocumented and may change without notice: a failed lookup keeps the stored
value, and stored values are only cleared when the same run shows the
endpoint works (claudedocs/2026-10-13-libib-item-links-join-id.md).

The barcode is sent to libib.com and nowhere else: it is never printed,
raised or reported (the repo's logs are public).
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Sequence

from catalog.libib.tags import LinkTarget, Unmatched

SEARCH_URL = "https://www.libib.com/u/littlemoviestore/search"
LIBRARY_ID = "2603141"
MAX_CLEARS = 10
LOOKUP_DELAY = 0.5
TIMEOUT_SECONDS = 30
_JOIN_ID = re.compile(r'data-join-id="(\d+)"')


class LookupFailed(Exception):
    pass


@dataclass(frozen=True)
class JoinIdChange:
    product_id: str
    title: str
    item_id: str
    old: int | None
    new: int | None   # None: clear the stored value


def parse_join_ids(payload: dict) -> list[str]:
    # Fixed messages only: the reply is server text and could echo the barcode.
    if payload.get("outcome") != "success":
        raise LookupFailed("search outcome was not success")
    info = payload.get("item-info") or ""
    if not isinstance(info, str):
        raise LookupFailed("search reply has no item list")
    return list(dict.fromkeys(_JOIN_ID.findall(info)))


def lookup_join_ids(barcode: str, urlopen=urllib.request.urlopen) -> list[str]:
    body = urllib.parse.urlencode({"keywords": barcode, "library_id": LIBRARY_ID, "offset": 0, "limit": 50})
    request = urllib.request.Request(SEARCH_URL, data=body.encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise LookupFailed(f"HTTPError {exc.code}") from None
    except Exception as exc:   # URLError, timeouts, dropped connections, bad JSON — the message may echo the request
        raise LookupFailed(type(exc).__name__) from None
    if not isinstance(payload, dict):
        raise LookupFailed("reply is not a JSON object")
    return parse_join_ids(payload)


def plan_join_ids(targets: Sequence[LinkTarget], lookup: Callable[[str], list[str]],
                  sleep=time.sleep) -> tuple[list[JoinIdChange], list[Unmatched]]:
    changes: list[JoinIdChange] = []
    clears: list[JoinIdChange] = []
    warnings: list[Unmatched] = []
    succeeded = False
    for n, target in enumerate(targets):
        if n:
            sleep(LOOKUP_DELAY)
        try:
            ids = lookup(target.barcode)
        except LookupFailed as exc:
            warnings.append(Unmatched(target.title, f"Libib link lookup failed ({exc}); kept as is"))
            continue
        if len(ids) == 1:
            succeeded = True
            new = int(ids[0])
            if new != target.stored:
                changes.append(JoinIdChange(target.product_id, target.title, target.item_id, target.stored, new))
        elif len(ids) > 1:
            warnings.append(Unmatched(target.title, f"public Libib search found {len(ids)} Libib items; kept as is"))
        elif target.stored is not None:
            clears.append(JoinIdChange(target.product_id, target.title, target.item_id, target.stored, None))
        else:
            warnings.append(Unmatched(target.title, "not found on the public Libib page"))

    if clears and not succeeded:
        warnings.append(Unmatched("Libib links", f"{len(clears)} not found, but no lookup succeeded this run "
                                                 "— kept every stored link"))
    elif len(clears) > MAX_CLEARS:
        warnings.append(Unmatched("Libib links", f"{len(clears)} links to clear is over the limit of {MAX_CLEARS} "
                                                 "— kept every stored link"))
    else:
        changes += clears
    return changes, warnings
