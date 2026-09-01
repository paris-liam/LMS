"""Canonical vocabulary for the movie catalogue: genres, formats and types.

Genre labels are the 13 shelf genres; their values are the metaobject
handles behind product.metafields.shopify.genre. Formats are the
values allowed in product.vendor (media format lives in Vendor, not in
shopify.media-format — see claudedocs/2026-08-07-product-data-model-audit.md).

The alias tables hold every misspelling actually observed in
products_export_1.csv. Anything outside them resolves to None and is
flagged rather than guessed.
"""

import re

GENRES = {
    "Comedy": "comedy",
    "Action": "action",
    "Drama": "drama",
    "Kids & Family": "kids-family",
    "Sci-Fi": "sci-fi",
    "Thriller": "thriller",
    "Horror": "horror",
    "Romantic Comedy": "romantic-comedy",
    "Musical": "musical",
    "Fantasy": "fantasy",
    "Documentary": "documentary",
    "Foreign": "foreign",
    "Holiday": "holiday",
}

FORMATS = ["VHS", "DVD", "Blu-Ray", "4K", "Laserdisc", "Betamax"]

TYPES = ["Rental", "Floor Sale"]

# Observed misspellings -> canonical label, keyed by normalize_key().
GENRE_ALIASES = {
    "horor": "Horror",
    "sc fi": "Sci-Fi",
    "scifi": "Sci-Fi",
    "kids famiy": "Kids & Family",
    "kids": "Kids & Family",
    "romatic comedy": "Romantic Comedy",
    "muscal": "Musical",
    "dcoumentary": "Documentary",
    "thriler": "Thriller",
}

FORMAT_ALIASES = {
    "bluray": "Blu-Ray",
    "laser disc": "Laserdisc",
    "laser": "Laserdisc",
    "ld": "Laserdisc",
    "beta": "Betamax",
}

TYPE_ALIASES = {
    "floorsale": "Floor Sale",
    "foor sale": "Floor Sale",
}


def normalize_key(value: str) -> str:
    """Lowercase and collapse every run of non-alphanumerics to one space."""
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _resolve(value: str, canonical: list[str], aliases: dict[str, str]) -> str | None:
    key = normalize_key(value)
    if not key:
        return None
    for label in canonical:
        if normalize_key(label) == key:
            return label
    return aliases.get(key)


def canonical_genre(value: str) -> str | None:
    """Return the canonical genre label for a raw value, or None."""
    return _resolve(value, list(GENRES), GENRE_ALIASES)


def canonical_format(value: str) -> str | None:
    """Return the canonical format for a raw Vendor or tag value, or None."""
    return _resolve(value, FORMATS, FORMAT_ALIASES)


def canonical_type(value: str) -> str | None:
    """Return "Rental" or "Floor Sale" for a raw tag value, or None."""
    return _resolve(value, TYPES, TYPE_ALIASES)


def genre_handle(label: str) -> str | None:
    """Return the shopify.genre metaobject handle for a canonical label."""
    return GENRES.get(label)
