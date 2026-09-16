"""Enrich rows with an IMDb ID (via TMDB) and a real UPC/EAN (via UPCMDB),
so libib_export.py can populate upc_isbn10/ean_isbn13 instead of leaving
them blank (see claudedocs/2026-09-14-libib-bulk-upload-plan.md, decision
#2 -- this supersedes that decision now that a real identifier is
available).

Reuses tmdb_fill.py's matching engine (clean_title_and_year, search_tmdb,
classify_match) rather than re-implementing title/year matching, so match
quality and matching decisions stay identical to the rest of the pipeline.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from catalog_common import group_rows_by_handle
from columns import GENRE_METAFIELD
from tmdb_fill import (
    GLOBAL_YEAR_CUTOFF,
    VHS_YEAR_CUTOFF,
    classify_match,
    clean_title_and_year,
    filter_by_year_cutoff,
    is_vhs,
    search_tmdb,
)
from tmdb_fill import strip_html as strip_body_html

TMDB_EXTERNAL_IDS_URL = "https://api.themoviedb.org/3/movie/{id}/external_ids"
UPCMDB_BASE = "https://us-central1-upcmdb-cbae5.cloudfunctions.net/api"

REQUEST_DELAY_SECONDS = 0.25

# Our Vendor values -> acceptable UPCMDB "format" values. VHS/Laserdisc/
# Betamax have no barcoded-edition equivalent in UPCMDB (it only tracks
# DVD/Blu-ray/4K retail editions), so there's nothing to map them to --
# those rows always fall through to "no format match".
FORMAT_MAP = {
    "DVD": {"DVD"},
    "BLU-RAY": {"BLURAY"},
    "4K": {"UHD4K", "4KUHD"},
}


def _clean_keys(obj):
    """UPCMDB occasionally returns a key like '\\ufeffupc' (stray BOM)
    instead of 'upc' on some records -- strip it so record['upc'] is
    reliable regardless."""
    if isinstance(obj, list):
        return [_clean_keys(o) for o in obj]
    if isinstance(obj, dict):
        return {k.lstrip("﻿").strip(): v for k, v in obj.items()}
    return obj


def pick_upc_record(records: list[dict], vendor: str) -> tuple[dict | None, str]:
    """Pick the UPCMDB edition matching our Vendor/format. Returns
    (record_or_None, method):

      - "format_match": an edition in our Vendor's format was found.
      - "no_format_match": UPCMDB has edition(s) for this title, but none
        in our Vendor's format -- including every VHS/Laserdisc/Betamax
        row, since UPCMDB only tracks DVD/Blu-ray/4K editions and
        FORMAT_MAP has no entry for those at all. Deliberately returns
        None rather than a different edition's UPC/EAN: that barcode
        belongs to a different physical release (a DVD when our copy is a
        VHS tape, say) and assigning it would misrepresent which copy it
        identifies, even though it's the same movie/imdb_id.
      - "no_records": UPCMDB has nothing at all for this IMDb ID.
    """
    wanted = FORMAT_MAP.get((vendor or "").upper().strip())
    if wanted:
        for r in records:
            if (r.get("format") or "").upper() in wanted:
                return r, "format_match"
    if records:
        return None, "no_format_match"
    return None, "no_records"


def make_external_ids_fetcher(api_key: str):
    """fetch_fn(tmdb_id) -> dict, e.g. {"imdb_id": "tt0133093", ...}."""

    def fetch(tmdb_id: int) -> dict:
        url = TMDB_EXTERNAL_IDS_URL.format(id=tmdb_id) + f"?api_key={api_key}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    return fetch


def make_upcmdb_fetcher(api_key: str):
    """fetch_fn(imdb_id) -> list[dict] of UPC records, or [] on a 404."""

    def fetch(imdb_id: str) -> list[dict]:
        url = f"{UPCMDB_BASE}/v1/lookup/imdb/{urllib.parse.quote(imdb_id)}"
        req = urllib.request.Request(url, headers={"x-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise
        data = _clean_keys(data)
        return data if isinstance(data, list) else [data]

    return fetch


def build_output(
    rows: list[dict],
    tmdb_fetch_fn,
    external_ids_fetch_fn,
    upc_fetch_fn,
    sleep_fn=time.sleep,
    progress_fn=lambda index, total, title, message: None,
    skip_upc: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Add "IMDb ID", "UPC", "EAN", "UPC Match Method" columns to each row's
    primary (first) record in its handle group; every copy of the same
    handle gets the same values. Returns (output_rows, review_rows).

    Row order and count are preserved -- a row that can't be resolved is
    still emitted unchanged (new columns blank), just like tmdb_fill.py's
    build_output does for unmatched/ambiguous rows.

    skip_upc=True stops after resolving the IMDb ID -- upc_fetch_fn is never
    called. Use this while tuning TMDB matching behavior (UPCMDB quota is
    limited; TMDB's isn't) -- rows still report their would-be status via
    progress_fn/review_rows using "imdb resolved, UPCMDB skipped".
    """
    output_rows: list[dict] = []
    review_rows: list[dict] = []

    groups = group_rows_by_handle(rows)
    total = len(groups)

    def review(handle, title, vendor, kind, reason):
        review_rows.append(
            {"Handle": handle, "Title": title, "Vendor": vendor, "Kind": kind, "Reason": reason}
        )

    def blank_enrichment(row: dict) -> dict:
        row = dict(row)
        row.setdefault("IMDb ID", "")
        row.setdefault("UPC", "")
        row.setdefault("EAN", "")
        row.setdefault("UPC Match Method", "")
        return row

    for index, (handle, group) in enumerate(groups, start=1):
        title = group[0].get("Title", "").strip() or handle
        vendor = group[0].get("Vendor", "")
        genre = group[0].get(GENRE_METAFIELD, "")
        overview_hint = strip_body_html(group[0].get("Body (HTML)", ""))
        clean_title, year = clean_title_and_year(title)

        try:
            results = search_tmdb(tmdb_fetch_fn, clean_title, year)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, vendor, "unmatched", f"TMDB request failed: {exc}")
            output_rows.extend(blank_enrichment(r) for r in group)
            progress_fn(index, total, title, f"unmatched: TMDB request failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)
        best, kind = classify_match(clean_title, year, results, genre, overview_hint)

        # Same fallback as tmdb_fill.py's build_output: when there's no
        # title-year to disambiguate with, a same-titled-but-newer release
        # (a 2024 remake, a franchise reboot) is often what's creating the
        # tie. Our catalogue never carries anything that recent, so retrying
        # with those candidates dropped resolves ties like "Weapons" (2007
        # in our catalogue vs. a 2025 same-titled film) without needing a
        # year hint we don't have. Only applied when the unfiltered result
        # was already ambiguous, never as a pre-filter -- see the comment on
        # this block in tmdb_fill.py for why order matters here.
        if year is None and kind == "ambiguous":
            cutoff = VHS_YEAR_CUTOFF if is_vhs(vendor) else GLOBAL_YEAR_CUTOFF
            filtered = filter_by_year_cutoff(results, cutoff)
            if filtered and filtered != results:
                filtered_best, filtered_kind = classify_match(
                    clean_title, year, filtered, genre, overview_hint
                )
                if filtered_kind == "confident":
                    best, kind = filtered_best, filtered_kind

        if kind != "confident":
            reason = "no TMDB match" if kind == "none" else "ambiguous TMDB match"
            review(handle, title, vendor, kind if kind == "ambiguous" else "unmatched", reason)
            output_rows.extend(blank_enrichment(r) for r in group)
            progress_fn(index, total, title, reason)
            continue

        tmdb_id = best["id"]
        try:
            external = external_ids_fetch_fn(tmdb_id)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, vendor, "unmatched", f"TMDB external_ids failed: {exc}")
            output_rows.extend(blank_enrichment(r) for r in group)
            progress_fn(index, total, title, f"unmatched: external_ids failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)
        imdb_id = (external.get("imdb_id") or "").strip()

        if not imdb_id:
            review(handle, title, vendor, "unmatched", "TMDB has no imdb_id for this title")
            output_rows.extend(blank_enrichment(r) for r in group)
            progress_fn(index, total, title, "unmatched: no imdb_id on TMDB")
            continue

        if skip_upc:
            enriched = blank_enrichment(group[0])
            enriched["IMDb ID"] = imdb_id
            output_rows.append(enriched)
            output_rows.extend(blank_enrichment(r) for r in group[1:])
            progress_fn(index, total, title, f"imdb {imdb_id} resolved, UPCMDB skipped")
            continue

        try:
            records = upc_fetch_fn(imdb_id)
        except Exception as exc:
            sleep_fn(REQUEST_DELAY_SECONDS)
            review(handle, title, vendor, "unmatched", f"UPCMDB request failed: {exc}")
            enriched = blank_enrichment(group[0])
            enriched["IMDb ID"] = imdb_id
            output_rows.append(enriched)
            output_rows.extend(blank_enrichment(r) for r in group[1:])
            progress_fn(index, total, title, f"partial (imdb only): UPCMDB failed: {exc}")
            continue

        sleep_fn(REQUEST_DELAY_SECONDS)
        record, method = pick_upc_record(records, vendor)

        primary = blank_enrichment(group[0])
        primary["IMDb ID"] = imdb_id
        if record:
            primary["UPC"] = (record.get("upc") or "").strip()
            primary["EAN"] = (record.get("ean") or "").strip()
            primary["UPC Match Method"] = method
        elif method == "no_format_match":
            review(handle, title, vendor, "unmatched",
                   f"UPCMDB has edition(s) for this title but none in {vendor or '(blank)'} format")
        else:
            review(handle, title, vendor, "unmatched", "no UPCMDB records for this imdb_id")

        output_rows.append(primary)
        output_rows.extend(blank_enrichment(r) for r in group[1:])

        if record:
            status = f"UPC {primary['UPC']} ({method})"
        elif method == "no_format_match":
            status = f"matched imdb, no {vendor or '(blank)'}-format UPC (left blank)"
        else:
            status = "matched imdb, no UPC records"
        progress_fn(index, total, title, status)

    return output_rows, review_rows


def print_progress(index: int, total: int, title: str, message: str) -> None:
    print(f"[{index}/{total}] {title}: {message}", flush=True)
