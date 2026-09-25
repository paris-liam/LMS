"""The one HTML-to-text and whitespace normaliser for the whole package.

strip_html deletes tags without inserting spaces — the same behaviour the
Libib imports so far were built with, so comparisons against Libib stay
stable.
"""

import html
import re


def strip_html(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def norm_ws(text: str | None) -> str:
    """Collapse whitespace runs (including non-breaking spaces) to one space."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
