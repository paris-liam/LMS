#!/usr/bin/env python3
"""
Look up TMDB matches + IMDb IDs for movies in a Shopify product CSV.

Usage:
    TMDB_API_KEY=xxxx python3 scripts/tmdb-imdb-lookup.py \
        --input products_imdbID.csv \
        --output claudedocs/tmdb-imdb-lookup-sample.csv \
        --limit 20
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

TMDB_BASE = "https://api.themoviedb.org/3"
YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
YEAR_ANY_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
TAG_RE = re.compile(r"<[^>]+>")

# Ordered by trustworthiness. "paren" sources are near-certain (someone
# deliberately wrote "Title (YYYY)"); "body_any" is a loose fallback that can
# pick up an in-plot year instead of the release year, so it gets a much
# lighter weight in scoring and never hard-filters the TMDB search.
YEAR_SOURCES = [
    ("title", "paren", 1.0),
    ("image_alt_text", "paren", 1.0),
    ("body", "paren", 0.9),
    ("body", "any", 0.4),
]


def strip_html(html):
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html or "")).strip()


def extract_year_hint(title, alt_text, body_text):
    fields = {"title": title, "image_alt_text": alt_text, "body": body_text}
    for field_name, kind, weight in YEAR_SOURCES:
        text = fields[field_name]
        pattern = YEAR_PAREN_RE if kind == "paren" else YEAR_ANY_RE
        match = pattern.search(text or "")
        if match:
            return match.group(1), f"{field_name}_{kind}", weight
    return "", "none", 0.0


def api_get(path, api_key, params):
    query = dict(params)
    query["api_key"] = api_key
    url = f"{TMDB_BASE}{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def word_overlap_score(a, b):
    a_words = set(re.findall(r"[a-z']+", a.lower()))
    b_words = set(re.findall(r"[a-z']+", b.lower()))
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def pick_best_match(results, title, year_hint, year_weight, overview_hint):
    if not results:
        return None, 0.0

    scored = []
    for r in results:
        score = 0.0
        r_year = (r.get("release_date") or "")[:4]
        if year_hint and r_year == year_hint:
            score += 0.5 * year_weight
        elif year_hint and r_year:
            try:
                if abs(int(r_year) - int(year_hint)) <= 1:
                    score += 0.2 * year_weight
            except ValueError:
                pass

        title_score = word_overlap_score(title, r.get("title") or "")
        score += title_score * 0.2

        overview_score = word_overlap_score(overview_hint, r.get("overview") or "")
        score += overview_score * 0.3

        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1], scored[0][0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="products_imdbID.csv")
    parser.add_argument("--output", default="claudedocs/tmdb-imdb-lookup-sample.csv")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        sys.exit("Set TMDB_API_KEY in the environment before running this script.")

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows = rows[: args.limit]

    out_fields = [
        "Handle",
        "Title",
        "Year_Hint",
        "Year_Source",
        "TMDB_ID",
        "Matched_Title",
        "Matched_Year",
        "IMDb_ID",
        "Match_Score",
        "Status",
    ]

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    out_f = open(args.output, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=out_fields)
    writer.writeheader()

    for i, row in enumerate(rows, start=1):
        handle = row.get("Handle", "")
        title = row.get("Title", "")
        alt_text = row.get("Image Alt Text", "")
        body = strip_html(row.get("Body (HTML)", ""))

        year_hint, year_source, year_weight = extract_year_hint(title, alt_text, body)

        print(f"[{i}/{len(rows)}] {title} ({year_hint or '?'} via {year_source})...", end=" ")

        record = {
            "Handle": handle,
            "Title": title,
            "Year_Hint": year_hint,
            "Year_Source": year_source,
            "TMDB_ID": "",
            "Matched_Title": "",
            "Matched_Year": "",
            "IMDb_ID": "",
            "Match_Score": "",
            "Status": "",
        }

        try:
            search_params = {"query": title, "include_adult": "false"}
            if year_hint and year_weight >= 0.9:
                # only hard-filter the search on trustworthy (parenthetical)
                # year hints -- a loose in-body year could exclude the right movie
                search_params["primary_release_year"] = year_hint

            search_resp = api_get("/search/movie", api_key, search_params)
            results = search_resp.get("results", [])

            if not results and "primary_release_year" in search_params:
                # retry without the year filter in case it was wrong/too strict
                results = api_get(
                    "/search/movie", api_key, {"query": title, "include_adult": "false"}
                ).get("results", [])

            best, score = pick_best_match(results, title, year_hint, year_weight, body)

            if not best:
                record["Status"] = "no_results"
                print("no results")
            else:
                tmdb_id = best["id"]
                external = api_get(f"/movie/{tmdb_id}/external_ids", api_key, {})
                imdb_id = external.get("imdb_id") or ""

                record.update(
                    {
                        "TMDB_ID": tmdb_id,
                        "Matched_Title": best.get("title", ""),
                        "Matched_Year": (best.get("release_date") or "")[:4],
                        "IMDb_ID": imdb_id,
                        "Match_Score": f"{score:.2f}",
                        "Status": "ok" if imdb_id else "no_imdb_id",
                    }
                )
                print(f"-> {record['Matched_Title']} ({record['Matched_Year']}) {imdb_id or 'NO IMDB ID'} [score {score:.2f}]")

        except urllib.error.HTTPError as e:
            record["Status"] = f"http_error_{e.code}"
            print(f"HTTP error {e.code}")
        except Exception as e:  # noqa: BLE001
            record["Status"] = f"error: {e}"
            print(f"error: {e}")

        writer.writerow(record)
        out_f.flush()
        time.sleep(0.25)  # stay well under TMDB rate limits

    out_f.close()
    print(f"\nWrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
