"""Pull the base CSV row for every still-ambiguous product out of its
source batch, into one consolidated file — the last thing needed from the
per-batch output folders before they can be deleted. Everything else
about a still-ambiguous entry (its title, vendor, genre, TMDB candidates)
already lives in ambiguous.json; only the live product's own current row
data (Title, Option1 Value, existing Tags, etc.) has to be read out of the
batch directory first.
"""


def collect_master_rows(
    entries: list[dict], rows_by_folder: dict[str, tuple[list[str], list[dict]]],
) -> tuple[list[str], list[dict], list[dict]]:
    """Build one base-row CSV from a set of ambiguous-queue entries.

    entries: ambiguous.json-shaped dicts, each needing "handle" and
    "source_folder".
    rows_by_folder: {source_folder: (fieldnames, rows)} — that batch's
    already-loaded base CSV (upload.csv or circa-refilled.csv).

    Returns (union_header, rows, missing_entries):
      - union_header: every column seen across all touched batches, in
        first-seen order — batches don't all share the same shape (one
        batch's rows are a full ~58-column Shopify export, others are the
        narrower ~18-column pipeline output), so a row from a narrower
        batch gets blank cells for columns only the wider batch has,
        rather than losing those columns for everyone.
      - rows: one row per unique handle, in entries' first-seen order.
      - missing_entries: entries whose handle wasn't found in its
        batch's rows, reported rather than raised so one bad batch
        mapping doesn't abort the whole extraction.
    """
    header: list[str] = []
    seen_columns = set()
    rows_by_handle: dict[str, dict] = {}
    handle_order: list[str] = []
    missing: list[dict] = []

    for entry in entries:
        handle = entry["handle"]
        if handle in rows_by_handle:
            continue

        fieldnames, rows = rows_by_folder[entry["source_folder"]]
        for column in fieldnames:
            if column not in seen_columns:
                seen_columns.add(column)
                header.append(column)

        row = next((r for r in rows if r.get("Handle") == handle), None)
        if row is None:
            missing.append(entry)
            continue

        rows_by_handle[handle] = dict(row)
        handle_order.append(handle)

    output_rows = []
    for handle in handle_order:
        row = rows_by_handle[handle]
        output_rows.append({column: row.get(column, "") for column in header})

    return header, output_rows, missing
