"""Audit rules. Pure: snapshot rows in, Findings out.

check_row covers one product; check_catalogue covers rules that need the
whole catalogue (rental barcode uniqueness). Content (poster/description)
and registry rules live in audit/run.py because they need TMDB and state.
"""

import re
from dataclasses import dataclass

from catalog.audit.findings import AUTO_FIX, MANUAL, Finding
from catalog.audit.resolvers import (
    dedupe, resolve_format, resolve_genres, resolve_price, resolve_type, split_list,
)
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.taxonomy import canonical_format, canonical_genre, canonical_type, genre_handle
from catalog.core.text import strip_html

RENTAL_BARCODE = re.compile(r"^[0-9]{8}$")
_TAG_ALIAS_RULES = (("type-alias", canonical_type), ("format-alias", canonical_format),
                    ("genre-alias", canonical_genre))


@dataclass
class Resolved:
    tags: list[str]
    type: str | None
    type_reason: str | None
    format: str | None
    genres: list[str]


def resolve_row(row: dict) -> Resolved:
    tags = split_list(row.get("Tags", ""))
    option1 = (row.get("Option1 Value") or "").strip()
    product_type, type_reason = resolve_type(tags)
    media_format, _ = resolve_format(row.get("Vendor", ""), option1, tags, "")
    genres, _ = resolve_genres(option1, tags, [])
    return Resolved(tags, product_type, type_reason, media_format, genres)


def respelled_tags(r: Resolved) -> str:
    """The product's own tags, in order, with each misspelt type/format/genre
    tag replaced by its canonical spelling. Nothing is added or dropped (apart
    from exact duplicates the respelling creates), so a tag fix can never
    remove a type or format tag — even on a product tagged with both types."""
    respelled = [canonical_type(t) or canonical_format(t) or canonical_genre(t) or t for t in r.tags]
    return ", ".join(dedupe(respelled))


def needs_poster(row: dict) -> bool:
    return not (row.get("Image Src") or "").strip()


def needs_description(row: dict) -> bool:
    return not strip_html(row.get("Body (HTML)", ""))


def is_multi_variant(row: dict) -> bool:
    try:
        return int(row.get("Variant Count") or 1) > 1
    except ValueError:
        return False


def _finder(row: dict, r: Resolved):
    handle = row.get("Handle", "")
    title = (row.get("Title") or "").strip()

    def make(rule, field, current, proposed, bucket, detail=""):
        return Finding(handle, title, r.type or "", rule, field, current or "", proposed or "", bucket, detail)

    return make


def _price_findings(row, r, make) -> list[Finding]:
    if r.type is None:
        return []  # price can't be validated against an unknown type
    raw = (row.get("Variant Price") or "").strip()
    if r.type == "Rental" and not raw:
        return [make("rental-price-blank", "Variant Price", "", "0", AUTO_FIX, "rentals are always 0")]
    _, reason = resolve_price(r.type, raw)
    if reason is None:
        return []
    if reason.startswith("unreadable"):
        rule = "price-unreadable"
    elif reason.startswith("Rental"):
        rule = "rental-price-nonzero"
    else:
        rule = "floor-sale-price"
    return [make(rule, "Variant Price", raw, "", MANUAL, reason)]


def _rental_barcode_findings(row, r, make) -> list[Finding]:
    if r.type != "Rental":
        return []
    barcode = (row.get("Variant Barcode") or "").strip()
    if not barcode:
        return [make("rental-barcode-missing", "Variant Barcode", "", "", MANUAL,
                     "rentals need a unique 8-digit barcode")]
    if not RENTAL_BARCODE.match(barcode):
        return [make("rental-barcode-format", "Variant Barcode", barcode, "", MANUAL,
                     "rental barcodes must be exactly 8 digits")]
    return []


def _autofix_findings(row, r, make) -> list[Finding]:
    out: list[Finding] = []
    current_tags = row.get("Tags", "")
    proposed_tags = respelled_tags(r)
    for tag in r.tags:
        for rule, resolver in _TAG_ALIAS_RULES:
            canonical = resolver(tag)
            if canonical and canonical != tag:
                out.append(make(rule, "Tags", current_tags, proposed_tags, AUTO_FIX, f"{tag!r} -> {canonical!r}"))

    vendor = (row.get("Vendor") or "").strip()
    if r.format and vendor != r.format:
        out.append(make("format-alias", "Vendor", vendor, r.format, AUTO_FIX, "Vendor carries the media format"))

    if r.genres:
        option1 = (row.get("Option1 Value") or "").strip()
        if option1 != r.genres[0]:
            out.append(make("option1-genre", "Option1 Value", option1, r.genres[0], AUTO_FIX,
                            "Option1 holds the primary genre (barcode label slot)"))
            option1_name = (row.get("Option1 Name") or "").strip()
            if option1_name != "Genre":
                out.append(make("option1-genre", "Option1 Name", option1_name, "Genre", AUTO_FIX,
                                "Option1 is the Genre option"))
        expected = [genre_handle(g) for g in r.genres]
        current = [h.strip() for h in (row.get(GENRE_METAFIELD) or "").split(";") if h.strip()]
        if set(current) != set(expected):
            out.append(make("genre-metafield-sync", GENRE_METAFIELD, "; ".join(current), "; ".join(expected),
                            AUTO_FIX, "the genre filter and PDP chip read this field"))

    if (row.get("Image Src") or "").strip() and not (row.get("Image Alt Text") or "").strip():
        out.append(make("alt-text-missing", "Image Alt Text", "", f"{(row.get('Title') or '').strip()} poster",
                        AUTO_FIX))
    return out


def check_row(row: dict) -> list[Finding]:
    r = resolve_row(row)
    make = _finder(row, r)
    findings: list[Finding] = []

    if r.type_reason:
        rule = "type-conflict" if r.type_reason.startswith("tagged as both") else "type-missing"
        findings.append(make(rule, "Tags", row.get("Tags", ""), "", MANUAL, r.type_reason))
    if r.format is None:
        findings.append(make("format-missing", "Vendor", row.get("Vendor", ""), "", MANUAL,
                             "no VHS/DVD/Blu-Ray/4K/Laserdisc/Betamax in Vendor, Option1 or tags"))
    if not r.genres:
        findings.append(make("genre-missing", GENRE_METAFIELD, row.get(GENRE_METAFIELD, ""), "", MANUAL,
                             "no recognisable genre in Option1 Value or tags"))
    findings += _price_findings(row, r, make)
    if (row.get("Variant Inventory Tracker") or "").strip() != "shopify":
        findings.append(make("inventory-untracked", "Variant Inventory Tracker",
                             row.get("Variant Inventory Tracker", ""), "shopify", MANUAL,
                             "an untracked product never shows as unavailable"))
    findings += _rental_barcode_findings(row, r, make)
    findings += _autofix_findings(row, r, make)

    if is_multi_variant(row):
        # A CSV fix on a multi-variant product can merge or clobber variants:
        # report only, never auto-fix.
        findings = [f for f in findings if f.bucket != AUTO_FIX]
        findings.insert(0, make("multiple-variants", "Variant Count", row.get("Variant Count", ""), "", MANUAL,
                                "one product per physical copy"))
    return findings


def check_catalogue(rows: list[dict]) -> list[Finding]:
    """rental-barcode-duplicate: a Rental's barcode on any other movie."""
    by_barcode: dict[str, list[str]] = {}
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if barcode:
            by_barcode.setdefault(barcode, []).append(row.get("Handle", ""))

    findings: list[Finding] = []
    for row in rows:
        barcode = (row.get("Variant Barcode") or "").strip()
        if not barcode:
            continue
        others = [h for h in by_barcode.get(barcode, []) if h != row.get("Handle", "")]
        if not others:
            continue
        r = resolve_row(row)
        if r.type != "Rental":
            continue
        findings.append(_finder(row, r)("rental-barcode-duplicate", "Variant Barcode", barcode, "", MANUAL,
                                        "also on " + ", ".join(others)))
    return findings
