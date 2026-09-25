"""Render the hosted picker page and the launcher from their HTML templates.

Both templates were extracted verbatim from the old f-string generator
(formatting-scripts/hosted_review_page.py). Placeholders are plain __NAME__
tokens, so the HTML/JS needs no brace-escaping.
"""

import json
from pathlib import Path
from urllib.parse import quote

_HERE = Path(__file__).parent


def _template(name: str) -> str:
    return (_HERE / name).read_text(encoding="utf-8")


def build_hosted_picker_html(products: list[dict], batch_id: str) -> str:
    html = _template("page.html")
    html = html.replace("__BATCH_ID_JSON__", json.dumps(batch_id))
    html = html.replace("__BATCH_ID_URL__", quote(batch_id, safe=""))
    html = html.replace("__PRODUCT_COUNT__", str(len(products)))
    # Products last: the only user-controlled text, so nothing inside it can
    # be mistaken for a placeholder by a later replace. "</" is escaped so an
    # overview can't close the <script> tag.
    return html.replace("__PRODUCTS_JSON__", json.dumps(products).replace("</", "<\\/"))


def build_launcher_html() -> str:
    return _template("launcher.html")
