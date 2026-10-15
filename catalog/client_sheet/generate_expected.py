"""Regenerate the scaffold's expected outputs from the scaffold.

    python3 -m catalog.client_sheet.generate_expected

Writes template/client-upload-template.expected.csv (tab 2, Shopify),
template/client-upload-template.libib-expected.csv (tab 3, Libib) and
template/floor-sale/floor-sale-template.expected.csv (the Floor Sale sheet's
tab 2). Run after
any taxonomy change, then re-run the tests. The expected files are the answer
keys the manual sheet-build pass checks the spreadsheet's tabs against.
"""

import csv
from pathlib import Path

from catalog.client_sheet.floor_sale import floor_sale_rows_to_import_rows, split_fill_tab
from catalog.client_sheet.transform import fill_rows_to_import_rows, fill_rows_to_libib_rows
from catalog.core.columns import FLOOR_SALE_TEMPLATE_COLUMNS, TEMPLATE_COLUMNS
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS

TEMPLATE_DIR = Path(__file__).parent / "template"
FILL_CSV = TEMPLATE_DIR / "client-upload-template.csv"
EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.expected.csv"
LIBIB_EXPECTED_CSV = TEMPLATE_DIR / "client-upload-template.libib-expected.csv"
FLOOR_SALE_DIR = TEMPLATE_DIR / "floor-sale"
FLOOR_SALE_FILL_CSV = FLOOR_SALE_DIR / "floor-sale-template.csv"
FLOOR_SALE_EXPECTED_CSV = FLOOR_SALE_DIR / "floor-sale-template.expected.csv"


def _write(path, columns, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


def _read(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    rows = _read(FILL_CSV)
    _write(EXPECTED_CSV, TEMPLATE_COLUMNS, fill_rows_to_import_rows(rows))
    _write(LIBIB_EXPECTED_CSV, LIBIB_MOVIE_COLUMNS, fill_rows_to_libib_rows(rows))
    floor_sale, batch_date = split_fill_tab(_read(FLOOR_SALE_FILL_CSV))
    _write(FLOOR_SALE_EXPECTED_CSV, FLOOR_SALE_TEMPLATE_COLUMNS,
           floor_sale_rows_to_import_rows(floor_sale, batch_date))


if __name__ == "__main__":
    main()
