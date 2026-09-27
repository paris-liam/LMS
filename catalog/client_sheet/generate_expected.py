"""Regenerate template/client-upload-template.expected.csv from the scaffold.

    python3 -m catalog.client_sheet.generate_expected

Run after any taxonomy change, then re-run the tests. The expected file is the
answer key the manual sheet-build pass checks the spreadsheet's tab 2 against.
"""

import csv
from pathlib import Path

from catalog.client_sheet.transform import fill_rows_to_import_rows
from catalog.core.columns import TEMPLATE_COLUMNS

TEMPLATE_DIR = Path(__file__).parent / "template"
FILL_CSV = TEMPLATE_DIR / "client-upload-template.csv"
EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.expected.csv"


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
