"""Turn planned changes into narrow Shopify import CSVs, one per field group.

Shopify leaves an absent column alone but clears a blank cell in a present
column. So each file carries only the columns its rows change, plus the
columns the importer requires on every row (Handle, Title, Option1 Name,
Option1 Value) restated with the product's *final* values — the same in
every file, so the files can be imported in any order.
"""

from pathlib import Path

from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import write_csv

REQUIRED_COLUMNS = ["Handle", "Title", "Option1 Name", "Option1 Value"]

GROUP_COLUMNS = {
    "image.csv": ["Image Src", "Image Alt Text"],
    "alt-text.csv": ["Image Src", "Image Alt Text"],
    "description.csv": ["Body (HTML)"],
    "genre.csv": ["Product Category", GENRE_METAFIELD],
    "tags.csv": ["Tags"],
    "vendor.csv": ["Vendor"],
    "price.csv": ["Variant Price"],
}

_FIELD_GROUP = {
    "Image Src": "image.csv",
    "Body (HTML)": "description.csv",
    "Option1 Name": "genre.csv",
    "Option1 Value": "genre.csv",
    GENRE_METAFIELD: "genre.csv",
    "Product Category": "genre.csv",
    "Tags": "tags.csv",
    "Vendor": "vendor.csv",
    "Variant Price": "price.csv",
}


def build_import_files(changes, rows_by_handle: dict) -> dict[str, tuple[list[str], list[dict]]]:
    final: dict[str, dict] = {}
    changed_fields: dict[str, set] = {}
    for change in changes:
        final.setdefault(change.handle, dict(rows_by_handle[change.handle]))[change.field] = change.after
        changed_fields.setdefault(change.handle, set()).add(change.field)

    members: dict[str, set] = {}
    for handle, fields in changed_fields.items():
        for field_name in fields:
            if field_name == "Image Alt Text":
                group = "image.csv" if "Image Src" in fields else "alt-text.csv"
            else:
                group = _FIELD_GROUP[field_name]
            members.setdefault(group, set()).add(handle)

    files = {}
    for group, extra in GROUP_COLUMNS.items():
        if group not in members:
            continue
        # Product Category only rides along when a row in the file sets it.
        extra = [c for c in extra if c != "Product Category"
                 or any(c in changed_fields[h] for h in members[group])]
        columns = REQUIRED_COLUMNS + [c for c in extra if c not in REQUIRED_COLUMNS]
        rows = [{c: final[h].get(c, "") for c in columns} for h in sorted(members[group])]
        files[group] = (columns, rows)
    return files


def warnings_for(files: dict, changes) -> list[str]:
    """Only warn about what is actually risky: an Option1 change (not a
    metafield-only genre fix) and restating an existing Image Src."""
    warnings = []
    if any(c.field in ("Option1 Name", "Option1 Value") for c in changes):
        warnings.append("genre.csv changes Option1 Name/Value — import it only after the dev-store check "
                        "(plan 2, Task 12) confirmed barcodes and inventory survive an Option1 change.")
    if "alt-text.csv" in files:
        warnings.append("alt-text.csv restates each product's existing Image Src — import it only after the "
                        "dev-store check confirmed this does not duplicate images.")
    return warnings


def write_import_files(import_dir, files: dict) -> list[Path]:
    import_dir = Path(import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)
    for stale in import_dir.glob("*.csv"):
        stale.unlink()
    paths = []
    for name, (columns, rows) in files.items():
        write_csv(import_dir / name, columns, rows)
        paths.append(import_dir / name)
    return paths
