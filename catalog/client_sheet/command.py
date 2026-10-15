"""`python3 -m catalog check-upload <csv>` — check a filled client upload sheet
or Floor Sale sheet (any tab) before it is imported. Exit 0 clean, 1 problems, 2 unreadable."""

from catalog.client_sheet.check import report


def register(subparsers) -> None:
    p = subparsers.add_parser("check-upload", help="check a client upload-sheet CSV before importing it")
    p.add_argument("csv", help="any tab of the upload sheet or the Floor Sale sheet, downloaded as CSV")
    p.set_defaults(func=lambda args: report(args.csv))
