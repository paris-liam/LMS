"""Uploaded Libib exports -> the copies the app offers to create.

The browser gzips each CSV and base64-encodes it (keeps two growing exports
under Vercel's 4.5 MB request limit). A copy is new when its 201… barcode is
on no Shopify variant; date added is shown, never used to decide.
"""

import base64
import binascii
import csv
import tempfile
import zlib
from collections import Counter
from pathlib import Path

from catalog.core.barcodes import is_new_flow_item
from catalog.errors import InputShapeError
from catalog.libib.exports import load_libib
from catalog.rental_sync.transform import transform

MAX_FILE_BYTES = 5 * 1024 * 1024
BARCODES_NAME = "Barcodes export.csv"
LIBRARY_NAME = "Library export.csv"


def decode_upload(encoded: str, label: str) -> bytes:
    if not encoded:
        raise InputShapeError(f"Choose the {label} file.")
    unreadable = f"The {label} upload is unreadable — choose the file again."
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InputShapeError(unreadable) from None
    inflater = zlib.decompressobj(wbits=31)  # gzip framing
    try:
        data = inflater.decompress(compressed, MAX_FILE_BYTES + 1)
    except zlib.error:
        raise InputShapeError(unreadable) from None
    if len(data) > MAX_FILE_BYTES or inflater.unconsumed_tail:
        raise InputShapeError(f"The {label} is over 5 MB — is it the right Libib export?")
    if not inflater.eof:
        raise InputShapeError(unreadable)
    return data


def _header(data: bytes) -> set[str]:
    first_line = data.decode("utf-8-sig", errors="replace").splitlines()[:1]
    return set(next(csv.reader(first_line), [])) if first_line else set()


def load_uploads(barcodes: bytes, library: bytes) -> list[dict]:
    barcodes_header, library_header = _header(barcodes), _header(library)
    if "barcode" not in barcodes_header and "description" in barcodes_header and "barcode" in library_header:
        raise InputShapeError("The two files are swapped — put the Barcodes export in the first box "
                              "and the Library export in the second.")
    with tempfile.TemporaryDirectory() as tmp:
        barcodes_path, library_path = Path(tmp) / BARCODES_NAME, Path(tmp) / LIBRARY_NAME
        barcodes_path.write_bytes(barcodes)
        library_path.write_bytes(library)
        try:
            return load_libib(barcodes_path, library_path)
        except (UnicodeDecodeError, csv.Error):
            raise InputShapeError("One of the files isn't a CSV — export it from Libib again.") from None


def _order(item: dict) -> tuple[str, str]:
    return (item.get("created") or "", (item.get("title") or "").lower())


def prepare(items: list[dict], shopify_barcodes: set[str]) -> dict:
    new_flow = [i for i in items if is_new_flow_item(i.get("barcode"), i.get("call_number"))]
    counts = Counter(i["barcode"] for i in new_flow)
    ready, set_aside, in_shopify = [], [], 0
    for item in sorted(new_flow, key=_order):
        if item["barcode"] in shopify_barcodes:
            in_shopify += 1
            continue
        copy = transform(item)
        if counts[item["barcode"]] > 1:
            copy["set_aside"].append(f"barcode {item['barcode']} is on {counts[item['barcode']]} Libib copies")
        (set_aside if copy["set_aside"] else ready).append(copy)
    return {"ready": ready, "set_aside": set_aside, "already_in_shopify": in_shopify,
            "not_new_flow": len(items) - len(new_flow)}
