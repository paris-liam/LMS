"""Build a Libib import batch: import.csv (for Add Items -> CSV with Force
Import Mode on), each rental's poster, and ready.csv (the fixer's input)."""

import re
import urllib.request
from pathlib import Path

from catalog.core import log
from catalog.core.csv_io import write_csv
from catalog.libib.columns import LIBIB_MOVIE_COLUMNS, READY_COLUMNS, import_row, ready_row

IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif")
_BATCH_NAME = re.compile(r"^batch-(\d+)$")


def next_batch_id(sync_dir) -> str:
    sync_dir = Path(sync_dir)
    numbers = [int(m.group(1)) for p in (sync_dir.iterdir() if sync_dir.is_dir() else [])
               if p.is_dir() and (m := _BATCH_NAME.match(p.name))]
    return f"batch-{(max(numbers) + 1) if numbers else 1:04d}"


def image_ext(url: str) -> str:
    name = (url or "").split("?")[0].rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in IMAGE_EXTS else "jpg"


def download_posters(rows: list[dict], dest_dir, download=urllib.request.urlretrieve) -> tuple[dict[str, str], list[str]]:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    failed: list[str] = []
    for index, row in enumerate(rows, start=1):
        call = (row.get("Variant Barcode") or "").strip()
        url = (row.get("Image Src") or "").strip()
        if not url:
            continue  # no poster yet: the rental still imports, and the poster is uploaded once it exists
        target = dest_dir / f"{call}.{image_ext(url)}"
        try:
            download(url, target)
            paths[call] = str(target)
            log.progress(index, len(rows), f"{call} {row.get('Title', '').strip()}", "poster ok")
        except Exception as exc:  # a bad URL must not abort the batch
            failed.append(call)
            log.progress(index, len(rows), f"{call} {row.get('Title', '').strip()}", f"poster FAILED: {exc}")
    return paths, failed


def write_batch(batch_dir, rows: list[dict], poster_paths: dict[str, str]) -> None:
    batch_dir = Path(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    write_csv(batch_dir / "import.csv", LIBIB_MOVIE_COLUMNS, [import_row(r) for r in rows])
    write_csv(batch_dir / "ready.csv", READY_COLUMNS,
              [ready_row(r, poster_paths.get((r.get("Variant Barcode") or "").strip(), "")) for r in rows])
