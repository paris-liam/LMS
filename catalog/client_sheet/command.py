"""`python3 -m catalog check-upload <csv>` — check a filled client upload sheet
(either tab) before it is imported. Exit 0 clean, 1 problems, 2 unreadable."""

from catalog.client_sheet.check import report


def register(subparsers) -> None:
    p = subparsers.add_parser("check-upload", help="check a client upload-sheet CSV before importing it")
    p.add_argument("csv", help="the fill tab or the Shopify import tab, downloaded as CSV")
    p.set_defaults(func=lambda args: report(args.csv))
