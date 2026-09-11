#!/usr/bin/env python3
"""Check a filled upload sheet before it reaches Shopify.

Every problem this catches is one Shopify will happily import. A product with
an empty genre metafield uploads clean, appears on the storefront, and is
simply missing from the genre filter and the PDP chip — with nothing anywhere
to say why. That exact fault survived three import rounds in testing before
anyone noticed, which is what this script exists to prevent.

Accepts either shape:

  fill    the "Add movies" tab  (10 columns, what the client types)
  import  the "Shopify import"  (17 columns, what actually gets imported)

The import shape is the one worth checking — it is what Shopify consumes, and
it is where a failed VLOOKUP shows up as a blank cell rather than an error.

    python3 formatting-scripts/check_upload.py <csv>

Exit status is 0 when nothing is wrong, 1 when anything is, so it can gate an
import in a script.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from columns import GENRE_METAFIELD, TEMPLATE_COLUMNS
from sheet_transform import FILL_COLUMNS
from taxonomy import FORMATS, GENRES, TYPES

GENRE_LABELS = set(GENRES)
GENRE_HANDLES = set(GENRES.values())
FORMAT_SET = set(FORMATS)
TYPE_SET = set(TYPES)


class Problem:
    """One thing wrong with one row. `row` is the spreadsheet row number."""

    def __init__(self, row, title, message, fix):
        self.row = row
        self.title = title
        self.message = message
        self.fix = fix


def _read(path):
    # utf-8-sig: Google Sheets writes a BOM on CSV download.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def detect_shape(header):
    """Return "fill" or "import", or raise ValueError naming the mismatch."""
    if header == FILL_COLUMNS:
        return "fill"
    if header == TEMPLATE_COLUMNS:
        return "import"

    for name, expected in (("fill", FILL_COLUMNS), ("import", TEMPLATE_COLUMNS)):
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
        "header matches neither the fill tab (10 columns) nor the import tab "
        f"(17 columns). Got {len(header)} columns: {', '.join(header[:6])}…"
    )


def _genres_of(row, shape):
    if shape == "fill":
        return [row.get(f"Genre {n}", "").strip() for n in (1, 2, 3)]
    # On the import shape the labels survive only in Tags; Option1 Value holds
    # the primary. Checking the primary is enough to catch a bad dropdown pick.
    return [row.get("Option1 Value", "").strip()]


def check_row(row, number, shape):
    """Every problem with one row, in reading order."""
    problems = []
    title = (row.get("Title") or "").strip()

    def bad(message, fix):
        problems.append(Problem(number, title or "(no title)", message, fix))

    if not title:
        bad("no Title", "every row needs a movie title")

    for label in [g for g in _genres_of(row, shape) if g]:
        if label not in GENRE_LABELS:
            bad(
                f"genre {label!r} is not one of the 13",
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
        if not (row.get("Image URL") or "").strip():
            bad("no Image URL", "the product would have no poster")
        if not (row.get("Description") or "").strip():
            bad("no Description", "the product page would have no copy")
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

    if not (row.get("Image Src") or "").strip():
        bad("no image", "the product would have no poster")

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

    if shape == "import":
        seen = {}
        for offset, row in enumerate(rows):
            handle_value = (row.get("Handle") or "").strip()
            if not handle_value:
                continue
            if handle_value in seen:
                # Two rows sharing a handle do not become two products — they
                # become one product with two variants, merging two physical
                # copies into a single item with a single barcode.
                problems.append(Problem(
                    offset + 2, (row.get("Title") or "").strip(),
                    f"handle {handle_value!r} is already used on row {seen[handle_value]}",
                    "edit one of the two Handle cells to something distinct",
                ))
            else:
                seen[handle_value] = offset + 2

    problems.sort(key=lambda p: p.row)
    return shape, rows, problems


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().split("\n\n")[-2].strip(), file=sys.stderr)
        print(f"\nusage: {os.path.basename(sys.argv[0])} <csv>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    try:
        shape, rows, problems = check(path)
    except FileNotFoundError:
        print(f"✗ no such file: {path}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"✗ {os.path.basename(path)}: {error}", file=sys.stderr)
        return 2

    label = {"fill": "fill tab", "import": "import tab"}[shape]
    print(f"{os.path.basename(path)} — {len(rows)} rows, {label}")

    if not problems:
        print(f"✓ nothing wrong. Safe to import.")
        return 0

    print(f"\n✗ {len(problems)} problem(s) in {len({p.row for p in problems})} row(s):\n")
    for problem in problems:
        print(f"  row {problem.row} — {problem.title}")
        print(f"    {problem.message}")
        print(f"    → {problem.fix}")
    print("\nFix these in the sheet, re-export, and run this again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
