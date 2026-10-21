"""Save Libib's two Rental Library exports byte-for-byte after a sanity check."""
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from catalog.backup.guard import LIBIB_BARCODES_REQUIRED, LIBIB_LIBRARY_REQUIRED, SourceResult, check_csv


def _is_playwright_timeout(exc: Exception) -> bool:
    return type(exc).__name__ == "TimeoutError" and type(exc).__module__.startswith("playwright")


def backup_libib(out_dir: Path, export: Callable[[Path], tuple[Path, Path]]) -> SourceResult:
    try:
        with tempfile.TemporaryDirectory() as temp:
            barcodes, library = export(Path(temp))
            barcode_rows = check_csv(barcodes, LIBIB_BARCODES_REQUIRED)
            library_rows = check_csv(library, LIBIB_LIBRARY_REQUIRED)
            target = out_dir / "libib"
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(barcodes, target / "barcodes.csv")
            shutil.copyfile(library, target / "library.csv")
        return SourceResult("libib", True, f"{barcode_rows}/{library_rows} rows")
    except Exception as exc:
        if _is_playwright_timeout(exc):
            message = "Libib login or export timed out"
        else:
            detail = " ".join(str(exc).split())
            message = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        return SourceResult("libib", False, "FAILED", message)
