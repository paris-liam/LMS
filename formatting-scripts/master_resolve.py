"""Resolve a master ambiguous-review queue (entries pooled across every
batch, each carrying its own source_folder) against cached TMDB search
results, using tmdb_fill.classify_match's rule-based triage.

Splits the queue into:
  - resolved: entries that now classify as "confident" — a TMDB match
    good enough to fill without a human.
  - still_ambiguous: everything else, unchanged, for the picker.

Confident resolutions are further split into two independent fill sets
(image vs. description) because a product missing only one of the two
must never have the other's column touched — see build_fill_rows.
"""

from tmdb_fill import (
    GLOBAL_YEAR_CUTOFF,
    POSTER_BASE_URL,
    VHS_YEAR_CUTOFF,
    classify_match,
    clean_title_and_year,
    filter_by_year_cutoff,
    is_vhs,
)

IMAGE_FILL_COLUMNS = ["Handle", "Title", "Option1 Name", "Option1 Value", "Image Src", "Image Alt Text"]
DESCRIPTION_FILL_COLUMNS = ["Handle", "Title", "Option1 Name", "Option1 Value", "Body (HTML)"]


def resolve_entry(entry: dict, results: list[dict]) -> tuple[dict | None, str]:
    """Classify one ambiguous-queue entry against its raw TMDB results,
    mirroring tmdb_fill.build_output's per-row resolution exactly
    (classify_match, then the format-aware year-cutoff retry)."""
    clean_title, year = clean_title_and_year(entry["title"])
    genre = entry.get("genre", "")
    best, kind = classify_match(clean_title, year, results, genre=genre)

    if year is None and kind == "ambiguous":
        cutoff = VHS_YEAR_CUTOFF if is_vhs(entry.get("vendor", "")) else GLOBAL_YEAR_CUTOFF
        filtered = filter_by_year_cutoff(results, cutoff)
        if filtered and filtered != results:
            filtered_best, filtered_kind = classify_match(clean_title, year, filtered, genre=genre)
            if filtered_kind == "confident":
                best, kind = filtered_best, filtered_kind

    return best, kind


def resolve_queue(entries: list[dict], results_lookup) -> tuple[list[dict], list[dict]]:
    """Split a master ambiguous queue into (resolved, still_ambiguous).

    results_lookup(entry) -> list[dict] | None returns that entry's raw
    cached TMDB search results, or None/empty if nothing is cached for it
    (in which case the entry is left in still_ambiguous untouched).

    Each resolved item is {"entry": original entry, "best": winning
    TMDB result}.
    """
    resolved = []
    still_ambiguous = []

    for entry in entries:
        results = results_lookup(entry)
        if not results:
            still_ambiguous.append(entry)
            continue

        best, kind = resolve_entry(entry, results)
        if kind == "confident":
            resolved.append({"entry": entry, "best": best})
        else:
            still_ambiguous.append(entry)

    return resolved, still_ambiguous


def build_fill_rows(resolved: list[dict], needs_lookup, product_fields_lookup) -> tuple[list[dict], list[dict]]:
    """Build the two independent fill-row sets from resolved matches.

    needs_lookup(handle) -> (image_blank: bool, description_blank: bool)
    reports whether that product currently has no image / no description
    at all — a resolved match only ever fills a field the product is
    actually missing, and only when TMDB itself has data for it. This
    keeps the two output CSVs safe to import with just their own narrow
    column set: a column that's absent is left alone by Shopify, but a
    blank cell in a present column would clear existing data, so a field
    is never written unless both conditions hold.

    product_fields_lookup(handle) -> {"Title", "Option1 Name",
    "Option1 Value"} | None supplies the product's actual current values
    for the columns Shopify's importer requires alongside any update, even
    a Handle-matched one touching only Image Src/Body (HTML):
      - Title: without it the importer rejects the file outright.
      - Option1 Name/Value: the importer treats every row as a variant
        row, and (per this catalogue's convention — genre lives in
        Option1, see product-data-model-audit) rejects a variant update
        with "Product options input is required when updating variants"
        if the option identifying that variant is missing.
    These must be the live values (not re-derived) so restating them is a
    no-op rather than a silent change. A handle with no known fields, or a
    blank Option1 Value, is skipped entirely rather than risking a write
    that either fails the import or silently changes the variant.
    """
    image_rows = []
    description_rows = []

    for item in resolved:
        entry, best = item["entry"], item["best"]
        handle = entry["handle"]
        product_fields = product_fields_lookup(handle)
        if not product_fields or not product_fields.get("Title") or not product_fields.get("Option1 Value"):
            continue

        image_blank, description_blank = needs_lookup(handle)
        clean_title, _ = clean_title_and_year(entry["title"])
        match_year = (best.get("release_date") or "")[:4]

        if image_blank:
            poster_path = best.get("poster_path")
            if poster_path:
                suffix = f" ({match_year})" if match_year else ""
                image_rows.append({
                    "Handle": handle,
                    **product_fields,
                    "Image Src": f"{POSTER_BASE_URL}{poster_path}",
                    "Image Alt Text": f"{clean_title}{suffix} poster",
                })

        if description_blank:
            overview = (best.get("overview") or "").strip()
            if overview:
                description_rows.append({
                    "Handle": handle,
                    **product_fields,
                    "Body (HTML)": f"<p>{overview}</p>",
                })

    return image_rows, description_rows
