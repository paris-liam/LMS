"""Refuse empty or malformed exports before they overwrite a good backup."""

import csv
from dataclasses import dataclass
from pathlib import Path

from catalog.errors import InputShapeError

LIBIB_BARCODES_REQUIRED = ("id", "barcode", "title")
LIBIB_LIBRARY_REQUIRED = ("id", "title", "call_number")
SHOPIFY_REQUIRED = ("Handle", "Title", "Status")


@dataclass
class SourceResult:
    name: str  # "libib" | "shopify"
    ok: bool
    summary: str  # "3962/3962 rows" | "7031 products" | "FAILED"
    error: str = ""  # one line, no row contents


def check_csv(path: Path, required: tuple[str, ...]) -> int:
    """Return the data-row count; raise InputShapeError if the file is not a
    UTF-8 CSV with every required column and at least one data row. Messages
    never include row contents."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None) or []
            missing = [c for c in required if c not in header]
            if missing:
                raise InputShapeError(
                    f"{path.name}: missing required column(s): {', '.join(missing)}"
                )
            rows = sum(1 for row in reader if row)
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputShapeError(f"{path.name}: not readable as UTF-8 CSV ({type(e).__name__})")
    if rows == 0:
        raise InputShapeError(f"{path.name}: no data rows")
    return rows
