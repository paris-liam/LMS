#!/usr/bin/env python3
"""Regenerate client-upload-template.expected.csv from the scaffold.

Run this after any taxonomy change, then re-run the test suite. The
expected file is the answer key the manual sheet-build pass checks the
spreadsheet's tab 2 against, cell for cell.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from columns import TEMPLATE_COLUMNS
from sheet_transform import fill_rows_to_import_rows

FILL_CSV = os.path.join(HERE, "client-upload-template.csv")
EXPECTED_CSV = os.path.join(HERE, "client-upload-template.expected.csv")


def main() -> None:
    with open(FILL_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    produced = fill_rows_to_import_rows(rows)

    with open(EXPECTED_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        writer.writerows(produced)

    print(f"wrote {EXPECTED_CSV} ({len(produced)} rows)")


if __name__ == "__main__":
    main()
