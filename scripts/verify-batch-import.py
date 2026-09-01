#!/usr/bin/env python3
"""Verify a batch import against what was intended and what production had
before, after you've manually imported <batch-dir>/upload.csv into Shopify
Admin.

Three-way check per handle:
  - live vs source (upload.csv): did the import actually apply what we told
    it to? Catches import failures (e.g. a genre value with no matching
    metaobject on production — the whole row silently fails to import).
  - live vs before (before-snapshot.csv, if the handle pre-existed): did we
    lose something production had that the source CSV never carried over?
    This is the check that matters most for reformatting *existing*
    production products rather than creating new ones.

FAIL (blocking, exits non-zero):
  - handle not found on production at all (import likely failed the row)
  - Vendor / Variant Price / Tags don't match what upload.csv specified
  - upload.csv specifies a Variant Barcode but production's doesn't match
  - upload.csv specifies a genre value but shopify.genre resolved empty
    (the "Value require that you select a metaobject" failure mode)

WARN (reported, not blocking — needs a human look):
  - before-snapshot had a non-blank Variant SKU that's genuinely distinct
    from its own Barcode (not just a duplicate of it — that specific pattern
    is dev's known, intentional convention) and it's now gone
  - before-snapshot had an image and upload.csv doesn't carry one, and
    production now has none
  - before-snapshot had a non-blank scf.avf value and it's gone now (no
    script populates this field, so any loss here is unexplained upstream)

Usage:
  python3 scripts/verify-batch-import.py 9.1-products/batches/batch-001
  python3 scripts/verify-batch-import.py 9.1-products/batches/batch-001 --store p0wkgv-wy.myshopify.com
"""

import argparse
import csv
import json
import os
import subprocess
import sys

SCF_AVF_KEY = "Rental Availability (product.metafields.scf.avf)"
GENRE_KEY = "Genre (product.metafields.shopify.genre)"


def read_rows_by_handle(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        h = r["Handle"].strip()
        out.setdefault(h, r)  # first row per handle is enough for these checks
    return out


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_live(store, handles):
    """Batched Admin GraphQL fetch, keyed by handle."""
    live = {}
    query = """
    query Batch($q: String!) {
      products(first: 20, query: $q) {
        nodes {
          handle vendor status tags
          images(first: 3) { nodes { url } }
          variants(first: 3) { nodes { sku barcode price } }
          metafields(first: 20) { nodes { namespace key value } }
        }
      }
    }
    """
    for batch in chunked(handles, 15):
        q = " OR ".join(f"handle:{h}" for h in batch)
        variables = json.dumps({"q": q})
        proc = subprocess.run(
            [
                "shopify", "store", "execute",
                "--store", store,
                "-j",
                "-q", query,
                "-v", variables,
            ],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print("shopify store execute failed:", proc.stderr, file=sys.stderr)
            sys.exit(2)
        data = json.loads(proc.stdout)
        for p in data.get("products", {}).get("nodes", []):
            live[p["handle"]] = p
    return live


def tags_from_csv(value):
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch_dir")
    ap.add_argument("--store", default="p0wkgv-wy.myshopify.com")
    args = ap.parse_args()

    upload_path = os.path.join(args.batch_dir, "upload.csv")
    snapshot_path = os.path.join(args.batch_dir, "before-snapshot.csv")

    source_by_handle = read_rows_by_handle(upload_path)
    before_by_handle = read_rows_by_handle(snapshot_path)

    handles = list(source_by_handle.keys())
    print(f"Verifying {len(handles)} handles from {upload_path} against {args.store} ...")
    live_by_handle = fetch_live(args.store, handles)

    fails = []
    warns = []

    for h in handles:
        source = source_by_handle[h]
        before = before_by_handle.get(h)
        live = live_by_handle.get(h)

        if live is None:
            fails.append((h, "MISSING", "not found on production — import likely failed this row"))
            continue

        live_variant = live["variants"]["nodes"][0] if live["variants"]["nodes"] else {}
        live_mf = {f"{m['namespace']}.{m['key']}": m["value"] for m in live["metafields"]["nodes"]}

        # --- live vs source: did the import apply what we intended? ---
        src_vendor = (source.get("Vendor") or "").strip()
        if src_vendor and src_vendor != (live.get("vendor") or "").strip():
            fails.append((h, "VENDOR", f"source={src_vendor!r} live={live.get('vendor')!r}"))

        src_price = (source.get("Variant Price") or "").strip()
        if src_price:
            try:
                if float(src_price) != float(live_variant.get("price") or 0):
                    fails.append((h, "PRICE", f"source={src_price!r} live={live_variant.get('price')!r}"))
            except ValueError:
                pass

        src_barcode = (source.get("Variant Barcode") or "").strip()
        if src_barcode and src_barcode != (live_variant.get("barcode") or "").strip():
            fails.append((h, "BARCODE_MISMATCH", f"source={src_barcode!r} live={live_variant.get('barcode')!r}"))

        src_tags = tags_from_csv(source.get("Tags"))
        live_tags = set(live.get("tags") or [])
        if src_tags and src_tags != live_tags:
            fails.append((h, "TAGS", f"source={sorted(src_tags)} live={sorted(live_tags)}"))

        src_genre = (source.get(GENRE_KEY) or "").strip()
        if src_genre and not (live_mf.get("shopify.genre") or "").strip():
            fails.append((h, "GENRE_UNRESOLVED", f"source specified {src_genre!r} but shopify.genre is empty on production"))

        # --- live vs before: did we lose something old prod had? ---
        if before:
            before_sku = (before.get("Variant SKU") or "").strip()
            before_barcode = (before.get("Variant Barcode") or "").strip()
            live_sku = (live_variant.get("sku") or "").strip()
            is_duplicate_pattern = before_sku and before_sku == before_barcode
            if before_sku and not live_sku and not is_duplicate_pattern:
                warns.append((h, "SKU_LOST", f"before={before_sku!r} now blank (not a barcode-duplicate)"))

            before_image = (before.get("Image Src") or "").strip()
            src_image = (source.get("Image Src") or "").strip()
            live_has_image = bool(live.get("images", {}).get("nodes"))
            if before_image and not src_image and not live_has_image:
                warns.append((h, "IMAGE_LOST", "before had an image, source CSV didn't carry one, none live"))

            before_scf = (before.get(SCF_AVF_KEY) or "").strip()
            live_scf = (live_mf.get("scf.avf") or "").strip()
            if before_scf and before_scf != live_scf:
                warns.append((h, "SCF_AVF_LOST", f"before={before_scf!r} live={live_scf!r}"))

    print()
    if not fails and not warns:
        print(f"✓ Clean: all {len(handles)} handles verified with no issues.")
        sys.exit(0)

    if fails:
        print(f"✗ {len(fails)} FAIL(s):")
        for h, kind, detail in fails:
            print(f"  [{kind}] {h}: {detail}")
    if warns:
        print(f"\n! {len(warns)} WARN(s) — review, not blocking:")
        for h, kind, detail in warns:
            print(f"  [{kind}] {h}: {detail}")

    print()
    print(f"Summary: {len(handles)} checked, {len(fails)} fail(s), {len(warns)} warn(s).")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
