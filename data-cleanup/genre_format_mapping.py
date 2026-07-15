"""Canonical Vendor/Genre value normalization for the movie catalogue reformat.

Source of truth: /Users/liamparis/Desktop/format-mapping.md, derived from
every distinct Vendor and Option1 Value seen in current-movies-export.csv,
with one correction: Foreign maps to "foreign" (the real metaobject handle
on the store), not the file's "foreignz".
"""

# Raw Vendor string -> product.metafields.shopify.media-format metaobject handle,
# or None if the vendor value carries no format information.
VENDOR_TO_FORMAT = {
    "VHS": "vhs",
    "DVD": "dvd",
    "Blu-Ray": "blu-ray",
    "BLU-RAY": "blu-ray",
    "Unknown": None,
    "Little Movie Store": None,
    "4K": "4-k",
    "4k": "4-k",
    "Unknown Brand": None,
    "Dvd": "dvd",
    "Walt Disney": None,
    "The Franchise Collection": None,
    "Walt Disney Pictures": None,
    "Blockbuster": None,
    "Basquiat": None,
    "Disney": None,
    "Arrow Video": None,
    "Alfred Hitchcock": None,
    "Universal Pictures": None,
    "Supercycle": None,
}

# Raw Option1 Value string (the fake "Genre" variant option value) ->
# (genre metaobject handle or None, format metaobject handle override or None).
# The format override is only set for compound values that mention "4K"/"4k";
# it takes precedence over VENDOR_TO_FORMAT when resolving format.
GENRE_VALUE_MAP = {
    "Comedy": ("comedy", None),
    "Action": ("action", None),
    "Drama": ("drama", None),
    "Kids & Family": ("kids-family", None),
    "Sci-Fi": ("sci-fi", None),
    "Thriller": ("thriller", None),
    "Horror": ("horror", None),
    "Romantic Comedy": ("romantic-comedy", None),
    "Musical": ("musical", None),
    "Fantasy": ("fantasy", None),
    "Documentary": ("documentary", None),
    "Foreign": ("foreign", None),
    "4K, Action": ("action", "4-k"),
    "Special Interest": (None, None),
    "4K, Kids & Family": ("kids-family", "4-k"),
    "Comedy, Criterion Collection": ("comedy", None),
    "Kids & Family, 4K": ("kids-family", "4-k"),
    "Romatic Comedy": ("romantic-comedy", None),
    "4K, Drama": ("drama", "4-k"),
    "4K, Sci-Fi": ("sci-fi", "4-k"),
    "4K, Fantasy": ("fantasy", "4-k"),
    "Muscal": ("musical", None),
    "SciFi": ("sci-fi", None),
    "4k, Fantasy": ("fantasy", "4-k"),
    "A24, Sci-Fi": ("sci-fi", None),
    "Action, 4K": ("action", "4-k"),
    "Horror, 4K": ("horror", "4-k"),
    "Kids": ("kids-family", None),
}


def resolve_format(vendor: str, option1_value: str) -> str | None:
    """Return the media-format metaobject handle for a product, or None."""
    mapping = GENRE_VALUE_MAP.get(option1_value)
    if mapping is not None:
        _, format_override = mapping
        if format_override is not None:
            return format_override
    return VENDOR_TO_FORMAT.get(vendor)


def resolve_genre(option1_value: str) -> str | None:
    """Return the genre metaobject handle for a product, or None."""
    mapping = GENRE_VALUE_MAP.get(option1_value)
    if mapping is None:
        return None
    genre_handle, _ = mapping
    return genre_handle
