"""Playwright lives only in .venv-libib, so a browser command run with the
system python3 should say which interpreter to use, not raise an ImportError."""

from catalog.errors import CatalogError


def sync_playwright(command: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CatalogError("Playwright is not installed for this Python. Run it with the Libib venv:\n"
                           f"  .venv-libib/bin/python -m catalog libib {command} …") from None
    return sync_playwright
