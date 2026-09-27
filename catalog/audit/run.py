"""Stage 1 orchestration: snapshot rows -> findings, auto-fixes and picker entries.

run_audit is pure apart from progress logging and mutating `registry` in
place (applied -> resolved promotion); the caller saves the registry and
writes outputs.
"""

import html
import json
from dataclasses import dataclass
from pathlib import Path

from catalog.audit.findings import AUTO_FIX, FINDING_COLUMNS, MANUAL, PICKER, Finding
from catalog.audit.rules import (
    check_catalogue, check_row, is_multi_variant, needs_description, needs_poster, resolve_row,
)
from catalog.core import log
from catalog.core.columns import GENRE_METAFIELD
from catalog.core.csv_io import write_csv
from catalog.core.registry import promote_applied
from catalog.core.runs import COMPLETE_MARKER
from catalog.shopify.snapshot import write_snapshot
from catalog.tmdb.match import alt_text_for, match_product, poster_url

AMBIGUOUS_QUEUE = "ambiguous-queue"
UNMATCHED_QUEUE = "unmatched-queue"
_CONTENT_RULE = {"Image Src": "poster-missing", "Body (HTML)": "description-missing"}


@dataclass
class AuditResult:
    findings: list[Finding]
    autofix: dict       # {handle: {"changes": {field: value}, "rules": [rule, ...]}}
    review: list[dict]  # review.json entries for picker push
    promoted: list[str]


def _review_entry(row: dict, kind: str, reason: str) -> dict:
    return {"Handle": row["Handle"], "Title": row.get("Title", ""), "Vendor": row.get("Vendor", ""),
            "Genre": row.get(GENRE_METAFIELD, ""), "Tags": row.get("Tags", ""),
            "Kind": kind, "Reason": reason}


def _content(row: dict, registry: dict, fetch_fn) -> tuple[list[Finding], dict | None, str]:
    """Findings for a missing poster/description, plus a review entry if the
    product needs the picker, plus a one-line progress message."""
    missing = [f for f, needed in (("Image Src", needs_poster(row)), ("Body (HTML)", needs_description(row))) if needed]
    ptype = resolve_row(row).type or ""
    title = (row.get("Title") or "").strip()

    def make(field, bucket, detail, proposed="", rule=None):
        return Finding(row["Handle"], title, ptype, rule or _CONTENT_RULE[field], field, "", proposed, bucket, detail)

    entry = registry.get(row["Handle"])
    if entry:
        status = entry.get("status")
        if status == "queued":
            detail = f"already queued in {entry.get('batch', '?')}"
            return [make(f, PICKER, detail) for f in missing], None, detail
        if status == "skipped":
            return ([make(f, MANUAL, "client skipped this in the picker", rule="client-skipped") for f in missing],
                    None, "client skipped")
        if status == "resolved":
            return ([make(f, MANUAL, "marked resolved in the registry but still missing in Shopify",
                          rule="applied-but-missing") for f in missing], None, "resolved but still missing")
        return [], None, "applied, awaiting import"  # reported by the registry step

    if fetch_fn is None:
        return [make(f, PICKER, "not matched (--skip-tmdb)") for f in missing], None, "TMDB skipped"

    result = match_product(row, fetch_fn)
    if result.kind == "error":
        return ([make(f, MANUAL, result.reason, rule="tmdb-request-failed") for f in missing],
                None, result.reason)
    if result.kind in ("ambiguous", "none"):
        kind = "ambiguous" if result.kind == "ambiguous" else "unmatched"
        queue = AMBIGUOUS_QUEUE if kind == "ambiguous" else UNMATCHED_QUEUE
        return ([make(f, PICKER, result.reason) for f in missing],
                _review_entry(row, kind, result.reason), f"-> {queue}")

    findings: list[Finding] = []
    unfilled: list[tuple[str, str]] = []
    if "Image Src" in missing:
        url = poster_url(result.best)
        if url:
            findings.append(make("Image Src", AUTO_FIX, result.reason, url))
            if not (row.get("Image Alt Text") or "").strip():
                findings.append(make("Image Alt Text", AUTO_FIX, result.reason, alt_text_for(title, result.best),
                                     rule="poster-missing"))
        else:
            unfilled.append(("Image Src", "matched but TMDB has no poster"))
    if "Body (HTML)" in missing:
        overview = ((result.best or {}).get("overview") or "").strip()
        if overview:
            findings.append(make("Body (HTML)", AUTO_FIX, result.reason, f"<p>{html.escape(overview, quote=False)}</p>"))
        else:
            unfilled.append(("Body (HTML)", "matched but TMDB has no overview"))

    review = None
    if unfilled:
        findings += [make(f, PICKER, why) for f, why in unfilled]
        review = _review_entry(row, "unmatched", "; ".join(why for _, why in unfilled))
    filled = [_CONTENT_RULE[f.field].split("-")[0] for f in findings if f.bucket == AUTO_FIX and f.field in _CONTENT_RULE]
    message = ("auto-fill " + ", ".join(filled)) if filled else ""
    if review:
        message = (message + "; " if message else "") + f"-> {UNMATCHED_QUEUE}"
    return findings, review, message


def _applied_missing(registry: dict, rows_by_handle: dict, handles: list[str]) -> list[Finding]:
    out = []
    for handle in handles:
        entry, row = registry[handle], rows_by_handle[handle]
        fields = ", ".join((entry.get("values") or {}).keys())
        out.append(Finding(handle, (row.get("Title") or "").strip(), resolve_row(row).type or "",
                           "applied-but-missing", fields, "", "", MANUAL,
                           f"applied in run {entry.get('run', '?')} but not visible in Shopify — was that import CSV imported?"))
    return out


def collect_autofix(findings: list[Finding]) -> dict:
    out: dict = {}
    for f in findings:
        if f.bucket != AUTO_FIX:
            continue
        entry = out.setdefault(f.handle, {"changes": {}, "rules": []})
        existing = entry["changes"].get(f.field)
        if existing is not None and existing != f.proposed_value:
            raise ValueError(f"conflicting auto-fixes for {f.handle} {f.field}: {existing!r} vs {f.proposed_value!r}")
        entry["changes"][f.field] = f.proposed_value
        if f.rule not in entry["rules"]:
            entry["rules"].append(f.rule)
    return out


def run_audit(rows: list[dict], registry: dict, fetch_fn=None) -> AuditResult:
    rows_by_handle = {row["Handle"]: row for row in rows}
    promoted, still_missing = promote_applied(registry, rows_by_handle)

    findings: list[Finding] = []
    for row in rows:
        findings.extend(check_row(row))
    findings.extend(check_catalogue(rows))
    findings.extend(_applied_missing(registry, rows_by_handle, still_missing))
    log.summary(f"rules: {len(findings)} findings before content checks")

    content_rows = [r for r in rows if (needs_poster(r) or needs_description(r)) and not is_multi_variant(r)]
    review: list[dict] = []
    for index, row in enumerate(content_rows, start=1):
        found, entry, message = _content(row, registry, fetch_fn)
        findings.extend(found)
        if entry:
            review.append(entry)
        log.progress(index, len(content_rows), (row.get("Title") or row["Handle"]).strip(), message)

    for row in rows:
        if not is_multi_variant(row):
            continue
        for field_name, needed in (("Image Src", needs_poster(row)), ("Body (HTML)", needs_description(row))):
            if needed:
                findings.append(Finding(row["Handle"], (row.get("Title") or "").strip(), resolve_row(row).type or "",
                                        _CONTENT_RULE[field_name], field_name, "", "", MANUAL,
                                        "multi-variant product — fill by hand"))

    for f in findings:
        log.detail(f"{f.handle}: {f.rule} [{f.bucket}] {f.field} {f.current_value!r} -> {f.proposed_value!r} {f.detail}")
    return AuditResult(findings, collect_autofix(findings), review, promoted)


def build_report(result: AuditResult, *, source: str, audited: int, excluded: dict, tmdb_status: str) -> str:
    by_rule: dict[str, set] = {}
    by_bucket: dict[str, set] = {}
    for f in result.findings:
        by_rule.setdefault(f.rule, set()).add(f.handle)
        by_bucket.setdefault(f.bucket, set()).add(f.handle)
    excluded_text = ", ".join(f"{k}: {v}" for k, v in sorted(excluded.items())) or "none"
    lines = [
        f"source:    {source}",
        f"audited:   {audited} movies (excluded — {excluded_text})",
        f"findings:  {len(result.findings)} across {len({f.handle for f in result.findings})} products",
        "by bucket (products):",
        *[f"  {b:<10} {len(by_bucket.get(b, ()))}" for b in (AUTO_FIX, PICKER, MANUAL)],
        "by rule (products):",
        *[f"  {rule:<26} {len(handles)}" for rule, handles in sorted(by_rule.items())],
        f"auto-fix:  {len(result.autofix)} products in autofix.json",
        f"picker:    {len(result.review)} new products in review.json",
        f"registry:  {len(result.promoted)} applied -> resolved",
        f"tmdb:      {tmdb_status}",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(run_dir, rows: list[dict], result: AuditResult, report: str) -> None:
    """Write every output; the completion marker (run-report.txt) goes last."""
    run_dir = Path(run_dir)
    write_snapshot(run_dir / "snapshot.json", rows)
    ordered = sorted(result.findings, key=lambda f: (f.handle, f.rule, f.field))
    write_csv(run_dir / "findings.csv", FINDING_COLUMNS, [f.as_row() for f in ordered])
    (run_dir / "autofix.json").write_text(json.dumps(result.autofix, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "review.json").write_text(json.dumps(result.review, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / COMPLETE_MARKER).write_text(report, encoding="utf-8")
