"""Regenerate the scaffold's expected outputs from the scaffold.

    python3 -m catalog.client_sheet.generate_expected

Writes template/client-upload-template.expected.csv (tab 2, Shopify) and
template/client-upload-template.libib-expected.csv (tab 3, Libib). Run after
any taxonomy change, then re-run the tests. The expected files are the answer
keys the manual sheet-build pass checks the spreadsheet's tabs against.
"""

import csv
from pathlib import Path

from catalog.client_sheet.transform import fill_rows_to_import_rows, fill_rows_to_libib_rows
from catalog.core.columns import TEMPLATE_COLUMNS
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

TEMPLATE_DIR = Path(__file__).parent / "template"
FILL_CSV = TEMPLATE_DIR / "client-upload-template.csv"
EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.expected.csv"
LIBIB_EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.libib-expected.csv"


def _write(path, columns, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> None:
    with open(FILL_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    _write(EXPECTED_CSV, TEMPLATE_COLUMNS, fill_rows_to_import_rows(rows))
    _write(LIBIB_EXPECTED_CSV, LIBIB_MOVIE_COLUMNS, fill_rows_to_libib_rows(rows))


if __name__ == "__main__":
    main()
