"""Handle derivation for new products, mirroring the sheet's LET formula.

Apostrophes are deleted rather than turned into hyphens ("the-monkeys-uncle",
not "the-monkey-s-uncle"). Every other non-alphanumeric run collapses to a
single hyphen, which is why accents drop out ("Amelie" -> "am-lie") exactly
as they do in the sheet. Rare titles like that are corrected by hand.

Only rows that describe a product Shopify does not have yet get a derived
handle. Export rows keep theirs verbatim.
"""

import re

APOSTROPHES = re.compile(r"['']")


def slugify(text: str) -> str:
    """Lowercase, delete apostrophes, collapse everything else to hyphens."""
    lowered = APOSTROPHES.sub("", (text or "").strip().lower())
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    return hyphenated.strip("-")


def derive_handle(title: str, media_format: str, product_type: str) -> str:
    """title + format + type -> the unsuffixed base handle."""
    return f"{slugify(title)}-{slugify(media_format)}-{slugify(product_type)}"


class HandleAllocator:
    """Hands out unique handles within a single run, suffixing repeats -2, -3.

    All reserve() calls for a batch must happen before any allocate() call.
    reserve() only adds to the used-handles set; it never checks whether a
    handle was already issued by allocate(), so a reserve() called after an
    allocate() that happened to produce the same handle silently no-ops —
    the earlier allocation keeps the handle and the collision goes
    undetected. normalize.py satisfies this today by reserving every
    hand-typed Handle up front, before the loop that calls allocate().
    """

    def __init__(self):
        self._used: set[str] = set()

    def reserve(self, handle: str) -> None:
        """Mark a handle as taken without allocating it (hand-typed overrides)."""
        if handle:
            self._used.add(handle)

    def allocate(self, base: str) -> str:
        """Return base, or base-2 / base-3 / ... if base is already taken."""
        if base not in self._used:
            self._used.add(base)
            return base
        index = 2
        while f"{base}-{index}" in self._used:
            index += 1
        handle = f"{base}-{index}"
        self._used.add(handle)
        return handle
