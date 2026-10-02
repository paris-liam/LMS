"""duplicates.csv, duplicate-editions.csv and duplicates-summary.txt."""

from collections import Counter

from catalog.core.csv_io import write_csv
from catalog.duplicates.match import CERTAIN, CONFIDENCES, LIKELY, REVIEW, product_type, quantity

CSV_COLUMNS = ["Group", "Confidence", "Tier", "Format", "Type", "Edition", "Copies In Group", "Handle", "Title",
               "Barcode", "Status", "Quantity", "Created At", "Reasons"]
EDITION_COLUMNS = ["Pair", "Format", "Type", "Handle", "Title", "Barcode", "Status", "Created At"]


def group_rows(groups: list[dict]) -> list[dict]:
    out = []
    for group in groups:
        for row in group["members"]:
            out.append({
                "Group": group["id"], "Confidence": group["confidence"], "Tier": group["tier"],
                "Format": group["format"], "Type": group["type"], "Edition": group["edition"],
                "Copies In Group": len(group["members"]), "Handle": row.get("Handle", ""),
                "Title": row.get("Title", ""), "Barcode": row.get("Variant Barcode", ""),
                "Status": row.get("Status", ""), "Quantity": row.get("Variant Inventory Qty", ""),
                "Created At": row.get("Created At", ""), "Reasons": group["reasons"],
            })
    return out


def edition_rows(pairs: list[dict]) -> list[dict]:
    out = []
    for number, pair in enumerate(pairs, 1):
        for row in pair["members"]:
            out.append({"Pair": f"E{number:03d}", "Format": pair["format"], "Type": pair["type"],
                        "Handle": row.get("Handle", ""), "Title": row.get("Title", ""),
                        "Barcode": row.get("Variant Barcode", ""), "Status": row.get("Status", ""),
                        "Created At": row.get("Created At", "")})
    return out


def _copies(row: dict) -> int:
    """Copies held: the tracked quantity, or 1 when it is unknown."""
    q = quantity(row)
    return 1 if q is None else max(q, 0)


def summary_lines(rows: list[dict], groups: list[dict], unclassifiable: list[dict],
                  pairs: list[dict], run_name: str) -> list[str]:
    movies = [r for r in rows if r not in unclassifiable]
    lines = [f"Duplicate copies — audit run {run_name}", "",
             "Product = movie + format + type (Rental / Floor Sale), editions and box sets kept",
             "separate (claudedocs/2026-10-02-duplicate-copies-lookup-plan.md). Read-only.", "",
             f"Movies in the snapshot: {len(movies)}"]
    by_type = Counter(product_type(r) for r in movies)
    lines.append("  by type:   " + ", ".join(f"{k} {v}" for k, v in by_type.most_common()))
    by_format = Counter(r.get("Vendor", "") for r in movies)
    lines.append("  by format: " + ", ".join(f"{k} {v}" for k, v in by_format.most_common()))
    drafts = sum(1 for r in movies if (r.get("Status") or "") == "draft")
    lines.append(f"  drafts:    {drafts}")
    if unclassifiable:
        lines.append(f"Not a media format (not grouped): {len(unclassifiable)} — "
                     + ", ".join(sorted({r.get('Vendor') or '(blank)' for r in unclassifiable})))

    lines += ["", "Groups of 2+ products that would become one product:", ""]
    lines.append(f"  {'confidence':<12}{'groups':>7}{'products':>10}{'after':>8}{'fewer':>8}")
    cumulative = []
    for level in CONFIDENCES:
        level_groups = [g for g in groups if g["confidence"] == level]
        n = sum(len(g["members"]) for g in level_groups)
        lines.append(f"  {level:<12}{len(level_groups):>7}{n:>10}{len(level_groups):>8}{n - len(level_groups):>8}")
        cumulative += level_groups
    lines.append("")
    for label, levels in (("certain only", {CERTAIN}), ("certain + likely", {CERTAIN, LIKELY}),
                          ("everything", {CERTAIN, LIKELY, REVIEW})):
        chosen = [g for g in groups if g["confidence"] in levels]
        fewer = sum(len(g["members"]) - 1 for g in chosen)
        lines.append(f"  {label:<18} {len(movies)} products -> {len(movies) - fewer} ({fewer} fewer)")

    main = [g for g in groups if g["confidence"] in (CERTAIN, LIKELY)]
    lines += ["", "Certain + likely groups:"]
    sizes = Counter(len(g["members"]) for g in main)
    lines.append("  products per group: " + ", ".join(f"{k} copies x{v}" for k, v in sorted(sizes.items())))
    lines.append(f"  {'format':<11}{'type':<12}{'groups':>7}{'products':>10}{'fewer':>7}")
    split = Counter()
    for g in main:
        split[(g["format"], g["type"])] += 1
    for (fmt, ptype), count in sorted(split.items()):
        n = sum(len(g["members"]) for g in main if (g["format"], g["type"]) == (fmt, ptype))
        lines.append(f"  {fmt:<11}{ptype:<12}{count:>7}{n:>10}{n - count:>7}")
    rental_groups = [g for g in main if g["type"] == "Rental"]
    lines.append(f"  rental groups (would affect Libib): {len(rental_groups)} "
                 f"({sum(len(g['members']) for g in rental_groups)} products)")
    draft_groups = [g for g in main if any((r.get('Status') or '') == 'draft' for r in g["members"])]
    lines.append(f"  groups containing a draft: {len(draft_groups)}")
    copies = sum(_copies(r) for g in main for r in g["members"])
    lines.append(f"  copies held in these groups (tracked quantity): {copies}")

    multi = [r for r in movies if (quantity(r) or 0) > 1]
    lines += ["", f"Products already holding more than one copy (quantity > 1): {len(multi)}"]
    multi_types = Counter(product_type(r) for r in multi)
    if multi:
        lines.append("  " + ", ".join(f"{k} {v}" for k, v in multi_types.most_common()))
    lines += ["", f"Same title, different edition (kept separate, listed in duplicate-editions.csv): "
                  f"{len(pairs)} titles"]
    return lines


def write_reports(run_dir, rows, groups, unclassifiable, pairs) -> dict:
    paths = {
        "groups": run_dir / "duplicates.csv",
        "editions": run_dir / "duplicate-editions.csv",
        "summary": run_dir / "duplicates-summary.txt",
    }
    write_csv(paths["groups"], CSV_COLUMNS, group_rows(groups))
    write_csv(paths["editions"], EDITION_COLUMNS, edition_rows(pairs))
    lines = summary_lines(rows, groups, unclassifiable, pairs, run_dir.name)
    paths["summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
