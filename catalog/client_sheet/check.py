"""Check a filled upload sheet before it reaches Shopify or Libib.

Every problem this catches is one Shopify will happily import. A product with
an empty genre metafield uploads clean, appears on the storefront, and is
simply missing from the genre filter and the PDP chip — with nothing anywhere
to say why. That exact fault survived three import rounds in testing before
anyone noticed, which is what this script exists to prevent.

Accepts any of the sheet's three tabs:

  fill    the "Add movies" tab    (11 columns, what the client types)
  import  the "Shopify import" tab (17 columns, what Shopify imports)
  libib   the "Libib import" tab   (26 columns, what Libib force-imports)

The import shape is the one worth checking for Shopify — it is where a failed
VLOOKUP shows up as a blank cell rather than an error. The libib shape guards
the call number, which is how every Libib command finds an item again.

Description and image are deliberately not required (decided 2026-10-01): the
client may upload a copy without them and the catalogue fill adds them later.

    python3 -m catalog check-upload <csv>

Exit status is 0 when nothing is wrong (warnings allowed), 1 when anything
is, so it can gate an import in a script.
"""

import csv
import os
import re
import sys

from catalog.core.barcodes import is_rental_barcode
from catalog.core.columns import GENRE_METAFIELD, TEMPLATE_COLUMNS
from catalog.client_sheet.transform import FILL_COLUMNS
from catalog.core.taxonomy import FORMATS, GENRES, TYPES
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

SHAPES = {"fill": FILL_COLUMNS, "import": TEMPLATE_COLUMNS, "libib": LIBIB_MOVIE_COLUMNS}
LABELS = {"fill": "fill tab", "import": "Shopify import tab", "libib": "Libib import tab"}
# The column that must be unique per row, and why a repeat is costly.
UNIQUE = {
    # Two rows sharing a handle do not become two products — they become one
    # product with two variants, merging two copies under a single barcode.
    "import": ("Handle", "handle", "edit one of the two Handle cells to something distinct"),
    "fill": ("Barcode", "barcode", "two copies can't share a label; check both cases"),
    "libib": ("call_number", "call number", "two copies can't share a label; check both cases"),
}
BARCODE_FIX = ("format the Barcode column as Plain text (a leading 0 is otherwise "
               "dropped) and type all 8 digits from the label")

GENRE_LABELS = set(GENRES)
GENRE_HANDLES = set(GENRES.values())
FORMAT_SET = set(FORMATS)
TYPE_SET = set(TYPES)


class Problem:
    """One thing wrong with one row. `row` is the spreadsheet row number."""

    def __init__(self, row, title, message, fix, warning=False):
        self.row = row
        self.title = title
        self.message = message
        self.fix = fix
        # A warning is worth seeing but does not make the file unsafe to import.
        self.warning = warning


def _read(path):
    # utf-8-sig: Google Sheets writes a BOM on CSV download.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def detect_shape(header):
    """Return "fill", "import" or "libib", or raise ValueError naming the mismatch."""
    for name, expected in SHAPES.items():
        if header == expected:
            return name

    for name, expected in SHAPES.items():
        missing = [c for c in expected if c not in header]
        extra = [c for c in header if c not in expected]
        # Close enough to be that shape, but not exactly — say what differs
        # rather than making the operator diff two column lists by eye.
        if len(missing) + len(extra) <= 3:
            parts = []
            if missing:
                parts.append("missing " + ", ".join(repr(c) for c in missing))
            if extra:
                parts.append("unexpected " + ", ".join(repr(c) for c in extra))
            raise ValueError(f"looks like the {name} shape but {'; '.join(parts)}")

    raise ValueError(
        "header matches none of the fill tab (11 columns), the Shopify import "
        f"tab (17) or the Libib import tab (26). Got {len(header)} columns: "
        f"{', '.join(header[:6])}…"
    )


def _genres_of(row, shape):
    if shape == "fill":
        return [row.get(f"Genre {n}", "").strip() for n in (1, 2, 3)]
    # On the import shape only the primary label survives, in Option1 Value
    # (the rest are handles in the genre metafield, checked separately).
    # Checking the primary is enough to catch a bad dropdown pick.
    return [row.get("Option1 Value", "").strip()]


def check_row(row, number, shape):
    """Every problem with one row, in reading order."""
    if shape == "libib":
        return check_libib_row(row, number)
    problems = []
    title = (row.get("Title") or "").strip()

    def bad(message, fix, warning=False):
        problems.append(Problem(number, title or "(no title)", message, fix, warning))

    if not title:
        bad("no Title", "every row needs a movie title")

    for label in [g for g in _genres_of(row, shape) if g]:
        if label not in GENRE_LABELS:
            bad(
                f"genre {label!r} is not one of the {len(GENRES)}",
                "pick from the dropdown; if it came from the mappings tab, "
                "re-import genre-mappings.csv",
            )

    if shape == "fill":
        fmt = (row.get("Format") or "").strip()
        if fmt and fmt not in FORMAT_SET:
            bad(f"format {fmt!r} is not recognised",
                f"use one of: {', '.join(FORMATS)}")
        ptype = (row.get("Type") or "").strip()
        if ptype and ptype not in TYPE_SET:
            bad(f"type {ptype!r} is not recognised", "use Rental or Floor Sale")
        if not ptype:
            bad("no Type", "every row needs Rental or Floor Sale")
        price = (row.get("Price") or "").strip()
        if ptype == "Floor Sale" and not price:
            bad("Floor Sale with no price",
                "a blank price ships a live product sellable at $0.00")
        barcode = (row.get("Barcode") or "").strip()
        if barcode and not is_rental_barcode(barcode):
            bad(f"barcode {barcode!r} is not 8 digits", BARCODE_FIX)
        if ptype == "Rental" and not barcode:
            bad("no Barcode yet, so it is not on the Libib import tab",
                "type it in after printing the label, before downloading the Libib tab",
                warning=True)
        return problems

    # --- import shape only ---------------------------------------------
    # THE important check. A genre label the mappings tab doesn't know makes
    # the sheet's VLOOKUP return "" through IFERROR, so this cell goes blank
    # and the product imports with no genre at all — silently.
    primary = (row.get("Option1 Value") or "").strip()
    handles = [h.strip() for h in (row.get(GENRE_METAFIELD) or "").split(";") if h.strip()]
    if primary and not handles:
        bad(
            f"genre {primary!r} produced no genre handle",
            "the mappings tab is missing this genre — re-import "
            "genre-mappings.csv, then re-export",
        )
    for handle in handles:
        if handle not in GENRE_HANDLES:
            bad(f"genre handle {handle!r} is not a real genre",
                "check the mappings tab's column B")

    vendor = (row.get("Vendor") or "").strip()
    if vendor and vendor not in FORMAT_SET:
        bad(f"Vendor {vendor!r} is not a media format",
            f"Vendor carries the format; use one of: {', '.join(FORMATS)}")

    tags = [t.strip() for t in (row.get("Tags") or "").split(",") if t.strip()]
    types = [t for t in tags if t in TYPE_SET]
    if len(types) != 1:
        bad(
            "tags name " + (f"{len(types)} types" if types else "no type"),
            "each row needs exactly one of Rental / Floor Sale",
        )

    raw_price = (row.get("Variant Price") or "").strip()
    try:
        price = float(raw_price or 0)
    except ValueError:
        bad(f"price {raw_price!r} is not a number", "enter digits only")
    else:
        if types == ["Rental"] and price != 0:
            bad(f"Rental priced {raw_price}", "rentals must be 0")
        if types == ["Floor Sale"] and price <= 0:
            bad("Floor Sale priced 0",
                "this ships a live product sellable at $0.00")

    if (row.get("Variant Inventory Tracker") or "").strip() != "shopify":
        bad(
            "inventory not tracked",
            "an untracked product can never show as unavailable on the site",
        )

    return problems


def check_libib_row(row, number):
    """Every problem with one Libib import row."""
    problems = []
    title = (row.get("title") or "").strip()

    def bad(message, fix, warning=False):
        problems.append(Problem(number, title or "(no title)", message, fix, warning))

    if not title:
        bad("no title", "every row needs a movie title")

    call = (row.get("call_number") or "").strip()
    if not call:
        bad("no call number",
            "Libib finds every copy by its call number; the sheet copies it from Barcode")
    elif not is_rental_barcode(call):
        bad(f"call number {call!r} is not 8 digits", BARCODE_FIX)

    # "VHS, drama; documentary": the format, then the genre handles — the same
    # string `libib sync` writes, so a hand-imported copy shows no drift.
    parts = [p.strip() for p in re.split(r"[,;]", row.get("tags") or "") if p.strip()]
    if not parts or parts[0] not in FORMAT_SET:
        bad(f"tags {row.get('tags', '')!r} do not start with a media format",
            f"Format must be one of: {', '.join(FORMATS)}")
    genres = parts[1:]
    for handle in genres:
        if handle not in GENRE_HANDLES:
            bad(f"genre handle {handle!r} is not a real genre", "check the mappings tab's column B")
    if parts and not genres:
        bad("no genre", "pick a Genre 1 so the copy can be found by genre", warning=True)

    try:
        price = float((row.get("price") or "0").strip())
    except ValueError:
        price = None
    if price != 0:
        bad(f"price {row.get('price')!r} is not 0", "rentals carry no price")
    if (row.get("copies") or "").strip() != "1":
        bad(f"copies {row.get('copies')!r} is not 1", "one row per physical copy")
    return problems


def check(path):
    """Return (shape, rows, problems). Raises ValueError on a bad header."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    shape = detect_shape(header)
    rows = _read(path)

    problems = []
    for offset, row in enumerate(rows):
        problems.extend(check_row(row, offset + 2, shape))  # +2: header is row 1

    column, noun, fix = UNIQUE[shape]
    seen = {}
    for offset, row in enumerate(rows):
        value = (row.get(column) or "").strip()
        if not value:
            continue
        if value in seen:
            problems.append(Problem(
                offset + 2, (row.get("Title") or row.get("title") or "").strip(),
                f"{noun} {value!r} is already used on row {seen[value]}", fix,
            ))
        else:
            seen[value] = offset + 2

    problems.sort(key=lambda p: p.row)
    return shape, rows, problems


def report(path) -> int:
    """Print the check for one file. 0 = clean (warnings allowed), 1 = problems,
    2 = unreadable."""
    try:
        shape, rows, problems = check(path)
    except FileNotFoundError:
        print(f"✗ no such file: {path}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"✗ {os.path.basename(path)}: {error}", file=sys.stderr)
        return 2

    print(f"{os.path.basename(path)} — {len(rows)} rows, {LABELS[shape]}")
    errors = [p for p in problems if not p.warning]
    warnings = [p for p in problems if p.warning]

    def show(items):
        for problem in items:
            print(f"  row {problem.row} — {problem.title}")
            print(f"    {problem.message}")
            print(f"    → {problem.fix}")

    if warnings:
        print(f"\n! {len(warnings)} warning(s):\n")
        show(warnings)

    if not errors:
        print("\n✓ nothing wrong. Safe to import." if warnings else "✓ nothing wrong. Safe to import.")
        return 0

    print(f"\n✗ {len(errors)} problem(s) in {len({p.row for p in errors})} row(s):\n")
    show(errors)
    print("\nFix these in the sheet, re-export, and run this again.")
    return 1
