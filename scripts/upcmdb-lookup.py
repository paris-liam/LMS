#!/usr/bin/env python3
"""
Look up UPCs for movies via UPCMDB, using IMDb IDs from tmdb-imdb-lookup.py
and matching the edition to each product's physical format (Vendor column).

Usage:
    UPCMDB_API_KEY=xxxx python3 scripts/upcmdb-lookup.py \
        --imdb-input claudedocs/tmdb-imdb-lookup-sample.csv \
        --rental-input products_imdbID.csv \
        --output claudedocs/upcmdb-lookup-sample.csv \
        --limit 20
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

UPCMDB_BASE = "https://us-central1-upcmdb-cbae5.cloudfunctions.net/api"

# Our Vendor values -> acceptable UPCMDB "format" values (seen: DVD, BLURAY,
# UHD4K, 4KUHD). VHS/Laserdisc/Betamax aren't barcoded editions UPCMDB tracks,
# so there's nothing to map them to.
FORMAT_MAP = {
    "DVD": {"DVD"},
    "BLU-RAY": {"BLURAY"},
    "4K": {"UHD4K", "4KUHD"},
}


def _clean_keys(obj):
    """UPCMDB occasionally returns a key like '\\ufeffupc' (stray BOM) instead
    of 'upc' on some records -- strip BOM/whitespace off every key so lookups
    like record['upc'] are reliable."""
    if isinstance(obj, list):
        return [_clean_keys(o) for o in obj]
    if isinstance(obj, dict):
        return {k.lstrip("﻿").strip(): v for k, v in obj.items()}
    return obj


def api_get(path, api_key):
    url = f"{UPCMDB_BASE}{path}"
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return _clean_keys(json.loads(resp.read().decode("utf-8")))


def pick_upc(records, vendor):
    wanted = FORMAT_MAP.get((vendor or "").upper().strip())
    if wanted:
        for r in records:
            if (r.get("format") or "").upper() in wanted:
                return r, "format_match"
    # no vendor match (or unmapped format like VHS) -- fall back to first record
    if records:
        return records[0], "fallback_first"
    return None, "no_records"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--imdb-input", default="claudedocs/tmdb-imdb-lookup-sample.csv")
    parser.add_argument("--rental-input", default="products_imdbID.csv")
    parser.add_argument("--output", default="claudedocs/upcmdb-lookup-sample.csv")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    api_key = os.environ.get("UPCMDB_API_KEY")
    if not api_key:
        sys.exit("Set UPCMDB_API_KEY in the environment before running this script.")

    with open(args.imdb_input, newline="", encoding="utf-8") as f:
        imdb_rows = list(csv.DictReader(f))

    with open(args.rental_input, newline="", encoding="utf-8") as f:
        rental_by_handle = {row["Handle"]: row for row in csv.DictReader(f)}

    imdb_rows = imdb_rows[: args.limit]

    out_fields = [
        "Handle",
        "Title",
        "Vendor",
        "IMDb_ID",
        "UPC",
        "Matched_Format",
        "Match_Method",
        "Editions_Found",
        "Status",
    ]

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    out_f = open(args.output, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=out_fields)
    writer.writeheader()

    for i, row in enumerate(imdb_rows, start=1):
        handle = row.get("Handle", "")
        title = row.get("Title", "")
        imdb_id = row.get("IMDb_ID", "")
        rental_row = rental_by_handle.get(handle, {})
        vendor = rental_row.get("Vendor", "")

        print(f"[{i}/{len(imdb_rows)}] {title} ({vendor}) {imdb_id}...", end=" ")

        record = {
            "Handle": handle,
            "Title": title,
            "Vendor": vendor,
            "IMDb_ID": imdb_id,
            "UPC": "",
            "Matched_Format": "",
            "Match_Method": "",
            "Editions_Found": "",
            "Status": "",
        }

        if not imdb_id:
            record["Status"] = "no_imdb_id"
            writer.writerow(record)
            print("skipped (no IMDb ID)")
            continue

        try:
            records = api_get(f"/v1/lookup/imdb/{imdb_id}", api_key)
            if isinstance(records, dict):
                records = [records]

            record["Editions_Found"] = len(records)

            best, method = pick_upc(records, vendor)
            if not best:
                record["Status"] = "no_records"
                print("no records")
            else:
                record.update(
                    {
                        "UPC": best.get("upc", ""),
                        "Matched_Format": best.get("format", ""),
                        "Match_Method": method,
                        "Status": "ok",
                    }
                )
                print(f"-> UPC {record['UPC']} ({record['Matched_Format']}, {method})")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                record["Status"] = "not_found"
                print("not found")
            else:
                record["Status"] = f"http_error_{e.code}"
                print(f"HTTP error {e.code}")
        except Exception as e:  # noqa: BLE001
            record["Status"] = f"error: {e}"
            print(f"error: {e}")

        writer.writerow(record)
        out_f.flush()
        time.sleep(0.25)

    out_f.close()
    print(f"\nWrote {len(imdb_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
